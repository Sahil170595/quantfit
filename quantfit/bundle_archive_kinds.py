"""Explicit replay/screen ZIP profiles; native held verification stays authoritative."""

from __future__ import annotations

import hashlib
import io
import re
import stat
import struct
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quantfit import bundle
from quantfit import bundle_transport as transport
from quantfit import replay_bundle as replay
from quantfit import screen_bundle_inputs as screen
from quantfit import screen_bundle_publication as publication
from quantfit.resolution import MAX_REPORT_BYTES
from quantfit.safety.retention_io import HeldFile, _check_ancestors, admit_outputs, canonical, hold
from quantfit.screen import _SAFE_NAME, SUMMARY_FILENAME

REPLAY_ORDER = ("manifest.json", *replay.ROLES.values())
MAX_REPLAY_PAYLOAD_BYTES = 4 * MAX_REPORT_BYTES + bundle.MAX_MANIFEST_BYTES
MAX_REPLAY_CANONICAL_BYTES = MAX_REPLAY_PAYLOAD_BYTES + 520
MAX_SCREEN_CENTRAL_BYTES = 259 * (46 + 77)
SCOPE = (
    "Explicit canonical offline replay or screen transport and native held verification only. "
    "Original reports, T0, target population, adverse verdicts and unknowns are preserved. "
    "Whole-container integrity is not safety PASS, scientific GO or authentication. Producer paths "
    "are labels, never followed. No captures, labels, model assets or network work. Archive publication "
    "is exclusive; restoration is manifest-last with owned-only cleanup, not a directory transaction "
    "or a guarantee against every hostile concurrent rename."
)


@dataclass(frozen=True)
class _Profile:
    raw_bytes: int
    payload_bytes: int
    minimum: int
    maximum: int
    central_bytes: int
    name_bytes: int
    manifest_bytes: int
    member_bytes: int
    targets_bytes: int


REPLAY = _Profile(
    33 * 1024 * 1024, MAX_REPLAY_PAYLOAD_BYTES, 5, 5, 295, 13, bundle.MAX_MANIFEST_BYTES, MAX_REPORT_BYTES, 0
)
SCREEN = _Profile(
    65 * 1024 * 1024,
    screen.MAX_TRANSPORT_BYTES,
    2,
    259,
    MAX_SCREEN_CENTRAL_BYTES,
    77,
    screen.MAX_OUTER_BYTES,
    screen.MAX_MEMBER_BYTES,
    screen.MAX_TARGETS_BYTES,
)


def _profile(kind: str) -> _Profile:
    transport._require(type(kind) is str and kind in ("replay", "screen"))
    return REPLAY if kind == "replay" else SCREEN


def _limit(name: str, kind: str) -> int:
    profile = _profile(kind)
    if kind == "replay":
        transport._require(name in REPLAY_ORDER)
        return profile.manifest_bytes if name == "manifest.json" else profile.member_bytes
    if name == "manifest.json":
        return profile.manifest_bytes
    if name == "targets.json":
        return profile.targets_bytes
    transport._require(name.startswith("reports/") and name.endswith(".json"))
    bare = name.removeprefix("reports/")
    transport._require(bare == SUMMARY_FILENAME or bool(_SAFE_NAME.fullmatch(bare.removesuffix(".json"))))
    return profile.member_bytes


def _native(files: dict[str, bytes], kind: str) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]:
    transport._require("manifest.json" in files)
    if kind == "replay":
        transport._require(set(files) == set(REPLAY_ORDER))
        manifest = replay._manifest(files["manifest.json"])
        data = {role: files[name] for role, name in replay.ROLES.items()}
        transport._require(not replay._checked_payloads(manifest, data))
        original, receiving = replay._validate(data, [replay.ROLES[f"replicate-{i}"] for i in range(1, 4)])
        native = {
            "bundle_schema": replay.BUNDLE_SCHEMA,
            "original_t0": original,
            "receiving_t0": receiving,
            "producer_locations_verified": False,
            "scientific_claims_verified": False,
            "scope": replay.SCOPE,
        }
        return manifest, native, REPLAY_ORDER
    manifest = screen._outer(files["manifest.json"])
    rows = [*manifest["reports"], manifest["producer_summary"]]
    present = tuple(row["path"] for row in rows if row["status"] == "present")
    order = ("manifest.json", "targets.json", *present)
    transport._require(len(set(order)) == len(order) and set(files) == set(order))
    return manifest, screen._verify_held(_screen_payload(files)), order


def _screen_payload(files: dict[str, bytes]) -> screen._HeldScreen:
    return screen._HeldScreen(
        files["manifest.json"],
        files["targets.json"],
        tuple((name.removeprefix("reports/"), raw) for name, raw in files.items() if name.startswith("reports/")),
    )


def _encode(files: dict[str, bytes], order: tuple[str, ...], kind: str) -> bytes:
    profile = _profile(kind)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name in order:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, files[name])
    raw = buffer.getvalue()
    transport._require(len(raw) <= profile.raw_bytes)
    return raw


def _decode(raw: bytes, kind: str) -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any]]:
    profile = _profile(kind)
    transport._require(22 <= len(raw) <= profile.raw_bytes)
    transport._require(raw[-42:-38] != b"PK\x06\x07")
    magic, disk, central_disk, disk_n, n, size, offset, comment = struct.unpack("<4s4H2LH", raw[-22:])
    transport._require(
        magic == b"PK\x05\x06"
        and disk == central_disk == comment == 0
        and disk_n == n
        and profile.minimum <= n <= profile.maximum
    )
    transport._require(size <= profile.central_bytes and offset + size == len(raw) - 22)
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(raw), "r", allowZip64=False) as archive:
        entries = archive.infolist()
        transport._require(len(entries) == n and not archive.comment)
        remaining = profile.payload_bytes
        seen = set()
        # Admit every central member/size before any potentially large payload read.
        for entry in entries:
            name = entry.filename
            transport._require(entry.orig_filename == name and name.casefold() not in seen)
            transport._require(len(name.encode("ascii")) <= profile.name_bytes)
            limit = _limit(name, kind)
            transport._require(
                not entry.is_dir() and entry.compress_type == zipfile.ZIP_STORED and entry.flag_bits == 0
            )
            transport._require(0 < entry.file_size == entry.compress_size <= min(limit, remaining))
            transport._require(entry.create_system == 3 and entry.external_attr == (stat.S_IFREG | 0o600) << 16)
            transport._require(not entry.extra and not entry.comment)
            remaining -= entry.file_size
            seen.add(name.casefold())
        for entry in entries:
            # ZipFile enforces local/central names, overlaps, stored size and CRC.
            with archive.open(entry) as stream:
                data = stream.read(entry.file_size + 1)
            transport._require(len(data) == entry.file_size)
            files[entry.filename] = data
    manifest, native, order = _native(files, kind)
    transport._require(_encode(files, order, kind) == raw)
    return files, manifest, native


def _result(raw: bytes, kind: str, manifest: dict[str, Any], native: dict[str, Any]) -> dict[str, Any]:
    return {
        "bundle_transport_schema": 2,
        "kind": kind,
        "archive": {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)},
        "manifest": manifest,
        "integrity_verified": True,
        "scientific_claims_verified": False,
        "native_verification": native,
        "scope": SCOPE,
    }


def _capture(root: Path, kind: str) -> tuple[dict[str, bytes], tuple[HeldFile, ...], Callable[[], None]]:
    root_id = transport._identity(root)
    transport._require(transport._directory(root, root_id))
    first = hold(root / "manifest.json", bundle.MAX_MANIFEST_BYTES if kind == "replay" else screen.MAX_OUTER_BYTES)
    inputs = [first]
    files = {"manifest.json": first.data}
    if kind == "replay":
        manifest = replay._manifest(first.data)
        rows = {row["path"]: row for row in manifest["files"]}
        transport._inventory(root, set(REPLAY_ORDER))
        for name in REPLAY_ORDER[1:]:
            row = rows[name]
            transport._require((root / name).lstat().st_size == row["size_bytes"])
            item = hold(root / name, row["size_bytes"])
            inputs.append(item)
            files[name] = item.data

        def recheck() -> None:
            transport._require(transport._directory(root, root_id))
            transport._inventory(root, set(REPLAY_ORDER))
            for held in inputs:
                held.check()
    else:
        manifest = screen._outer(first.data)  # Declared total admitted before large member reads.
        screen._scan(root, {"manifest.json": False, "targets.json": False, "reports": True})
        report_root = root / "reports"
        report_id = transport._identity(report_root)
        rows = {
            row["path"]: row
            for row in [*manifest["reports"], manifest["producer_summary"]]
            if row["status"] == "present"
        }
        names = {name.removeprefix("reports/") for name in rows}
        screen._scan(report_root, dict.fromkeys(names, False))
        for name, row in (("targets.json", manifest["targets"]), *rows.items()):
            screen._file_info(root / name, _limit(name, kind))
            transport._require((root / name).lstat().st_size == row["size_bytes"])
            item = hold(root / name, row["size_bytes"])
            inputs.append(item)
            files[name] = item.data

        def recheck() -> None:
            transport._require(transport._directory(root, root_id) and transport._directory(report_root, report_id))
            screen._scan(root, {"manifest.json": False, "targets.json": False, "reports": True})
            screen._scan(report_root, dict.fromkeys(names, False))
            for held in inputs:
                held.check()

    recheck()
    return files, tuple(inputs), recheck


def _receive_contents(
    path: str, pin: str, kind: str
) -> tuple[HeldFile, dict[str, bytes], dict[str, Any], dict[str, Any]]:
    profile = _profile(kind)
    transport._require(type(pin) is str and re.fullmatch(r"[0-9a-f]{64}", pin) is not None)
    held = hold(path, profile.raw_bytes)
    transport._require(hashlib.sha256(held.data).hexdigest() == pin)
    files, manifest, native = _decode(held.data, kind)
    return held, files, manifest, native


def _receive(path: str, pin: str, kind: str) -> tuple[HeldFile, dict[str, bytes], dict[str, Any]]:
    held, files, manifest, native = _receive_contents(path, pin, kind)
    return held, files, _result(held.data, kind, manifest, native)


def pack(bundle_path: str, out_path: str, *, kind: str) -> dict[str, Any]:
    try:
        _profile(kind)
        root = canonical(bundle_path)
        transport._require(not canonical(out_path).is_relative_to(root))
        files, inputs, recheck = _capture(root, kind)
        manifest, native, order = _native(files, kind)
        raw = _encode(files, order, kind)
        recheck()
        transport._publish_archive(out_path, raw, inputs, recheck=recheck)
        return _result(raw, kind, manifest, native)
    except bundle.BundleError as error:
        if str(error) == "archive_stage_preserved":
            raise
        raise bundle.BundleError("invalid_bundle_transport") from None
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, RecursionError, zipfile.BadZipFile):
        raise bundle.BundleError("invalid_bundle_transport") from None


def verify(archive_path: str, pin: str, *, kind: str) -> dict[str, Any]:
    _profile(kind)
    return transport.verify_bundle_archive(archive_path, pin, kind=kind)


def unpack(archive_path: str, pin: str, out_path: str, *, kind: str) -> dict[str, Any]:
    try:
        held, files, result = _receive(archive_path, pin, kind)
        target = admit_outputs((out_path,), (held,))[0]
        held.check()
        target.check()
        if kind == "replay":
            transport._restore(target.path, files, held, order=REPLAY_ORDER)
        else:

            def recheck() -> None:
                held.check()
                _check_ancestors(target.ancestors)

            ordered = tuple((name, raw) for name, raw in files.items() if name != "manifest.json")
            publication._publish(target.path, (*ordered, ("manifest.json", files["manifest.json"])), recheck=recheck)
        return result
    except bundle.BundleError as error:
        if str(error) == "partial_destination_preserved":
            raise
        raise bundle.BundleError("invalid_bundle_transport") from None
    except screen.ScreenBundleError as error:
        if error.category == "publication_failed_preserved":
            raise bundle.BundleError("partial_destination_preserved") from None
        raise bundle.BundleError("invalid_bundle_transport") from None
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, RecursionError, zipfile.BadZipFile):
        raise bundle.BundleError("invalid_bundle_transport") from None
