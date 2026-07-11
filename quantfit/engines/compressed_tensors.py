"""compressed-tensors Engine: wraps the llm-compressor backend for the router.

Thin adapter over `quantfit.backends.compressed_tensors.quantize_ct`. The method ×
scheme matrix and calibration flags live in `quantfit.registry`; this engine only
gates on hardware (CT kernels are CUDA-only) and delegates execution verbatim.
"""

from __future__ import annotations

from pathlib import Path

from quantfit import registry
from quantfit.backends.compressed_tensors import quantize_ct
from quantfit.engines.base import EngineConfig, Target
from quantfit.spec import QuantSpec

_CUDA = "cuda"  # llm-compressor / vLLM CT path requires a CUDA device


class CompressedTensorsEngine:
    """Engine wrapping llm-compressor's compressed-tensors output (vLLM-loadable)."""

    name = "compressed-tensors"

    def feasible(self, target: Target) -> list[EngineConfig]:
        """One config per CT method at its registry default scheme; CUDA-only."""
        if target.device != _CUDA:
            return []
        return [
            EngineConfig(engine=self.name, method=m.name, scheme=m.default_scheme)
            for m in registry.METHODS.values()
            if m.backend == registry.BACKEND_CT
        ]

    def quantize(
        self,
        model_id: str,
        config: EngineConfig,
        out_dir: str,
        spec: QuantSpec,
        token: str | None = None,
    ) -> Path:
        """Delegate to quantize_ct, pulling needs_calibration from the registry."""
        needs_calibration = registry.METHODS[config.method].needs_calibration
        return quantize_ct(
            model_id,
            config.method,
            config.scheme,
            out_dir,
            spec,
            needs_calibration,
            token=token,
        )
