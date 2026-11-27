"""Grouped symmetric quantization of finite flattened task updates."""

from __future__ import annotations

import math

import numpy as np

from . import _vectors
from ._tensors import Tensor, require

LOWBIT = "grouped-int-v1"


def parameters(bits, group_size):
    require(type(bits) is int and bits in (4, 8), "bits must be 4 or 8")
    require(type(group_size) is int and 1 <= group_size <= 65536, "group size must be in [1, 65536]")
    return {"bits": bits, "group_size": group_size}


def pack(original, wanted, changes, metadata, bits, group_size):
    payload, rebuilt = {}, dict(original)
    worst = 0.0
    bound = (1 << (bits - 1)) - 1
    for idx, name in enumerate(sorted(changes)):
        diff = _vectors.values(changes[name]).ravel()
        codes = np.empty(diff.size, dtype="i1")
        scales = np.empty((diff.size + group_size - 1) // group_size, dtype="<f8")
        for group, start in enumerate(range(0, diff.size, group_size)):
            segment = diff[start : start + group_size]
            peak = float(np.max(np.abs(segment)))
            step = peak / bound
            require(peak == 0 or step > 0, "group scale underflows float64")
            scales[group] = step
            codes[start : start + len(segment)] = np.rint(np.clip(segment / step, -bound, bound)) if step else 0
        if bits == 4:
            unsigned = codes.astype("u1") & 15
            packed = unsigned[::2].copy()
            packed[: len(unsigned) // 2] |= unsigned[1::2] << 4
        else:
            packed = codes.view("u1")
        payload[f"codes.{idx}"] = Tensor("U8", (len(packed),), packed.tobytes())
        payload[f"scales.{idx}"] = Tensor("F64", (len(scales),), scales.tobytes())
        dense = _expand(codes, scales, group_size, changes[name].shape)
        rebuilt[name] = _vectors.apply(original[name], dense, 1.0)
        error = np.max(np.abs(_vectors.values(rebuilt[name]) - _vectors.values(wanted[name])), initial=0.0)
        require(np.isfinite(error), "reconstruction error exceeds float64 range")
        worst = max(worst, float(error))
    return payload, {**metadata, "max_abs_error": worst}, rebuilt


def _expand(codes, scales, group_size, shape):
    # Index only the encoded element count, including for a short final group.
    with np.errstate(over="ignore"):
        dense = codes * scales[np.arange(codes.size) // group_size]
    require(np.isfinite(dense).all(), "nonfinite decoded update")
    return dense.reshape(shape)


def unpack(original, payload, metadata, bits, group_size):
    require(isinstance(metadata, dict), "missing grouped codec metadata")
    unchanged = metadata.get("unchanged")
    require(isinstance(unchanged, list) and all(isinstance(n, str) for n in unchanged), "invalid unchanged names")
    changed = sorted(set(original).difference(unchanged))
    require(len(payload) == 2 * len(changed), "incorrect packed tensor count")
    dense = {}
    bound = (1 << (bits - 1)) - 1
    for idx, name in enumerate(changed):
        count = math.prod(original[name].shape)
        c, s = payload.get(f"codes.{idx}"), payload.get(f"scales.{idx}")
        require(c is not None and s is not None, "missing packed codes or scales")
        require(c.dtype == "U8" and c.shape == ((count + 1) // 2 if bits == 4 else count,), "packed code size mismatch")
        require(s.dtype == "F64" and s.shape == ((count + group_size - 1) // group_size,), "group scale size mismatch")
        scales = np.frombuffer(s.data, "<f8")
        require(np.all(np.isfinite(scales) & (scales >= 0)), "invalid group scale")
        packed = np.frombuffer(c.data, "u1")
        if bits == 4:
            require(count % 2 == 0 or packed[-1] >> 4 == 0, "odd code padding must be zero")
            codes = np.empty(count, dtype="i1")
            codes[::2] = packed & 15
            codes[1::2] = packed[: count // 2] >> 4
            codes[codes >= 8] -= 16
        else:
            codes = packed.view("i1")
        require(np.all(codes >= -bound), "reserved signed code")
        require(np.all((codes == 0) | (scales[np.arange(count) // group_size] > 0)), "nonzero code with zero scale")
        values = _expand(codes, scales, group_size, original[name].shape)
        dense[name] = Tensor("F64", original[name].shape, values.astype("<f8", copy=False).tobytes())
    return dense
