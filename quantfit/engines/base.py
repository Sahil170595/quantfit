"""Engine abstraction + the types the policy routes over.

quantfit is a router on top of the ecosystem: the policy picks an `EngineConfig`,
an `Engine` executes it. Adding a quantization method = adding an `Engine`, never
touching the policy. This module is the contract; everything implements it exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from quantfit.spec import QuantSpec


@dataclass(frozen=True)
class Target:
    """Where the quantized model will run — the policy's hardware input."""

    device: str  # "cuda" | "cpu"
    vram_bytes: int  # free VRAM (0 on cpu)
    gpu_arch: str | None  # "ada" | "ampere" | "hopper" | "blackwell" | None
    serve: str  # "vllm" | "llama.cpp" | "transformers"


@dataclass(frozen=True)
class Budget:
    """What the user is optimizing for — the policy's preference input."""

    prefer: str = "quality"  # "quality" | "speed" | "size"


@dataclass(frozen=True)
class EngineConfig:
    """A concrete, runnable quantization choice."""

    engine: str  # Engine.name that produced/handles this
    method: str  # awq | gptq | smoothquant | fp8 | rtn | gguf
    scheme: str  # W4A16 / W4A16_ASYM / FP8_DYNAMIC / Q4_K_M / ...


@dataclass(frozen=True)
class Plan:
    """The routed decision, with its reasoning made legible."""

    config: EngineConfig
    rationale: str  # human-readable WHY — legibility is the product


@runtime_checkable
class Engine(Protocol):
    """A quantization backend. Implementations WRAP existing tooling."""

    name: str

    def feasible(self, target: Target) -> list[EngineConfig]:
        """The configs this engine can produce for `target` (hardware-gated)."""
        ...

    def quantize(
        self,
        model_id: str,
        config: EngineConfig,
        out_dir: str,
        spec: QuantSpec,
        token: str | None = None,
    ) -> Path:
        """Run the quantization and return the output directory."""
        ...
