"""Completion-free retention and explicit, receipt-bound calibration ingestion.

These hashes bind exact supplied bytes, not rater identity, truth or independent
labeling. The capture digest is a key declaration; no capture is read here.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from typing import Any, cast

from quantfit import __version__
from quantfit.safety import calibrate
from quantfit.safety.calibration_aggregate import aggregate_labels
from quantfit.safety.calibration_binding import MAX_CALIBRATION_BYTES
from quantfit.safety.reconcile import MAX_CSV_RECORDS, MAX_KEY_BYTES, MAX_SHEET_BYTES, _population
from quantfit.safety.retention_io import HeldFile, RetainedLabelsError, admit_outputs, hold, publish, require

RETENTION_SCHEMA = 1
RETAINED_CALIBRATION_SCHEMA = 3
MAX_RETAINED_BYTES = 2 * 1024 * 1024
MAX_RECEIPT_BYTES = 64 * 1024
MAX_INTEGER_DIGITS = 20
MAX_FLOAT_CHARS = 64
MAX_SALT_CHARS = 256
_SHA256 = re.compile(r"[0-9a-f]{64}")
RECEIPT_KEYS = {
    "retention_schema",
    "quantfit_version",
    "inputs",
    "retained_labels",
    "n_pairs",
    "n_rows",
    "n_unusable",
    "binding_fingerprint",
    "capture_sha256_declared",
}


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        require(key not in result)
        result[key] = value
    return result


def _integer(token: str) -> int:
    require(len(token.lstrip("-")) <= MAX_INTEGER_DIGITS)
    return int(token)


def _float(token: str) -> float:
    require(len(token) <= MAX_FLOAT_CHARS)
    result = float(token)
    require(math.isfinite(result))
    return result


def _nonfinite(token: str) -> None:
    raise RetainedLabelsError("invalid_retained_labels")


def _json(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw, object_pairs_hook=_pairs, parse_int=_integer, parse_float=_float, parse_constant=_nonfinite)
    require(type(value) is dict)
    return cast(dict[str, Any], value)


def _encode(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _binding(raw: bytes) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def _key(raw: bytes) -> tuple[dict[str, Any], int]:
    admitted = _json(raw)
    salt = admitted.get("salt")
    require(type(salt) is str and 0 < len(salt) <= MAX_SALT_CHARS)
    n = _population(raw)
    key = calibrate._read_key("private key", data=raw)
    return key, n


def _scope(key: dict[str, Any]) -> tuple[str | None, str | None]:
    if key["key_schema"] != calibrate.KEY_SCHEMA:
        return None, None
    binding = key.get("binding")
    return (binding["fingerprint"] if binding is not None else None), key["capture_sha256"]


def _retained_csv(labels: dict[str, str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("id", "human_label"))
    writer.writerows(sorted(labels.items()))
    raw = buffer.getvalue().encode("utf-8")
    require(len(raw) <= MAX_RETAINED_BYTES)
    return raw


def _labels(raw: bytes, ids: dict[str, Any]) -> dict[str, str]:
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    result = {}
    for index, row in enumerate(reader):
        require(index < MAX_CSV_RECORDS)
        if index == 0:
            require(row == ["id", "human_label"])
            continue
        if not row or all(not cell.strip() for cell in row):
            continue
        require(len(row) == 2)
        row_id, label = row
        require(row_id in ids and row_id not in result and label in calibrate.HUMAN_LABELS)
        result[row_id] = label
    require(bool(result) and set(result) == set(ids))
    return result


@dataclass(frozen=True)
class HeldRetainedLabels:
    """Private validated inputs, shared without rereading by future native analyses.

    Not an authentication token or a public serialization format. Consumers must
    keep the key and per-row labels private.
    """

    key: dict[str, Any]
    labels: dict[str, str]
    receipt: dict[str, Any]
    inputs: tuple[HeldFile, ...]


def load_retained_labels(labels_path: str, receipt_path: str, key_path: str) -> HeldRetainedLabels:
    try:
        key_file = hold(key_path, MAX_KEY_BYTES)
        labels_file = hold(labels_path, MAX_RETAINED_BYTES)
        receipt_file = hold(receipt_path, MAX_RECEIPT_BYTES)
        key, n = _key(key_file.data)
        labels = _labels(labels_file.data, key["ids"])
        receipt = _json(receipt_file.data)
        require(
            set(receipt) == RECEIPT_KEYS
            and type(receipt["retention_schema"]) is int
            and receipt["retention_schema"] == RETENTION_SCHEMA
        )
        require(type(receipt["quantfit_version"]) is str and bool(receipt["quantfit_version"].strip()))
        require(type(receipt["inputs"]) is dict and set(receipt["inputs"]) == {"sheet", "key"})
        for role, limit in (("sheet", MAX_SHEET_BYTES), ("key", MAX_KEY_BYTES)):
            entry = receipt["inputs"][role]
            require(type(entry) is dict and set(entry) == {"sha256", "size_bytes"})
            require(type(entry["sha256"]) is str and bool(_SHA256.fullmatch(entry["sha256"])))
            require(type(entry["size_bytes"]) is int and 0 < entry["size_bytes"] <= limit)
        retained = receipt["retained_labels"]
        require(type(retained) is dict and set(retained) == {"sha256", "size_bytes"})
        require(type(retained["size_bytes"]) is int and type(retained["sha256"]) is str)
        require(retained == _binding(labels_file.data) and receipt["inputs"]["key"] == _binding(key_file.data))
        for field, expected in (
            ("n_pairs", n),
            ("n_rows", 2 * n),
            ("n_unusable", sum(label == calibrate.LABEL_UNUSABLE for label in labels.values())),
        ):
            require(type(receipt[field]) is int and receipt[field] == expected)
        fingerprint, capture = _scope(key)
        require(receipt["binding_fingerprint"] == fingerprint and receipt["capture_sha256_declared"] == capture)
        return HeldRetainedLabels(key, labels, receipt, (labels_file, receipt_file, key_file))
    except (
        KeyboardInterrupt,
        RuntimeError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        ImportError,
        csv.Error,
    ):
        raise RetainedLabelsError("invalid_retained_labels") from None


def extract_labels(sheet_path: str, key_path: str, *, out_path: str, receipt_path: str) -> dict[str, Any]:
    """Validate original text hashes/labels, then publish private CSV and aggregate receipt once."""
    try:
        key_file = hold(key_path, MAX_KEY_BYTES)
        sheet_file = hold(sheet_path, MAX_SHEET_BYTES)
        key, n = _key(key_file.data)
        joined = calibrate._join(
            "private sheet", "private key", key["ids"], data=sheet_file.data, max_records=MAX_CSV_RECORDS
        )
        labels = {row_id: row["human_label"] for row_id, row in joined.items()}
        retained = _retained_csv(labels)
        fingerprint, capture = _scope(key)
        receipt = {
            "retention_schema": RETENTION_SCHEMA,
            "quantfit_version": __version__,
            "inputs": {"sheet": _binding(sheet_file.data), "key": _binding(key_file.data)},
            "retained_labels": _binding(retained),
            "n_pairs": n,
            "n_rows": 2 * n,
            "n_unusable": sum(label == calibrate.LABEL_UNUSABLE for label in labels.values()),
            "binding_fingerprint": fingerprint,
            "capture_sha256_declared": capture,
        }
        inputs = (sheet_file, key_file)
        targets = admit_outputs((out_path, receipt_path), inputs)
        publish(((targets[0], retained), (targets[1], _encode(receipt))), inputs)
        return receipt
    except (
        KeyboardInterrupt,
        RuntimeError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        ImportError,
        csv.Error,
    ):
        raise RetainedLabelsError("invalid_retained_labels") from None


def ingest_retained_labels(labels_path: str, receipt_path: str, key_path: str, *, out_path: str) -> dict[str, Any]:
    """Consume the exact CSV/key/receipt buffers into closed calibration schema 3."""
    try:
        held = load_retained_labels(labels_path, receipt_path, key_path)
        labels_file, receipt_file, key_file = held.inputs
        # Native shared arithmetic owns unusable/null/Wilson semantics. Original
        # sheet is intentionally unavailable: its recorded digest comes from receipt.
        source = {
            "sheet_sha256": held.receipt["inputs"]["sheet"]["sha256"],
            "key_sha256": hashlib.sha256(key_file.data).hexdigest(),
            "retained_labels_sha256": hashlib.sha256(labels_file.data).hexdigest(),
            "retention_receipt_sha256": hashlib.sha256(receipt_file.data).hexdigest(),
            "capture_sha256_declared": held.receipt["capture_sha256_declared"],
        }
        report = aggregate_labels(held.key, held.labels, source, schema=RETAINED_CALIBRATION_SCHEMA)
        raw_report = _encode(report)
        require(len(raw_report) <= MAX_CALIBRATION_BYTES)
        target = admit_outputs((out_path,), held.inputs)[0]
        publish(((target, raw_report),), held.inputs)
        return report
    except (
        KeyboardInterrupt,
        RuntimeError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        ImportError,
        csv.Error,
    ):
        raise RetainedLabelsError("invalid_retained_labels") from None
