"""Bounded little-endian GGUF2/3 directory scanner; tensor payload is not interpreted."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import struct
from pathlib import Path

MAX_DIRECTORY_BYTES = 128 * 1024 * 1024
MAX_STRING_BYTES = 1024 * 1024
MAX_METADATA = 100000
MAX_TENSORS = 100000
MAX_ARRAY_ITEMS = 2000000
_KEY = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:_[a-z0-9]+)*)*\Z")
# The format's standardized source keys explicitly contain decimal index segments.
# b9817 Metadata.set_gguf_meta_model emits these and quantization preserves them.
_INDEXED_SOURCE_KEY = re.compile(
    r"general\.(?:base_model|dataset)\.[0-9]+\."
    r"(?:name|author|version|organization|description|url|doi|uuid|repo_url)\Z"
)
_SCALARS = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "B", 10: "Q", 11: "q", 12: "d"}


class InvalidGguf(ValueError):
    """Demonstrated invalid/truncated supported binary; exit 3."""


class UnsupportedGguf(RuntimeError):
    """Outside the bounded supported profile or unavailable capability; exit 2."""


def _valid(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidGguf(message)


def _supported(condition: bool, message: str) -> None:
    if not condition:
        raise UnsupportedGguf(message)


def identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


class Reader:
    def __init__(self, stream, size: int):
        self.stream, self.size, self.position = stream, size, 0
        self.items, self.digest = 0, hashlib.sha256()

    def read(self, count: int) -> bytes:
        _valid(count <= self.size - self.position, "truncated GGUF declaration")
        _supported(self.position + count <= MAX_DIRECTORY_BYTES, "GGUF directory exceeds bounded profile")
        raw = self.stream.read(count)
        _valid(len(raw) == count, "GGUF changed or truncated while reading")
        self.position += count
        self.digest.update(raw)
        return raw

    def number(self, kind: str):
        return struct.unpack("<" + kind, self.read(struct.calcsize(kind)))[0]

    def string(self, maximum: int = MAX_STRING_BYTES, *, format_bound: bool = False) -> str:
        count = self.number("Q")
        _valid(count <= self.size - self.position, "truncated GGUF string")
        if format_bound:
            _valid(count <= maximum, "GGUF key/tensor name exceeds specified format length")
        else:
            _supported(count <= maximum, "GGUF string exceeds bounded profile")
        try:
            return self.read(count).decode("utf-8")
        except UnicodeError:
            raise InvalidGguf("GGUF string is not valid UTF8") from None

    def value(self, tag: int, *, keep: bool = False):
        if tag == 8:
            value = self.string()
            return value if keep else None
        if tag == 9:
            subtype, length = self.number("I"), self.number("Q")
            _supported(subtype != 9, "nested GGUF arrays are outside this bounded profile")
            _supported(subtype in _SCALARS or subtype == 8, "unknown GGUF array subtype is unverified")
            self.items += length
            _supported(self.items <= MAX_ARRAY_ITEMS, "GGUF array population exceeds bounded profile")
            if subtype == 8:
                _valid(length * 8 <= self.size - self.position, "truncated GGUF string array")
                for _ in range(length):
                    self.string()
            else:
                remaining = length * struct.calcsize(_SCALARS[subtype])
                _valid(remaining <= self.size - self.position, "truncated GGUF typed array")
                _supported(self.position + remaining <= MAX_DIRECTORY_BYTES, "GGUF array bytes exceed bounded profile")
                while remaining:
                    raw = self.read(min(65536, remaining))
                    if subtype == 7:
                        _valid(all(value in (0, 1) for value in raw), "invalid GGUF boolean array encoding")
                    remaining -= len(raw)
            return None  # Arrays are validated without retaining tokenizer/payload contents.
        _supported(tag in _SCALARS, "unknown GGUF metadata type is unverified")
        value = self.number(_SCALARS[tag])
        if tag == 7:
            _valid(value in (0, 1), "invalid GGUF boolean encoding")
        return value if keep else None


def scan(path: str) -> tuple[dict, dict, tuple[int, int, int, int]]:
    """One resolved readonly regular FD; metadata held selectively, payload extents checked."""
    resolved = Path(path).resolve(strict=True)  # Readonly Hub-cache symlinks resolve to canonical blobs.
    descriptor = os.open(
        resolved, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(descriptor, "rb") as stream:
        initial = os.fstat(stream.fileno())
        _supported(stat.S_ISREG(initial.st_mode), "GGUF verification requires a regular file")
        reader = Reader(stream, initial.st_size)
        _valid(reader.read(4) == b"GGUF", "invalid GGUF magic")
        version_raw = reader.read(4)
        version = struct.unpack("<I", version_raw)[0]
        _supported(
            struct.unpack(">I", version_raw)[0] not in (1, 2, 3),
            "big-endian GGUF is unverified by this little-endian profile",
        )
        _valid(version != 0, "invalid GGUF version zero")
        _supported(version in (2, 3), "GGUF version is outside supported2/3 profile")
        tensors, metadata = reader.number("Q"), reader.number("Q")
        _valid(
            tensors * 32 + metadata * 13 <= initial.st_size - reader.position, "GGUF directory counts cannot fit file"
        )
        _supported(0 < tensors <= MAX_TENSORS and metadata <= MAX_METADATA, "GGUF nonempty/count profile exceeded")
        try:
            from gguf.constants import GGML_QUANT_SIZES, GGMLQuantizationType, GGUFValueType, LlamaFileType
        except ImportError:
            raise UnsupportedGguf("GGUF constants require the optional package: pip install 'quantfit[gguf]'") from None
        keys, selected, alignment = set(), {}, 32
        selected_types = {
            "general.architecture": 8,
            "general.file_type": 4,
            "general.name": 8,
            "tokenizer.chat_template": 8,
        }
        for _ in range(metadata):
            key = reader.string(65535, format_bound=True)
            _valid(
                key.isascii() and (_KEY.fullmatch(key) is not None or _INDEXED_SOURCE_KEY.fullmatch(key) is not None),
                "invalid hierarchical ASCII lower_snake_case GGUF key",
            )
            _valid(key not in keys, "duplicate GGUF metadata key")
            keys.add(key)
            tag = reader.number("I")
            _supported(tag in {int(t) for t in GGUFValueType}, "unknown GGUF metadata type is unverified")
            _valid(key not in selected_types or tag == selected_types[key], "invalid selected GGUF metadata type")
            _valid(key != "general.alignment" or tag == 4, "GGUF alignment must be UINT32")
            value = reader.value(tag, keep=key in selected_types or key == "general.alignment")
            if key == "general.alignment":
                _valid(value > 0 and value & (value - 1) == 0, "invalid GGUF alignment")
                alignment = value
            elif key in selected_types:
                selected[key] = value
        names, intervals, counts, packed = set(), [], {}, 0
        for _ in range(tensors):
            name = reader.string(64, format_bound=True)
            _valid(name not in names, "duplicate GGUF tensor name")
            names.add(name)
            rank = reader.number("I")
            _supported(1 <= rank <= 4, "GGUF tensor rank is outside supported1..4 profile")
            dimensions = [reader.number("Q") for _ in range(rank)]
            _valid(all(n > 0 for n in dimensions), "GGUF tensor dimensions must be positive")
            tag, offset = reader.number("I"), reader.number("Q")
            try:
                kind = GGMLQuantizationType(tag)
            except ValueError:
                raise UnsupportedGguf("unknown GGUF tensor type has unverified extent") from None
            _supported(kind in GGML_QUANT_SIZES, "GGUF tensor packing is outside the SDK extent profile")
            block, block_bytes = GGML_QUANT_SIZES[kind]
            _valid(dimensions[0] % block == 0, "GGUF tensor ne0 row is not divisible by quantization block")
            size = dimensions[0] // block * block_bytes
            for dimension in dimensions[1:]:
                size *= dimension  # Python integers; no NumPy overflow or payload allocation.
            _valid(offset % alignment == 0, "GGUF tensor offset is not aligned")
            intervals.append((offset, offset + size))
            counts[kind.name] = counts.get(kind.name, 0) + 1
            packed += block > 1
        start = reader.position + (-reader.position % alignment)
        _valid(start <= initial.st_size, "GGUF tensor data start exceeds EOF")
        end = 0
        for lower, upper in sorted(intervals):
            _valid(lower >= end and upper <= initial.st_size - start, "GGUF tensor intervals overlap or exceed EOF")
            end = upper
        _supported(
            identity(os.fstat(stream.fileno())) == identity(initial),
            "GGUF file identity changed during structural scan",
        )
        file_type = selected.get("general.file_type")
        try:
            file_type_name = (
                LlamaFileType(file_type).name.removeprefix("MOSTLY_").removeprefix("ALL_")
                if file_type is not None
                else None
            )
        except ValueError:
            file_type_name = None  # Unknown metadata declaration is not a tensor-size claim.
        facts = {
            "status": "pass",
            "version": version,
            "byte_order": "little",
            "file_size_bytes": initial.st_size,
            "metadata_entries": metadata,
            "tensor_count": tensors,
            "tensor_types": counts,
            "packed_tensors": packed,
            "alignment_bytes": alignment,
            "data_start_bytes": start,
            "directory_bytes_read": reader.position,
            "directory_sha256": reader.digest.hexdigest(),
            "tensor_payload_interpreted": False,
            "general_file_type_code": file_type,
            "general_file_type_name": file_type_name,
            "profile": "nonempty little-endian GGUF2/3; scalar/non-nested typed arrays; rank1..4; aligned nonoverlapping complete extents",
        }
        return {"path": str(resolved), **facts}, selected, identity(initial)
