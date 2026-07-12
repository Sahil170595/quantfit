"""Capacity decision: in-GPU / CPU-offload / refuse.

Three resources gate a quantization job:
  - disk : weights must be downloaded (unless cached) + the output written.
           Needed in every mode, so it's a precondition.
  - RAM  : weights ALWAYS load into CPU RAM first (llm-compressor's sequential
           onloading then streams layers to the GPU), so RAM is a precondition
           in every mode too — including models that fit VRAM.
  - VRAM : enough -> calibration runs fully GPU-resident (fast); not enough ->
           offload mode (layers stream from RAM; slower; fits any size).
Refuse only when a precondition fails, and always name the actual limiting
resource.
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

# Offload holds the model in CPU RAM and moves one layer at a time to the GPU.
OFFLOAD_RAM_FACTOR = 1.15
# Quantized output is smaller than fp16; reserve this fraction (covers 8-bit, the
# largest common output; 4-bit is ~half this).
OUTPUT_DISK_FACTOR = 0.6
# GGUF writes a full-size f16 intermediate before quantizing it; budget ~1x fp16 for it.
GGUF_F16_DISK_FACTOR = 1.0
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
        ram_need = int(self.fp16_bytes * OFFLOAD_RAM_FACTOR) + HEADROOM_BYTES
        return (
            f"CAN'T QUANTIZE: {self.model_id} ~{g(self.fp16_bytes)} GB must load into "
            f"CPU RAM first (~{g(ram_need)} GB with overhead) but only "
            f"{g(self.ram_available)} GB is available. Use a machine with more RAM."
        )


def _existing_parent(path: str) -> str:
    p = Path(path).resolve()
    while not p.exists() and p != p.parent:  # stop at the root; a missing drive never .exists()
        p = p.parent
    return str(p)


def _cached_weight_bytes(model_id: str) -> int:
    """Bytes of this model's cached weights (safetensors, else .bin); 0 if absent.

    Mirrors estimate_fp16_bytes' suffix preference so cache detection and footprint
    estimation count the same files — a .bin-only repo would otherwise read as cached=0
    and inflate the estimated download.
    """
    from huggingface_hub.constants import HF_HUB_CACHE

    snap = Path(HF_HUB_CACHE) / ("models--" + model_id.replace("/", "--")) / "snapshots"
    if not snap.exists():
        return 0
    for suffix in (".safetensors", ".bin"):
        total = 0
        for f in snap.rglob("*" + suffix):
            try:
                total += f.stat().st_size
            except OSError as exc:
                logger.warning("skipping unreadable cache file %s: %s", f, exc)
        if total:
            return total
    return 0


def gguf_disk_need(model_id: str, out_dir: str = ".", token: str | None = None) -> tuple[int, int]:
    """(free, need) disk bytes for a GGUF job: download + f16 intermediate + quantized output.

    GGUF is CPU-only (no VRAM gate) but writes a full-size f16 GGUF before quantizing it,
    so it needs more disk than a compressed-tensors job — give it its own pre-flight.
    """
    fp16 = estimate_fp16_bytes(model_id, token=token)
    free = shutil.disk_usage(_existing_parent(out_dir)).free
    download_need = max(0, fp16 - _cached_weight_bytes(model_id))
    need = download_need + int(fp16 * GGUF_F16_DISK_FACTOR) + int(fp16 * OUTPUT_DISK_FACTOR)
    return free, need


def capacity_plan(model_id: str, out_dir: str = ".", token: str | None = None) -> CapacityPlan:
    """Decide gpu / offload / refuse for quantizing `model_id`.

    Named capacity_plan (not plan) so it can't be confused with the ROUTING
    plan — the `quantfit plan` subcommand's (method, scheme) pick in policy/route.
    """
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
    elif ram < ram_need:
        # RAM gates EVERY mode: the CPU-first load materializes the full weights in
        # host RAM even for models that fit VRAM (sequential onloading streams from
        # there), so a big-VRAM/small-RAM machine must refuse, not OOM mid-load.
        mode, limit = MODE_REFUSE, LIMIT_MACHINE
    elif gpu_need <= gpu:
        mode, limit = MODE_GPU, LIMIT_NONE
    else:
        mode, limit = MODE_OFFLOAD, LIMIT_NONE
    return CapacityPlan(model_id, fp16, gpu, ram, disk, disk_need, mode, limit)
