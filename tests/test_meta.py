"""Release hygiene: version parity + terminology purge (the 0.3 gate, as tests).

0.1.0 shipped to PyPI with `__init__.__version__` trailing pyproject (0.1.0 vs
0.2.0) — a skew nothing caught. These tests make both halves of that failure
impossible to repeat silently.
"""

import re
from pathlib import Path

import quantfit

_ROOT = Path(__file__).resolve().parent.parent


def test_version_matches_pyproject():
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', pyproject, flags=re.MULTILINE)
    assert match, "pyproject.toml has no version line"
    assert quantfit.__version__ == match.group(1)


def test_no_safety_tax_on_shipped_surfaces():
    # "safety tax" collides with the literature's alignment-tax usage (capability
    # paid FOR safety) — quantfit measures the opposite and says "safety drift".
    # Shipped surfaces = code, README, package metadata. CHANGELOG is history and
    # exempt; ROADMAP discusses the rename and is exempt.
    surfaces = [_ROOT / "README.md", _ROOT / "pyproject.toml", *sorted((_ROOT / "quantfit").rglob("*.py"))]
    pattern = re.compile(r"safety[ -]?tax", flags=re.IGNORECASE)
    offenders = [str(f) for f in surfaces if pattern.search(f.read_text(encoding="utf-8"))]
    assert not offenders, f"'safety tax' still on shipped surfaces: {offenders}"


def test_the_readme_sample_output_is_what_the_code_prints():
    """The README's `verify-safety` sample is transcribed output, and it went stale.

    0.12.8 appended ", perfect-judge floor" to `_axis_stats`' zero-flip branch and
    deleted the claim that a no-detection result "bounds the drift" from JUnit and the
    model card. The README kept the pre-0.12.8 text on both counts for three releases,
    on the page a first-time reader sees before anything else.

    Transcription is the defect, so the fix is to stop transcribing: the sample is
    reproduced here from the same `SafetyDrift.summary()` that produced it, and its
    inputs are the numbers the README block states, so a reviewer can read them off the
    page.
    """
    from quantfit.safety.verify import SafetyDrift

    summary = SafetyDrift(
        n=40,
        unsafe_n=12,
        unsafe_baseline_refused=12,
        unsafe_quant_refused=12,
        harmful_compliance_regressions=0,
        safe_n=28,
        safe_baseline_refused=18,
        safe_quant_refused=18,
        overrefusal_regressions=2,
        by_zone={
            "borderline": {"n": 16, "baseline_refused": 10, "quant_refused": 10},
            "clear_safe": {"n": 12, "baseline_refused": 8, "quant_refused": 8},
            "clear_unsafe": {"n": 12, "baseline_refused": 12, "quant_refused": 12},
        },
    ).summary()

    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    assert summary in readme, (
        "the README's verify-safety sample is not what SafetyDrift.summary() prints. "
        "Regenerate it rather than editing it by hand:" + chr(10) + summary
    )


def test_no_shipped_surface_says_a_pass_bounds_the_drift():
    """The sentence 0.12.8 removed from JUnit and the model card, and left in the
    terminal.

    `verify-safety`'s human-readable note said "a no-detection result bounds the drift,
    it does not certify safety" - asserting a bound in the same breath as disclaiming
    one, on the surface a user reads FIRST. CHANGELOG 0.12.8 fixed the card's clean
    branch and both JUnit suites on exactly this wording and did not check stdout.
    """
    surfaces = [
        _ROOT / "README.md",
        *sorted((_ROOT / "quantfit").rglob("*.py")),
    ]
    pattern = re.compile(r"bounds the drift", flags=re.IGNORECASE)
    offenders = [str(f) for f in surfaces if pattern.search(f.read_text(encoding="utf-8"))]
    assert not offenders, f"'bounds the drift' still on shipped surfaces: {offenders}"


def test_the_no_go_leg_names_the_axis_it_is_about():
    """The pre-registered NO-GO rule is conjunctive, and one of its three legs was
    ambiguous in a way that would have decided the milestone.

    It read "no hand-verified regression found", naming no axis, while the screen has
    produced six hand-verified regressions - all on the OVER-REFUSAL axis
    (validation/2026-08-19-screen-adjudication/). Read unqualified, that leg fails and the
    whole NO-GO can never fire. Read as the dangerous axis - which is what the text
    intends, because the next sentence conditions the leg on a dangerous-axis sensitivity
    control - it holds.

    The qualifier is the difference between a decision rule and a rule that cannot fire,
    so it is pinned. Dropping it later would re-open the ambiguity silently, and the whole
    value of a pre-registration is that its amendments are visible and dated.
    """
    roadmap = (_ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    assert "no hand-verified **dangerous-axis** regression found" in roadmap, (
        "the NO-GO leg must name the axis it is about"
    )

    lines = roadmap.splitlines()
    for i, line in enumerate(lines):
        if "no hand-verified regression found" not in line:
            continue
        window = " ".join(lines[max(0, i - 4) : i + 5]).lower()
        assert "dated defect" in window, f"ROADMAP.md:{i + 1} uses the unqualified NO-GO leg outside a dated correction"
