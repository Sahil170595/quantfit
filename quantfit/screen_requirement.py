"""Opt-in receiving criteria over existing native conditional resolution; no new math."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any
from xml.etree import ElementTree as ET

from quantfit.saved_screen import SavedScreenError

AXES = ("refusal-robustness", "over-refusal")
SCOPE = (
    "Explicit conditional-resolution requirement on the same held supplied aggregates. Native outcome, "
    "flags and evidence remain unchanged; the qualification exit is emitted separately. Every declared "
    "target and both axes must have matched report/calibration evidence, a measurable denominator, "
    "attainable target power and finite effective MDE no greater than the declared percentage-point ceiling. "
    "No pooling, authenticated labels/assumptions, independence, source/weight authenticity, sensitivity "
    "or scientific GO is established."
)
AXIS_SCOPE = (
    "Explicit selected-axis conditional-resolution requirements on the same held supplied aggregates. "
    "Every original target and declared calibration choice contributes. Native outcomes, flags, "
    "evidence and analyses remain unchanged, including native adverse verdicts on unselected axes. "
    "Each selected axis requires matched evidence, a measurable denominator, attainable target power "
    "and finite effective MDE no greater than its declared percentage-point ceiling. No pooling, "
    "authenticated labels/assumptions, independence, source/weight authenticity, sensitivity or scientific GO."
)


def validate_requirement(value: float | None) -> float | None:
    """Check range before conversion so arbitrary Python integers cannot overflow."""
    if value is None:
        return None
    if type(value) not in (int, float) or not 0 < value <= 100 or not math.isfinite(value):
        raise SavedScreenError("invalid_conditional_resolution_requirement")
    return float(value)


def validate_axis_requirements(
    values: Mapping[str, float] | None, *, scalar: float | None = None
) -> dict[str, float] | None:
    """Snapshot the original mapping once, with bounded exact-key admission before IO."""
    if values is None:
        return None
    try:
        if scalar is not None or not isinstance(values, Mapping):
            raise SavedScreenError("invalid_conditional_resolution_requirement")
        size = len(values)
        if not 1 <= size <= len(AXES):
            raise SavedScreenError("invalid_conditional_resolution_requirement")
        selected = {}
        for number, axis in enumerate(values):
            if number >= len(AXES) or type(axis) is not str or axis not in AXES or axis in selected:
                raise SavedScreenError("invalid_conditional_resolution_requirement")
            ceiling = validate_requirement(values[axis])
            if ceiling is None:
                raise SavedScreenError("invalid_conditional_resolution_requirement")
            selected[axis] = ceiling
        if len(selected) != size:
            raise SavedScreenError("invalid_conditional_resolution_requirement")
        return {axis: selected[axis] for axis in AXES if axis in selected}
    except SavedScreenError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError, RuntimeError):
        raise SavedScreenError("invalid_conditional_resolution_requirement") from None


def parse_axis_requirement_options(options: list[str]) -> dict[str, float]:
    """Keep duplicate CLI occurrences visible before creating the canonical map."""
    if type(options) is not list or not 1 <= len(options) <= len(AXES):
        raise SavedScreenError("invalid_conditional_resolution_requirement")
    selected = {}
    try:
        for option in options:
            if type(option) is not str or "=" not in option:
                raise SavedScreenError("invalid_conditional_resolution_requirement")
            axis, _, raw = option.partition("=")
            if axis in selected:
                raise SavedScreenError("invalid_conditional_resolution_requirement")
            selected[axis] = float(raw)
    except (ValueError, OverflowError):
        raise SavedScreenError("invalid_conditional_resolution_requirement") from None
    result = validate_axis_requirements(selected)
    assert result is not None
    return result


def _check_axis(
    observed: dict[str, Any] | None, report_present: bool, calibration_present: bool, ceiling: float
) -> dict[str, Any]:
    """Pure criterion shared by legacy single and named-choice receiving modes."""
    reasons = []
    if not report_present:
        reasons.append("report_missing")
    if not calibration_present:
        reasons.append("calibration_missing")
    effective_pp = None
    if observed is not None:
        if observed["measurable"] is not True:
            reasons.append("axis_unmeasurable")
        if observed["detectable_at_target_power"] is not True:
            reasons.append("target_power_unattainable")
        effective = observed["resolution"]["effective_mde"]
        if type(effective) not in (int, float) or not 0 <= effective <= 1 or not math.isfinite(effective):
            reasons.append("resolution_unavailable")
        else:
            effective_pp = effective * 100
            if effective_pp > ceiling:
                reasons.append("resolution_exceeds_requirement")
    elif report_present and calibration_present:
        reasons.append("analysis_unavailable")
    return {
        "requirement_met": not reasons,
        "measurable": observed["measurable"] if observed is not None else None,
        "detectable_at_target_power": observed["detectable_at_target_power"] if observed is not None else None,
        "effective_mde_pp": effective_pp,
        "reasons": reasons,
    }


def qualify_screen(result: dict[str, Any], ceiling: float) -> None:
    """Append criteria using exactly the already-computed, ordered native analyses."""
    native_exit = result["exit_code"]
    rows = []
    all_reasons = []
    if native_exit in (3, 4):
        all_reasons.append("native_flags_detected" if native_exit == 3 else "native_evidence_incomplete")
    for row in result["conditional_resolution"]["rows"]:
        axes = {}
        for name in AXES:
            axes[name] = _check_axis(
                row["analysis"]["axes"][name] if row["analysis"] is not None else None,
                row["native_report_sha256"] is not None,
                row["calibration"]["status"] == "present",
                ceiling,
            )
            all_reasons.extend(axes[name]["reasons"])
        rows.append(
            {
                "name": row["name"],
                "native_report_sha256": row["native_report_sha256"],
                "calibration_sha256": row["calibration"]["sha256"],
                "axes": axes,
                "requirement_met": all(block["requirement_met"] for block in axes.values()),
            }
        )
    code = (
        native_exit if native_exit in (3, 4) else 4 if "calibration_missing" in all_reasons else 5 if all_reasons else 0
    )
    result["conditional_resolution_requirement"] = {
        "screen_resolution_requirement_schema_version": 1,
        "required_conditional_resolution_pp": ceiling,
        "manifest_sha256": result["manifest"]["sha256"],
        "native_exit_code": native_exit,
        "native_outcome": result["outcome"],
        "qualification_exit_code": code,
        "requirement_met": code == 0,
        "rows": rows,
        "reasons": list(dict.fromkeys(all_reasons)),
        "human_labels_authenticated": False,
        "assumptions_verified": False,
        "independent_execution_verified": False,
        "scientific_go": False,
        "scope": SCOPE,
    }
    result["exit_code"] = code


def axis_requirement(
    result: dict[str, Any],
    observed_rows: list[dict[str, Any]],
    ceilings: dict[str, float],
    *,
    variants: bool = False,
) -> dict[str, Any]:
    """Project selected criteria over already-computed original rows, without replay."""
    native_exit = result["exit_code"]
    reasons = []
    if native_exit in (3, 4):
        reasons.append("native_flags_detected" if native_exit == 3 else "native_evidence_incomplete")
    rows = []
    for row in observed_rows:
        checked = {}
        for axis, ceiling in ceilings.items():
            checked[axis] = _check_axis(
                row["analysis"]["axes"][axis] if row["analysis"] is not None else None,
                row["native_report_sha256"] is not None,
                row["calibration"]["status"] == "present",
                ceiling,
            )
            reasons.extend(checked[axis]["reasons"])
        rows.append(
            {
                "name": row["name"],
                **({"variant": row["variant"]} if variants else {}),
                "native_report_sha256": row["native_report_sha256"],
                "calibration_sha256": row["calibration"]["sha256"],
                "axes": checked,
                "requirement_met": all(item["requirement_met"] for item in checked.values()),
            }
        )
    code = native_exit if native_exit in (3, 4) else 4 if "calibration_missing" in reasons else 5 if reasons else 0
    return {
        "calibration_choice_requirement_schema_version"
        if variants
        else "screen_resolution_requirement_schema_version": 2,
        "selected_axes": list(ceilings),
        "required_conditional_resolution_by_axis_pp": dict(ceilings),
        "manifest_sha256": result["manifest"]["sha256"],
        "native_exit_code": native_exit,
        "native_outcome": result["outcome"],
        "qualification_exit_code": code,
        "requirement_met": code == 0,
        "rows": rows,
        "reasons": list(dict.fromkeys(reasons)),
        "human_labels_authenticated": False,
        "assumptions_verified": False,
        "independent_execution_verified": False,
        "scientific_go": False,
        "scope": AXIS_SCOPE,
    }


def qualify_screen_axes(result: dict[str, Any], ceilings: dict[str, float]) -> None:
    """Attach selected requirements to the existing native screen and resolution rows."""
    requirement = axis_requirement(result, result["conditional_resolution"]["rows"], ceilings)
    result["conditional_resolution_requirement"] = requirement
    result["exit_code"] = requirement["qualification_exit_code"]


def append_junit_cases(suite: ET.Element, requirement: dict[str, Any]) -> None:
    """Append requirements after all native cases; missing evidence is a failure here."""
    for row in requirement["rows"]:
        for axis in requirement.get("selected_axes", AXES):
            checked = row["axes"][axis]
            case = ET.SubElement(
                suite,
                "testcase",
                {
                    "classname": "quantfit.screen-summary.conditional-resolution",
                    "name": f"{row['name']}:{axis}:requirement",
                },
            )
            if not checked["requirement_met"]:
                ET.SubElement(
                    case,
                    "failure",
                    {
                        "type": "ConditionalResolutionRequirement",
                        "message": ", ".join(checked["reasons"]),
                    },
                )
    overall = ET.SubElement(
        suite,
        "testcase",
        {
            "classname": "quantfit.screen-summary.conditional-resolution",
            "name": "overall:conditional-resolution-requirement",
        },
    )
    if not requirement["requirement_met"]:
        ET.SubElement(
            overall,
            "failure",
            {
                "type": "ConditionalResolutionRequirement",
                "message": ", ".join(requirement["reasons"]),
            },
        )


def print_requirement(requirement: dict[str, Any]) -> None:
    state = "MET" if requirement["requirement_met"] else "UNMET"
    if "selected_axes" in requirement:
        ceilings = requirement["required_conditional_resolution_by_axis_pp"]
        declared = ", ".join(f"{axis}={ceilings[axis]:g} pp" for axis in requirement["selected_axes"])
        print(f"Conditional-resolution requirements: {declared} — {state}")
    else:
        print(f"Conditional-resolution requirement: {requirement['required_conditional_resolution_pp']:g} pp — {state}")
    print(f"Qualification exit {requirement['qualification_exit_code']}; native exit {requirement['native_exit_code']}")
    for row in requirement["rows"]:
        for axis in requirement.get("selected_axes", AXES):
            if row["axes"][axis]["reasons"]:
                label = row["name"] + (f" {row['variant']}" if "variant" in row else "")
                print(f"{label} {axis}: {', '.join(row['axes'][axis]['reasons'])}")
