"""compressed-tensors Engine: declares the llm-compressor matrix to the router.

The method × scheme matrix and calibration flags live in `quantfit.registry`;
this engine only gates on hardware (CT kernels are CUDA-only). Execution goes
through `quantfit.quantize` -> `backends.compressed_tensors.quantize_ct` — one
validated path, not re-implemented here.
"""

from __future__ import annotations

from quantfit import registry
from quantfit.engines.base import EngineConfig, Target

_CUDA = "cuda"  # llm-compressor / vLLM CT path requires a CUDA device


class CompressedTensorsEngine:
    """Engine declaring llm-compressor's compressed-tensors configs (vLLM-loadable)."""

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
