"""GPU capacity pre-flight.

The whole point of the tool: decide whether a model can be quantized in-GPU on
*this* machine BEFORE downloading weights or starting a multi-minute job. The
estimate is the FP16 footprint of the released weights (read from the Hub file
metadata, no download) times a calibration-overhead factor, plus fixed headroom,
compared against free VRAM. Errs toward refusal — a clear "can't quantize" beats
an OOM crash 20 minutes in.
"""
from __future__ import annotations

from dataclasses import dataclass

from huggingface_hub import HfApi

# In-GPU PTQ (GPTQ/AWQ) holds the FP16 model plus per-layer Hessian/activation
# buffers; observed peak runs ~1.25x the released FP16 size. Headroom covers the
# CUDA context, calibration-batch activations, and allocator fragmentation.
CALIB_OVERHEAD_FACTOR = 1.25
HEADROOM_BYTES = 2 * 1024**3
_GIB = 1024**3
# Prefer safetensors; fall back to .bin only if no safetensors shards exist
# (summing both would double-count repos that ship both formats).
_WEIGHT_SUFFIXES = (".safetensors", ".bin")


@dataclass(frozen=True)
class FitReport:
    model_id: str
    fp16_bytes: int
    required_bytes: int
    free_bytes: int
    fits: bool

    @property
    def fp16_gib(self) -> float:
        return self.fp16_bytes / _GIB

    @property
    def required_gib(self) -> float:
        return self.required_bytes / _GIB

    @property
    def free_gib(self) -> float:
        return self.free_bytes / _GIB

    def reason(self) -> str:
        if self.fits:
            return (
                f"OK: {self.model_id} is ~{self.fp16_gib:.1f} GB FP16, needs "
                f"~{self.required_gib:.1f} GB to quantize, {self.free_gib:.1f} GB free."
            )
        return (
            f"CAN'T QUANTIZE: {self.model_id} needs ~{self.required_gib:.1f} GB "
            f"in-GPU but only {self.free_gib:.1f} GB is free. Use a bigger GPU "
            f"or a smaller model."
        )


def estimate_fp16_bytes(model_id: str, token: str | None = None) -> int:
    """Sum the released weight-file sizes from Hub metadata (no weight download)."""
    info = HfApi().model_info(model_id, files_metadata=True, token=token)
    by_suffix: dict[str, int] = {}
    for f in info.siblings:
        for suffix in _WEIGHT_SUFFIXES:
            if f.rfilename.endswith(suffix) and f.size:
                by_suffix[suffix] = by_suffix.get(suffix, 0) + f.size
    for suffix in _WEIGHT_SUFFIXES:
        if by_suffix.get(suffix):
            return by_suffix[suffix]
    raise ValueError(
        f"{model_id}: no weight-file sizes found via Hub metadata; cannot "
        "estimate footprint (model may be gated without access, or unavailable)."
    )


def gpu_free_bytes() -> int:
    """Free VRAM on the current default CUDA device, in bytes."""
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("no CUDA GPU visible; quantfit needs a GPU to quantize.")
    free, _total = torch.cuda.mem_get_info()
    return int(free)


def check_fit(
    model_id: str,
    token: str | None = None,
    overhead: float = CALIB_OVERHEAD_FACTOR,
    headroom_bytes: int = HEADROOM_BYTES,
) -> FitReport:
    """Estimate footprint vs. free VRAM and return a fit verdict."""
    fp16 = estimate_fp16_bytes(model_id, token=token)
    required = int(fp16 * overhead) + headroom_bytes
    free = gpu_free_bytes()
    return FitReport(model_id, fp16, required, free, fits=required <= free)
