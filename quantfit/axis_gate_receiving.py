"""Strict opted gate-v2 reconstruction over the same held native evidence."""

from __future__ import annotations

from typing import Any

from quantfit.axis_gate import admit_thresholds, canonical_report, decision
from quantfit.gate_receiving import validate_gate_context
from quantfit.safety.calibration_binding import BoundCalibration
from quantfit.safety.report import DriftReport

KEYS = {
    "schema_version",
    "quantfit_version",
    "created_utc",
    "arms",
    "policy",
    "eps",
    "resolution_is_a_floor",
    "floor_mode_caveats",
    "resolution",
    "axis_results",
    "diagnostic_axes",
    "verdict",
    "exit_code",
    "passed",
    "drift",
    "underlying_run_verdict",
    "verdict_reconciliation",
    "unselected_axis_regressions",
    "selected_flips_below_detection_threshold",
    "unmeasurable_axes",
    "corpus_composition",
    "decode",
    "caps",
    "notes",
    "message",
    "headline",
}


def validate_axis_gate(
    value: dict[str, Any],
    report: DriftReport | None,
    calibration: BoundCalibration | None,
    *,
    report_sha256: str | None = None,
) -> dict[str, Any]:
    from quantfit.bundle import _require
    from quantfit.safety.calibration_binding import _same_numbers

    _require(
        set(value) == KEYS | ({"source_evidence"} if "source_evidence" in value else set()),
        "gate-v2 has missing or unsupported aggregate fields",
    )
    policy = value.get("policy")
    _require(
        isinstance(policy, dict) and isinstance(policy.get("axis_thresholds"), dict),
        "gate-v2 requires a closed native axis policy",
    )
    assert isinstance(policy, dict)
    thresholds = admit_thresholds(policy["axis_thresholds"])
    if report is not None:
        canonical_report(report)
    eps, _, observed = validate_gate_context(value, report, calibration, report_sha256=report_sha256)
    decode = value["decode"]
    _require(
        isinstance(decode, dict)
        and set(decode) == {"max_new_tokens", "do_sample"}
        and type(decode["max_new_tokens"]) is int
        and decode["max_new_tokens"] > 0
        and decode["do_sample"] is False,
        "gate-v2 requires the native greedy decode contract",
    )
    arms = value["arms"]
    drift = None
    if observed:
        assert report is not None
        drift = report.drift
    expected = decision(
        baseline=arms["baseline"],
        quant=arms["quant"],
        policy=thresholds,
        eps=eps,
        max_new_tokens=decode["max_new_tokens"],
        report_path=arms["report"],
        drift=drift,
        report_sha256=report_sha256 if "source_evidence" in value else None,
    )
    for key in ("created_utc", "quantfit_version"):
        _require(isinstance(value.get(key), str) and bool(value[key]), f"gate-v2 {key} must be a string")
        expected[key] = value[key]
    _same_numbers(value, expected, "gate-v2 aggregate")
    return {
        "exit_code": value["exit_code"],
        "verdict": value["verdict"],
        "selected_axes": list(thresholds),
        "resolution_is_a_floor": value["resolution_is_a_floor"],
        "actual_run_matched": eps.get("actual_run_matched"),
        "assumptions_verified": eps.get("assumptions_verified"),
        "human_labels_verified": eps.get("measured"),
        "unmeasurable_axes": value["unmeasurable_axes"],
    }
