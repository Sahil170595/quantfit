"""Ten native reproduction cases, with bounded aggregate-only XML messages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from xml.etree import ElementTree as ET

from quantfit.junit import _case, _render
from quantfit.reproduce import OUTCOME_EXIT_CODES, OUTCOME_REPRODUCED, OUTCOME_VOID, _decide

SUITE_NAME = "quantfit.reproduce"
_CHECKS = ("T1_same_measurement", "T2_verdict_class", "T3_denominators", "T4_flip_counts", "T5_refusal_totals")


class ReproductionJUnitError(RuntimeError):
    """A malformed or contradictory decision cannot advertise a native XML result."""


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ReproductionJUnitError("Malformed native reproduction decision")
    return cast(Mapping[str, object], value)


def _state(block: Mapping[str, object], *, unknown: bool = False) -> bool | None:
    value = block.get("pass")
    if isinstance(value, bool) or (value is None and unknown and "pass" in block):
        return value
    raise ReproductionJUnitError("Malformed native reproduction decision")


def _checked_block(value: object) -> dict[str, object]:
    block = dict(_mapping(value))
    state = _state(block)
    predicates = block.get("predicates")
    if not isinstance(predicates, list) or not predicates:
        raise ReproductionJUnitError("Malformed native reproduction decision")
    observed = [_state(_mapping(predicate)) for predicate in predicates]
    if state is not all(observed):
        raise ReproductionJUnitError("Contradictory native reproduction decision")
    return block


def _finalise(suite: ET.Element) -> str:
    cases = list(suite.iter("testcase"))
    counts = {
        "tests": str(len(cases)),
        **{
            name: str(sum(case.find(tag) is not None for case in cases))
            for name, tag in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped"))
        },
    }
    suite.attrib.update(counts)
    suites = ET.Element("testsuites", counts)
    suites.append(suite)
    return _render(suites)


def _result_case(suite: ET.Element, name: str, state: bool | None, reason: str = "not established") -> None:
    case = _case(suite, name, SUITE_NAME)
    if state is None:
        ET.SubElement(case, "skipped", {"message": f"{name}: {reason}"})
    elif state is False:
        ET.SubElement(case, "failure", {"type": "ReproductionCheckFailed", "message": f"{name}: native check failed"})


def reproduction_to_junit(decision: Mapping[str, object]) -> str:
    """Render a consistent native decision without mutating it or exposing its prose/paths.

    Unknown per-side T0 is skipped; known negatives fail. Overall fails for every
    native nonpass, including void and unverified outcomes. This renders protocol
    results, not authenticated execution, sensitivity, human truth or scientific GO.
    """
    try:
        preconditions = _mapping(decision.get("preconditions"))
        t0 = _mapping(preconditions.get("T0_within_hardware_byte_identity"))
        sides = [_mapping(t0.get(side)) for side in ("reference", "candidate")]
        states = [_state(side, unknown=True) for side in sides]
        for side, state in zip(sides, states, strict=True):
            if not isinstance(side.get("supplied"), bool):
                raise ReproductionJUnitError("Malformed native reproduction decision")
            if state is not None and side["supplied"] is not True:
                raise ReproductionJUnitError("Contradictory native reproduction decision")
            if state is True and any(
                side.get(key) is not True
                for key in (
                    "supplied",
                    "meets_protocol_replicate_count",
                    "comparison_report_is_member",
                    "bound_to_comparison_report",
                )
            ):
                raise ReproductionJUnitError("Contradictory native reproduction decision")
        supplied_by_side = _mapping(t0.get("supplied_by_side"))
        if set(supplied_by_side) != {"reference", "candidate"} or any(
            not isinstance(supplied_by_side.get(name), bool) or supplied_by_side[name] is not side["supplied"]
            for name, side in zip(("reference", "candidate"), sides, strict=True)
        ):
            raise ReproductionJUnitError("Contradictory native reproduction decision")
        if not isinstance(t0.get("supplied"), bool) or t0["supplied"] is not all(side["supplied"] for side in sides):
            raise ReproductionJUnitError("Contradictory native reproduction decision")
        combined = False if False in states else None if None in states else True
        if _state(t0, unknown=True) is not combined:
            raise ReproductionJUnitError("Contradictory native reproduction decision")
        p0 = _checked_block(preconditions.get("P0_gated_axis_measured"))
        p1 = _checked_block(preconditions.get("P1_distinct_reports"))
        checks = _mapping(decision.get("checks"))
        blocks = [_checked_block(checks.get(name)) for name in _CHECKS]
        expected, reasons = _decide(blocks[0], blocks[1], blocks[2], blocks[3], blocks[4], p0, p1, combined)
        outcome, code = decision.get("outcome"), decision.get("exit_code")
        passed = None if expected == OUTCOME_VOID else expected == OUTCOME_REPRODUCED
        if (
            outcome != expected
            or type(code) is not int
            or code != OUTCOME_EXIT_CODES[expected]
            or decision.get("passed") is not passed
            or decision.get("void_reasons") != reasons
        ):
            raise ReproductionJUnitError("Contradictory native reproduction decision")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ReproductionJUnitError("Malformed native reproduction decision") from exc

    suite = ET.Element("testsuite", {"name": SUITE_NAME})
    for name, side, state in zip(("reference-t0", "candidate-t0"), sides, states, strict=True):
        reason = (
            "not supplied"
            if side["supplied"] is False
            else "below the protocol replicate count"
            if side.get("sub_protocol_replicate_count") is True
            else "positive evidence unverified"
        )
        _result_case(suite, name, state, reason)
    for name, block in zip(("P0", "P1", "T1", "T2", "T3", "T4", "T5"), (p0, p1, *blocks), strict=True):
        _result_case(suite, name, _state(block))
    _result_case(suite, "overall", expected == OUTCOME_REPRODUCED)
    ET.SubElement(suite, "system-out").text = (
        "Native saved-aggregate reproduction checks only. Unknown prerequisites are not passes. "
        "Agreement does not authenticate independent execution, physical hosts, human labels, sensitivity or scientific GO."
    )
    return _finalise(suite)


def _operational_error_to_junit() -> str:
    """One generic error, without inventing a decision or serializing exception diagnostics."""
    suite = ET.Element("testsuite", {"name": SUITE_NAME})
    case = _case(suite, "operational-error", SUITE_NAME)
    ET.SubElement(
        case, "error", {"type": "OperationalError", "message": "Reproduction could not be evaluated or published"}
    )
    return _finalise(suite)
