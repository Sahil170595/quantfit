"""Compute-capability -> arch mapping — decides whether the FP8 route exists."""

import pytest

from quantfit.policy.target import _arch_for_sm


@pytest.mark.parametrize(
    ("sm", "arch"),
    [
        (80, "ampere"),  # A100
        (86, "ampere"),  # A10 / RTX 30-series
        (89, "ada"),  # L4/L40S / RTX 40-series
        (90, "hopper"),  # H100/H200
        (100, "blackwell"),  # B100/B200
        (120, "blackwell"),  # future sm_100+ stays blackwell-classed
        (75, None),  # Turing: known CUDA, unmapped arch — router falls back to device
        (87, None),  # Orin: between the pinned values, must not misclassify
    ],
)
def test_arch_for_sm(sm, arch):
    assert _arch_for_sm(sm) == arch
