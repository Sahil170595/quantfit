"""The repo must not claim that no epsilon has been measured for this instrument.

One was, on 2026-08-18: `validation/2026-08-18-judge-calibration/`, n = 80 hand-labelled
completions from a real paired run, single-rater. `verify.JUDGE_MEASURED_*` carries it.

From that date until 2026-08-28 the repo asserted the opposite in eleven places, several
of which are serialized verbatim into gate artifacts and comparison records — so two
machine-readable artifacts a consumer could hold side by side stated opposite facts about
the same instrument. `quantfit audit` did not catch it: nothing pinned the prose against
the constant that refutes it.

These tests are that pin. They are deliberately source-level rather than behavioural,
because the defect was in published *strings*, and a string is exactly what no other check
in this repo looks at.
"""

from __future__ import annotations

import pathlib

from quantfit.safety.mde import effective_mde, false_flip_rate_bound
from quantfit.safety.verify import (
    JUDGE_MEASURED_FALSE_NEGATIVE_RATE,
    JUDGE_MEASURED_FALSE_POSITIVE_RATE,
    JUDGE_MEASURED_N,
    wilson_interval,
)

_SRC = pathlib.Path(__file__).resolve().parent.parent / "quantfit"

# Phrasings that assert no epsilon EXISTS. The true statement is that none is folded
# into a printed MDE, which is a claim about the pipeline, not about the judge.
_FALSE_CLAIMS = (
    "no judge error has been measured",
    "no in-distribution judge error has been measured",
    "no in-distribution judge error exists",
    "no epsilon has been measured for this instrument",
    "judge error is unmeasured",
    "the number nobody has measured",
)


def _sources():
    """Whitespace-collapsed, because every one of these claims lives in wrapped prose.

        A literal substring check misses them: `mde.py` had "No epsilon
    has been measured
        for this instrument" split across a line break, and a naive scan reported it clean.
    """
    for path in sorted(_SRC.rglob("*.py")):
        yield path, " ".join(path.read_text(encoding="utf-8").split()).lower()


def test_no_module_claims_the_instrument_has_no_measured_epsilon():
    offenders = [
        f"{path.relative_to(_SRC.parent)}: {claim!r}"
        for path, text in _sources()
        for claim in _FALSE_CLAIMS
        if claim in text
    ]
    assert not offenders, "these assert no epsilon exists; one was measured 2026-08-18:\n" + "\n".join(offenders)


def test_the_measured_epsilon_is_still_there_to_be_claimed():
    """The guard above is only meaningful while the constants it defends exist."""
    assert JUDGE_MEASURED_N == 80
    assert JUDGE_MEASURED_FALSE_POSITIVE_RATE == 0.083
    assert JUDGE_MEASURED_FALSE_NEGATIVE_RATE == 0.0


def test_the_amount_the_floor_is_off_by_is_derivable_and_total():
    """The published strings say "1.0 for every n <= 34". That number is checked here.

    It is the whole reason the old "coarser by an unknown amount" wording was a defect:
    the amount is not unknown, and it is not small. It is everything.
    """
    eps = wilson_interval(4, 48)[1]  # 4 false positives in 48 compliant completions
    bound = false_flip_rate_bound(eps, eps)
    assert bound == pytest_approx(0.3910660358073456)

    assert all(effective_mde(n, bound) == 1.0 for n in range(1, 35)), "1.0 must hold for every n <= 34"
    assert effective_mde(35, bound) < 1.0, "35 is the first n that resolves anything at all"


def pytest_approx(value, rel=1e-9):
    from pytest import approx

    return approx(value, rel=rel)


# --- prose ------------------------------------------------------------------------
#
# The same claim lived in eight docs, and none of the checks in this repo look at prose.
# `quantfit audit` reads doc *citations* -- it verifies that quoted code is where a doc
# says it is -- so it happily passed a doc asserting the opposite of a constant.
#
# Occurrences are allowed where the doc is CORRECTING itself: the repo's rule is that an
# amendment must be visible, so a dated-defect note that quotes the old false claim is the
# desired state, not a violation. `CHANGELOG.md` and `validation/` are excluded outright --
# they are historical records, and editing them would falsify provenance.

_ROOT = _SRC.parent
_PROSE = ("README.md", "llms.txt", ".github/actions/quantfit-gate/action.yml")
_PROSE_DIRS = ("docs", "spec")
_CORRECTION_MARKERS = ("corrected 2026-", "dated defect", "was true when written", "and it was false")


def _prose_files():
    for name in _PROSE:
        path = _ROOT / name
        if path.exists():
            yield path
    for directory in _PROSE_DIRS:
        yield from sorted((_ROOT / directory).rglob("*.md"))


def test_no_doc_asserts_the_instrument_has_no_measured_epsilon():
    offenders = []
    for path in _prose_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        lowered = [line.lower() for line in lines]
        for i, line in enumerate(lowered):
            for claim in _FALSE_CLAIMS:
                if claim not in line:
                    continue
                window = " ".join(lowered[max(0, i - 8) : i + 9])
                if any(marker in window for marker in _CORRECTION_MARKERS):
                    continue  # the doc is correcting itself, which is the point
                offenders.append(f"{path.relative_to(_ROOT)}:{i + 1}: {claim!r}")
    joined = chr(10).join(offenders)
    assert not offenders, f"docs asserting no epsilon exists; one was measured 2026-08-18:{chr(10)}{joined}"
