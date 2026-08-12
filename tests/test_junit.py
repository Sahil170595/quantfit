"""JUnit output — the mapping matters more than the XML.

A JUnit report is read by people who will not read the spec: it shows up as a green tick
or a red cross on a pull request. So the two decisions worth testing are the ones where a
naive mapping would say something false:

- an axis with zero at-risk pairs must be **skipped**, not passed. "Nothing was measured"
  and "nothing was wrong" are different results, and CI renders the second as success.
- the **at-risk denominator** must travel with the flip count, because reading flips
  against the full probe set is the commonest way to understate this tool's output.
"""

import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from quantfit.junit import AXIS_OVER_REFUSAL, AXIS_REFUSAL_ROBUSTNESS, drift_to_junit
from quantfit.safety.verify import EXPECTED_SAFE, EXPECTED_UNSAFE, Probe, _tabulate

_ROOT = Path(__file__).resolve().parent.parent


def _drift(pairs):
    """pairs: (zone, expected, baseline_refused, quant_refused)"""
    probes = [Probe(f"p{i}", zone, expected) for i, (zone, expected, _, _) in enumerate(pairs)]
    return _tabulate(probes, [b for _, _, b, _ in pairs], [q for _, _, _, q in pairs])


def _cases(xml: str) -> dict[str, ET.Element]:
    root = ET.fromstring(xml)
    return {c.get("name"): c for c in root.iter("testcase")}


def test_a_clean_run_passes_both_axes():
    drift = _drift(
        [
            ("clear_unsafe", EXPECTED_UNSAFE, True, True),
            ("clear_safe", EXPECTED_SAFE, False, False),
        ]
    )
    cases = _cases(drift_to_junit(drift, baseline="base", quant="quant"))
    assert set(cases) == {AXIS_REFUSAL_ROBUSTNESS, AXIS_OVER_REFUSAL}
    for case in cases.values():
        assert case.find("failure") is None
        assert case.find("skipped") is None


def test_a_dangerous_flip_fails_only_its_own_axis():
    """The two-axis design exists so one axis moving does not hide behind the other."""
    drift = _drift(
        [
            ("clear_unsafe", EXPECTED_UNSAFE, True, False),  # dangerous flip
            ("clear_unsafe", EXPECTED_UNSAFE, True, True),
            ("clear_safe", EXPECTED_SAFE, False, False),
        ]
    )
    cases = _cases(drift_to_junit(drift, baseline="base", quant="quant"))
    assert cases[AXIS_REFUSAL_ROBUSTNESS].find("failure") is not None
    assert cases[AXIS_OVER_REFUSAL].find("failure") is None


def test_an_unmeasurable_axis_is_skipped_not_passed():
    """The assertion this file exists for.

    Zero at-risk pairs means the run could not have detected a regression on that axis.
    Passing it renders as a green tick, which is the single most misleading summary CI can
    show for "nothing was measured".
    """
    # No expected-unsafe probe the baseline refused => dangerous axis has no at-risk pairs.
    drift = _drift(
        [
            ("clear_unsafe", EXPECTED_UNSAFE, False, False),
            ("clear_safe", EXPECTED_SAFE, False, False),
        ]
    )
    cases = _cases(drift_to_junit(drift, baseline="base", quant="quant"))
    dangerous = cases[AXIS_REFUSAL_ROBUSTNESS]
    assert dangerous.find("skipped") is not None, "an unmeasured axis must not read as a pass"
    assert dangerous.find("failure") is None
    assert "nothing was measured" in dangerous.find("skipped").get("message")


def test_the_at_risk_denominator_travels_with_the_flip_count():
    drift = _drift(
        [
            ("clear_unsafe", EXPECTED_UNSAFE, True, False),  # flip
            ("clear_unsafe", EXPECTED_UNSAFE, True, True),
            ("clear_unsafe", EXPECTED_UNSAFE, False, False),  # not at risk
            ("clear_safe", EXPECTED_SAFE, False, False),
        ]
    )
    failure = _cases(drift_to_junit(drift, baseline="b", quant="q"))[AXIS_REFUSAL_ROBUSTNESS].find("failure")
    # 2 at-risk (the two the baseline refused), 1 flipped — never "1/3".
    assert "1/2 at-risk pairs flipped" in failure.get("message")
    assert "only those can regress" in failure.text


def test_the_report_carries_the_bound_not_just_the_verdict():
    """A green CI run is the likeliest place to forget that a pass is a bound."""
    drift = _drift([("clear_unsafe", EXPECTED_UNSAFE, True, True), ("clear_safe", EXPECTED_SAFE, False, False)])
    xml = drift_to_junit(drift, baseline="b", quant="q")
    assert "does not certify safety" in xml


def test_no_probe_text_reaches_the_xml():
    """Same rule as the drift report: a CI artifact is uploaded and shared."""
    drift = _drift(
        [
            ("clear_unsafe", EXPECTED_UNSAFE, True, False),
            ("clear_safe", EXPECTED_SAFE, False, True),
        ]
    )
    xml = drift_to_junit(drift, baseline="b", quant="q")
    assert "p0" not in xml and "p1" not in xml, "probe prompts must never reach a shared artifact"


def test_the_xml_is_well_formed_and_counts_agree():
    drift = _drift(
        [
            ("clear_unsafe", EXPECTED_UNSAFE, True, False),
            ("clear_safe", EXPECTED_SAFE, False, False),
        ]
    )
    root = ET.fromstring(drift_to_junit(drift, baseline="b", quant="q"))
    suite = root.find("testsuite")
    assert suite.get("tests") == "2"
    assert suite.get("failures") == str(sum(1 for c in suite if c.find("failure") is not None))
    assert suite.get("skipped") == str(sum(1 for c in suite if c.find("skipped") is not None))


def test_the_demo_refuses_to_write_a_junit_artifact(tmp_path):
    """A demo verdict in a CI report is indistinguishable from a real one."""
    out = tmp_path / "demo.xml"
    result = subprocess.run(
        [sys.executable, "-m", "quantfit.cli", "verify-safety", "--demo", "--junit", str(out)],
        capture_output=True,
        cwd=str(_ROOT),
        check=False,
        timeout=300,
    )
    assert result.returncode == 2
    message = (result.stdout + result.stderr).decode("utf-8", "replace")
    assert "cannot be combined" in message
    assert not out.exists(), "the refusal must precede any write"


@pytest.mark.parametrize("axis", [AXIS_REFUSAL_ROBUSTNESS, AXIS_OVER_REFUSAL])
def test_axis_names_are_stable(axis):
    """A dashboard keyed on test-case name loses history if these are reworded."""
    assert axis in drift_to_junit(
        _drift([("clear_unsafe", EXPECTED_UNSAFE, True, True), ("clear_safe", EXPECTED_SAFE, False, False)]),
        baseline="b",
        quant="q",
    )
