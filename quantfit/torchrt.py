"""Torch runtime helpers shared by every model-touching module.

torch is imported INSIDE the function bodies, deliberately: light CLI commands
(`list`, argument parsing, registry validation) must never pay the torch import.
This module exists so the device pick and the GPU-memory hygiene between model
loads live in exactly one place instead of a copy per caller.
"""

from __future__ import annotations

CUDA = "cuda"
CPU = "cpu"


def pick_device() -> str:
    """The device every quantfit model load targets: cuda when visible, else cpu."""
    import torch

    return CUDA if torch.cuda.is_available() else CPU


def free_gpu(device: str) -> None:
    """Reclaim GPU memory between model loads so sequential loads fit a small GPU."""
    import gc

    import torch

    gc.collect()
    if device == CUDA:
        torch.cuda.empty_cache()
