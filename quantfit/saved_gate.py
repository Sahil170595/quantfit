"""Single-buffer offline gate replay; recorded evidence is not new inference."""

from __future__ import annotations

from pathlib import Path

from quantfit.gate import (
    EXIT_UNRESOLVABLE,
    SHIPPED_EXPECTED_UNSAFE_N,
    STAGE_PRE_RUN,
    VERDICT_UNRESOLVABLE,
    GateError,
    _block,
    _decision,
    _declared,
    _eps,
    _observed_policy,
    _refusal_message,
    _require,
    _resolution,
    _write,
)


def validate_replay_outputs(inputs, outputs):
    """Refuse direct, canonical and same-file aliases before publishing any output."""
    sources = [Path(path).resolve() for path in inputs if path is not None]
    destinations = [Path(path).resolve() for path in outputs if path is not None]
    for index, target in enumerate(destinations):
        for other in [*sources, *destinations[:index]]:
            _require(
                target != other and not (target.exists() and other.exists() and target.samefile(other)),
                "saved report/calibration inputs and all replay outputs must be distinct",
            )


def evaluate_report(
    source_path: str,
    *,
    threshold: float | None = None,
    tier: str | None = None,
    eps_upper: float | None = None,
    eps_source: str | None = None,
    calibration_report: str | None = None,
    report_path_out: str | None = None,
    out_path: str | None = None,
) -> dict:
    """Re-evaluate a saved aggregate under native gate policy, without new inference.

    Consume and bind each input once. The native best-case policy precheck still
    precedes observed-count evaluation; pre_run labels that policy phase only.
    Recorded scope is checkable, not fresh authentication of the host or labels.
    """
    import hashlib

    from quantfit.bundle import _json, _read, _report
    from quantfit.resolution import MAX_REPORT_BYTES
    from quantfit.safety.calibrated_gate import calibration_epsilon
    from quantfit.safety.calibration_binding import MAX_CALIBRATION_BYTES, load_bound_calibration_bytes

    validate_replay_outputs([source_path, calibration_report], [report_path_out, out_path])
    try:
        raw = _read(Path(source_path), MAX_REPORT_BYTES)
        _json(raw)
        report = _report(raw)
        from quantfit.modelcard import _check_original_statistics

        # Original verdict/statistics are recomputed by _report. Its existing
        # helper also exposes the canonical derived flags for this new consumer.
        canonical = _check_original_statistics(report)
        _require(
            type(report.drift["regression_detected"]) is bool
            and report.drift["regression_detected"] is canonical["regression_detected"]
            and report.drift["unmeasurable_axes"] == canonical["unmeasurable_axes"],
            "saved report derived flags contradict its validated counts",
        )
        decode = report.decode
        max_tokens = decode.get("max_new_tokens")
        _require(type(max_tokens) is int and max_tokens > 0, "saved report needs a positive recorded token limit")
        _require(
            decode.get("do_sample", not decode.get("greedy", False)) is False
            and decode.get("greedy", True) is True
            and type(decode.get("temperature", 0)) in (int, float)
            and decode.get("temperature", 0) == 0,
            "saved-report gate requires the recorded greedy decode contract",
        )
        threshold_value, tier_row, declared_as = _declared(threshold, tier)
        if calibration_report is None:
            eps = _eps(eps_upper, eps_source)
        else:
            _require(
                eps_upper is None and eps_source is None,
                "calibration_report is mutually exclusive with operator epsilon/source",
            )
            cal_raw = _read(Path(calibration_report), MAX_CALIBRATION_BYTES)
            _json(cal_raw)
            bound = load_bound_calibration_bytes(cal_raw, report=report)
            eps = calibration_epsilon(bound, saved_report=True)
        best = _block(eps, SHIPPED_EXPECTED_UNSAFE_N)
        pre = _resolution(STAGE_PRE_RUN, threshold_value, best, eps, SHIPPED_EXPECTED_UNSAFE_N)
        options = (
            {
                "block": best,
                "resolution": pre,
                "verdict": VERDICT_UNRESOLVABLE,
                "exit_code": EXIT_UNRESOLVABLE,
                "message": _refusal_message(pre, eps, declared_as),
                "passed": None,
                "drift": None,
                "over_refusal": None,
            }
            if not pre["not_refused"]
            else _observed_policy(report.drift, threshold_value, eps, declared_as)
        )
        source_evidence = {
            "kind": "saved_report",
            "report_sha256": hashlib.sha256(raw).hexdigest(),
            "evaluation_phase": "policy_preflight" if options["drift"] is None else "observed_counts",
            "inference_performed": False,
        }
        decision = _decision(
            baseline=report.baseline.model,
            quant=report.quantized.model,
            threshold=threshold_value,
            tier=tier_row,
            declared_as=declared_as,
            eps=eps,
            max_new_tokens=max_tokens,
            report_path=report_path_out or source_path,
            source_evidence=source_evidence,
            **options,
        )
        validate_replay_outputs([source_path, calibration_report], [report_path_out, out_path])
        if report_path_out is not None:
            Path(report_path_out).write_bytes(raw)
        if out_path is not None:
            _write(out_path, decision)
        return decision
    except (OSError, RuntimeError) as exc:
        if isinstance(exc, GateError):
            raise
        raise GateError(str(exc)) from exc
