"""Explicit local review preparation/application; private sheets, aggregate receipts."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any

from quantfit import __version__
from quantfit.safety import calibrate
from quantfit.safety.reconcile import MAX_CSV_RECORDS, MAX_KEY_BYTES, MAX_SHEET_BYTES
from quantfit.safety.retained_labels import MAX_RECEIPT_BYTES, _binding, _encode, _json, _key, _scope
from quantfit.safety.retention_io import HeldFile, admit_outputs, hold, publish, require

PREPARATION_SCHEMA = 1
APPLICATION_SCHEMA = 1
SELECTION = "unequal_normalized_labels"
LIMITS = {
    "human_labels_authenticated": False,
    "rater_identity_verified": False,
    "source_authenticity_verified": False,
    "authentic_blinding": False,
    "independent_adjudication": False,
    "post_review_agreement_is_independent": False,
    "scientific_go": False,
}
SCOPE = (
    "Local transformation from supplied labels only. Queue membership reveals disagreement; "
    "a returning labeler may remember earlier labels. No authentic blinding, rater authentication, "
    "independent adjudication, human truth, preregistration, sensitivity or scientific GO. "
    "Judgments must follow an externally fixed operator rule; software supplies no preferred rater, "
    "consensus policy, automatic ingestion or replacement for pre-review inter-rater statistics. "
    "Capture digest and measurement scope are key declarations; no capture is read."
)


class LabelReviewError(RuntimeError):
    """Categorical review refusal, with private native parser/IO causes suppressed."""


@dataclass(frozen=True)
class _Originals:
    key: dict[str, Any]
    first: dict[str, dict[str, Any]]
    second: dict[str, dict[str, Any]]
    n_pairs: int
    selected: tuple[str, ...]
    inputs: tuple[HeldFile, ...]


def _originals(inputs: tuple[HeldFile, ...]) -> _Originals:
    key, n = _key(inputs[2].data)
    first = calibrate._join(
        "private sheet A", "private key", key["ids"], data=inputs[0].data, max_records=MAX_CSV_RECORDS
    )
    second = calibrate._join(
        "private sheet B", "private key", key["ids"], data=inputs[1].data, max_records=MAX_CSV_RECORDS
    )
    require(all(first[row_id]["completion"] == second[row_id]["completion"] for row_id in first))
    selected = tuple(
        sorted(row_id for row_id in first if first[row_id]["human_label"] != second[row_id]["human_label"])
    )
    return _Originals(key, first, second, n, selected, inputs)


def _csv(rows: list[tuple[str, str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(calibrate.SHEET_COLUMNS)
    writer.writerows(rows)
    raw = stream.getvalue().encode("utf-8")
    require(len(raw) <= MAX_SHEET_BYTES)
    return raw


def _queue(originals: _Originals) -> bytes:
    return _csv([(row_id, originals.first[row_id]["completion"], "") for row_id in originals.selected])


def _input_bindings(originals: _Originals) -> dict[str, Any]:
    return {
        role: _binding(held.data)
        for role, held in zip(("sheet_a", "sheet_b", "key"), originals.inputs[:3], strict=True)
    }


def _preparation(originals: _Originals, queue: bytes, version: str) -> dict[str, Any]:
    fingerprint, capture = _scope(originals.key)
    per_arm = {}
    for arm in calibrate.ARMS:
        selected = sum(originals.key["ids"][row_id]["arm"] == arm for row_id in originals.selected)
        per_arm[arm] = {"n_rows": originals.n_pairs, "n_selected": selected, "n_agreed": originals.n_pairs - selected}
    return {
        "review_preparation_schema": PREPARATION_SCHEMA,
        "quantfit_version": version,
        "inputs": _input_bindings(originals),
        "review_sheet": _binding(queue),
        "n_pairs": originals.n_pairs,
        "n_rows": 2 * originals.n_pairs,
        "n_selected": len(originals.selected),
        "n_agreed": len(originals.first) - len(originals.selected),
        "per_arm": per_arm,
        "binding_fingerprint": fingerprint,
        "capture_sha256_declared": capture,
        "selection": SELECTION,
        "limits": dict(LIMITS),
        "scope": SCOPE,
    }


def _receipt_bytes(receipt: dict[str, Any]) -> bytes:
    raw = _encode(receipt)
    require(len(raw) <= MAX_RECEIPT_BYTES)
    return raw


def _review(data: bytes, originals: _Originals) -> dict[str, str]:
    """Strict selected subset, including header-only zero selection; never a full-key join."""
    reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    labels: dict[str, str] = {}
    header = False
    selected = set(originals.selected)
    for index, row in enumerate(reader):
        require(index < MAX_CSV_RECORDS)
        if index == 0:
            require(tuple(cell.strip() for cell in row) == calibrate.SHEET_COLUMNS)
            header = True
            continue
        if not row or all(not cell.strip() for cell in row):
            continue
        require(len(row) == 3)
        row_id, text, label = row[0].strip(), row[1], row[2].strip().lower()
        require(row_id in selected and row_id not in labels)
        require(text == originals.first[row_id]["completion"])
        require(label in calibrate.HUMAN_LABELS)
        labels[row_id] = label
    require(header and set(labels) == selected)
    return labels


def prepare_label_review(
    sheet_a_path: str, sheet_b_path: str, key_path: str, *, review_path: str, receipt_path: str
) -> dict[str, Any]:
    """Validate complete originals and publish a private blank subset plus aggregate receipt once."""
    try:
        inputs = (
            hold(sheet_a_path, MAX_SHEET_BYTES),
            hold(sheet_b_path, MAX_SHEET_BYTES),
            hold(key_path, MAX_KEY_BYTES),
        )
        originals = _originals(inputs)
        queue = _queue(originals)
        receipt = _preparation(originals, queue, __version__)
        raw_receipt = _receipt_bytes(receipt)
        targets = admit_outputs((review_path, receipt_path), inputs)
        publish(((targets[0], queue), (targets[1], raw_receipt)), inputs)
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
        raise LabelReviewError("invalid_label_review") from None


def apply_label_review(
    sheet_a_path: str,
    sheet_b_path: str,
    key_path: str,
    review_path: str,
    preparation_path: str,
    *,
    out_path: str,
    receipt_path: str,
) -> dict[str, Any]:
    """Apply only explicit selected labels to a new complete private native sheet; never ingest."""
    try:
        inputs = (
            hold(sheet_a_path, MAX_SHEET_BYTES),
            hold(sheet_b_path, MAX_SHEET_BYTES),
            hold(key_path, MAX_KEY_BYTES),
            hold(review_path, MAX_SHEET_BYTES),
            hold(preparation_path, MAX_RECEIPT_BYTES),
        )
        originals = _originals(inputs)
        preparation = _json(inputs[4].data)
        version = preparation.get("quantfit_version")
        if not isinstance(version, str):
            raise LabelReviewError("invalid_label_review")
        require(bool(version.strip()))
        # Canonical encoding is type-sensitive: True != 1, 1.0 != 1, and unknown
        # fields cannot hide behind Python dict equality. Producer version is a
        # declared compatibility field used internally, never echoed by application.
        require(_encode(preparation) == _encode(_preparation(originals, _queue(originals), version)))
        reviewed = _review(inputs[3].data, originals)
        labels = {row_id: reviewed.get(row_id, row["human_label"]) for row_id, row in originals.first.items()}
        output = _csv([(row_id, originals.first[row_id]["completion"], labels[row_id]) for row_id in sorted(labels)])
        per_arm = {}
        for arm in calibrate.ARMS:
            ids = [row_id for row_id in labels if originals.key["ids"][row_id]["arm"] == arm]
            per_arm[arm] = {
                "n_rows": len(ids),
                "n_reviewed": sum(row_id in reviewed for row_id in ids),
                "n_changed_vs_a": sum(labels[row_id] != originals.first[row_id]["human_label"] for row_id in ids),
                "n_unusable": sum(labels[row_id] == calibrate.LABEL_UNUSABLE for row_id in ids),
            }
        fingerprint, capture = _scope(originals.key)
        receipt = {
            "review_application_schema": APPLICATION_SCHEMA,
            "quantfit_version": __version__,
            "inputs": {
                **_input_bindings(originals),
                "review": _binding(inputs[3].data),
                "preparation": _binding(inputs[4].data),
            },
            "output_sheet": _binding(output),
            "n_pairs": originals.n_pairs,
            "n_rows": len(labels),
            "n_reviewed": len(reviewed),
            "n_changed_vs_a": sum(block["n_changed_vs_a"] for block in per_arm.values()),
            "n_unusable": sum(block["n_unusable"] for block in per_arm.values()),
            "per_arm": per_arm,
            "binding_fingerprint": fingerprint,
            "capture_sha256_declared": capture,
            "limits": dict(LIMITS),
            "scope": SCOPE,
        }
        raw_receipt = _receipt_bytes(receipt)
        targets = admit_outputs((out_path, receipt_path), inputs)
        publish(((targets[0], output), (targets[1], raw_receipt)), inputs)
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
        raise LabelReviewError("invalid_label_review") from None
