"""GGUF engine — wraps the llama.cpp GGUF backend behind the Engine protocol.

GGUF k-quants are CPU-quantizable and target the llama.cpp / transformers serving
world. This engine only routes + delegates; the actual conversion + quantization
lives in `quantfit.backends.gguf.quantize_gguf` and is not re-implemented here.
"""

from __future__ import annotations

from pathlib import Path

from quantfit.backends.gguf import GGUF_TYPES, quantize_gguf
from quantfit.engines.base import EngineConfig, Target
from quantfit.spec import QuantSpec

ENGINE_NAME = "gguf"
# Schemes this engine offers to the policy — a curated subset of backend GGUF_TYPES
# (one balanced 4-bit, one higher-quality 5-bit, one near-lossless 8-bit).
OFFERED_SCHEMES = ("Q4_K_M", "Q5_K_M", "Q8_0")
# serve targets that consume GGUF artifacts directly.
GGUF_SERVE_TARGETS = ("llama.cpp", "transformers")
CPU_DEVICE = "cpu"


class GgufEngine:
    """Engine producing GGUF k-quants via the pinned llama.cpp tooling."""

    name = ENGINE_NAME

    def feasible(self, target: Target) -> list[EngineConfig]:
        """GGUF is CPU-capable + serve-target oriented; gate on serve or device."""
        if target.serve not in GGUF_SERVE_TARGETS and target.device != CPU_DEVICE:
            return []
        return [EngineConfig(engine=ENGINE_NAME, method="gguf", scheme=scheme) for scheme in OFFERED_SCHEMES]

    def quantize(
        self,
        model_id: str,
        config: EngineConfig,
        out_dir: str,
        spec: QuantSpec,
        token: str | None = None,
    ) -> Path:
        """Delegate to quantize_gguf; the scheme is the GGUF quant type (qtype)."""
        if config.scheme not in GGUF_TYPES:
            raise ValueError(f"unknown GGUF scheme {config.scheme!r}; expected one of {GGUF_TYPES}")
        return quantize_gguf(model_id, config.scheme, out_dir, token=token)
