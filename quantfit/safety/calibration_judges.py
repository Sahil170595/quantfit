"""Descriptive two-judge diagnostics over one exact supplied completion/truth vector."""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfit import __version__, resolution
from quantfit.adjudication_record import _validate_report, _version
from quantfit.safety import calibrate, verify
from quantfit.safety.calibration_binding import _same_numbers, identity_fingerprint, measurement_identity
from quantfit.safety.calibration_inputs import (
    MAX_CAPTURE_BYTES,
    CalibrationRow,
    HeldCalibrationInputs,
    _verified_capture,
)
from quantfit.safety.calibration_strata import _group
from quantfit.safety.reconcile import MAX_CSV_RECORDS, MAX_KEY_BYTES, MAX_SHEET_BYTES
from quantfit.safety.retained_labels import (
    MAX_RECEIPT_BYTES,
    MAX_RETAINED_BYTES,
    _binding,
    _encode,
    _json,
    _key,
    _load_retained_held,
)
from quantfit.safety.retention_io import HeldFile, admit_outputs, canonical, hold, publish
from quantfit.safety.verify import JUDGE_INPUT_CONTRACT

MAX_INPUT_BYTES = 52 * 1024 * 1024
MAX_JUDGES_BYTES = 256 * 1024
COMMAND = "calibrate compare-judges"
OBSERVE_COMMAND = "calibrate observe-judge"
COMPARE_OBSERVED_COMMAND = "calibrate compare-observed-judge"
OBSERVATION_KIND = "quantfit.calibration-judge-observation"
OBSERVED_SCOPE = (
    "A is the original recorded flags; B is a fresh pinned judge observation over the exact same held completions. "
    "Both sides use the same supplied ternary truth. Whole flag tables retain unusable rows; error tables omit them. "
    "No source or execution authentication, independence, calibration replacement, sensitivity or scientific GO."
)
SCOPE = (
    "Descriptive comparison of captured judge flags against the same supplied ternary truth labels. "
    "Whole-population flag tables retain unusable truth; error tables use only each arm's usable truth. "
    "Native per-arm/directional Wilson denominators remain separate. Exact strings do not establish "
    "equal tokenization, truncation, prompts or actual execution. No pooled calibration, preferred judge, "
    "paired significance, independence, authenticated source/human truth, sensitivity or scientific GO."
)


class CalibrationJudgesError(RuntimeError):
    """Categorical refusal; no private paths, parser values or exception chains."""


def _require(condition: bool) -> None:
    if not condition:
        raise CalibrationJudgesError("invalid_calibration_judges")


def _mode(sheet: str | None, retained: str | None, receipt: str | None) -> str:
    _require((sheet is not None) != (retained is not None))
    _require((retained is not None) == (receipt is not None))
    return "full_sheet" if sheet is not None else "retained_labels"


def _held_truth(
    files: dict[str, HeldFile], mode: str, key: dict[str, Any], n: int
) -> tuple[dict[str, str], dict[str, Any]]:
    if mode == "full_sheet":
        joined = calibrate._join(
            "private sheet", "private key", key["ids"], data=files["sheet"].data, max_records=MAX_CSV_RECORDS
        )
        labels = {row_id: row["human_label"] for row_id, row in joined.items()}
        original = {**_binding(files["sheet"].data), "held_and_validated": True}
    else:
        retained = _load_retained_held(
            files["retained_labels"], files["retention_receipt"], files["key"], parsed_key=(key, n)
        )
        labels = retained.labels
        original = {**retained.receipt["inputs"]["sheet"], "held_and_validated": False}
    return labels, original


def _side(
    files: dict[str, HeldFile], mode: str
) -> tuple[HeldCalibrationInputs, dict[tuple[int, str], str], dict[str, Any]]:
    key, n = _key(files["key"].data)
    _require(key["key_schema"] == calibrate.KEY_SCHEMA and key.get("binding") is not None)
    captured = _verified_capture(files["capture"], key, n)
    identity = key["binding"]["identity"]
    _require(identity["judge"]["input_contract"] == JUDGE_INPUT_CONTRACT)
    common = {**identity, "judge": {k: v for k, v in identity["judge"].items() if k not in {"id", "revision"}}}
    labels, original = _held_truth(files, mode, key, n)
    rows = tuple(
        sorted(
            (
                CalibrationRow(
                    entry["pair"],
                    entry["arm"],
                    captured[row_id]["zone"],
                    captured[row_id]["expected"],
                    captured[row_id]["judge_refusal"],
                    labels[row_id],
                )
                for row_id, entry in key["ids"].items()
            ),
            key=lambda row: (row.pair, row.arm),
        )
    )
    text = {(entry["pair"], entry["arm"]): captured[row_id]["completion"] for row_id, entry in key["ids"].items()}
    held = HeldCalibrationInputs(
        rows, n, key["binding"]["fingerprint"], tuple(files.values()), tuple(files), mode, original
    )
    return held, text, common


def _tables(a: tuple[CalibrationRow, ...], b: tuple[CalibrationRow, ...], native: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for arm in calibrate.ARMS:
        first = [row for row in a if row.arm == arm]
        second = {(row.pair, row.arm): row for row in b if row.arm == arm}
        flags, errors = [[0, 0], [0, 0]], [[0, 0], [0, 0]]
        usable = 0
        for one in first:
            two = second[(one.pair, one.arm)]
            flags[int(one.judge_refusal)][int(two.judge_refusal)] += 1
            if one.human_label != calibrate.LABEL_UNUSABLE:
                truth = one.human_label == calibrate.LABEL_REFUSAL
                errors[int(one.judge_refusal != truth)][int(two.judge_refusal != truth)] += 1
                usable += 1
        _require(sum(map(sum, flags)) == len(first) and sum(map(sum, errors)) == usable)
        _require(usable == native["a"]["arms"][arm]["n"] == native["b"]["arms"][arm]["n"])
        _require(sum(errors[1]) == native["a"]["arms"][arm]["judge_errors"])
        _require(sum(row[1] for row in errors) == native["b"]["arms"][arm]["judge_errors"])
        result[arm] = {
            "whole_n": len(first),
            "flag_states": ["compliance", "refusal"],
            "judge_a_by_judge_b": flags,
            "flag_disagreements": flags[0][1] + flags[1][0],
            "usable_truth_n": usable,
            "unusable_truth_n": len(first) - usable,
            "error_states": ["correct", "incorrect"],
            "error_a_by_error_b": errors,
            "error_a_margin": sum(errors[1]),
            "error_b_margin": sum(row[1] for row in errors),
        }
    return result


def _truth_coverage(rows: tuple[CalibrationRow, ...], n: int) -> dict[str, int]:
    by_cell = {(row.pair, row.arm): row for row in rows}
    coverage = {"both_usable": 0, "baseline_only": 0, "quantized_only": 0, "neither_usable": 0}
    states = {
        (True, True): "both_usable",
        (True, False): "baseline_only",
        (False, True): "quantized_only",
        (False, False): "neither_usable",
    }
    for pair in range(n):
        state = (
            by_cell[(pair, "baseline")].human_label != calibrate.LABEL_UNUSABLE,
            by_cell[(pair, "quantized")].human_label != calibrate.LABEL_UNUSABLE,
        )
        coverage[states[state]] += 1
    return {"denominator_pairs": n, **coverage}


def _analyze(
    capture_a: str,
    key_a: str,
    capture_b: str,
    key_b: str,
    *,
    sheet_a: str | None = None,
    retained_labels_a: str | None = None,
    retention_receipt_a: str | None = None,
    sheet_b: str | None = None,
    retained_labels_b: str | None = None,
    retention_receipt_b: str | None = None,
    out_path: str,
) -> tuple[dict[str, Any], bytes]:
    try:
        modes = (
            _mode(sheet_a, retained_labels_a, retention_receipt_a),
            _mode(sheet_b, retained_labels_b, retention_receipt_b),
        )
        _require(
            all(
                isinstance(path, (str, Path)) and bool(str(path))
                for path in (capture_a, key_a, capture_b, key_b, out_path)
            )
        )
        _require(
            all(
                isinstance(path, (str, Path)) and bool(str(path))
                for path in (
                    sheet_a,
                    retained_labels_a,
                    retention_receipt_a,
                    sheet_b,
                    retained_labels_b,
                    retention_receipt_b,
                )
                if path is not None
            )
        )
        remaining = MAX_INPUT_BYTES
        cache: dict[Path, HeldFile] = {}
        suites = []
        for capture, key, sheet, labels, receipt in (
            (capture_a, key_a, sheet_a, retained_labels_a, retention_receipt_a),
            (capture_b, key_b, sheet_b, retained_labels_b, retention_receipt_b),
        ):
            files = {}
            for role, path, cap in (
                ("capture", capture, MAX_CAPTURE_BYTES),
                ("key", key, MAX_KEY_BYTES),
                ("sheet", sheet, MAX_SHEET_BYTES),
                ("retained_labels", labels, MAX_RETAINED_BYTES),
                ("retention_receipt", receipt, MAX_RECEIPT_BYTES),
            ):
                if path is None:
                    continue
                name = canonical(path)
                if name not in cache:
                    cache[name] = hold(name, min(cap, remaining))
                item = cache[name]
                _require(len(item.data) <= min(cap, remaining))
                remaining -= len(item.data)
                files[role] = item
            suites.append(files)
        inputs = tuple(cache.values())
        target = admit_outputs((out_path,), inputs)[0]
        a, text_a, common_a = _side(suites[0], modes[0])
        b, text_b, common_b = _side(suites[1], modes[1])
        _require(a.n_pairs == b.n_pairs and identity_fingerprint(common_a) == identity_fingerprint(common_b))
        rows_a = {(row.pair, row.arm): row for row in a.rows}
        rows_b = {(row.pair, row.arm): row for row in b.rows}
        cells = [(pair, arm) for pair in range(a.n_pairs) for arm in calibrate.ARMS]
        _require(set(rows_a) == set(rows_b) == set(cells) and len(a.rows) == len(b.rows) == len(cells))
        population, truth = [], []
        for cell in cells:
            one, two = rows_a[cell], rows_b[cell]
            _require(one.zone == two.zone and one.expected == two.expected)
            _require(one.human_label == two.human_label and text_a[cell] == text_b[cell])
            population.append([one.pair, one.arm, one.zone, one.expected, calibrate._completion_sha256(text_a[cell])])
            truth.append([one.pair, one.arm, one.human_label])
        _require(len(population) == 2 * a.n_pairs)
        native = {"a": _group(a.rows), "b": _group(b.rows)}
        result = {
            "calibration_judges_schema": 1,
            "kind": "quantfit.calibration-judges",
            "quantfit_version": __version__,
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_pairs": a.n_pairs,
            "n_rows_per_judge": len(a.rows),
            "population_fingerprint": identity_fingerprint({"rows": population}),
            "truth_fingerprint": identity_fingerprint({"rows": truth}),
            "common_protocol_fingerprint": identity_fingerprint(common_a),
            "sources": {
                side: {
                    "binding_fingerprint": held.binding_fingerprint,
                    "label_mode": held.label_mode,
                    "inputs": held.public_inputs(),
                    "original_sheet": held.original_sheet,
                }
                for side, held in (("a", a), ("b", b))
            },
            "native_per_judge": native,
            "per_arm": _tables(a.rows, b.rows, native),
            "truth_coverage": _truth_coverage(a.rows, a.n_pairs),
            "human_labels_authenticated": False,
            "source_authenticity_verified": False,
            "judge_execution_verified": False,
            "independence_verified": False,
            "sensitivity_verified": False,
            "scientific_go": False,
            "replaces_calibration": False,
            "gate_eligible": False,
            "scope": SCOPE,
        }
        from quantfit.cli import _json_document

        raw = _encode(result)
        envelope = (json.dumps(_json_document(COMMAND, 0, result), indent=2, allow_nan=False) + "\n").encode("utf-8")
        _require(len(raw) <= MAX_JUDGES_BYTES and len(envelope) <= MAX_JUDGES_BYTES)
        publish(((target, raw),), inputs)
        return result, envelope
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
        raise CalibrationJudgesError("invalid_calibration_judges") from None


def analyze_calibration_judges(
    capture_a: str,
    key_a: str,
    capture_b: str,
    key_b: str,
    *,
    sheet_a: str | None = None,
    retained_labels_a: str | None = None,
    retention_receipt_a: str | None = None,
    sheet_b: str | None = None,
    retained_labels_b: str | None = None,
    retention_receipt_b: str | None = None,
    out_path: str,
) -> dict[str, Any]:
    """Complete descriptive diagnostics (0); invalid/unsafe evidence refuses (2)."""
    result, _ = _analyze(
        capture_a,
        key_a,
        capture_b,
        key_b,
        sheet_a=sheet_a,
        retained_labels_a=retained_labels_a,
        retention_receipt_a=retention_receipt_a,
        sheet_b=sheet_b,
        retained_labels_b=retained_labels_b,
        retention_receipt_b=retention_receipt_b,
        out_path=out_path,
    )
    return result


@dataclass(frozen=True)
class _OriginalObservation:
    key: dict[str, Any]
    ids: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    facts: dict[str, Any]


def _original_observation(files: dict[str, HeldFile]) -> _OriginalObservation:
    from quantfit.safety.adjudication import _capture_selection

    report = resolution.parse_report_bytes(files["report"].data)
    n = _validate_report(report)
    key, key_pairs = _key(files["key"].data)
    _require(key_pairs == n and key["key_schema"] == calibrate.KEY_SCHEMA and key["binding"] is not None)
    captured = _verified_capture(files["capture"], key, n)
    identity = measurement_identity(report)
    _require(identity["judge"]["input_contract"] == JUDGE_INPUT_CONTRACT)
    _same_numbers(key["binding"]["identity"], identity, "original report identity")
    _require(key["binding"]["fingerprint"] == identity_fingerprint(identity))
    _, probes, baseline, quantized = _capture_selection(n, list(captured.values()))
    _same_numbers(report.drift, verify._tabulate(probes, baseline, quantized).to_dict(), "original capture drift")
    by_cell = {(entry["arm"], entry["pair"]): row_id for row_id, entry in key["ids"].items()}
    ids = tuple(by_cell[(arm, pair)] for arm in calibrate.ARMS for pair in range(n))
    rows = tuple(captured[row_id] for row_id in ids)
    cells = [[row["pair"], row["arm"], calibrate._completion_sha256(row["completion"])] for row in rows]
    return _OriginalObservation(
        key,
        ids,
        rows,
        {
            "inputs": {role: _binding(files[role].data) for role in ("report", "capture", "key")},
            "original_measurement_fingerprint": key["binding"]["fingerprint"],
            "n_pairs": n,
            "arm_order": list(calibrate.ARMS),
            "ordered_cells_sha256": identity_fingerprint({"cells": cells}),
        },
    )


def _fresh_judge() -> dict[str, str]:
    return {"id": verify.JUDGE_MODEL_ID, "revision": verify.JUDGE_REVISION, "input_contract": JUDGE_INPUT_CONTRACT}


def _check_vector(flags: object, runtime: object, n: int) -> None:
    _require(type(flags) is list and len(flags) == n and all(type(flag) is bool for flag in flags))
    _require((type(runtime) is int or type(runtime) is float) and math.isfinite(runtime) and runtime >= 0)


def _held_originals(report: str, capture: str, key: str) -> dict[str, HeldFile]:
    return {
        "report": hold(report, resolution.MAX_REPORT_BYTES),
        "capture": hold(capture, MAX_CAPTURE_BYTES),
        "key": hold(key, MAX_KEY_BYTES),
    }


def _observed_envelope(command: str, result: dict[str, Any]) -> bytes:
    from quantfit.cli import _json_document

    envelope = (json.dumps(_json_document(command, 0, result), indent=2, allow_nan=False) + "\n").encode("utf-8")
    _require(len(envelope) <= MAX_JUDGES_BYTES)
    return envelope


def _observe(
    report_path: str, capture_path: str, key_path: str, *, out_path: str, token: str | None = None
) -> tuple[dict[str, Any], bytes]:
    try:
        files = _held_originals(report_path, capture_path, key_path)
        inputs = tuple(files.values())
        target = admit_outputs((out_path,), inputs)[0]
        original = _original_observation(files)
        completions = [row["completion"] for row in original.rows]
        try:
            flags, runtime = verify._classify_refusals(completions, token)
        except Exception:  # noqa: BLE001 -- External classifier failures must not disclose private values.
            # SDK failures can carry private values and need not be RuntimeError.
            raise CalibrationJudgesError("invalid_calibration_judges") from None
        _check_vector(flags, runtime, len(original.rows))
        record = {
            "judge_observation_schema": 1,
            "kind": OBSERVATION_KIND,
            "quantfit_version": __version__,
            **original.facts,
            "fresh_judge": _fresh_judge(),
            "runtime_s": runtime,
            "flags": flags,
        }
        raw = _encode(record)
        _require(len(raw) <= MAX_JUDGES_BYTES)
        result = {
            "observation": _binding(raw),
            "n_pairs": original.facts["n_pairs"],
            "n_rows": len(original.rows),
        }
        envelope = _observed_envelope(OBSERVE_COMMAND, result)
        publish(((target, raw),), inputs)
        return result, envelope
    except (
        KeyboardInterrupt,
        RuntimeError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        ImportError,
        OverflowError,
        csv.Error,
    ):
        raise CalibrationJudgesError("invalid_calibration_judges") from None


def observe_calibration_judge(
    report_path: str, capture_path: str, key_path: str, *, out_path: str, token: str | None = None
) -> dict[str, Any]:
    """Run the pinned judge once on held private completions; return a hash/count receipt."""
    result, _ = _observe(report_path, capture_path, key_path, out_path=out_path, token=token)
    return result


def _observation_flags(data: bytes, pin: str, original: _OriginalObservation) -> tuple[list[bool], dict[str, Any]]:
    _require(type(pin) is str and re.fullmatch(r"[0-9a-f]{64}", pin) is not None and _binding(data)["sha256"] == pin)
    received = _json(data)
    expected = {
        "judge_observation_schema": 1,
        "kind": OBSERVATION_KIND,
        **original.facts,
        "fresh_judge": _fresh_judge(),
    }
    _require(set(received) == set(expected) | {"quantfit_version", "runtime_s", "flags"})
    _version(received["quantfit_version"])
    _same_numbers({name: received[name] for name in expected}, expected, "observation binding")
    flags, runtime = received["flags"], received["runtime_s"]
    _check_vector(flags, runtime, len(original.rows))
    return flags, {
        "judge": received["fresh_judge"],
        "runtime_s": runtime,
        "quantfit_version": received["quantfit_version"],
    }


def _compare_observed(
    report_path: str,
    capture_path: str,
    key_path: str,
    observation_path: str,
    *,
    observation_sha256: str,
    sheet_path: str | None = None,
    retained_labels_path: str | None = None,
    retention_receipt_path: str | None = None,
    out_path: str,
) -> tuple[dict[str, Any], bytes]:
    try:
        mode = _mode(sheet_path, retained_labels_path, retention_receipt_path)
        files = _held_originals(report_path, capture_path, key_path)
        files["observation"] = hold(observation_path, MAX_JUDGES_BYTES)
        if sheet_path is not None:
            files["sheet"] = hold(sheet_path, MAX_SHEET_BYTES)
        else:
            assert retained_labels_path is not None and retention_receipt_path is not None
            files["retained_labels"] = hold(retained_labels_path, MAX_RETAINED_BYTES)
            files["retention_receipt"] = hold(retention_receipt_path, MAX_RECEIPT_BYTES)
        inputs = tuple(files.values())
        target = admit_outputs((out_path,), inputs)[0]
        original = _original_observation(files)
        flags, fresh = _observation_flags(files["observation"].data, observation_sha256, original)
        n = original.facts["n_pairs"]
        labels, sheet = _held_truth(files, mode, original.key, n)
        a = tuple(
            CalibrationRow(row["pair"], row["arm"], row["zone"], row["expected"], row["judge_refusal"], labels[row_id])
            for row_id, row in zip(original.ids, original.rows, strict=True)
        )
        b = tuple(replace(row, judge_refusal=flag) for row, flag in zip(a, flags, strict=True))
        old_judge = original.key["binding"]["identity"]["judge"]
        native = {"a": _group(a), "b": _group(b)}
        result = {
            "calibration_observed_judge_schema": 1,
            "kind": "quantfit.calibration-observed-judge-comparison",
            "quantfit_version": __version__,
            "n_pairs": n,
            "n_rows_per_judge": len(a),
            "inputs": {role: _binding(item.data) for role, item in files.items()},
            "original_measurement_fingerprint": original.facts["original_measurement_fingerprint"],
            "original_recorded_judge_fingerprint": identity_fingerprint(old_judge),
            "fresh_observation": fresh,
            "same_judge_pin": all(old_judge[name] == fresh["judge"][name] for name in ("id", "revision")),
            "label_mode": mode,
            "original_sheet": sheet,
            "native_per_judge": native,
            "per_arm": _tables(a, b, native),
            "truth_coverage": _truth_coverage(a, n),
            "human_truth_authenticated": False,
            "source_authenticity_verified": False,
            "judge_execution_verified": False,
            "independence_verified": False,
            "sensitivity_verified": False,
            "scientific_go": False,
            "replaces_calibration": False,
            "gate_eligible": False,
            "scope": OBSERVED_SCOPE,
        }
        raw = _encode(result)
        envelope = _observed_envelope(COMPARE_OBSERVED_COMMAND, result)
        _require(len(raw) <= MAX_JUDGES_BYTES)
        publish(((target, raw),), inputs)
        return result, envelope
    except (
        KeyboardInterrupt,
        RuntimeError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        ImportError,
        OverflowError,
        csv.Error,
    ):
        raise CalibrationJudgesError("invalid_calibration_judges") from None


def compare_observed_judge(
    report_path: str,
    capture_path: str,
    key_path: str,
    observation_path: str,
    *,
    observation_sha256: str,
    sheet_path: str | None = None,
    retained_labels_path: str | None = None,
    retention_receipt_path: str | None = None,
    out_path: str,
) -> dict[str, Any]:
    """Compare a pinned observation against the original flags and one native truth suite offline."""
    result, _ = _compare_observed(
        report_path,
        capture_path,
        key_path,
        observation_path,
        observation_sha256=observation_sha256,
        sheet_path=sheet_path,
        retained_labels_path=retained_labels_path,
        retention_receipt_path=retention_receipt_path,
        out_path=out_path,
    )
    return result
