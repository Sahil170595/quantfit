"""Explicit capture-backed review from two complete receipt-bound retained label sets.

Capture/key agreement proves supplied-byte consistency, never provenance authenticity,
rater identity or human truth. Original completion-bearing sheets are not read.
"""

from __future__ import annotations

import csv
from typing import Any

from quantfit import __version__
from quantfit.safety import calibrate
from quantfit.safety.calibration_inputs import MAX_CAPTURE_BYTES, _verified_capture
from quantfit.safety.label_review import LIMITS, SELECTION, _csv, _Originals, _queue, _receipt_bytes, _review
from quantfit.safety.reconcile import MAX_CSV_RECORDS, MAX_KEY_BYTES, MAX_SHEET_BYTES
from quantfit.safety.retained_labels import (
    MAX_RECEIPT_BYTES,
    MAX_RETAINED_BYTES,
    _binding,
    _encode,
    _json,
    _key,
    _load_retained_held,
    _scope,
)
from quantfit.safety.retention_io import HeldFile, admit_outputs, canonical, hold, publish, require

# One admitted logical-input budget, including both actual retained receipts,
# and, for application, the selected queue and its preparation receipt.
MAX_INPUT_BYTES = MAX_CAPTURE_BYTES + MAX_KEY_BYTES + 2 * MAX_RETAINED_BYTES + MAX_SHEET_BYTES + 3 * MAX_RECEIPT_BYTES
ROLES = ("capture", "key", "retained_labels_a", "retention_receipt_a", "retained_labels_b", "retention_receipt_b")
ROLE_LIMITS = (
    MAX_CAPTURE_BYTES,
    MAX_KEY_BYTES,
    MAX_RETAINED_BYTES,
    MAX_RECEIPT_BYTES,
    MAX_RETAINED_BYTES,
    MAX_RECEIPT_BYTES,
)
SCOPE = (
    "Actual supplied capture bytes, effective measurement binding, complete pair/arm population, "
    "judge flags and completion digests are verified against the supplied key. Both retained "
    "label sets are verified against their own supplied receipts and that same held key. "
    "Original full-sheet digests are receipt declarations only; no original sheet is read. "
    "Local transformation only: queue membership reveals disagreement and a returning labeler "
    "may remember labels. No source authenticity, rater authentication, human truth, authentic "
    "blinding, independent adjudication, automatic ingestion, new calibration schema or scientific GO. "
    "Explicit judgments require an externally fixed operator rule; software supplies no preferred rater."
)


class RetainedReviewError(RuntimeError):
    """Categorical refusal with private parser, path and text details suppressed."""


def _hold_inputs(paths: tuple[str, ...]) -> tuple[HeldFile, ...]:
    limits = ROLE_LIMITS + (MAX_SHEET_BYTES, MAX_RECEIPT_BYTES)
    require(len(paths) in (6, 8))
    remaining = MAX_INPUT_BYTES
    held: dict[str, HeldFile] = {}
    result = []
    for path, limit in zip(paths, limits[: len(paths)], strict=True):
        name = str(canonical(path))
        if name not in held:
            held[name] = hold(path, min(limit, remaining))
        item = held[name]
        require(len(item.data) <= limit and len(item.data) <= remaining)
        remaining -= len(item.data)
        result.append(item)
    return tuple(result)


def _originals(inputs: tuple[HeldFile, ...]) -> tuple[_Originals, dict[str, Any]]:
    key, n = _key(inputs[1].data)
    require(key["key_schema"] == calibrate.KEY_SCHEMA and key.get("binding") is not None)
    a = _load_retained_held(inputs[2], inputs[3], inputs[1], parsed_key=(key, n))
    b = _load_retained_held(inputs[4], inputs[5], inputs[1], parsed_key=(key, n))
    captured = _verified_capture(inputs[0], key, n)
    first = {
        row_id: {"completion": captured[row_id]["completion"], "human_label": label}
        for row_id, label in a.labels.items()
    }
    second = {
        row_id: {"completion": captured[row_id]["completion"], "human_label": label}
        for row_id, label in b.labels.items()
    }
    selected = tuple(
        sorted(row_id for row_id in first if first[row_id]["human_label"] != second[row_id]["human_label"])
    )
    declared = {
        name: {**retained.receipt["inputs"]["sheet"], "held_and_validated": False}
        for name, retained in (("a", a), ("b", b))
    }
    return _Originals(key, first, second, n, selected, inputs), declared


def _common(originals: _Originals, declared: dict[str, Any]) -> dict[str, Any]:
    fingerprint, capture = _scope(originals.key)
    return {
        "input_mode": "retained_labels",
        "inputs": {role: _binding(item.data) for role, item in zip(ROLES, originals.inputs[:6], strict=True)},
        "n_pairs": originals.n_pairs,
        "n_rows": 2 * originals.n_pairs,
        "binding_fingerprint": fingerprint,
        "capture_sha256_declared": capture,
        "capture_verification": {
            "held_and_validated": True,
            "effective_binding_verified": True,
            "complete_population_and_row_facts_verified": True,
            "source_authenticity_verified": False,
        },
        "original_sheets_declared": declared,
        "limits": dict(LIMITS),
        "scope": SCOPE,
    }


def _preparation(originals: _Originals, declared: dict[str, Any], version: str) -> dict[str, Any]:
    per_arm = {}
    for arm in calibrate.ARMS:
        selected = sum(originals.key["ids"][row_id]["arm"] == arm for row_id in originals.selected)
        per_arm[arm] = {"n_rows": originals.n_pairs, "n_selected": selected, "n_agreed": originals.n_pairs - selected}
    return {
        **_common(originals, declared),
        "retained_review_preparation_schema": 1,
        "quantfit_version": version,
        "review_sheet": _binding(_queue(originals)),
        "n_selected": len(originals.selected),
        "n_agreed": len(originals.first) - len(originals.selected),
        "per_arm": per_arm,
        "selection": SELECTION,
    }


def prepare_retained_label_review(
    capture_path: str,
    key_path: str,
    labels_a_path: str,
    receipt_a_path: str,
    labels_b_path: str,
    receipt_b_path: str,
    *,
    review_path: str,
    receipt_path: str,
) -> dict[str, Any]:
    """Hold six roles once; publish a new private blank disagreement queue and aggregate receipt."""
    try:
        inputs = _hold_inputs((capture_path, key_path, labels_a_path, receipt_a_path, labels_b_path, receipt_b_path))
        originals, declared = _originals(inputs)
        queue = _queue(originals)
        receipt = _preparation(originals, declared, __version__)
        encoded = _receipt_bytes(receipt)
        targets = admit_outputs((review_path, receipt_path), inputs)
        publish(((targets[0], queue), (targets[1], encoded)), inputs)
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
        raise RetainedReviewError("invalid_retained_label_review") from None


def apply_retained_label_review(
    capture_path: str,
    key_path: str,
    labels_a_path: str,
    receipt_a_path: str,
    labels_b_path: str,
    receipt_b_path: str,
    review_path: str,
    preparation_path: str,
    *,
    out_path: str,
    receipt_path: str,
) -> dict[str, Any]:
    """Apply every explicit selected judgment; native-validate a new complete full sheet, never ingest."""
    try:
        inputs = _hold_inputs(
            (
                capture_path,
                key_path,
                labels_a_path,
                receipt_a_path,
                labels_b_path,
                receipt_b_path,
                review_path,
                preparation_path,
            )
        )
        originals, declared = _originals(inputs)
        preparation = _json(inputs[7].data)
        version = preparation.get("quantfit_version")
        if not isinstance(version, str) or not version.strip():
            raise RetainedReviewError("invalid_retained_label_review")
        require(_encode(preparation) == _encode(_preparation(originals, declared, version)))
        reviewed = _review(inputs[6].data, originals)
        labels = {row_id: reviewed.get(row_id, row["human_label"]) for row_id, row in originals.first.items()}
        output = _csv([(row_id, originals.first[row_id]["completion"], labels[row_id]) for row_id in sorted(labels)])
        # No fabricated retention receipt: this new full sheet must satisfy the
        # unchanged native join before the caller may separately extract/ingest.
        calibrate._join("new full sheet", "private key", originals.key["ids"], data=output, max_records=MAX_CSV_RECORDS)
        per_arm = {}
        for arm in calibrate.ARMS:
            ids = [row_id for row_id in labels if originals.key["ids"][row_id]["arm"] == arm]
            per_arm[arm] = {
                "n_rows": len(ids),
                "n_reviewed": sum(row_id in reviewed for row_id in ids),
                "n_changed_vs_a": sum(labels[row_id] != originals.first[row_id]["human_label"] for row_id in ids),
                "n_unusable": sum(labels[row_id] == calibrate.LABEL_UNUSABLE for row_id in ids),
            }
        common = _common(originals, declared)
        receipt = {
            **common,
            "retained_review_application_schema": 1,
            "quantfit_version": __version__,
            "inputs": {**common["inputs"], "review": _binding(inputs[6].data), "preparation": _binding(inputs[7].data)},
            "output_sheet": _binding(output),
            "n_reviewed": len(reviewed),
            "n_changed_vs_a": sum(block["n_changed_vs_a"] for block in per_arm.values()),
            "n_unusable": sum(block["n_unusable"] for block in per_arm.values()),
            "per_arm": per_arm,
        }
        encoded = _receipt_bytes(receipt)
        targets = admit_outputs((out_path, receipt_path), inputs)
        publish(((targets[0], output), (targets[1], encoded)), inputs)
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
        raise RetainedReviewError("invalid_retained_label_review") from None
