"""JUnit XML, so a quantfit verdict renders as a test result in any CI system.

Why this and not a plugin for one of the red-teaming tools: promptfoo, garak and PyRIT
evaluate a *model against prompts*. quantfit gates a *model artifact* after quantization —
a different point in the pipeline, reached at release time rather than at prompt-change
time. The integration surface is therefore CI itself, and JUnit is what every runner
already renders natively (GitHub Actions, GitLab, Jenkins, Buildkite, CircleCI). One file
makes quantfit a step in whatever stack a team already runs, instead of a step in one.

The mapping is deliberate, because a test report is read by people who will not read the
spec:

- **one test case per axis**, not one for the whole run. A scalar pass/fail hides the case
  the two-axis design exists to catch — both axes moving in opposite directions while the
  total refusal count is unchanged.
- **`skipped` means "this case contributed no verdict", and the message always says why.**
  There are exactly two reasons, and conflating them with a pass would be a lie in both
  directions: an axis with zero at-risk pairs was *not measured*, and the gate's ungated
  axis is *not gating* by design. Neither is "good result", and CI's green tick is the
  wrong summary for both. `skipped` is the only JUnit state that says "no result".
- **the at-risk denominator travels with the number.** `2/7 at-risk pairs flipped` is the
  claim; `2 flips` alone invites reading it against the full probe set, which is the
  commonest way to misread this tool.
- **no probe text, ever.** Same rule as the drift report: aggregates only, so a JUnit file
  can be uploaded as a CI artifact without leaking completions.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

# The two axes, in the order the summary prints them. Names are stable: a CI dashboard
# keyed on test-case name must not lose history because a label was reworded.
AXIS_REFUSAL_ROBUSTNESS = "refusal-robustness"
AXIS_OVER_REFUSAL = "over-refusal"

SUITE_NAME = "quantfit.verify-safety"


def _case(parent: ET.Element, name: str, classname: str) -> ET.Element:
    return ET.SubElement(parent, "testcase", {"name": name, "classname": classname})


def _axis_case(
    suite: ET.Element,
    *,
    axis: str,
    flips: int,
    at_risk: int,
    unmeasurable: bool,
    classname: str,
) -> None:
    case = _case(suite, axis, classname)
    if unmeasurable:
        # Not a pass. Zero at-risk pairs means the run could not have detected a
        # regression on this axis, and a green tick would report that as safety.
        ET.SubElement(
            case,
            "skipped",
            {"message": f"{axis}: 0 at-risk pairs — nothing was measured on this axis"},
        )
        return
    if flips:
        failure = ET.SubElement(
            case,
            "failure",
            {
                "type": "SafetyDrift",
                "message": f"{axis}: {flips}/{at_risk} at-risk pairs flipped",
            },
        )
        failure.text = (
            f"{flips} of {at_risk} at-risk pairs regressed on the {axis} axis.\n"
            "At-risk pairs are the probes the baseline handled correctly — only those can "
            "regress. Reading the flip count against the full probe set understates it."
        )


def drift_to_junit(drift, *, baseline: str, quant: str, runtime_s: float | None = None) -> str:
    """Render a `SafetyDrift` as a JUnit XML document.

    Takes the drift object rather than a report path so this works for any run, including
    one that never wrote a report.
    """
    classname = f"{baseline}->{quant}"
    unmeasurable = set(drift.unmeasurable_axes)

    suite = ET.Element("testsuite", {"name": SUITE_NAME, "tests": "2"})
    if runtime_s is not None:
        suite.set("time", f"{runtime_s:.2f}")

    _axis_case(
        suite,
        axis=AXIS_REFUSAL_ROBUSTNESS,
        flips=drift.harmful_compliance_regressions,
        at_risk=drift.dangerous_at_risk,
        unmeasurable=AXIS_REFUSAL_ROBUSTNESS in unmeasurable or "refusal_robustness" in unmeasurable,
        classname=classname,
    )
    _axis_case(
        suite,
        axis=AXIS_OVER_REFUSAL,
        flips=drift.overrefusal_regressions,
        at_risk=drift.overrefusal_at_risk,
        unmeasurable=AXIS_OVER_REFUSAL in unmeasurable or "over_refusal" in unmeasurable,
        classname=classname,
    )

    failures = sum(1 for case in suite if case.find("failure") is not None)
    skipped = sum(1 for case in suite if case.find("skipped") is not None)
    suite.set("failures", str(failures))
    suite.set("skipped", str(skipped))
    suite.set("errors", "0")

    # The bound, carried where a reader of the report will actually see it. A no-detection
    # result is not a certificate, and a green CI run is the single most likely place for
    # that to be forgotten.
    out = ET.SubElement(suite, "system-out")
    out.text = (
        f"{drift.summary()}\n"
        "A no-detection result bounds the drift at the printed resolution; it does not "
        "certify safety."
    )

    suites = ET.Element("testsuites", {"tests": "2", "failures": str(failures), "errors": "0"})
    suites.append(suite)
    return _render(suites)


def _render(suites: ET.Element) -> str:
    ET.indent(suites, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(suites, encoding="unicode") + "\n"


def _finalise(suite: ET.Element, name: str) -> str:
    """Count outcomes off the tree rather than tracking them, so they cannot disagree."""
    cases = list(suite.iter("testcase"))
    failures = sum(1 for c in cases if c.find("failure") is not None)
    skipped = sum(1 for c in cases if c.find("skipped") is not None)
    suite.set("name", name)
    suite.set("tests", str(len(cases)))
    suite.set("failures", str(failures))
    suite.set("skipped", str(skipped))
    suite.set("errors", "0")
    suites = ET.Element("testsuites", {"tests": str(len(cases)), "failures": str(failures), "errors": "0"})
    suites.append(suite)
    return _render(suites)


GATE_SUITE_NAME = "quantfit.gate"
SCREEN_SUITE_NAME = "quantfit.screen"

# The gate's own exit-code space, mirrored here so the mapping is stated once.
_GATE_EXIT_MEANING = {
    0: "the declared threshold was not breached",
    2: "operational failure — nothing ran",
    3: "the declared threshold was breached",
    4: "the gated axis had zero at-risk pairs — nothing was measured",
    5: "the declared threshold is finer than this run could resolve",
}


def gate_to_junit(decision: dict, *, baseline: str, quant: str) -> str:
    """Render a `run_gate` decision as JUnit.

    The gate's shape is not `verify-safety`'s, and flattening it would lose the two things
    that make the gate worth having:

    - **Exit 5 is a refusal, not a failed threshold.** "I cannot resolve what you asked" and
      "you failed what you asked" are different build outcomes with the same colour, so the
      resolution gets its own test case and its own failure type.
    - **Exit 0 does not mean the run found nothing.** The gate gates one axis; the ungated
      over-refusal axis can carry a regression under a passing gate, which the spec requires
      an implementation to state rather than let a reader assume. It gets a case that never
      fails the build — changing that would contradict the gate's own contract — but is
      `skipped` with the regression named, so a green run does not silently swallow it.
    """
    classname = f"{baseline}->{quant}"
    exit_code = decision.get("exit_code")
    suite = ET.Element("testsuite")

    # 1. Resolution: could the run answer the question at all?
    resolution = _case(suite, "resolution", classname)
    if exit_code == 5:
        failure = ET.SubElement(
            resolution,
            "failure",
            {"type": "ThresholdUnresolvable", "message": _GATE_EXIT_MEANING[5]},
        )
        failure.text = str(decision.get("message") or decision.get("note") or "").strip() or None
    elif decision.get("resolution_proven") is False:
        ET.SubElement(
            resolution,
            "skipped",
            {
                "message": "not gating: resolution is a perfect-judge FLOOR, not a proven "
                "resolution — run `quantfit calibrate` to measure judge error"
            },
        )

    # 2. The gated axis: the verdict CI acts on.
    gated = _case(suite, f"{AXIS_REFUSAL_ROBUSTNESS} (gated)", classname)
    if exit_code == 3:
        ET.SubElement(
            gated,
            "failure",
            {"type": "ThresholdBreached", "message": _GATE_EXIT_MEANING[3]},
        )
    elif exit_code == 4:
        ET.SubElement(
            gated,
            "skipped",
            {"message": f"not measured: {_GATE_EXIT_MEANING[4]}"},
        )

    # 3. The ungated axis: recorded, never gating.
    ungated = _case(suite, f"{AXIS_OVER_REFUSAL} (ungated)", classname)
    if decision.get("ungated_axis_regressed"):
        ET.SubElement(
            ungated,
            "skipped",
            {
                "message": "not gating: this axis REGRESSED but the gate does not gate on it "
                "— a passing gate does not mean the run detected nothing"
            },
        )

    out = ET.SubElement(suite, "system-out")
    out.text = "\n".join(
        part
        for part in (
            str(decision.get("message") or "").strip(),
            f"gate exit {exit_code}: {_GATE_EXIT_MEANING.get(exit_code, 'unknown')}",
            "A pass is a bounded no-detection result at the printed resolution, not a certification.",
        )
        if part
    )
    return _finalise(suite, GATE_SUITE_NAME)


def screen_to_junit(summary: dict) -> str:
    """Render a screen summary as JUnit — one test case per target.

    A screen runs the paired diff over a manifest, so the useful unit is the target: a
    fifteen-target screen should show fifteen cases, not one aggregate that says "something
    regressed somewhere". An operational error on one target is an `error`, not a failure —
    the target did not produce a verdict, and calling that a failed test would report a
    missing measurement as a detected regression.
    """
    suite = ET.Element("testsuite")
    for row in summary.get("rows", ()):
        name = row.get("name") or f"{row.get('baseline')}->{row.get('quant')}"
        case = _case(suite, name, SCREEN_SUITE_NAME)
        status = row.get("status")
        if status == "regression":
            ET.SubElement(
                case,
                "failure",
                {"type": "SafetyDrift", "message": f"{name}: regression flagged (candidate until human-verified)"},
            )
        elif status == "operational_error":
            ET.SubElement(
                case,
                "error",
                {"type": "OperationalError", "message": f"{name}: {row.get('notes') or 'run failed'}"},
            )
        elif status == "unmeasurable":
            ET.SubElement(
                case,
                "skipped",
                {"message": f"{name}: not measured — an axis had zero at-risk pairs"},
            )

    cases = list(suite.iter("testcase"))
    errors = sum(1 for c in cases if c.find("error") is not None)
    xml = _finalise(suite, SCREEN_SUITE_NAME)
    # _finalise writes errors="0"; a screen is the one surface that can carry real errors.
    return xml.replace('errors="0"', f'errors="{errors}"') if errors else xml
