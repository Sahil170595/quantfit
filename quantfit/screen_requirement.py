"""Opt-in receiving criteria over existing native conditional resolution; no new math."""

from __future__ import annotations

import math
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


def validate_requirement(value: float | None) -> float | None:
    """Check range before conversion so arbitrary Python integers cannot overflow."""
    if value is None:
        return None
    if type(value) not in (int, float) or not 0 < value <= 100 or not math.isfinite(value):
        raise SavedScreenError("invalid_conditional_resolution_requirement")
    return float(value)


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
            reasons = []
            report_present = row["native_report_sha256"] is not None
            calibration_present = row["calibration"]["status"] == "present"
            if not report_present:
                reasons.append("report_missing")
            if not calibration_present:
                reasons.append("calibration_missing")
            observed = row["analysis"]["axes"][name] if row["analysis"] is not None else None
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
            axes[name] = {
                "requirement_met": not reasons,
                "measurable": observed["measurable"] if observed is not None else None,
                "detectable_at_target_power": observed["detectable_at_target_power"] if observed is not None else None,
                "effective_mde_pp": effective_pp,
                "reasons": reasons,
            }
            all_reasons.extend(reasons)
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


def append_junit_cases(suite: ET.Element, requirement: dict[str, Any]) -> None:
    """Append requirements after all native cases; missing evidence is a failure here."""
    for row in requirement["rows"]:
        for axis in AXES:
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
    print(f"Conditional-resolution requirement: {requirement['required_conditional_resolution_pp']:g} pp — {state}")
    print(f"Qualification exit {requirement['qualification_exit_code']}; native exit {requirement['native_exit_code']}")
    for row in requirement["rows"]:
        for axis in AXES:
            if row["axes"][axis]["reasons"]:
                print(f"{row['name']} {axis}: {', '.join(row['axes'][axis]['reasons'])}")
