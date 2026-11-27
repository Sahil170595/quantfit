"""Logical tensor identity and byte-preserving SafeTensors I/O."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import safetensors

from quantfit.bundle import _read

SCHEMA = "weightspace-manifest/v1"
MAX_FILE_BYTES = 256 * 1024**2
MAX_MANIFEST_BYTES = 16 * 1024**2
DTYPES = {
    "BOOL": "bool",
    "I8": "int8",
    "U8": "uint8",
    "I16": "int16",
    "U16": "uint16",
    "I32": "int32",
    "U32": "uint32",
    "I64": "int64",
    "U64": "uint64",
    "BF16": "bfloat16",
    "F16": "float16",
    "F32": "float32",
    "F64": "float64",
}


class WeightspaceError(RuntimeError):
    """A supplied checkpoint, artifact or operation does not meet its contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WeightspaceError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def read_json(raw: bytes) -> dict:
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            require(key not in obj, "duplicate JSON key")
            obj[key] = value
        return obj

    try:
        value = json.loads(raw.decode(), object_pairs_hook=unique)
        require(isinstance(value, dict), "expected a JSON object")
        canonical(value)  # Reject nonfinite numbers and invalid Unicode at the boundary.
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise WeightspaceError("invalid JSON object") from exc


@dataclass(frozen=True)
class Tensor:
    dtype: str
    shape: tuple[int, ...]
    data: bytes

    def record(self, name: str) -> dict:
        return {"name": name, "dtype": self.dtype, "shape": list(self.shape), "sha256": sha(self.data)}


def records(tensors: dict[str, Tensor]) -> list[dict]:
    return [tensors[name].record(name) for name in sorted(tensors)]


def identity(tensors: dict[str, Tensor]) -> str:
    return sha(canonical(records(tensors)))


def serialize(tensors: dict[str, Tensor]) -> bytes:
    # Buffers must live through serialize(). TensorSpec is the supported SafeTensors
    # 0.8 raw API and preserves BF16 independently of the host's NumPy dtype set.
    buffers = {name: np.frombuffer(t.data, dtype=np.uint8) for name, t in tensors.items()}
    specs = {}
    for name, t in tensors.items():
        element_bytes = 2 if t.dtype == "BF16" else np.dtype(DTYPES[t.dtype]).itemsize
        require(math.prod(t.shape) * element_bytes == len(t.data), "tensor layout and bytes disagree")
        specs[name] = safetensors.TensorSpec(
            dtype=DTYPES[t.dtype], shape=list(t.shape), data_ptr=buffers[name].ctypes.data, data_len=len(t.data)
        )
    return bytes(safetensors.serialize(specs))


def unpack(raw: bytes) -> dict[str, Tensor]:
    try:
        entries = safetensors.deserialize(raw)
    except (safetensors.SafetensorError, ValueError) as exc:
        raise WeightspaceError("invalid SafeTensors checkpoint") from exc
    tensors = {}
    for name, item in entries:
        require(bool(name) and item["dtype"] in DTYPES, "unsupported tensor name or dtype")
        tensors[name] = Tensor(item["dtype"], tuple(item["shape"]), bytes(item["data"]))
    return tensors


def checkpoint(source, max_bytes: int) -> tuple[bytes, dict[str, Tensor]]:
    require(type(max_bytes) is int and max_bytes > 0, "max_bytes must be a positive integer")
    if isinstance(source, (str, Path)):
        raw = _read(Path(source), max_bytes)
        return raw, unpack(raw)
    require(isinstance(source, Mapping), "expected a SafeTensors path or named ndarray mapping")
    tensors: dict[str, Tensor] = {}
    arrays: list[np.ndarray] = []
    total = 0
    for name, array in source.items():
        require(isinstance(name, str) and bool(name) and name != "__metadata__", "invalid tensor name")
        require(isinstance(array, np.ndarray), "mapping values must be NumPy arrays")
        require(
            not any(np.may_share_memory(array, old) for old in arrays), "overlapping tensor mappings are unsupported"
        )
        arrays.append(array)
        total += array.nbytes
        require(total <= max_bytes, "checkpoint exceeds byte budget")
        dtype = next((key for key, value in DTYPES.items() if value == array.dtype.name), None)
        require(dtype is not None, "unsupported tensor dtype")
        little = array.astype(array.dtype.newbyteorder("<"), copy=False)
        tensors[name] = Tensor(dtype, array.shape, little.tobytes(order="C"))
    raw = serialize(tensors)
    require(len(raw) <= max_bytes, "checkpoint exceeds byte budget")
    return raw, tensors
