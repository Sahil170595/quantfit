"""Floating-point task updates. Storage and reconstruction semantics are explicit."""

from __future__ import annotations

import math
import re

import numpy as np

from ._tensors import Tensor, canonical, identity, ordered_records, require, sha

TASK = "task-vector-v1"
FLOAT = {"F16": "<f2", "F32": "<f4", "F64": "<f8"}


def values(t: Tensor) -> np.ndarray:
    if t.dtype == "BF16":
        arr = (np.frombuffer(t.data, "<u2").astype("<u4") << 16).view("<f4")
    else:
        require(t.dtype in FLOAT, "only floating-point tensors can carry arithmetic updates")
        arr = np.frombuffer(t.data, FLOAT[t.dtype])
    require(np.isfinite(arr).all(), "arithmetic inputs must be finite")
    return arr.astype("<f8").reshape(t.shape)


def cast(a: Tensor, values64: np.ndarray) -> Tensor:
    with np.errstate(over="ignore", invalid="ignore"):
        if a.dtype == "BF16":
            f32 = values64.astype("<f4")
            bits = f32.view("<u4")
            # Round-to-nearest-even at the BF16 boundary.
            raw = ((bits + np.uint32(0x7FFF) + ((bits >> 16) & 1)) >> 16).astype("<u2")
            require(np.all((raw & 0x7F80) != 0x7F80), "scaled update overflows the base dtype")
        else:
            raw = values64.astype(FLOAT[a.dtype])
            require(np.isfinite(raw).all(), "scaled update overflows the base dtype")
    return Tensor(a.dtype, a.shape, raw.tobytes())


def apply(original: Tensor, diff: np.ndarray, scale: float) -> Tensor:
    require(diff.shape == original.shape and np.isfinite(diff).all(), "invalid numerical update")
    a = values(original)
    if scale == 0:
        return original  # Includes the physical sign bit of base zeros.
    with np.errstate(over="ignore", invalid="ignore"):
        return cast(original, a + diff * scale)


def extract(original, wanted):
    changes, unchanged, reconstructed = {}, [], dict(original)
    worst = 0.0
    for name in sorted(original):
        a, b = original[name], wanted[name]
        require((a.dtype, a.shape) == (b.dtype, b.shape), f"incompatible layout for {name}")
        if a.data == b.data:
            unchanged.append(name)
            continue
        with np.errstate(over="ignore", invalid="ignore"):
            diff = values(b) - values(a)
        require(np.isfinite(diff).all(), "task delta exceeds float64 range")
        changes[name] = Tensor("F64", a.shape, diff.astype("<f8", copy=False).tobytes())
        reconstructed[name] = apply(a, diff, 1.0)
        error = np.max(np.abs(values(reconstructed[name]) - values(b)), initial=0.0)
        require(np.isfinite(error), "reconstruction error exceeds float64 range")
        worst = max(worst, float(error))
    return changes, {"unchanged": unchanged, "max_abs_error": worst}, reconstructed


def restore(original, payload, doc, scale):
    require(type(scale) in (int, float) and math.isfinite(scale), "scale must be a finite real number")
    meta = doc.get("metadata")
    require(isinstance(meta, dict), "missing task-vector metadata")
    unchanged = meta.get("unchanged")
    require(
        isinstance(unchanged, list)
        and all(isinstance(n, str) for n in unchanged)
        and len(unchanged) == len(set(unchanged)),
        "invalid unchanged tensor list",
    )
    require(
        set(unchanged).isdisjoint(payload) and set(unchanged) | payload.keys() == original.keys(),
        "task-vector tensor coverage disagrees with base",
    )
    source = ordered_records(doc.get("tensors"))
    require(isinstance(source, list) and len(source) == len(original), "invalid target tensor inventory")
    for name, row in zip(sorted(original), source):
        expected = original[name].record(name)
        require(
            isinstance(row, dict)
            and isinstance(row.get("sha256"), str)
            and re.fullmatch("[a-f0-9]{64}", row["sha256"]),
            "invalid tensor digest",
        )
        expected["sha256"] = row["sha256"]
        require(canonical(row) == canonical(expected), "target tensor layout mismatch")
    require(sha(canonical(source)) == doc["identities"].get("target"), "target inventory commitment mismatch")
    standard, scaled = dict(original), dict(original)
    for name, t in payload.items():
        a = original[name]
        require(t.dtype == "F64" and t.shape == a.shape, "invalid task-vector tensor layout")
        diff = values(t)
        standard[name] = apply(a, diff, 1.0)
        scaled[name] = standard[name] if scale == 1 else apply(a, diff, scale)
    require(identity(standard) == doc["identities"].get("reconstructed"), "standard reconstruction commitment mismatch")
    return scaled
