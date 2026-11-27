"""Canonical, bounded schema-1 aggregate ZIP transport; native results stay declarations."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import struct
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quantfit import bundle
from quantfit.resolution import MAX_REPORT_BYTES
from quantfit.safety.calibration_binding import MAX_CALIBRATION_BYTES
from quantfit.safety.retention_io import HeldFile, _stamp, admit_outputs, canonical, hold

MAX_PAYLOAD_BYTES = 3 * MAX_REPORT_BYTES + MAX_CALIBRATION_BYTES + bundle.MAX_MANIFEST_BYTES
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
ORDER = ("manifest.json", *bundle.ROLES.values())
LIMITS = {name: MAX_REPORT_BYTES for name in ORDER}
LIMITS.update({"manifest.json": bundle.MAX_MANIFEST_BYTES, "calibration.json": MAX_CALIBRATION_BYTES})
SCOPE = (
    "Canonical offline aggregate transport and native relationship checks only. Original adverse verdicts "
    "and unknowns remain declarations; intact transport is not scientific PASS or authentication. "
    "No captures, labels, model assets, redaction, network or referenced producer paths are followed. "
    "Archive publication is exclusive and atomic; restored directory publication is manifest-last, "
    "not a directory transaction or protection against every hostile concurrent rename."
)


def _require(condition: bool) -> None:
    if not condition:
        raise bundle.BundleError("invalid_bundle_transport")


def _identity(path: Path) -> tuple[int, int]:
    bundle._no_links(path)
    value = path.lstat()
    return value.st_dev, value.st_ino


def _directory(path: Path, identity: tuple[int, int]) -> bool:
    return _identity(path) == identity and stat.S_ISDIR(path.lstat().st_mode)


def _inventory(root: Path, names: set[str]) -> None:
    seen: set[str] = set()
    with os.scandir(root) as entries:
        for entry in entries:
            _require(entry.name in names and entry.name not in seen)
            seen.add(entry.name)
    _require(seen == names)


def _native(files: dict[str, bytes]) -> tuple[dict[str, Any], dict[str, Any]]:
    _require("manifest.json" in files and set(files) <= set(ORDER))
    _require(sum(map(len, files.values())) <= MAX_PAYLOAD_BYTES)
    manifest = bundle._manifest(files["manifest.json"])
    _require(set(files) == {"manifest.json", *(entry["path"] for entry in manifest["files"])})
    data = {entry["role"]: files[entry["path"]] for entry in manifest["files"]}
    declarations, mismatches = bundle._checked_payloads(manifest, data)
    _require(not mismatches)
    return manifest, declarations


def _encode(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name in ORDER:
            if name in files:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                archive.writestr(info, files[name])
    raw = buffer.getvalue()
    _require(len(raw) <= MAX_ARCHIVE_BYTES)
    return raw


def _decode(raw: bytes) -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any]]:
    _require(22 <= len(raw) <= MAX_ARCHIVE_BYTES)
    # The SDK reads ZIP64 despite allowZip64=False and can override classic bounds.
    _require(raw[-42:-38] != b"PK\x06\x07")
    # Bound central-directory work BEFORE ZipFile constructs an unbounded list.
    magic, disk, central_disk, disk_n, n, size, offset, comment = struct.unpack("<4s4H2LH", raw[-22:])
    _require(magic == b"PK\x05\x06" and disk == central_disk == comment == 0 and disk_n == n and 2 <= n <= 5)
    _require(size <= 5 * (46 + max(map(len, ORDER))) and offset + size == len(raw) - 22)
    files = {}
    with zipfile.ZipFile(io.BytesIO(raw), "r", allowZip64=False) as archive:
        entries = archive.infolist()
        _require(len(entries) == n and not archive.comment)
        remaining = MAX_PAYLOAD_BYTES
        for entry in entries:
            name = entry.filename
            _require(entry.orig_filename == name and name in ORDER and name not in files)
            _require(not entry.is_dir() and entry.compress_type == zipfile.ZIP_STORED and entry.flag_bits == 0)
            _require(0 < entry.file_size == entry.compress_size <= min(LIMITS[name], remaining))
            _require(entry.create_system == 3 and entry.external_attr == (stat.S_IFREG | 0o600) << 16)
            _require(not entry.extra and not entry.comment)
            # SDK checks local/central names, overlaps, exact stored sizes and CRC.
            with archive.open(entry) as stream:
                data = stream.read(entry.file_size + 1)
            _require(len(data) == entry.file_size)
            files[name] = data
            remaining -= len(data)
    manifest, declarations = _native(files)
    # Closed format: refuse alternate headers, offsets, order, trailers or metadata.
    _require(_encode(files) == raw)
    return files, manifest, declarations


def _result(raw: bytes, manifest: dict[str, Any], declarations: dict[str, Any]) -> dict[str, Any]:
    return {
        "bundle_transport_schema": 1,
        "bundle_schema": 1,
        "archive": {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)},
        "manifest": manifest,
        "integrity_verified": True,
        "scientific_claims_verified": False,
        "declared_results": declarations,
        "scope": SCOPE,
    }


def _receive(path: str, expected_sha256: str) -> tuple[HeldFile, dict[str, bytes], dict[str, Any]]:
    _require(type(expected_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None)
    held = hold(path, MAX_ARCHIVE_BYTES)
    _require(hashlib.sha256(held.data).hexdigest() == expected_sha256)
    files, manifest, declarations = _decode(held.data)
    return held, files, _result(held.data, manifest, declarations)


def _publish_archive(
    out_path: str, raw: bytes, inputs: tuple[HeldFile, ...], *, recheck: Callable[[], None] | None = None
) -> None:
    target = admit_outputs((out_path,), inputs)[0]
    stage: Path | None = None
    identity: tuple[int, int] | None = None
    descriptor, name = tempfile.mkstemp(prefix=".quantfit-archive-", dir=target.path.parent)
    try:
        stage = Path(name)
        info = os.fstat(descriptor)
        identity = info.st_dev, info.st_ino
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            _require(stream.write(raw) == len(raw))
            stream.flush()
            os.fsync(stream.fileno())
        _require(hold(stage, len(raw)).data == raw and _identity(stage) == identity)
        for held in inputs:
            held.check()
        if recheck is not None:
            recheck()
        target.check()
        # Same-parent hard link is atomic and no-replace on supported filesystems.
        # Unsupported linking refuses; never fall back to replacing rename.
        os.link(stage, target.path, follow_symlinks=False)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if identity is None or stage is None:
            raise bundle.BundleError("archive_stage_preserved") from None
        try:
            _require(_identity(stage) == identity)
            stage.unlink()
        except (OSError, RuntimeError):
            raise bundle.BundleError("archive_stage_preserved") from None


def pack_bundle(bundle_path: str, out_path: str, *, kind: str = "aggregate") -> dict[str, Any]:
    """Hold one explicitly selected native kind; aggregate is the unchanged default."""
    _require(type(kind) is str and kind in ("aggregate", "replay", "screen"))
    if kind != "aggregate":
        from quantfit.bundle_archive_kinds import pack

        return pack(bundle_path, out_path, kind=kind)
    try:
        root = canonical(bundle_path)
        identity = _identity(root)
        _require(_directory(root, identity))
        _require(not canonical(out_path).is_relative_to(root))
        first = hold(root / "manifest.json", bundle.MAX_MANIFEST_BYTES)
        manifest = bundle._manifest(first.data)
        names = {"manifest.json", *(entry["path"] for entry in manifest["files"])}
        _inventory(root, names)
        inputs = [first]
        remaining = MAX_PAYLOAD_BYTES - len(first.data)
        for name in ORDER[1:]:
            if name in names:
                item = hold(root / name, min(LIMITS[name], remaining))
                inputs.append(item)
                remaining -= len(item.data)
        files = {held.path.name: held.data for held in inputs}
        manifest, declarations = _native(files)
        raw = _encode(files)
        _require(_directory(root, identity))
        _inventory(root, names)
        _publish_archive(out_path, raw, tuple(inputs))
        return _result(raw, manifest, declarations)
    except bundle.BundleError as exc:
        if str(exc) == "archive_stage_preserved":
            raise
        raise bundle.BundleError("invalid_bundle_transport") from None
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, RecursionError, zipfile.BadZipFile):
        raise bundle.BundleError("invalid_bundle_transport") from None


def verify_bundle_archive(
    archive_path: str, expected_sha256: str, *, kind: str = "aggregate", out_path: str | None = None
) -> dict[str, Any]:
    """Pin and validate the selected container and optionally save its native receipt."""
    _require(type(kind) is str and kind in ("aggregate", "replay", "screen"))
    try:
        if kind == "aggregate":
            held, _, result = _receive(archive_path, expected_sha256)
        else:
            from quantfit.bundle_archive_kinds import _receive as receive_kind

            held, _, result = receive_kind(archive_path, expected_sha256, kind)
        held.check()
        if out_path is not None:
            raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
            _publish_archive(out_path, raw, (held,))
        return result
    except bundle.BundleError as exc:
        if str(exc) == "archive_stage_preserved":
            raise
        raise bundle.BundleError("invalid_bundle_transport") from None
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, RecursionError, zipfile.BadZipFile):
        raise bundle.BundleError("invalid_bundle_transport") from None


def _owned_bytes(root: Path, identity: tuple[int, int], member: tuple[Path, tuple[int, int], bytes]) -> bytes:
    path, expected_id, raw = member
    _require(_directory(root, identity) and _identity(path) == expected_id)
    info = path.lstat()
    _require((info.st_dev, info.st_ino) == expected_id and stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
    observed = bundle._read(path, len(raw))
    _require(_directory(root, identity) and _identity(path) == expected_id and _stamp(path.lstat()) == _stamp(info))
    return observed


def _remove_owned(root: Path, identity: tuple[int, int], member: tuple[Path, tuple[int, int], bytes]) -> None:
    path, _, raw = member
    _require(raw.startswith(_owned_bytes(root, identity, member)))
    path.unlink()


def _cleanup(root: Path, identity: tuple[int, int], owned: list[tuple[Path, tuple[int, int], bytes]]) -> bool:
    """Only inode-attested expected-prefix files; never recurse or delete unknown entries."""
    try:
        _require(_directory(root, identity))
        # Revoke an owned readiness manifest even if an unrelated entry prevents full rollback.
        if owned and owned[-1][0].name == "manifest.json":
            _remove_owned(root, identity, owned[-1])
            owned = owned[:-1]
        _inventory(root, {path.name for path, _, _ in owned})
        for member in reversed(owned):
            _remove_owned(root, identity, member)
        _require(_directory(root, identity))
        root.rmdir()
        return True
    except (OSError, RuntimeError):
        return False


def _publish_flat_bundle(
    root: Path,
    files: dict[str, bytes],
    *,
    order: tuple[str, ...],
    recheck: Callable[[], None] | None = None,
    directory_mode: int = 0o777,
    member_mode: int = 0o666,
) -> None:
    """Publish original flat members, then advertise readiness with the manifest."""
    bundle._no_links(root)
    identity: tuple[int, int] | None = None
    owned: list[tuple[Path, tuple[int, int], bytes]] = []
    root.mkdir(mode=directory_mode)
    try:
        identity = _identity(root)
        # The exact original manifest is readiness and is published last.
        for name in (*order[1:], order[0]):
            if name not in files:
                continue
            _require(_directory(root, identity))
            if recheck is not None:
                recheck()
            if name == order[0]:
                _inventory(root, {path.name for path, _, _ in owned})
            path, raw = root / name, files[name]
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
                member_mode,
            )
            try:
                info = os.fstat(descriptor)
                owned.append((path, (info.st_dev, info.st_ino), raw))
                with os.fdopen(descriptor, "wb") as stream:
                    descriptor = -1
                    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
                    _require(stream.write(raw) == len(raw))
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            _require(_directory(root, identity) and _identity(path) == owned[-1][1])
        if recheck is not None:
            recheck()
        _inventory(root, set(files))
        for member in owned:
            _require(_owned_bytes(root, identity, member) == member[2])
    except BaseException:
        if identity is None or not _cleanup(root, identity, owned):
            raise bundle.BundleError("partial_destination_preserved") from None
        raise


def _restore(root: Path, files: dict[str, bytes], held: HeldFile, *, order: tuple[str, ...] = ORDER) -> None:
    target = admit_outputs((str(root),), (held,))[0]
    target.check()
    held.check()
    _publish_flat_bundle(root, files, order=order, recheck=held.check, directory_mode=0o700, member_mode=0o600)


def unpack_bundle(archive_path: str, expected_sha256: str, out_path: str, *, kind: str = "aggregate") -> dict[str, Any]:
    """Validate the selected kind, then restore into a newly reserved directory."""
    _require(type(kind) is str and kind in ("aggregate", "replay", "screen"))
    if kind != "aggregate":
        from quantfit.bundle_archive_kinds import unpack

        return unpack(archive_path, expected_sha256, out_path, kind=kind)
    try:
        held, files, result = _receive(archive_path, expected_sha256)
        _restore(canonical(out_path), files, held)
        return result
    except bundle.BundleError as exc:
        if str(exc) == "partial_destination_preserved":
            raise
        raise bundle.BundleError("invalid_bundle_transport") from None
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, RecursionError, zipfile.BadZipFile):
        raise bundle.BundleError("invalid_bundle_transport") from None
