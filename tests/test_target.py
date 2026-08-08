"""Compute-capability -> arch mapping — decides whether the FP8 route exists — and the
CUDA probe's guard, which decides whether `quantfit plan` exits 2 or dies with a traceback.
"""

import sys
import types

import pytest

from quantfit.policy.target import SERVE_CPU, SERVE_CUDA, _arch_for_sm, detect_target


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


# --------------------------------------------------------------------------------
# The CUDA probe guard. These run on any machine, GPU or not: `detect_target` imports
# torch inside the function, so substituting a fake in sys.modules controls the probe
# exactly. The states below are the ones measured on a real box with a real GPU:
#
#   CUDA_VISIBLE_DEVICES=""    is_available() True,  device_count() 0
#   CUDA_VISIBLE_DEVICES="-1"  is_available() False, device_count() 0
#
# The first state is the defect: it entered the CUDA branch and torch raised
# `AssertionError: Invalid device id`, which cli.main's `(RuntimeError, OSError)` handler
# does not catch, so `quantfit plan` exited 1 with a traceback instead of the documented 2.
# --------------------------------------------------------------------------------


def _fake_torch(*, available, count, mem_get_info=None, capability=None):
    cuda = types.SimpleNamespace(
        is_available=lambda: available,
        device_count=lambda: count,
        mem_get_info=mem_get_info or (lambda: (0, 0)),
        get_device_capability=capability or (lambda: (8, 9)),
    )
    return types.SimpleNamespace(cuda=cuda)


@pytest.fixture
def fake_torch(monkeypatch):
    def install(**kwargs):
        monkeypatch.setitem(sys.modules, "torch", _fake_torch(**kwargs))

    return install


def test_masked_gpu_plans_for_cpu_instead_of_raising(fake_torch):
    """`CUDA_VISIBLE_DEVICES=""` — available, zero devices. The user masked the GPU; that is
    a CPU machine, not an error, and it must not touch the device."""

    def explode():
        raise AssertionError("Invalid device id")  # what torch actually raises here

    fake_torch(available=True, count=0, mem_get_info=explode, capability=explode)
    target = detect_target()
    assert (target.device, target.serve, target.vram_bytes) == ("cpu", SERVE_CPU, 0)


def test_unavailable_cuda_plans_for_cpu(fake_torch):
    fake_torch(available=False, count=0)
    assert detect_target().device == "cpu"


def test_a_real_device_still_reports_cuda(fake_torch):
    fake_torch(available=True, count=1, mem_get_info=lambda: (11_600_396_288, 12_884_901_888))
    target = detect_target()
    assert (target.device, target.serve, target.gpu_arch) == ("cuda", SERVE_CUDA, "ada")
    assert target.vram_bytes == 11_600_396_288


@pytest.mark.parametrize("failure", [AssertionError("Invalid device id"), ValueError("nonsense"), KeyError("x")])
def test_a_failing_probe_becomes_a_runtime_error_the_cli_can_report(fake_torch, failure):
    """torch does not contract which exception a CUDA query raises, and quantfit's contract
    is that every operational failure is a RuntimeError — so the conversion cannot depend on
    guessing the type. cli.main catches (RuntimeError, OSError) and exits 2."""

    def explode():
        raise failure

    fake_torch(available=True, count=1, mem_get_info=explode)
    with pytest.raises(RuntimeError) as caught:
        detect_target()
    assert "probing the default device failed" in str(caught.value)
    assert type(failure).__name__ in str(caught.value)
    assert caught.value.__cause__ is failure
