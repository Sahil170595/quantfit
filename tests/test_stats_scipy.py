"""Wilson CI + MDE cross-checked against scipy — the independent reference.

quantfit ships closed-form stats with no scipy runtime dependency; these tests
prove the closed forms agree with scipy to 1e-9 so the printed numbers can be
cited without a caveat. CI installs scipy for exactly this file.
"""

import pytest

scipy_stats = pytest.importorskip("scipy.stats", reason="scipy is the reference implementation for these checks")

from quantfit.safety.verify import detectable_flip_rate, wilson_interval  # noqa: E402

# Covers the shipped probe set's shapes (0/12, x/28) plus degenerate corners.
GRID = [(0, 12), (1, 12), (2, 10), (5, 12), (12, 12), (0, 28), (3, 28), (0, 1), (1, 1), (7, 40)]


@pytest.mark.parametrize(("flips", "n"), GRID)
def test_wilson_matches_scipy(flips, n):
    ref = scipy_stats.binomtest(flips, n).proportion_ci(confidence_level=0.95, method="wilson")
    lo, hi = wilson_interval(flips, n)
    assert lo == pytest.approx(ref.low, abs=1e-9)
    assert hi == pytest.approx(ref.high, abs=1e-9)


@pytest.mark.parametrize("n", [1, 5, 12, 28, 40])
def test_mde_delivers_stated_power(n):
    # At exactly the MDE flip rate, P(>=1 observed flip in n pairs) must equal
    # the stated 80% power — checked against scipy's binomial CDF.
    p = detectable_flip_rate(n, power=0.8)
    detect_prob = 1 - scipy_stats.binom.cdf(0, n, p)
    assert detect_prob == pytest.approx(0.8, abs=1e-9)
