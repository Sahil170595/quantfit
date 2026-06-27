"""Hardware detection — the policy's `Target` input.

`detect_target()` reads the live machine (CUDA availability, free VRAM, compute
capability) and maps it onto the `Target` contract the router consumes. No
weights, no network: a cheap pre-flight the policy can call on every request.
"""

from __future__ import annotations

from quantfit.engines.base import Budget, Target

# Compute-capability (sm_XX = major*10 + minor) -> GPU arch family. Named so the
# arch mapping is auditable rather than a wall of magic integers.
SM_AMPERE = (80, 86)  # A100 (sm_80) / A10, RTX 30-series (sm_86)
SM_ADA = 89  # L4/L40S, RTX 40-series
SM_HOPPER = 90  # H100/H200
SM_BLACKWELL_MIN = 100  # B100/B200 and newer (sm_100+)

# Serving backends keyed off device class.
SERVE_CUDA = "vllm"
SERVE_CPU = "llama.cpp"

# Default preference, exposed so callers have a ready Budget without importing base.
DEFAULT_BUDGET = Budget()


def _arch_for_sm(sm: int) -> str | None:
    """Map a packed compute-capability int (major*10+minor) to an arch family."""
    if sm >= SM_BLACKWELL_MIN:
        return "blackwell"
    if sm == SM_HOPPER:
        return "hopper"
    if sm == SM_ADA:
        return "ada"
    if sm in SM_AMPERE:
        return "ampere"
    return None  # known-CUDA but unmapped arch: router still routes on device.


def detect_target() -> Target:
    """Probe this machine and return the `Target` the policy routes over."""
    import torch

    if torch.cuda.is_available():
        free_bytes = torch.cuda.mem_get_info()[0]  # free VRAM on the default device
        major, minor = torch.cuda.get_device_capability()
        sm = major * 10 + minor
        return Target(
            device="cuda",
            vram_bytes=int(free_bytes),
            gpu_arch=_arch_for_sm(sm),
            serve=SERVE_CUDA,
        )
    return Target(device="cpu", vram_bytes=0, gpu_arch=None, serve=SERVE_CPU)
