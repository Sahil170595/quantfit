"""Live selected-axis orchestration: one native run after every policy precheck."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quantfit import gate
from quantfit.axis_gate import admit_thresholds, decision, preflight


def run_axis_gate(
    baseline: str,
    quant: str,
    *,
    axis_thresholds: Mapping[str, float],
    threshold: float | None = None,
    tier: str | None = None,
    eps_upper: float | None = None,
    eps_source: str | None = None,
    token: str | None = None,
    max_new_tokens: int = 64,
    report_path: str | None = None,
    out_path: str | None = None,
    baseline_cache_dir: str | None = None,
    calibration_report: str | None = None,
) -> dict[str, Any]:
    policy = admit_thresholds(axis_thresholds, threshold, tier)
    baseline, quant = gate._text(baseline, "baseline"), gate._text(quant, "quant")
    gate._require(type(max_new_tokens) is int and max_new_tokens > 0, "max_new_tokens must be a positive integer")
    gate.validate_replay_outputs([calibration_report], [report_path, out_path])
    bound = None
    if calibration_report is not None:
        from quantfit.safety.calibrated_gate import prepare_calibration

        gate._require(
            eps_upper is None and eps_source is None,
            "calibration_report is mutually exclusive with operator epsilon/source",
        )
        bound, eps = prepare_calibration(calibration_report, baseline, quant, max_new_tokens, gate.SHIPPED_CORPUS_N)
    else:
        eps = gate._eps(eps_upper, eps_source)
    best = preflight(policy, eps)
    drift = None
    if all(row["resolution"]["not_refused"] for row in best.values()):
        if bound is not None:
            from quantfit.safety.calibrated_gate import verify_bound_run

            drift = verify_bound_run(
                bound,
                eps,
                baseline,
                quant,
                token=token,
                max_new_tokens=max_new_tokens,
                report_path=report_path,
                baseline_cache_dir=baseline_cache_dir,
            )
        else:
            from quantfit.safety.verify import verify_safety

            drift = verify_safety(
                baseline,
                quant,
                token=token,
                max_new_tokens=max_new_tokens,
                report_path=report_path,
                baseline_cache_dir=baseline_cache_dir,
            )
    value = decision(
        baseline=baseline,
        quant=quant,
        policy=policy,
        eps=eps,
        max_new_tokens=max_new_tokens,
        report_path=report_path,
        drift=None if drift is None else drift.to_dict(),
    )
    if out_path is not None:
        gate._write(out_path, value)
    return value
