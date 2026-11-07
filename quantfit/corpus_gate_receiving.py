"""Closed gate3 receiving through the same native decision, never a new calculator."""

from __future__ import annotations

from typing import Any

from quantfit.safety.calibration_binding import BoundCalibration
from quantfit.safety.report import DriftReport


def validate_corpus_gate(
    value: dict[str, Any],
    report: DriftReport | None,
    calibration: BoundCalibration | None,
    *,
    report_sha256: str | None = None,
) -> dict[str, Any]:
    from quantfit import gate
    from quantfit.axis_gate import admit_thresholds
    from quantfit.axis_gate_receiving import KEYS as AXIS_KEYS
    from quantfit.bundle import _GATE_KEYS, _require
    from quantfit.corpus_gate import decision
    from quantfit.gate_receiving import validate_gate_context
    from quantfit.probe_bundle import _dataset, _source_from_context
    from quantfit.probe_population import admit_context, match_report
    from quantfit.safety.calibration_binding import _same_numbers

    kind = value.get("decision_schema_version")
    _require(type(kind) is int and kind in (1, 2), "unknown gate3 native decision schema")
    keys = _GATE_KEYS if kind == 1 else AXIS_KEYS
    _require(
        set(value)
        == keys
        | {"decision_schema_version", "probe_corpus"}
        | ({"source_evidence"} if "source_evidence" in value else set()),
        "gate3 missing or unsupported fields",
    )
    context = admit_context(value["probe_corpus"])
    replay = "source_evidence" in value
    _require(
        context["population_basis"] == ("saved_report_native_counts" if replay else "resolved_native_population"),
        "gate3 population basis contradicts producer",
    )
    if report is not None:
        match_report(report, context)
    if calibration is not None:
        _same_numbers(
            calibration.identity["probe_dataset"],
            _dataset(_source_from_context(context), context["n_probes"]),
            "gate3 calibration population",
        )
    eps, _, observed = validate_gate_context(
        value, report, calibration, report_sha256=report_sha256, _corpus_scope=True
    )
    decode = value["decode"]
    _require(
        type(decode) is dict
        and set(decode) == {"max_new_tokens", "do_sample"}
        and type(decode["max_new_tokens"]) is int
        and decode["max_new_tokens"] > 0
        and decode["do_sample"] is False,
        "gate3 native decode required",
    )
    policy = None
    threshold = tier = None
    if kind == 2:
        _require(type(value.get("policy")) is dict, "gate3 selected policy required")
        policy = admit_thresholds(value["policy"].get("axis_thresholds"))
    else:
        _require(type(value.get("gate")) is dict, "gate3 native scalar declaration required")
        settings = value["gate"]
        tier = settings.get("tier")
        threshold = settings.get("threshold") if tier is None else None
        gate._declared(threshold, tier)
    arms = value["arms"]
    drift = None
    if observed:
        assert report is not None
        drift = report.drift
    expected = decision(
        baseline=arms["baseline"],
        quant=arms["quant"],
        threshold=threshold,
        tier=tier,
        axis_thresholds=policy,
        eps=eps,
        max_new_tokens=decode["max_new_tokens"],
        report_path=arms["report"],
        drift=drift,
        context=context,
        report_sha256=report_sha256 if replay else None,
    )
    for key in ("created_utc", "quantfit_version"):
        _require(type(value.get(key)) is str and bool(value[key]), "gate3 string metadata required")
        expected[key] = value[key]
    _same_numbers(value, expected, "gate3 native aggregate")
    return {
        "exit_code": value["exit_code"],
        "verdict": value["verdict"],
        "decision_schema_version": kind,
        "probe_corpus": context,
        "resolution_is_a_floor": value["resolution_is_a_floor"],
        "actual_run_matched": eps.get("actual_run_matched"),
        "human_labels_verified": False,
    }
