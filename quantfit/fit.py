"""Capacity decision: in-GPU / CPU-offload / refuse.

Three resources gate a quantization job:
  - disk : weights must be downloaded (unless cached) + the output written. Needed
           in BOTH gpu and offload modes, so it's a precondition.
  - VRAM : enough -> quantize in-GPU (fast).
  - RAM  : not enough VRAM but enough RAM -> hold the model on CPU and stream
           layers to the GPU (offload; slower; fits any size).
Refuse only when none of the above can be satisfied, and always name the actual
limiting resource.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import psutil

from quantfit.gpufit import (
    CALIB_OVERHEAD_FACTOR,
    HEADROOM_BYTES,
    estimate_fp16_bytes,
    gpu_free_bytes,
)

# Offload holds the model in CPU RAM and moves one layer at a time to the GPU.
OFFLOAD_RAM_FACTOR = 1.15
# Quantized output is smaller than fp16; reserve this fraction (covers 8-bit, the
# largest common output; 4-bit is ~half this).
OUTPUT_DISK_FACTOR = 0.6
_GIB = 1024**3

MODE_GPU = "gpu"
MODE_OFFLOAD = "offload"
MODE_REFUSE = "refuse"

LIMIT_NONE = ""
LIMIT_DISK = "disk"
LIMIT_MACHINE = "machine"


@dataclass(frozen=True)
class CapacityPlan:
    model_id: str
    fp16_bytes: int
    gpu_free: int
    ram_available: int
    disk_free: int
    disk_need: int
    mode: str
    limit: str

    @property
    def fits(self) -> bool:
        return self.mode != MODE_REFUSE

    @property
    def offload(self) -> bool:
        return self.mode == MODE_OFFLOAD

    def reason(self) -> str:
        def g(b: int) -> str:
            return f"{b / _GIB:.1f}"

        if self.mode == MODE_GPU:
            return f"OK (in-GPU): {self.model_id} ~{g(self.fp16_bytes)} GB, {g(self.gpu_free)} GB VRAM free."
        if self.mode == MODE_OFFLOAD:
            return (
                f"OK (offload): {self.model_id} ~{g(self.fp16_bytes)} GB won't fit "
                f"{g(self.gpu_free)} GB VRAM — quantizing via CPU "
                f"({g(self.ram_available)} GB RAM). Slower."
            )
        if self.limit == LIMIT_DISK:
            return (
                f"CAN'T QUANTIZE: {self.model_id} needs ~{g(self.disk_need)} GB free "
                f"disk (download + output) but only {g(self.disk_free)} GB is free."
            )
        return (
            f"CAN'T QUANTIZE: {self.model_id} ~{g(self.fp16_bytes)} GB needs more than "
            f"{g(self.gpu_free)} GB VRAM and {g(self.ram_available)} GB RAM. "
            f"Use a bigger machine."
        )


def _existing_parent(path: str) -> str:
    p = Path(path).resolve()
    while not p.exists():
        p = p.parent
    return str(p)


def _cached_weight_bytes(model_id: str) -> int:
    """Bytes of this model's safetensors already in the HF cache (0 if absent)."""
    from huggingface_hub.constants import HF_HUB_CACHE

    snap = Path(HF_HUB_CACHE) / ("models--" + model_id.replace("/", "--")) / "snapshots"
    if not snap.exists():
        return 0
    total = 0
    for f in snap.rglob("*.safetensors"):
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return total


def plan(model_id: str, out_dir: str = ".", token: str | None = None) -> CapacityPlan:
    """Decide gpu / offload / refuse for quantizing `model_id`."""
    fp16 = estimate_fp16_bytes(model_id, token=token)
    gpu = gpu_free_bytes()
    ram = int(psutil.virtual_memory().available)
    disk = shutil.disk_usage(_existing_parent(out_dir)).free

    download_need = max(0, fp16 - _cached_weight_bytes(model_id))
    disk_need = download_need + int(fp16 * OUTPUT_DISK_FACTOR)
    gpu_need = int(fp16 * CALIB_OVERHEAD_FACTOR) + HEADROOM_BYTES
    ram_need = int(fp16 * OFFLOAD_RAM_FACTOR) + HEADROOM_BYTES

    if disk < disk_need:
        mode, limit = MODE_REFUSE, LIMIT_DISK
    elif gpu_need <= gpu:
        mode, limit = MODE_GPU, LIMIT_NONE
    elif ram_need <= ram:
        mode, limit = MODE_OFFLOAD, LIMIT_NONE
    else:
        mode, limit = MODE_REFUSE, LIMIT_MACHINE
    return CapacityPlan(model_id, fp16, gpu, ram, disk, disk_need, mode, limit)
