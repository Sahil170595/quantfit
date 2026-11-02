"""Shared strict gate evidence admission; decision schemas retain separate reconstruction."""

from __future__ import annotations

from typing import Any

from quantfit.safety.calibration_binding import BoundCalibration
from quantfit.safety.report import DriftReport


def validate_gate_context(
    value: dict[str, Any],
    report: DriftReport | None,
    calibration: BoundCalibration | None,
    *,
    report_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, bool]:
    from quantfit import gate
    from quantfit.bundle import _require
    from quantfit.modelcard import _check_original_statistics
    from quantfit.safety.calibrated_gate import (
        ASSUMPTIONS,
        OBSERVED_STATEMENT,
        PREFLIGHT_STATEMENT,
        SAVED_REPORT_STATEMENT,
    )
    from quantfit.safety.calibration_binding import _same_numbers
    from quantfit.safety.mde import EPS_DEFINITION

    replay = "source_evidence" in value
    code = value["exit_code"]
    _require(type(code) is int and code in (0, 3, 4, 5), "gate exit code must retain a supported decision state")
    _require(
        value["verdict"] == {0: "PASS", 3: "FAIL", 4: "UNMEASURABLE", 5: "UNRESOLVABLE"}[code],
        "gate verdict and exit code disagree",
    )
    _require(value["passed"] is (True if code == 0 else False if code == 3 else None), "gate passed flag disagrees")
    _require(isinstance(value["eps"], dict) and isinstance(value["resolution"], dict), "gate blocks must be objects")
    _require(type(value["resolution_is_a_floor"]) is bool, "gate floor flag must be boolean")
    _require(
        isinstance(value["arms"], dict) and set(value["arms"]) == {"baseline", "quant", "report"},
        "gate arms must contain only aggregate names/report provenance",
    )
    arms = value["arms"]
    _require(all(isinstance(arms[key], str) and arms[key] for key in ("baseline", "quant")), "invalid gate arm names")
    _require(arms["report"] is None or isinstance(arms["report"], str), "gate report locator must be a string/null")
    observed = value["drift"] is not None
    source_evidence: dict[str, Any] | None = None
    if replay:
        source_evidence = value["source_evidence"]
        _require(
            report is not None and report_sha256 is not None, "saved-report gate requires its exact consumed report"
        )
        assert report is not None
        _require(
            isinstance(source_evidence, dict)
            and set(source_evidence) == {"kind", "report_sha256", "evaluation_phase", "inference_performed"}
            and source_evidence["kind"] == "saved_report"
            and isinstance(source_evidence["report_sha256"], str)
            and source_evidence["report_sha256"] == report_sha256
            and source_evidence["evaluation_phase"] == ("observed_counts" if observed else "policy_preflight")
            and source_evidence["inference_performed"] is False,
            "saved-report provenance contradicts consumed bytes or policy phase",
        )
        _require(
            arms["baseline"] == report.baseline.model and arms["quant"] == report.quantized.model,
            "saved-report gate arm names differ from consumed report",
        )
        _require(
            value["decode"] == {"max_new_tokens": report.decode.get("max_new_tokens"), "do_sample": False}
            and report.decode.get("do_sample", not report.decode.get("greedy", False)) is False
            and report.decode.get("greedy", True) is True
            and type(report.decode.get("temperature", 0)) in (int, float)
            and report.decode.get("temperature", 0) == 0,
            "saved-report gate decode differs from report",
        )
        canonical = _check_original_statistics(report)
        _require(
            type(report.drift["regression_detected"]) is bool
            and report.drift["regression_detected"] is canonical["regression_detected"]
            and report.drift["unmeasurable_axes"] == canonical["unmeasurable_axes"],
            "saved-report derived flags contradict validated counts",
        )
    if observed:
        _require(report is not None, "observed gate requires its aggregate report")
        assert report is not None
        _require(
            arms["baseline"] == report.baseline.model and arms["quant"] == report.quantized.model,
            "gate arm names do not match bundled report",
        )
        _same_numbers(value["drift"], report.drift, "gate drift")
        _require(
            value["decode"] == {"max_new_tokens": report.decode.get("max_new_tokens"), "do_sample": False}
            and report.decode.get("do_sample", not report.decode.get("greedy", False)) is False,
            "gate decode does not match bundled report",
        )
    else:
        _require(
            code == 5 and value["resolution"].get("stage") == "pre_run", "absent gate drift requires pre-run refusal"
        )
    eps = value["eps"]
    if eps.get("mode") == "bound_calibration_report":
        _require(calibration is not None, "bound gate requires the consumed calibration role")
        assert calibration is not None
        _require(
            eps.get("source_sha256") == calibration.source_sha256
            and eps.get("scope_fingerprint") == calibration.fingerprint,
            "gate calibration hashes do not match consumed input",
        )
        _require(
            eps.get("measured") is False and eps.get("assumptions_verified") is False,
            "bound gate cannot authenticate human labels or conditional assumptions",
        )
        _require(
            set(eps)
            == {
                "upper",
                "baseline_upper",
                "quantized_upper",
                "source",
                "source_sha256",
                "scope_fingerprint",
                "binding_status",
                "actual_run_matched",
                "measured",
                "assumptions_verified",
                "assumptions",
                "definition",
                "mode",
                "resolution_is_a_floor",
                "statement",
            }
            and eps["upper"] is None
            and eps["resolution_is_a_floor"] is False
            and eps["source"] == calibration.eps_source
            and eps["assumptions"] == ASSUMPTIONS
            and eps["definition"] == EPS_DEFINITION
            and eps["statement"]
            == (SAVED_REPORT_STATEMENT if replay else OBSERVED_STATEMENT if observed else PREFLIGHT_STATEMENT),
            "gate conditional epsilon does not match validated calibration",
        )
        _same_numbers(eps["baseline_upper"], calibration.eps_baseline_upper, "gate conditional epsilon.baseline_upper")
        _same_numbers(eps["quantized_upper"], calibration.eps_quant_upper, "gate conditional epsilon.quantized_upper")
        _require(
            eps["actual_run_matched"] is (observed or replay)
            and eps["binding_status"]
            == ("actual_run_matched" if observed or replay else "scope_validated_actual_run_unobserved"),
            "gate actual-run status contradicts its drift",
        )
        identity = calibration.identity
        _require(
            arms["baseline"] == identity["baseline"]["model"]
            and arms["quant"] == identity["quantized"]["model"]
            and value["decode"] == {"max_new_tokens": identity["decode"]["max_new_tokens"], "do_sample": False},
            "gate requested arms/decode do not match calibration scope",
        )
    else:
        canonical_eps = (
            gate._eps(None, None)
            if eps.get("mode") == gate.EPS_MODE_FLOOR
            else gate._eps(eps.get("upper"), eps.get("source"))
        )
        _same_numbers(eps, canonical_eps, "gate epsilon")
        eps = canonical_eps
    calculation_eps = dict(eps)
    if eps.get("mode") == "bound_calibration_report":
        assert calibration is not None
        # A nearby serialized float is not the source of the decision. Recompute
        # discrete thresholds from the validated calibration's canonical bounds.
        calculation_eps["baseline_upper"] = calibration.eps_baseline_upper
        calculation_eps["quantized_upper"] = calibration.eps_quant_upper
    return calculation_eps, source_evidence, observed
