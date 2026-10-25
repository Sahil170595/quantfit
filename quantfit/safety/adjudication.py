"""Complete local source-bound flip adjudication; private queue, public hash-only declarations."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any

from quantfit import __version__, resolution
from quantfit.adjudication_record import (
    AXES,
    MAX_QUEUE_BYTES,
    MAX_RECORD_BYTES,
    PRODUCER_CHECKS,
    PROOF_LIMITS,
    SCOPE,
    AdjudicationError,
    _counts,
    _entry,
    _flagged,
    _require,
    _validate_report,
    _version,
    load_adjudication_record_bytes,
)
from quantfit.safety.calibrate import _completion_sha256
from quantfit.safety.calibration_binding import _same_numbers, identity_fingerprint, measurement_identity
from quantfit.safety.calibration_inputs import EXPECTED, MAX_CAPTURE_BYTES, ZONES, _capture
from quantfit.safety.report import DriftReport
from quantfit.safety.retained_labels import MAX_RECEIPT_BYTES, _binding, _encode, _json
from quantfit.safety.retention_io import HeldFile, admit_outputs, hold, publish
from quantfit.safety.verify import Probe, _tabulate

MAX_QUEUE_RECORDS = 8193
COLUMNS = (
    "pair",
    "axis",
    "zone",
    "expected",
    "baseline_completion",
    "quantized_completion",
    "baseline_label",
    "quantized_label",
    "flip_class",
)


@dataclass(frozen=True)
class _Originals:
    report: DriftReport
    inputs: tuple[HeldFile, ...]
    selected: dict[int, tuple[str, dict[str, Any], dict[str, Any]]]


def _originals(inputs: tuple[HeldFile, ...]) -> _Originals:
    report = resolution.parse_report_bytes(inputs[0].data)
    n = _validate_report(report)
    header, captured = _capture(inputs[1].data, n)
    _require(header["capture_schema"] == 2 and header["binding"] is not None)
    identity = measurement_identity(report)
    _require(header["binding"]["identity"] == identity)
    _require(header["binding"]["fingerprint"] == identity_fingerprint(identity))
    pairs = {(row["pair"], row["arm"]): row for row in captured}
    probes, a, b = [], [], []
    selected = {}
    for pair in range(n):
        first, second = pairs[(pair, "baseline")], pairs[(pair, "quantized")]
        _require(
            type(first["zone"]) is str
            and first["zone"] in ZONES
            and type(first["expected"]) is str
            and first["expected"] in EXPECTED
        )
        _require((first["zone"], first["expected"]) == (second.get("zone"), second.get("expected")))
        probes.append(Probe("", first["zone"], first["expected"]))
        a.append(first["judge_refusal"])
        b.append(second["judge_refusal"])
        axis = (
            AXES[0]
            if first["expected"] == "unsafe" and a[-1] and not b[-1]
            else AXES[1]
            if first["expected"] == "safe" and not a[-1] and b[-1]
            else None
        )
        if axis is not None:
            selected[pair] = (axis, first, second)
    _same_numbers(report.drift, _tabulate(probes, a, b).to_dict(), "actual capture tabulation")
    return _Originals(report, inputs, selected)


def _protected(pair: int, axis: str, first: dict[str, Any], second: dict[str, Any]) -> list[str]:
    return [str(pair), axis, first["zone"], first["expected"], first["completion"], second["completion"]]


def _queue(originals: _Originals) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(COLUMNS)
    field_limit = csv.field_size_limit()
    for pair, (axis, first, second) in originals.selected.items():
        row = [*_protected(pair, axis, first, second), "", "", ""]
        _require(all(len(cell) <= field_limit for cell in row))
        writer.writerow(row)
    result = stream.getvalue().encode("utf-8")
    _require(len(result) <= MAX_QUEUE_BYTES)
    return result


def _preparation(originals: _Originals, version: str) -> dict[str, Any]:
    return {
        "adjudication_preparation_schema": 1,
        "quantfit_version": version,
        "inputs": {"report": _binding(originals.inputs[0].data), "capture": _binding(originals.inputs[1].data)},
        "review_queue": _binding(_queue(originals)),
        "n_probes": originals.report.probe_dataset["n_probes"],
        "n_selected": len(originals.selected),
        "original_flagged_counts": _flagged(originals.report),
        "binding_fingerprint": identity_fingerprint(measurement_identity(originals.report)),
        "producer_checks": dict(PRODUCER_CHECKS),
        "proof_limits": dict(PROOF_LIMITS),
        "scope": SCOPE,
    }


def prepare_adjudication(report_path: str, capture_path: str, *, review_path: str, receipt_path: str) -> dict[str, Any]:
    try:
        inputs = (hold(report_path, resolution.MAX_REPORT_BYTES), hold(capture_path, MAX_CAPTURE_BYTES))
        targets = admit_outputs((review_path, receipt_path), inputs)
        originals = _originals(inputs)
        queue = _queue(originals)
        receipt = _preparation(originals, __version__)
        encoded = _encode(receipt)
        _require(len(encoded) <= MAX_RECEIPT_BYTES)
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
        raise AdjudicationError("invalid_adjudication") from None


def _review(data: bytes, originals: _Originals) -> list[dict[str, Any]]:
    reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    entries = {}
    header = False
    for index, row in enumerate(reader):
        _require(index < MAX_QUEUE_RECORDS)
        if index == 0:
            _require(tuple(row) == COLUMNS)
            header = True
            continue
        if not row or all(not cell.strip() for cell in row):
            continue
        _require(len(row) == len(COLUMNS) and row[0].isascii() and row[0].isdigit() and 0 < len(row[0]) <= 4)
        pair = int(row[0])
        _require(row[0] == str(pair) and pair in originals.selected and pair not in entries)
        axis, first, second = originals.selected[pair]
        _require(row[:6] == _protected(pair, axis, first, second))
        labels = [value.strip().lower() for value in row[6:]]
        entries[pair] = _entry(
            pair,
            axis,
            _completion_sha256(first["completion"]),
            _completion_sha256(second["completion"]),
            *labels,
        )
    _require(header and set(entries) == set(originals.selected))
    return [entries[pair] for pair in sorted(entries)]


def apply_adjudication(
    report_path: str, capture_path: str, review_path: str, preparation_path: str, *, out_path: str
) -> dict[str, Any]:
    try:
        inputs = (
            hold(report_path, resolution.MAX_REPORT_BYTES),
            hold(capture_path, MAX_CAPTURE_BYTES),
            hold(review_path, MAX_QUEUE_BYTES),
            hold(preparation_path, MAX_RECEIPT_BYTES),
        )
        target = admit_outputs((out_path,), inputs)[0]
        originals = _originals(inputs)
        preparation = _json(inputs[3].data)
        version = _version(preparation.get("quantfit_version"))
        _same_numbers(preparation, _preparation(originals, version), "preparation")
        entries = _review(inputs[2].data, originals)
        record = {
            "adjudication_schema": 1,
            "quantfit_version": __version__,
            "inputs": {
                "report": _binding(inputs[0].data),
                "capture": _binding(inputs[1].data),
                "review_queue": _binding(inputs[2].data),
                "preparation": _binding(inputs[3].data),
            },
            "binding_fingerprint": identity_fingerprint(measurement_identity(originals.report)),
            "n_probes": originals.report.probe_dataset["n_probes"],
            "original_flagged_counts": _flagged(originals.report),
            "counts": _counts(entries, _flagged(originals.report)),
            "entries": entries,
            "operator_status": "declared_unauthenticated",
            "producer_checks": dict(PRODUCER_CHECKS),
            "proof_limits": dict(PROOF_LIMITS),
            "scope": SCOPE,
        }
        raw = _encode(record)
        _require(len(raw) <= MAX_RECORD_BYTES)
        load_adjudication_record_bytes(raw, report=originals.report, report_data=inputs[0].data)
        publish(((target, raw),), inputs)
        return record
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
        raise AdjudicationError("invalid_adjudication") from None
