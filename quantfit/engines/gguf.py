"""GGUF engine — declares llama.cpp GGUF configs to the router.

GGUF k-quants are CPU-quantizable and target the llama.cpp / transformers serving
world. This engine only declares feasibility; execution goes through
`quantfit.quantize` -> `backends.gguf.quantize_gguf` — one validated path, not
re-implemented here.
"""

from __future__ import annotations

from quantfit.engines.base import EngineConfig, Target

ENGINE_NAME = "gguf"
# Schemes this engine offers to the policy — a curated subset of backend GGUF_TYPES
# (one balanced 4-bit, one higher-quality 5-bit, one near-lossless 8-bit).
OFFERED_SCHEMES = ("Q4_K_M", "Q5_K_M", "Q8_0")
# serve targets that consume GGUF artifacts directly.
GGUF_SERVE_TARGETS = ("llama.cpp", "transformers")
CPU_DEVICE = "cpu"


class GgufEngine:
    """Engine declaring GGUF k-quants (produced via the pinned llama.cpp tooling)."""

    name = ENGINE_NAME

    def feasible(self, target: Target) -> list[EngineConfig]:
        """GGUF is CPU-capable + serve-target oriented; gate on serve or device."""
        if target.serve not in GGUF_SERVE_TARGETS and target.device != CPU_DEVICE:
            return []
        return [EngineConfig(engine=ENGINE_NAME, method="gguf", scheme=scheme) for scheme in OFFERED_SCHEMES]
