"""Hardware detection — the policy's `Target` input.

`detect_target()` reads the live machine (CUDA availability, free VRAM, compute
capability) and maps it onto the `Target` contract the router consumes. No
weights, no network: a cheap pre-flight the policy can call on every request.
"""

from __future__ import annotations

from quantfit.engines.base import Target

# Compute-capability (sm_XX = major*10 + minor) -> GPU arch family. Named so the
# arch mapping is auditable rather than a wall of magic integers.
SM_AMPERE = (80, 86)  # A100 (sm_80) / A10, RTX 30-series (sm_86)
SM_ADA = 89  # L4/L40S, RTX 40-series
SM_HOPPER = 90  # H100/H200
SM_BLACKWELL_MIN = 100  # B100/B200 and newer (sm_100+)

# Serving backends keyed off device class.
SERVE_CUDA = "vllm"
SERVE_CPU = "llama.cpp"


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
    """Probe this machine and return the `Target` the policy routes over.

    `is_available()` alone is not the right guard: with `CUDA_VISIBLE_DEVICES=""` — the
    ordinary way to mask a GPU, and what the README's own `quantfit plan` example hits in a
    sandbox — it returns True while `device_count()` is 0. Probing a device in that state
    raised `AssertionError: Invalid device id` from inside torch, which is outside
    quantfit's error taxonomy: `cli.main` catches `(RuntimeError, OSError)`, so the
    documented operational exit 2 became an exit-1 traceback.

    Zero visible devices is not an error, it is a CPU machine — the user said so — so that
    state falls through to the CPU target, matching `CUDA_VISIBLE_DEVICES="-1"`, which
    already did. Anything else the probe throws becomes a RuntimeError: torch does not
    contract the exception types of its CUDA queries, and this project's contract is that
    every operational failure is a RuntimeError the CLI can turn into exit 2.
    """
    import torch

    if torch.cuda.is_available() and torch.cuda.device_count() > 0:
        try:
            free_bytes = torch.cuda.mem_get_info()[0]  # free VRAM on the default device
            major, minor = torch.cuda.get_device_capability()
        except Exception as exc:  # broad on purpose: torch's probe exception types are not a contract
            raise RuntimeError(
                f"CUDA reported {torch.cuda.device_count()} device(s) but probing the default "
                f"device failed ({type(exc).__name__}: {exc}). Set CUDA_VISIBLE_DEVICES=-1 to "
                "plan for CPU instead."
            ) from exc
        sm = major * 10 + minor
        return Target(
            device="cuda",
            vram_bytes=int(free_bytes),
            gpu_arch=_arch_for_sm(sm),
            serve=SERVE_CUDA,
        )
    return Target(device="cpu", vram_bytes=0, gpu_arch=None, serve=SERVE_CPU)
