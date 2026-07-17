"""Engine feasibility gating — the set the `plan` command actually routes over."""

from quantfit import registry
from quantfit.engines.base import Target
from quantfit.engines.compressed_tensors import CompressedTensorsEngine
from quantfit.engines.gguf import OFFERED_SCHEMES, GgufEngine


def _target(device, serve, arch=None):
    return Target(device=device, vram_bytes=12 * 1024**3 if device == "cuda" else 0, gpu_arch=arch, serve=serve)


def test_gguf_feasible_on_cpu_llamacpp():
    configs = GgufEngine().feasible(_target("cpu", "llama.cpp"))
    assert [c.scheme for c in configs] == list(OFFERED_SCHEMES)
    assert all(c.method == "gguf" for c in configs)


def test_gguf_feasible_when_serving_transformers_on_cuda():
    assert len(GgufEngine().feasible(_target("cuda", "transformers", "ada"))) == len(OFFERED_SCHEMES)


def test_gguf_infeasible_for_cuda_vllm():
    # vLLM serving on GPU is the compressed-tensors world; GGUF must not offer.
    assert GgufEngine().feasible(_target("cuda", "vllm", "ada")) == []


def test_ct_offers_every_ct_method_at_default_scheme_on_cuda():
    configs = CompressedTensorsEngine().feasible(_target("cuda", "vllm", "ada"))
    expected = {(m.name, m.default_scheme) for m in registry.METHODS.values() if m.backend == registry.BACKEND_CT}
    assert {(c.method, c.scheme) for c in configs} == expected


def test_ct_infeasible_on_cpu():
    assert CompressedTensorsEngine().feasible(_target("cpu", "llama.cpp")) == []
