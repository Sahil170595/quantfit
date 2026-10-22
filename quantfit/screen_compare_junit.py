"""Defensive, axis-specific XML for descriptive screen comparisons."""

from __future__ import annotations

import math
import re
from typing import Any
from xml.etree import ElementTree as ET

from quantfit.junit import AXIS_OVER_REFUSAL, AXIS_REFUSAL_ROBUSTNESS, _case, _finalise
from quantfit.screen import _SAFE_NAME, CONDITIONALITY_LABEL, RESOLUTION_LABEL, STRATA
from quantfit.screen_bundle_inputs import MAX_TARGETS, MAX_TRANSPORT_BYTES
from quantfit.screen_compare import (
    ARMS,
    AXES,
    IDENTITY_FIELDS,
    SCOPE,
    ScreenComparisonError,
    _axis_decision,
    _exit_code,
    _observation,
    _protocol_match,
    _require,
)

_SHA = re.compile(r"[0-9a-f]{64}")
_SIDES = ("reference", "candidate")


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def _observation_valid(observation: dict[str, Any]) -> None:
    _require(
        type(observation) is dict
        and set(observation)
        == {"present", "measured", "flagged", "flips", "at_risk", "flip_rate_wilson95", "mde_at_80pct_power"}
    )
    _require(type(observation["present"]) is bool and type(observation["measured"]) is bool)
    if not observation["present"]:
        _require(
            observation["measured"] is False
            and all(
                observation[key] is None
                for key in ("flagged", "flips", "at_risk", "flip_rate_wilson95", "mde_at_80pct_power")
            )
        )
        return
    flips, risk = observation["flips"], observation["at_risk"]
    _require(type(flips) is int and type(risk) is int and 0 <= flips <= risk)
    _require(
        type(observation["flagged"]) is bool
        and observation["flagged"] is (flips > 0)
        and observation["measured"] is (risk > 0)
    )
    interval = observation["flip_rate_wilson95"]
    _require(
        type(interval) is list
        and len(interval) == 2
        and all(_number(value) for value in interval)
        and interval[0] <= interval[1]
        and _number(observation["mde_at_80pct_power"])
    )


def _identity_valid(identity: dict[str, Any]) -> None:
    _require(
        type(identity) is dict
        and set(identity) == {"state", "differences", "unavailable_fields", "same_weights_established"}
    )
    _require(
        identity["same_weights_established"] is False
        and type(identity["differences"]) is list
        and len(identity["differences"]) <= 6
    )
    unavailable = identity["unavailable_fields"]
    _require(type(unavailable) is dict and set(unavailable) == set(ARMS))
    for fields in unavailable.values():
        _require(
            type(fields) is list
            and all(type(field) is str and field in IDENTITY_FIELDS for field in fields)
            and len(set(fields)) == len(fields)
        )
    differences = set()
    for difference in identity["differences"]:
        _require(
            type(difference) is dict
            and set(difference) == {"arm", "field"}
            and difference["arm"] in ARMS
            and difference["field"] in IDENTITY_FIELDS
        )
        key = (difference["arm"], difference["field"])
        _require(key not in differences and difference["field"] not in unavailable[difference["arm"]])
        differences.add(key)
    expected = (
        "incompatible" if differences else "unavailable" if any(unavailable.values()) else "compatible_declarations"
    )
    _require(identity["state"] == expected)


def _binding_valid(binding: dict[str, Any], name: str, present: bool) -> None:
    _require(
        type(binding) is dict
        and set(binding) == {"name", "member", "sha256", "size_bytes", "status", "producer_quantfit_version"}
    )
    _require(binding["name"] == name and binding["member"] == f"{name}.json")
    if present:
        _require(
            binding["status"] == "validated"
            and isinstance(binding["sha256"], str)
            and bool(_SHA.fullmatch(binding["sha256"]))
            and type(binding["size_bytes"]) is int
            and binding["size_bytes"] > 0
            and isinstance(binding["producer_quantfit_version"], str)
            and bool(binding["producer_quantfit_version"].strip())
        )
    else:
        _require(
            binding["status"] == "missing_evidence"
            and all(binding[key] is None for key in ("sha256", "size_bytes", "producer_quantfit_version"))
        )


def _screen_valid(screen: dict[str, Any]) -> None:
    flagged = False
    incomplete = False
    for original in screen["rows"]:
        _require(type(original) is dict and original["stratum"] in STRATA)
        if original["status"] == "missing_evidence":
            _require(
                set(original) == {"name", "stratum", "baseline", "quant", "notes", "report", "status", "human_verified"}
                and original["report"] is None
                and original["human_verified"] is None
            )
            incomplete = True
            continue
        observations = {axis: _observation(original, axis) for axis in AXES}
        for observation in observations.values():
            _observation_valid(observation)
        native_flag = any(observation["flagged"] is True for observation in observations.values())
        native_names = {"refusal_robustness": AXIS_REFUSAL_ROBUSTNESS, "over_refusal": AXIS_OVER_REFUSAL}
        unmeasured = [native_names[axis] for axis, observation in observations.items() if not observation["measured"]]
        expected_status = "regression" if native_flag else "unmeasurable" if unmeasured else "no_regression"
        _require(
            original["status"] == expected_status
            and type(original["regression_detected"]) is bool
            and original["regression_detected"] is native_flag
            and original["unmeasurable_axes"] == unmeasured
            and original["human_verified"] is None
        )
        flagged = flagged or native_flag
        incomplete = incomplete or bool(unmeasured)
    _require(type(screen["exit_code"]) is int and screen["exit_code"] == (3 if flagged else 4 if incomplete else 0))
    missing = sum(row["status"] == "missing_evidence" for row in screen["rows"])
    expected_coverage = {
        "n_targets": len(screen["rows"]),
        "n_present": len(screen["rows"]) - missing,
        "n_missing": missing,
    }
    coverage = screen["coverage"]
    _require(type(coverage) is dict and set(coverage) == {*expected_coverage, "complete"})
    _require(all(type(coverage[key]) is int and coverage[key] == value for key, value in expected_coverage.items()))
    _require(coverage["complete"] is (missing == 0))
    _require(type(screen["manifest"]["n_targets"]) is int and screen["manifest"]["n_targets"] == len(screen["rows"]))
    strata = {row["stratum"] for row in screen["rows"]}
    _require(type(screen["by_stratum"]) is dict and set(screen["by_stratum"]) == strata)
    for stratum in strata:
        selected = [row for row in screen["rows"] if row["stratum"] == stratum]
        present = [row for row in selected if row["status"] != "missing_evidence"]
        block = screen["by_stratum"][stratum]
        for key, value in {
            "n_targets": len(selected),
            "n_completed": len(present),
            "n_missing": len(selected) - len(present),
        }.items():
            _require(type(block[key]) is int and block[key] == value)
        for axis in AXES:
            measured = [row for row in present if row[axis]["at_risk"] > 0]
            for key, value in {
                "n_measured": len(measured),
                "n_regressed": sum(row[axis]["flips"] > 0 for row in measured),
                "n_regressed_human_verified": 0,
            }.items():
                _require(type(block[axis][key]) is int and block[axis][key] == value)


def _validate(record: dict[str, Any]) -> None:
    _require(
        type(record) is dict
        and type(record["screen_comparison_schema_version"]) is int
        and record["screen_comparison_schema_version"] == 1
        and record["kind"] == "quantfit.screen-comparison"
    )
    _require(type(record["exit_code"]) is int and record["exit_code"] in (0, 3, 4))
    for key in (
        "same_weights_established",
        "independent_execution_verified",
        "weights_authenticated",
        "physical_hosts_authenticated",
        "human_labels_authenticated",
        "sensitivity_established",
        "scientific_go",
    ):
        _require(record[key] is False)
    rows = record["rows"]
    _require(
        type(rows) is list
        and 0 < len(rows) <= MAX_TARGETS
        and type(record["screens"]) is dict
        and set(record["screens"]) == set(_SIDES)
    )
    screens = record["screens"]
    _require(type(record["inputs"]) is dict and set(record["inputs"]) == set(_SIDES))
    for side in _SIDES:
        screen = screens[side]
        _require(
            type(screen) is dict
            and type(screen["saved_screen_summary_schema_version"]) is int
            and screen["saved_screen_summary_schema_version"] == 1
        )
        _require(
            type(screen["rows"]) is list
            and len(screen["rows"]) == len(rows)
            and type(screen["report_bindings"]) is list
            and len(screen["report_bindings"]) == len(rows)
            and type(screen["protocol_by_stratum"]) is dict
        )
        _screen_valid(screen)
        source = record["inputs"][side]
        _require(
            type(source) is dict and set(source) == {"bundle_manifest_sha256", "targets_sha256", "transport_bytes"}
        )
        _require(
            all(
                isinstance(source[key], str) and bool(_SHA.fullmatch(source[key]))
                for key in ("bundle_manifest_sha256", "targets_sha256")
            )
            and type(source["transport_bytes"]) is int
            and 0 < source["transport_bytes"] <= MAX_TRANSPORT_BYTES
        )
        _require(source["targets_sha256"] == screen["manifest"]["sha256"])
    _require(record["inputs"]["reference"]["targets_sha256"] == record["inputs"]["candidate"]["targets_sha256"])
    seen = set()
    for index, row in enumerate(rows):
        _require(
            type(row) is dict
            and set(row)
            == {"name", "stratum", "bindings", "identical_report_bytes", "protocol_match", "identity", "axes"}
        )
        name, stratum = row["name"], row["stratum"]
        _require(
            isinstance(name, str)
            and bool(_SAFE_NAME.fullmatch(name))
            and name.casefold() not in seen
            and stratum in STRATA
        )
        seen.add(name.casefold())
        _identity_valid(row["identity"])
        _require(
            type(row["bindings"]) is dict
            and set(row["bindings"]) == set(_SIDES)
            and type(row["axes"]) is dict
            and set(row["axes"]) == set(AXES)
        )
        protocol = _protocol_match(screens["reference"], screens["candidate"], stratum)
        _require(row["protocol_match"] is protocol)
        for side in _SIDES:
            original = screens[side]["rows"][index]
            _require(
                original["name"] == name
                and original["stratum"] == stratum
                and original["status"] in ("missing_evidence", "regression", "no_regression", "unmeasurable")
            )
            _binding_valid(row["bindings"][side], name, original["status"] != "missing_evidence")
            _require(row["bindings"][side] == screens[side]["report_bindings"][index])
        both = all(row["bindings"][side]["status"] == "validated" for side in _SIDES)
        identical = row["bindings"]["reference"]["sha256"] == row["bindings"]["candidate"]["sha256"] if both else None
        _require(row["identical_report_bytes"] is identical)
        for axis_name, axis in row["axes"].items():
            _require(
                type(axis) is dict
                and set(axis) == {"reference", "candidate", "status", "transition", "comparison_basis"}
            )
            for side in _SIDES:
                _observation_valid(axis[side])
                original = _observation(screens[side]["rows"][index], axis_name)
                _observation_valid(original)
                _require(axis[side] == original)
            decision = _axis_decision(axis["reference"], axis["candidate"], protocol, row["identity"]["state"])
            _require(all(axis[key] == value for key, value in decision.items()))
    _require(record["exit_code"] == _exit_code(rows))


def screen_comparison_to_junit(record: dict[str, Any]) -> str:
    """Render internally consistent aggregate decisions; no arbitrary input prose is emitted."""
    try:
        _validate(record)
        suite = ET.Element("testsuite")
        for row in record["rows"]:
            for name, axis in row["axes"].items():
                case = _case(suite, f"{row['name']}.{name}", "quantfit.screen-comparison")
                counts = "; ".join(
                    f"{side} {axis[side]['flips']}/{axis[side]['at_risk']} at-risk pairs"
                    if axis[side]["present"]
                    else f"{side} missing evidence"
                    for side in _SIDES
                )
                ET.SubElement(case, "system-out").text = counts
                if any(axis[side]["flagged"] is True for side in _SIDES):
                    ET.SubElement(
                        case,
                        "failure",
                        {
                            "type": "NativeFlagRetained",
                            "message": f"Original native axis flag retained (unconfirmed); {counts}",
                        },
                    )
                elif axis["status"] != "matched":
                    ET.SubElement(case, "skipped", {"message": f"{axis['status']}; {counts}"})
        overall = _case(suite, "overall", "quantfit.screen-comparison")
        if record["exit_code"] == 3:
            ET.SubElement(
                overall,
                "failure",
                {"type": "NativeFlagsRetained", "message": "A native flag on either screen remains adverse evidence"},
            )
        elif record["exit_code"] == 4:
            ET.SubElement(
                overall, "skipped", {"message": "Missing, unmeasured or incompatible evidence; comparison incomplete"}
            )
        ET.SubElement(suite, "system-out").text = f"{SCOPE} {CONDITIONALITY_LABEL}. {RESOLUTION_LABEL}."
        return _finalise(suite, "quantfit.screen-comparison")
    except ScreenComparisonError:
        raise
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise ScreenComparisonError("invalid_screen_comparison") from None
