"""Routing heuristic — pure Python, no torch (mock engines supply feasible configs)."""

import pytest

from quantfit.engines.base import Budget, EngineConfig, Target
from quantfit.policy.route import route


class _MockEngine:
    name = "mock"

    def __init__(self, configs):
        self._configs = configs

    def feasible(self, target):
        return self._configs

    def quantize(self, *args, **kwargs):  # pragma: no cover - route() never calls this
        raise NotImplementedError


_GPU = [
    EngineConfig("compressed-tensors", "awq", "W4A16_ASYM"),
    EngineConfig("compressed-tensors", "gptq", "W4A16"),
    EngineConfig("compressed-tensors", "fp8", "FP8_DYNAMIC"),
    EngineConfig("gguf", "gguf", "Q4_K_M"),
]
_CPU = [EngineConfig("gguf", "gguf", "Q4_K_M")]


def _route(target, budget, configs):
    return route("some/model", target, budget, [_MockEngine(configs)])


def _gpu(arch="ada"):
    return Target(device="cuda", vram_bytes=10**10, gpu_arch=arch, serve="vllm")


def test_gpu_quality_routes_awq():
    plan = _route(_gpu(), Budget(prefer="quality"), _GPU)
    assert (plan.config.method, plan.config.scheme) == ("awq", "W4A16_ASYM")


def test_gpu_size_routes_gptq():
    plan = _route(_gpu("ampere"), Budget(prefer="size"), _GPU)
    assert plan.config.method == "gptq"


def test_gpu_speed_on_fp8_arch_routes_fp8():
    plan = _route(_gpu("hopper"), Budget(prefer="speed"), _GPU)
    assert plan.config.method == "fp8"


def test_ada_speed_routes_fp8():
    # regression for the audit fix: Ada has FP8 tensor cores and must take the FP8 path
    plan = _route(_gpu("ada"), Budget(prefer="speed"), _GPU)
    assert plan.config.method == "fp8"


def test_speed_without_fp8_arch_falls_through_to_awq():
    # ampere has no first-class FP8 -> speed rule skips -> default AWQ
    plan = _route(_gpu("ampere"), Budget(prefer="speed"), _GPU)
    assert plan.config.method == "awq"


def test_cpu_routes_gguf():
    t = Target(device="cpu", vram_bytes=0, gpu_arch=None, serve="llama.cpp")
    plan = _route(t, Budget(prefer="quality"), _CPU)
    assert plan.config.method == "gguf"


def test_no_feasible_config_raises():
    # RuntimeError: operational (no engine can serve this host) -> the CLI catches
    # it and exits cleanly instead of dumping a traceback.
    with pytest.raises(RuntimeError):
        _route(_gpu(), Budget(), [])


def test_rationale_is_legible():
    plan = _route(_gpu(), Budget(prefer="quality"), _GPU)
    assert "heuristic" in plan.rationale.lower()
    assert plan.config.method in plan.rationale.lower()
