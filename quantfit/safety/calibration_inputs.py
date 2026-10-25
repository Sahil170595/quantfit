"""Held native capture/key/label admission for descriptive calibration diagnostics.

This verifies agreement of supplied bytes and declarations, never authenticity,
human truth or actual execution. No caller paths or private values escape errors.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from typing import Any

from quantfit.safety import calibrate
from quantfit.safety.reconcile import MAX_CSV_RECORDS, MAX_KEY_BYTES, MAX_PAIRS, MAX_SHEET_BYTES
from quantfit.safety.retained_labels import _binding, _json, _key, _scope, load_retained_labels
from quantfit.safety.retention_io import HeldFile, hold

MAX_CAPTURE_BYTES = 16 * 1024 * 1024
MAX_CAPTURE_RECORDS = 16385
ZONES = ("clear_safe", "clear_unsafe", "borderline")
EXPECTED = ("safe", "unsafe")
_SEPARATORS = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")


class CalibrationInputsError(RuntimeError):
    """Invalid diagnostic inputs; categorical, with native private causes suppressed."""


def _require(condition: bool) -> None:
    if not condition:
        raise CalibrationInputsError("invalid_calibration_inputs")


def _choice(value: object, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise CalibrationInputsError("invalid_calibration_inputs")
    return value


@dataclass(frozen=True)
class CalibrationRow:
    pair: int
    arm: str
    zone: str
    expected: str
    judge_refusal: bool
    human_label: str


@dataclass(frozen=True)
class HeldCalibrationInputs:
    rows: tuple[CalibrationRow, ...]
    n_pairs: int
    binding_fingerprint: str | None
    inputs: tuple[HeldFile, ...]
    roles: tuple[str, ...]
    label_mode: str
    original_sheet: dict[str, Any]

    def public_inputs(self) -> dict[str, Any]:
        return {role: _binding(item.data) for role, item in zip(self.roles, self.inputs, strict=True)}


def _capture(data: bytes, n: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    text = data.decode("utf-8")
    records = 0
    last_end = 0
    # Native str.splitlines recognizes more than LF/CRLF. Count those separators
    # before allocating its list, including blank records; no interpreter integer
    # protection policy or native unbounded range(n_pairs) is relied upon.
    for match in _SEPARATORS.finditer(text):
        records += 1
        last_end = match.end()
        _require(records <= MAX_CAPTURE_RECORDS)
    if last_end < len(text):
        records += 1
    _require(0 < records <= MAX_CAPTURE_RECORDS)
    nonblank = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        nonblank += 1
        _require(nonblank <= 2 * n + 1)
        item = _json(line.encode("utf-8"))
        if nonblank == 1:
            _require(type(item.get("n_pairs")) is int and 0 < item["n_pairs"] <= MAX_PAIRS and item["n_pairs"] == n)
            _require(type(item.get("capture_schema")) is int and item["capture_schema"] in (1, 2))
            for field in ("created_utc", "baseline", "quant"):
                _require(type(item.get(field)) is str and bool(item[field].strip()))
    _require(nonblank == 2 * n + 1)
    header, rows = calibrate._read_capture("private capture", data=data)
    return header, rows


def load_calibration_inputs(
    capture_path: str,
    key_path: str,
    *,
    sheet_path: str | None = None,
    retained_labels_path: str | None = None,
    retention_receipt_path: str | None = None,
) -> HeldCalibrationInputs:
    """Hold each role once, then join native captured facts with every validated label."""
    try:
        _require((sheet_path is not None) != (retained_labels_path is not None))
        _require((retained_labels_path is not None) == (retention_receipt_path is not None))
        capture_file = hold(capture_path, MAX_CAPTURE_BYTES)
        inputs: tuple[HeldFile, ...]
        roles: tuple[str, ...]
        if sheet_path is not None:
            key_file = hold(key_path, MAX_KEY_BYTES)
            sheet_file = hold(sheet_path, MAX_SHEET_BYTES)
            key, n = _key(key_file.data)
            inputs = (capture_file, key_file, sheet_file)
            roles = ("capture", "key", "sheet")
            label_mode = "full_sheet"
            original_sheet = {**_binding(sheet_file.data), "held_and_validated": True}
        else:
            assert retained_labels_path is not None and retention_receipt_path is not None
            retained = load_retained_labels(retained_labels_path, retention_receipt_path, key_path)
            key = retained.key
            n = retained.receipt["n_pairs"]
            labels_file, receipt_file, key_file = retained.inputs
            inputs = (capture_file, key_file, labels_file, receipt_file)
            roles = ("capture", "key", "retained_labels", "retention_receipt")
            label_mode = "retained_labels"
            original_sheet = {**retained.receipt["inputs"]["sheet"], "held_and_validated": False}
        _require(key["key_schema"] == calibrate.KEY_SCHEMA)
        _require(key["capture_sha256"] == hashlib.sha256(capture_file.data).hexdigest())
        header, captured = _capture(capture_file.data, n)
        _require(key["capture"] == {field: header[field] for field in ("created_utc", "baseline", "quant", "n_pairs")})
        effective_binding = header.get("binding") if header["capture_schema"] == 2 else None
        _require(key["binding"] == effective_binding)
        if sheet_path is not None:
            joined = calibrate._join(
                "private sheet", "private key", key["ids"], data=sheet_file.data, max_records=MAX_CSV_RECORDS
            )
            labels = {row_id: row["human_label"] for row_id, row in joined.items()}
        else:
            labels = retained.labels
        by_pair: dict[tuple[int, str], dict[str, Any]] = {}
        pair_metadata: dict[int, tuple[str, str]] = {}
        for row in captured:
            zone = _choice(row.get("zone"), ZONES)
            expected = _choice(row.get("expected"), EXPECTED)
            metadata = (zone, expected)
            pair = row["pair"]
            _require(pair not in pair_metadata or pair_metadata[pair] == metadata)
            pair_metadata[pair] = metadata
            by_pair[(pair, row["arm"])] = row
        rows = []
        for row_id, entry in key["ids"].items():
            row = by_pair[(entry["pair"], entry["arm"])]
            _require(entry["judge_refusal"] == row["judge_refusal"])
            _require(entry["completion_sha256"] == calibrate._completion_sha256(row["completion"]))
            rows.append(
                CalibrationRow(
                    entry["pair"], entry["arm"], row["zone"], row["expected"], row["judge_refusal"], labels[row_id]
                )
            )
        fingerprint, _ = _scope(key)
        return HeldCalibrationInputs(
            tuple(sorted(rows, key=lambda row: (row.pair, row.arm))),
            n,
            fingerprint,
            inputs,
            roles,
            label_mode,
            original_sheet,
        )
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
        raise CalibrationInputsError("invalid_calibration_inputs") from None
