"""Generated numerical invariants, independently checked against SciPy."""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.stats import binom

from quantfit.safety.mde import detection_threshold
from quantfit.safety.verify import wilson_interval


@settings(max_examples=100, derandomize=True, deadline=None)
@given(st.integers(1, 300), st.floats(0, 0.9, allow_nan=False, allow_infinity=False))
def test_rejection_threshold_is_minimal_and_controls_size(n, q):
    k = detection_threshold(n, q)
    assert 1 <= k <= n + 1
    assert binom.sf(k - 1, n, q) <= 0.05 + 1e-12
    if k > 1:
        assert binom.sf(k - 2, n, q) > 0.05 - 1e-12


@settings(max_examples=100, derandomize=True, deadline=None)
@given(st.integers(1, 10000), st.floats(0, 1, allow_nan=False, allow_infinity=False))
def test_wilson_interval_contains_estimate_and_is_complement_symmetric(n, fraction):
    x = min(n, math.floor(n * fraction))
    lo, hi = wilson_interval(x, n)
    other_lo, other_hi = wilson_interval(n - x, n)
    assert 0 <= lo <= x / n <= hi <= 1
    assert lo == pytest.approx(1 - other_hi, abs=1e-12)
    assert hi == pytest.approx(1 - other_lo, abs=1e-12)


@settings(max_examples=50, derandomize=True, deadline=None)
@given(st.integers(1, 8), st.integers(1, 64), st.integers(2, 8), st.integers(1, 32))
def test_rtn_reconstruction_obeys_half_step_bound(rows, cols, bits, group):
    import torch

    from quantfit.policy.probe import _rtn

    # Independent oracle: every element must reconstruct within half its group's step.
    weights = torch.linspace(-3.0, 3.0, rows * cols).reshape(rows, cols)
    actual = _rtn(weights, bits, group)
    g = group if cols % group == 0 else cols
    steps = weights.reshape(rows, -1, g).abs().amax(-1, keepdim=True) / (2 ** (bits - 1) - 1)
    bound = (steps / 2 + 1e-6).expand(rows, cols // g, g).reshape_as(weights)
    assert torch.isfinite(actual).all()
    assert torch.all((actual - weights).abs() <= bound)
    assert torch.equal(_rtn(torch.zeros_like(weights), bits, group), torch.zeros_like(weights))
