"""Bounded exhaustive hypothetical at-risk resolution, using the native calculator.

This plans no collection and changes no report, observed denominator or verdict.
All work upper bounds are conservative term accounting, never measured runtimes.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

from quantfit import resolution
from quantfit.safety.calibration_binding import MAX_CALIBRATION_BYTES, load_bound_calibration_bytes
from quantfit.safety.mde import (
    _BISECT_ITERS,
    CORRELATED_ERROR_NOTE,
    DEFAULT_ALPHA,
    DEFAULT_POWER,
    PRE_REGISTERED_EFFECT_SIZES,
    TEST_DESCRIPTION,
    _effective_mde_at,
    _power,
    detection_threshold,
    false_flip_rate_bound,
)
from quantfit.safety.report import DriftReport
from quantfit.safety.retained_labels import _encode
from quantfit.safety.retention_io import HeldFile, admit_outputs, hold, publish

MAX_GRID_POINTS = 256
MAX_REQUESTED_EFFECTS = 8
MAX_WORK_UNITS = 40_000_000
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
SCOPE = (
    "One hypothetical at-risk curve under the same supplied global directional calibration bounds, "
    "not separate axis measurements, new report scope, future evidence or a change to recorded probe/axis counts. "
    "Feasible runs and a stable suffix concern only EVERY integer in this finite declared range; "
    "no conclusion applies above n_max. Native power is not monotone in n. Conditional on unchanged "
    "directional-error applicability, arm-independent judge error and majority-real at-risk population. "
    "No source/label authentication, sampling instruction, adaptive stopping, sensitivity, safety verdict or scientific GO."
)


@dataclass(frozen=True)
class ResolutionBudget:
    """Predeclared inclusive integer grid; effect and MDE units are percentage points."""

    n_min: int
    n_max: int
    max_mde_pp: float
    effects_pp: tuple[float, ...] = ()


def _require(condition: bool) -> None:
    if not condition:
        raise resolution.ResolutionError("invalid_resolution_budget")


def _pp(value: object, *, positive: bool = False) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return (0 < value if positive else 0 <= value) and value <= 100 and math.isfinite(value)


def validate_budget(planning: ResolutionBudget) -> None:
    """Admit the complete grid/options before input reads, grid allocation or native math."""
    _require(type(planning) is ResolutionBudget)
    _require(type(planning.n_min) is int and type(planning.n_max) is int)
    _require(0 <= planning.n_min <= planning.n_max <= resolution.MAX_PROBES)
    _require(planning.n_max - planning.n_min + 1 <= MAX_GRID_POINTS)
    _require(_pp(planning.max_mde_pp, positive=True))
    _require(type(planning.effects_pp) is tuple and len(planning.effects_pp) <= MAX_REQUESTED_EFFECTS)
    _require(all(_pp(value) for value in planning.effects_pp))
    _require(len(set(planning.effects_pp)) == len(planning.effects_pp))


def _work(planning: ResolutionBudget, axes: dict[str, Any]) -> dict[str, Any]:
    def threshold(n: int) -> int:
        return n * (n + 1) // 2 + n + 1

    # Actual native _analysis does not use the planned cache: calibrated MDE,
    # perfect-judge contrast and detectability each obtain a threshold.
    actual_power_requests = 2 * (_BISECT_ITERS + 1) + len(PRE_REGISTERED_EFFECT_SIZES) + 1
    actual = sum(
        3 * threshold(axis["n_at_risk"]) + actual_power_requests * (axis["n_at_risk"] + 1) for axis in axes.values()
    )
    planned_power_requests = _BISECT_ITERS + 1 + len(PRE_REGISTERED_EFFECT_SIZES) + 1 + len(planning.effects_pp)
    planned = sum(threshold(n) + planned_power_requests * (n + 1) for n in range(planning.n_min, planning.n_max + 1))
    _require(actual + planned <= MAX_WORK_UNITS)
    return {
        "actual_upper_bound": actual,
        "planned_upper_bound": planned,
        "total_upper_bound": actual + planned,
        "limit": MAX_WORK_UNITS,
        "unit": "conservative binomial-tail terms plus threshold/scan overhead; not wall time or exact operations",
        "actual_thresholds_per_axis": 3,
        "actual_power_requests_per_axis_upper_bound": actual_power_requests,
        "planned_threshold_cache": "local exact (n, false_flip_bound, alpha); actual native analysis is not cached",
        "planned_power_requests_per_point_upper_bound": planned_power_requests,
        "planned_perfect_judge_contrast": False,
    }


def _curve(planning: ResolutionBudget, q: float) -> list[dict[str, Any]]:
    """Native math only, after admission; no axis-by-axis duplicate hypothetical curves."""
    cache: dict[tuple[int, float, float], int] = {}
    rows = []
    for n in range(planning.n_min, planning.n_max + 1):
        key = (n, q, DEFAULT_ALPHA)
        if key not in cache:
            cache[key] = detection_threshold(n, q, DEFAULT_ALPHA)
        k = cache[key]
        mde = _effective_mde_at(k, n, q, DEFAULT_POWER)
        detectable = n > 0 and _power(k, n, 1.0, q) >= DEFAULT_POWER
        rows.append(
            {
                "n_at_risk": n,
                "detection_threshold_flips": k,
                "effective_mde": mde,
                "detectable_at_target_power": detectable,
                "passes": detectable and mde <= float(planning.max_mde_pp) / 100,
                "power_at_pre_registered": [
                    {"effect": effect, "power": _power(k, n, effect, q)} for effect in PRE_REGISTERED_EFFECT_SIZES
                ],
                "power_at_requested": [
                    {"effect_pp": float(effect), "power": _power(k, n, float(effect) / 100, q)}
                    for effect in planning.effects_pp
                ],
            }
        )
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    runs: list[dict[str, int]] = []
    for row in rows:
        if not row["passes"]:
            continue
        n = row["n_at_risk"]
        if runs and runs[-1]["n_max"] == n - 1:
            runs[-1]["n_max"] = n
        else:
            runs.append({"n_min": n, "n_max": n})
    return {
        "first_passing_n": runs[0]["n_min"] if runs else None,
        "feasible_runs": runs,
        "stable_suffix": dict(runs[-1]) if runs and rows[-1]["passes"] else None,
        "no_feasible_point": not runs,
    }


def analyze_budget_bytes(
    report_data: bytes, calibration_data: bytes, planning: ResolutionBudget
) -> tuple[DriftReport, dict[str, Any]]:
    """Pure held-buffer admission/match/actual-count preparation before any power calculation."""
    try:
        validate_budget(planning)
        report = resolution.parse_report_bytes(report_data)
        calibration = load_bound_calibration_bytes(calibration_data, report=report)
        axes = resolution._axes(report)
        admission = _work(planning, axes)
        # Existing actual analysis is unchanged and runs only after ALL work is admitted.
        artifact = resolution._analysis(report, hashlib.sha256(report_data).hexdigest(), calibration)
        q = false_flip_rate_bound(calibration.eps_baseline_upper, calibration.eps_quant_upper)
        rows = _curve(planning, q)
        artifact["planning"] = {
            "planning_schema": 1,
            "hypothetical": True,
            "n_basis": "hypothetical at-risk pairs; not recorded corpus size or actual per-axis denominators",
            "grid": {"n_min": planning.n_min, "n_max": planning.n_max, "step": 1, "n_points": len(rows)},
            "max_mde_pp": float(planning.max_mde_pp),
            "false_flip_rate_bound": q,
            "alpha": DEFAULT_ALPHA,
            "power": DEFAULT_POWER,
            "test": TEST_DESCRIPTION,
            "work_admission": admission,
            "curve": rows,
            **_summary(rows),
            "correlated_error_note": CORRELATED_ERROR_NOTE,
            "scope": SCOPE,
            "human_confirmation_verified": False,
            "assumptions_verified": False,
            "scientific_go": False,
        }
        _require(len(_encode(artifact)) <= MAX_OUTPUT_BYTES)
        return report, artifact
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise resolution.ResolutionError("invalid_resolution_budget") from None


def _inputs(report_path: str, calibration_path: str, planning: ResolutionBudget) -> tuple[HeldFile, HeldFile]:
    validate_budget(planning)
    return hold(report_path, resolution.MAX_REPORT_BYTES), hold(calibration_path, MAX_CALIBRATION_BYTES)


def analyze_budget_inputs(
    report_path: str, calibration_path: str, planning: ResolutionBudget
) -> tuple[DriftReport, dict[str, Any]]:
    try:
        files = _inputs(report_path, calibration_path, planning)
        result = analyze_budget_bytes(files[0].data, files[1].data, planning)
        for held in files:
            held.check()
        return result
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise resolution.ResolutionError("invalid_resolution_budget") from None


def analyze_budget(
    report_path: str, calibration_path: str, out_path: str | None, planning: ResolutionBudget
) -> dict[str, Any]:
    try:
        files = _inputs(report_path, calibration_path, planning)
        targets = admit_outputs((out_path,), files) if out_path is not None else ()
        _, artifact = analyze_budget_bytes(files[0].data, files[1].data, planning)
        if targets:
            publish(((targets[0], _encode(artifact)),), files)
        else:
            for held in files:
                held.check()
        return artifact
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise resolution.ResolutionError("invalid_resolution_budget") from None
