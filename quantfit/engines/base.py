"""Engine abstraction + the types the policy routes over.

quantfit is a router on top of the ecosystem: engines declare what configs are
FEASIBLE for a target; the policy picks one. Execution deliberately does NOT go
through this contract — `quantfit.quantize` dispatches straight to the backends,
so there is exactly one execution path to validate. Adding a quantization method
= adding an Engine's feasibility + a backend, never touching the policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


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
    """A quantization capability, declared to the router. Execution lives in backends."""

    name: str

    def feasible(self, target: Target) -> list[EngineConfig]:
        """The configs this engine can produce for `target` (hardware-gated)."""
        ...
