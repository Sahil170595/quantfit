"""RTN quantizer math for the sensitivity probe.

Gated on torch (the CI test job installs only the light deps); runs locally.
"""

import pytest

torch = pytest.importorskip("torch")

from quantfit.policy.probe import _rtn  # noqa: E402  (after importorskip)


def test_more_bits_means_less_error():
    torch.manual_seed(0)
    w = torch.randn(64, 256)
    err4 = (w - _rtn(w, 4, 128)).abs().mean().item()
    err8 = (w - _rtn(w, 8, 128)).abs().mean().item()
    assert err8 < err4  # the load-bearing property: more bits, less reconstruction error


def test_preserves_shape_and_dtype():
    w = torch.randn(32, 128, dtype=torch.float32)
    dq = _rtn(w, 4, 128)
    assert dq.shape == w.shape and dq.dtype == w.dtype


def test_per_row_fallback_when_not_divisible():
    w = torch.randn(8, 100)  # 100 not divisible by group_size 128
    dq = _rtn(w, 4, 128)  # must fall back to per-row, not crash
    assert dq.shape == w.shape
