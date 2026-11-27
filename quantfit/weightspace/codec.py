"""Encode and reconstruct compatible checkpoints from pinned local artifacts."""

from __future__ import annotations

import json
import re
from functools import wraps
from pathlib import Path, PureWindowsPath

import numpy as np

from quantfit.bundle import BundleError, _read
from quantfit.bundle_transport import _publish_archive, _publish_flat_bundle
from quantfit.safety.retention_io import RetainedLabelsError

from . import _lowbit, _vectors
from ._tensors import (
    MAX_FILE_BYTES,
    MAX_MANIFEST_BYTES,
    SCHEMA,
    Tensor,
    WeightspaceError,
    canonical,
    checkpoint,
    identity,
    ordered_records,
    read_json,
    records,
    require,
    serialize,
    sha,
    unpack,
)

XOR = "xor-bytes-v1"


def _public_io(operation):
    @wraps(operation)
    def checked(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except (OSError, BundleError, RetainedLabelsError) as exc:
            raise WeightspaceError(str(exc)) from exc

    return checked


def _xor(left: bytes, right: bytes) -> bytes:
    require(len(left) == len(right), "incompatible XOR byte lengths")
    return np.bitwise_xor(np.frombuffer(left, "u1"), np.frombuffer(right, "u1")).tobytes()


def file_record(name: str, data: bytes, role: str, phases: list[str]) -> dict:
    return {"path": name, "role": role, "phases": phases, "size_bytes": len(data), "sha256": sha(data)}


def publish(out, manifest: dict, files: dict[str, bytes]) -> dict:
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    require(len(raw) <= MAX_MANIFEST_BYTES, "manifest exceeds size limit")
    members = {"manifest.json": raw, **files}
    _publish_flat_bundle(Path(out), members, order=tuple(members))
    total = sum(map(len, members.values()))
    return {
        "manifest_sha256": sha(raw),
        "cold_bytes": total,
        "incremental_bytes": total - sum(f["size_bytes"] for f in manifest["files"] if f["role"] == "base"),
        "identities": manifest["identities"],
        "codec": manifest["codec"]["id"],
    }


@_public_io
def encode(
    base,
    target,
    out,
    *,
    codec: str = XOR,
    bits: int | None = None,
    group_size: int | None = None,
    max_bytes: int = MAX_FILE_BYTES,
) -> dict:
    """Publish a new local artifact. Inputs are SafeTensors paths or named NumPy arrays."""
    require(codec in (XOR, _vectors.TASK, _lowbit.LOWBIT), "unsupported weight-space codec")
    params = {}
    if codec == _lowbit.LOWBIT:
        params = _lowbit.parameters(4 if bits is None else bits, 64 if group_size is None else group_size)
    else:
        require(bits is None and group_size is None, "bit and group settings require grouped-int-v1")
    base_raw, original = checkpoint(base, max_bytes)
    _, wanted = checkpoint(target, max_bytes)
    require(bool(original) and original.keys() == wanted.keys(), "incompatible or empty tensor inventory")
    ids = {"base": identity(original), "target": identity(wanted)}
    if codec != XOR:
        changes, metadata, reconstructed = _vectors.extract(original, wanted)
        if codec == _lowbit.LOWBIT:
            changes, metadata, reconstructed = _lowbit.pack(original, wanted, changes, metadata, **params)
        ids["reconstructed"] = identity(reconstructed)
    else:
        unchanged, changes = [], {}
        for name in sorted(original):
            a, b = original[name], wanted[name]
            require((a.dtype, a.shape) == (b.dtype, b.shape), f"incompatible layout for {name}")
            if a.data == b.data:
                unchanged.append(name)
            else:
                changes[name] = Tensor("U8", (len(a.data),), _xor(a.data, b.data))
        metadata = {"unchanged": unchanged}
    delta = serialize(changes)
    require(len(delta) <= max_bytes, "delta exceeds byte budget")
    files = {"base.safetensors": base_raw, "delta.safetensors": delta}
    manifest = {
        "schema": SCHEMA,
        "codec": {"id": codec, "exact": codec == XOR, "parameters": params},
        "identities": ids,
        "files": [
            file_record(name, data, role, ["decode"]) for (name, data), role in zip(files.items(), ("base", "payload"))
        ],
        "tensors": records(wanted),
        "metadata": metadata,
    }
    receipt = publish(out, manifest, files)
    if codec != XOR:
        receipt.update(
            changed_tensors=len(original) - len(metadata["unchanged"]), max_abs_error=metadata["max_abs_error"]
        )
    return receipt


def _artifacts(doc: dict, root: Path, max_bytes: int, *, roles=("base", "payload"), phases=None) -> dict[str, bytes]:
    if phases is None:
        phases = ["decode"]
    require(isinstance(doc.get("files"), list) and len(doc["files"]) == len(roles), "incorrect artifact role count")
    held: dict[str, bytes] = {}
    names: set[str] = set()
    for item in doc["files"]:
        require(isinstance(item, dict), "invalid artifact file")
        name, role = item.get("path"), item.get("role")
        require(isinstance(name, str) and name and not PureWindowsPath(name).drive, "invalid relative artifact path")
        for part in name.split("/"):
            require(
                part not in {"", ".", ".."}
                and not part.endswith((" ", "."))
                and not PureWindowsPath(part).is_reserved()
                and not any(ord(ch) < 32 or ch in '<>:"\\|?*' for ch in part),
                "invalid relative artifact path",
            )
        require(name.casefold() not in names and role in roles and role not in held, "duplicate role or path")
        require(item.get("phases") == phases, "unsupported artifact phases")
        size = item.get("size_bytes")
        require(type(size) is int and 0 <= size <= max_bytes, "invalid artifact byte count")
        raw = _read(root / name, size)
        require(len(raw) == size and sha(raw) == item.get("sha256"), "artifact digest or size mismatch")
        held[role] = raw
        names.add(name.casefold())
    return held


@_public_io
def decode(base, artifact, out, *, scale: float = 1.0, max_bytes: int = MAX_FILE_BYTES) -> dict:
    """Verify all commitments and write a new SafeTensors checkpoint without replacing an existing file."""
    path = Path(artifact)
    doc = read_json(_read(path, MAX_MANIFEST_BYTES))
    require(doc.get("schema") == SCHEMA, "unsupported weight-space manifest schema")
    declaration = doc.get("codec")
    require(isinstance(declaration, dict), "missing codec declaration")
    codec = declaration.get("id")
    params = {}
    if codec == _lowbit.LOWBIT:
        supplied = declaration.get("parameters")
        require(isinstance(supplied, dict), "missing group parameters")
        params = _lowbit.parameters(supplied.get("bits"), supplied.get("group_size"))
    require(
        codec in (XOR, _vectors.TASK, _lowbit.LOWBIT)
        and canonical(declaration) == canonical({"id": codec, "exact": codec == XOR, "parameters": params}),
        "unsupported codec declaration",
    )
    require(type(scale) in (int, float) and (codec != XOR or scale == 1), "exact XOR cannot be scaled")
    _, original = checkpoint(base, max_bytes)
    files = _artifacts(doc, path.parent, max_bytes)
    ids = doc.get("identities")
    require(
        isinstance(ids, dict) and all(isinstance(v, str) and re.fullmatch("[0-9a-f]{64}", v) for v in ids.values()),
        "invalid identity commitment",
    )
    require(
        isinstance(ids, dict) and ids.get("base") == identity(original) == identity(unpack(files["base"])),
        "wrong decode base",
    )
    delta = unpack(files["payload"])
    if codec != XOR:
        if codec == _lowbit.LOWBIT:
            delta = _lowbit.unpack(original, delta, doc.get("metadata"), **params)
        result = _vectors.restore(original, delta, doc, scale)
    else:
        require(isinstance(doc.get("metadata"), dict), "missing codec metadata")
        unchanged = doc["metadata"].get("unchanged")
        require(
            isinstance(unchanged, list)
            and all(isinstance(n, str) for n in unchanged)
            and len(set(unchanged)) == len(unchanged),
            "invalid unchanged tensor list",
        )
        require(
            set(unchanged).isdisjoint(delta) and set(unchanged) | delta.keys() == original.keys(),
            "payload coverage disagrees with base",
        )
        result = dict(original)
        for name, tensor in delta.items():
            a = original[name]
            require(tensor.dtype == "U8" and tensor.shape == (len(a.data),), "invalid XOR tensor layout")
            result[name] = Tensor(a.dtype, a.shape, _xor(a.data, tensor.data))
        require(
            canonical(ordered_records(doc.get("tensors"))) == canonical(records(result))
            and identity(result) == ids.get("target"),
            "decoded tensor commitment mismatch",
        )
    output = serialize(result)
    require(len(output) <= max_bytes, "decoded checkpoint exceeds byte budget")
    _publish_archive(str(out), output, ())
    return {
        "logical_sha256": identity(result),
        "file_sha256": sha(output),
        "size_bytes": len(output),
        "tensor_count": len(result),
        "codec": codec,
        **({"scale": scale} if codec != XOR else {}),
    }
