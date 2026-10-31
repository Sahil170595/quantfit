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


def _capture_originals(
    report: DriftReport, n: int, capture_data: bytes
) -> dict[int, tuple[str, dict[str, Any], dict[str, Any]]]:
    """Native whole-capture verification, independent of CSV and held-path adapters."""
    header, captured = _capture(capture_data, n)
    _require(header["capture_schema"] == 2 and header["binding"] is not None)
    identity = measurement_identity(report)
    _require(header["binding"]["identity"] == identity)
    _require(header["binding"]["fingerprint"] == identity_fingerprint(identity))
    selected, probes, a, b = _capture_selection(n, captured)
    _same_numbers(report.drift, _tabulate(probes, a, b).to_dict(), "actual capture tabulation")
    return selected


def _capture_selection(
    n: int, captured: list[dict[str, Any]]
) -> tuple[dict[int, tuple[str, dict[str, Any], dict[str, Any]]], list[Probe], list[bool], list[bool]]:
    """Native full-population metadata/selection, before tabulation statistics."""
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
    return selected, probes, a, b


def _originals(inputs: tuple[HeldFile, ...]) -> _Originals:
    report = resolution.parse_report_bytes(inputs[0].data)
    n = _validate_report(report)
    return _Originals(report, inputs, _capture_originals(report, n, inputs[1].data))


def _protected(pair: int, axis: str, first: dict[str, Any], second: dict[str, Any]) -> list[str]:
    return [str(pair), axis, first["zone"], first["expected"], first["completion"], second["completion"]]


def _queue(originals: _Originals) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    field_limit = csv.field_size_limit()
    _require(all(len(cell) <= field_limit for cell in COLUMNS))
    writer.writerow(COLUMNS)
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


def _review_rows(data: bytes) -> list[list[str]]:
    """Native bounded CSV structure; no original capture or decision claims."""
    reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    rows = []
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
        _require(row[0] == str(int(row[0])))
        rows.append(row)
    _require(header)
    return rows


def _review(data: bytes, originals: _Originals) -> list[dict[str, Any]]:
    entries = {}
    for row in _review_rows(data):
        pair = int(row[0])
        _require(pair in originals.selected and pair not in entries)
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
    _require(set(entries) == set(originals.selected))
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


VERIFICATION_SCOPE = (
    "Supplied report/capture/record consistency, not authenticated source or human truth. "
    "All native capture rows, tabulation, selected membership, axes and both UTF8 completion hashes were checked. "
    "Original preparation and review queue remain unverified declarations. Native flags, statistics, verdict, "
    "calibration, sensitivity and scientific GO are unchanged. Coordinated fabricated inputs may be consistent."
)


def _match_selected_record(
    selected: dict[int, tuple[str, dict[str, Any], dict[str, Any]]], record: dict[str, Any]
) -> None:
    """Exact selected index set, axes and both native UTF8 completion hashes."""
    entries = {entry["pair"]: entry for entry in record["entries"]}
    _require(set(entries) == set(selected))
    for pair, (axis, first, second) in selected.items():
        entry = entries[pair]
        _require(entry["axis"] == axis)
        _require(entry["baseline_sha256"] == _completion_sha256(first["completion"]))
        _require(entry["quantized_sha256"] == _completion_sha256(second["completion"]))


def _verify_held(
    report: DriftReport,
    report_file: HeldFile,
    capture_file: HeldFile,
    record_file: HeldFile,
    record: dict[str, Any],
) -> dict[str, Any]:
    """Receive already parsed/validated native report+record and one held capture."""
    _same_numbers(record["inputs"]["capture"], _binding(capture_file.data), "actual capture")
    selected = _capture_originals(report, record["n_probes"], capture_file.data)
    _match_selected_record(selected, record)
    proof = {
        "adjudication_verification_schema": 1,
        "quantfit_version": __version__,
        "source_verified": True,
        "inputs": {
            "report": _binding(report_file.data),
            "capture": _binding(capture_file.data),
            "record": _binding(record_file.data),
        },
        "binding_fingerprint": record["binding_fingerprint"],
        "n_probes": record["n_probes"],
        "n_selected": len(selected),
        "original_flagged_counts": record["original_flagged_counts"],
        "counts": record["counts"],
        "checks": {**PRODUCER_CHECKS, "receiver_capture_read": True, "selected_axes_checked": True},
        "operator_status": "declared_unauthenticated",
        "proof_limits": {key: value for key, value in PROOF_LIMITS.items() if key != "receiver_capture_read"},
        "unverified_declared_inputs": ["preparation", "review_queue"],
        "scope": VERIFICATION_SCOPE,
    }
    _require(len(_encode(proof)) <= MAX_RECEIPT_BYTES)
    return proof


def verify_adjudication(
    report_path: str, capture_path: str, record_path: str, *, out_path: str | None = None
) -> dict[str, Any]:
    """Verify supplied-source consistency; zero selected/unresolved declarations are valid.

    No original queue, preparation, label key or CSV is opened. An optional NEW
    output is exclusive; encoded inputs are bounded to 8/16/4 MiB by role, and
    the aggregate proof to 64 KiB. These are not heap or execution-time bounds.
    """
    try:
        inputs = (
            hold(report_path, resolution.MAX_REPORT_BYTES),
            hold(capture_path, MAX_CAPTURE_BYTES),
            hold(record_path, MAX_RECORD_BYTES),
        )
        targets = admit_outputs((out_path,), inputs) if out_path is not None else ()
        report = resolution.parse_report_bytes(inputs[0].data)
        record = load_adjudication_record_bytes(inputs[2].data, report=report, report_data=inputs[0].data)
        proof = _verify_held(report, *inputs, record)
        raw = _encode(proof)
        for held in inputs:
            held.check()
        if targets:
            publish(((targets[0], raw),), inputs)
        return proof
    except (KeyboardInterrupt, RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, ImportError):
        raise AdjudicationError("invalid_adjudication") from None
