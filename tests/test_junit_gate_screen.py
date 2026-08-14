"""JUnit for `gate` and `screen` — the two mappings that are not `verify-safety`'s.

Flattening either into the axis-pair shape would lose the thing that makes the command
worth having:

- the **gate** has an outcome `verify-safety` does not: exit 5, "I cannot resolve what you
  asked". That is a refusal, not a failed threshold, and the two are different build
  outcomes that would otherwise share one colour and one message. It also passes on ONE
  axis, so a green gate does not mean the run found nothing — the spec requires an
  implementation to state that rather than let a reader assume it.
- a **screen** runs over a manifest, so the useful unit is the target. One aggregate case
  saying "something regressed somewhere" is not actionable; fifteen cases are.
"""

from xml.etree import ElementTree as ET

import pytest

from quantfit.junit import (
    AXIS_OVER_REFUSAL,
    AXIS_REFUSAL_ROBUSTNESS,
    GATE_SUITE_NAME,
    SCREEN_SUITE_NAME,
    gate_to_junit,
    screen_to_junit,
)


def _cases(xml: str) -> dict[str, ET.Element]:
    return {c.get("name"): c for c in ET.fromstring(xml).iter("testcase")}


def _gate(**overrides) -> dict:
    decision = {
        "exit_code": 0,
        "message": "PASS at the declared threshold",
        "resolution_proven": True,
        "ungated_axis_regressed": False,
    }
    decision.update(overrides)
    return decision


# --------------------------------------------------------------------------------
# gate
# --------------------------------------------------------------------------------


def test_a_clean_gate_fails_nothing():
    xml = gate_to_junit(_gate(), baseline="b", quant="q")
    root = ET.fromstring(xml)
    assert root.find("testsuite").get("name") == GATE_SUITE_NAME
    assert root.find("testsuite").get("failures") == "0"


def test_exit_5_fails_as_a_refusal_not_as_a_breached_threshold():
    """The distinction the gate exists for.

    "You breached the threshold you declared" and "I cannot resolve the threshold you
    declared" are different facts. Both must fail the build, and a reader must be able to
    tell which happened from the report alone.
    """
    xml = gate_to_junit(_gate(exit_code=5, message="threshold finer than the run can resolve"), baseline="b", quant="q")
    cases = _cases(xml)
    resolution = cases["resolution"].find("failure")
    assert resolution is not None
    assert resolution.get("type") == "ThresholdUnresolvable"
    # ...and the threshold itself is NOT reported as breached.
    assert cases[f"{AXIS_REFUSAL_ROBUSTNESS} (gated)"].find("failure") is None


def test_exit_3_fails_the_gated_axis_with_a_different_type():
    xml = gate_to_junit(_gate(exit_code=3), baseline="b", quant="q")
    cases = _cases(xml)
    failure = cases[f"{AXIS_REFUSAL_ROBUSTNESS} (gated)"].find("failure")
    assert failure is not None
    assert failure.get("type") == "ThresholdBreached"
    assert cases["resolution"].find("failure") is None


def test_exit_4_skips_the_gated_axis_rather_than_passing_it():
    xml = gate_to_junit(_gate(exit_code=4), baseline="b", quant="q")
    gated = _cases(xml)[f"{AXIS_REFUSAL_ROBUSTNESS} (gated)"]
    assert gated.find("skipped") is not None
    assert "not measured" in gated.find("skipped").get("message")
    assert gated.find("failure") is None


def test_a_passing_gate_still_surfaces_a_regressed_ungated_axis():
    """The spec's divergence (b), carried into CI.

    The gate gates one axis. A regression on the ungated axis is real, and exit 0 is still
    correct — so this must NOT fail the build, because that would contradict the gate's own
    contract. It must also not vanish into a green tick.
    """
    xml = gate_to_junit(_gate(exit_code=0, ungated_axis_regressed=True), baseline="b", quant="q")
    root = ET.fromstring(xml)
    ungated = _cases(xml)[f"{AXIS_OVER_REFUSAL} (ungated)"]

    assert root.find("testsuite").get("failures") == "0", "a passing gate must not fail the build"
    skipped = ungated.find("skipped")
    assert skipped is not None, "a regressed ungated axis must not render as a plain pass"
    assert "REGRESSED" in skipped.get("message")
    assert "does not mean the run detected nothing" in skipped.get("message")


def test_a_floor_mode_run_says_the_resolution_is_unproven():
    """`resolution_proven: false` is the uncalibrated-judge floor. A green gate under a
    floor is a weaker claim than a green gate under a measured judge error."""
    xml = gate_to_junit(_gate(resolution_proven=False), baseline="b", quant="q")
    skipped = _cases(xml)["resolution"].find("skipped")
    assert skipped is not None
    assert "FLOOR" in skipped.get("message")
    assert "calibrate" in skipped.get("message")


def test_the_gate_report_carries_the_bound():
    xml = gate_to_junit(_gate(), baseline="b", quant="q")
    assert "not a certification" in xml


@pytest.mark.parametrize("code", [0, 3, 4, 5])
def test_every_gate_exit_code_is_explained_in_the_report(code):
    """A reader should not need the spec open to know what the number meant."""
    xml = gate_to_junit(_gate(exit_code=code), baseline="b", quant="q")
    assert f"gate exit {code}" in xml


# --------------------------------------------------------------------------------
# screen
# --------------------------------------------------------------------------------


def _summary(*rows) -> dict:
    return {"rows": list(rows)}


def test_a_screen_reports_one_case_per_target():
    xml = screen_to_junit(
        _summary(
            {"name": "a", "status": "no_regression"},
            {"name": "b", "status": "regression"},
            {"name": "c", "status": "unmeasurable"},
        )
    )
    cases = _cases(xml)
    assert set(cases) == {"a", "b", "c"}
    assert ET.fromstring(xml).find("testsuite").get("name") == SCREEN_SUITE_NAME


def test_a_flagged_target_fails_and_says_it_is_a_candidate():
    """Screen flips are candidates until human-verified — the report must not overclaim."""
    xml = screen_to_junit(_summary({"name": "b", "status": "regression"}))
    failure = _cases(xml)["b"].find("failure")
    assert failure is not None
    assert "candidate until human-verified" in failure.get("message")


def test_an_operational_error_is_an_error_not_a_failure():
    """A target that failed to run produced no verdict.

    Reporting that as a failed test would report a missing measurement as a detected
    regression — the same conflation the 0/2/3/4 exit-code split exists to prevent.
    """
    xml = screen_to_junit(_summary({"name": "c", "status": "operational_error", "notes": "OOM"}))
    case = _cases(xml)["c"]
    assert case.find("error") is not None
    assert case.find("failure") is None
    assert "OOM" in case.find("error").get("message")
    assert ET.fromstring(xml).find("testsuite").get("errors") == "1"


def test_an_unmeasurable_target_is_skipped():
    xml = screen_to_junit(_summary({"name": "d", "status": "unmeasurable"}))
    skipped = _cases(xml)["d"].find("skipped")
    assert skipped is not None
    assert "not measured" in skipped.get("message")


def test_counts_are_derived_from_the_tree_and_cannot_disagree():
    xml = screen_to_junit(
        _summary(
            {"name": "a", "status": "no_regression"},
            {"name": "b", "status": "regression"},
            {"name": "c", "status": "operational_error"},
            {"name": "d", "status": "unmeasurable"},
        )
    )
    suite = ET.fromstring(xml).find("testsuite")
    cases = list(suite.iter("testcase"))
    assert suite.get("tests") == str(len(cases)) == "4"
    assert suite.get("failures") == "1"
    assert suite.get("skipped") == "1"
    assert suite.get("errors") == "1"


def test_a_target_without_a_name_still_gets_one():
    xml = screen_to_junit(_summary({"baseline": "org/base", "quant": "org/q4", "status": "no_regression"}))
    assert "org/base->org/q4" in _cases(xml)


def test_an_empty_screen_produces_a_valid_empty_suite():
    """A manifest that matched nothing must not produce malformed XML."""
    suite = ET.fromstring(screen_to_junit(_summary())).find("testsuite")
    assert suite.get("tests") == "0"
    assert suite.get("failures") == "0"
