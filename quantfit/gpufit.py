"""Footprint estimation for the capacity pre-flight.

Estimates a model's FP16 footprint from Hub file metadata (no weight download)
and reads free VRAM. The actual gpu/offload/refuse decision lives in
`quantfit.fit.capacity_plan`, which consumes these numbers plus RAM and disk.
Errs toward refusal — a clear "can't quantize" beats an OOM crash 20 minutes in.
"""

from __future__ import annotations

from huggingface_hub import HfApi

# In-GPU PTQ (GPTQ/AWQ) holds the FP16 model plus per-layer Hessian/activation
# buffers; observed peak runs ~1.25x the released FP16 size. Headroom covers the
# CUDA context, calibration-batch activations, and allocator fragmentation.
CALIB_OVERHEAD_FACTOR = 1.25
HEADROOM_BYTES = 2 * 1024**3
# Prefer safetensors; fall back to .bin only if no safetensors shards exist
# (summing both would double-count repos that ship both formats).
_WEIGHT_SUFFIXES = (".safetensors", ".bin")


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
    # RuntimeError: operational (gated/unavailable/weightless repo) -> clean CLI exit 2.
    raise RuntimeError(
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
