"""Bounded exact transport capture and pure native screen-bundle receiving."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quantfit import saved_screen as saved
from quantfit.bundle import _json, _no_links, _read
from quantfit.reproduce import _canonical_receiving_path
from quantfit.screen import _SAFE_NAME, SUMMARY_FILENAME

MAX_OUTER_BYTES = 256 * 1024
MAX_TARGETS_BYTES = 1024 * 1024
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TRANSPORT_BYTES = 64 * 1024 * 1024
MAX_TARGETS = 256
_SHA = re.compile(r"[0-9a-f]{64}")
SCOPE = (
    "Exact aggregate transport integrity and strict native receiving only. Flags remain unconfirmed; "
    "dangerous zeros mean the detector did not fire. No source, weight, host, human-label, sensitivity, "
    "independence or scientific GO authentication. No model assets or report reference paths are followed. "
    "Publication has partial visibility, per-file ownership checks and no atomic-directory, crash-durability "
    "or hostile-concurrent-rename guarantee."
)


class ScreenBundleError(RuntimeError):
    """Categorical operational refusal without arbitrary producer diagnostics."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise ScreenBundleError(category)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _encode(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _scan(root: Path, allowed: dict[str, bool], required: set[str] | None = None) -> dict[str, Path]:
    """Stream a finite inventory; refuse its first unknown/duplicate without exposing names."""
    _no_links(root)
    _require(stat.S_ISDIR(root.lstat().st_mode), "invalid_directory")
    members: dict[str, Path] = {}
    with os.scandir(root) as scan:
        for entry in scan:
            _require(
                entry.name in allowed and entry.name not in members and len(members) < len(allowed), "invalid_inventory"
            )
            path = root / entry.name
            _no_links(path)
            info = path.lstat()
            _require(
                stat.S_ISDIR(info.st_mode) if allowed[entry.name] else stat.S_ISREG(info.st_mode), "invalid_member"
            )
            members[entry.name] = path
    _require((set(allowed) if required is None else required) <= set(members), "missing_member")
    return members


@dataclass
class _Budget:
    charged: int = 0

    def charge(self, size: int) -> None:
        _require(type(size) is int and 0 <= size <= MAX_TRANSPORT_BYTES - self.charged, "transport_byte_limit")
        self.charged += size


_Cache = dict[tuple[int, int], tuple[tuple[int, int], bytes]]


def _file_info(path: Path, limit: int) -> os.stat_result:
    _no_links(path)
    info = path.lstat()
    _require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= limit, "invalid_member")
    return info


def _hold(path: Path, limit: int, budget: _Budget, cache: _Cache, *, expected: int | None = None) -> bytes:
    info = _file_info(path, limit)
    _require(expected is None or info.st_size == expected, "member_size_mismatch")
    # Charge every declared occurrence BEFORE cache lookup or reading its raw bytes.
    budget.charge(info.st_size)
    identity = (info.st_dev, info.st_ino)
    signature = (info.st_size, info.st_mtime_ns)
    if identity in cache:
        old_signature, raw = cache[identity]
        _require(signature == old_signature, "source_changed")
        return raw
    raw = _read(path, min(limit, info.st_size))
    _require(len(raw) == info.st_size, "source_changed")
    cache[identity] = (signature, raw)
    return raw


def _row(row: Any, path: str, *, status: bool = True) -> None:
    fields = {"path", "sha256", "size_bytes"} | ({"status"} if status else set())
    _require(type(row) is dict and set(row) == fields and row["path"] == path, "invalid_bundle_manifest")
    if status:
        _require(row["status"] in ("present", "missing", "absent"), "invalid_bundle_manifest")
        if row["status"] != "present":
            _require(row["sha256"] is None and row["size_bytes"] is None, "invalid_bundle_manifest")
            return
    _require(isinstance(row["sha256"], str) and bool(_SHA.fullmatch(row["sha256"])), "invalid_bundle_manifest")
    _require(
        type(row["size_bytes"]) is int
        and 0 <= row["size_bytes"] <= (MAX_MEMBER_BYTES if status else MAX_TARGETS_BYTES),
        "invalid_bundle_manifest",
    )


def _outer(raw: bytes) -> dict[str, Any]:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_OUTER_BYTES, "invalid_bundle_manifest")
    outer = _json(raw)
    _require(
        set(outer) == {"bundle_schema_version", "kind", "targets", "reports", "producer_summary"},
        "invalid_bundle_manifest",
    )
    _require(
        type(outer["bundle_schema_version"]) is int
        and outer["bundle_schema_version"] == 1
        and outer["kind"] == "quantfit.screen-bundle",
        "invalid_bundle_manifest",
    )
    _row(outer["targets"], "targets.json", status=False)
    reports = outer["reports"]
    _require(type(reports) is list and 0 < len(reports) <= MAX_TARGETS, "invalid_bundle_manifest")
    seen = set()
    for row in reports:
        _require(
            type(row) is dict and set(row) == {"name", "path", "status", "sha256", "size_bytes"},
            "invalid_bundle_manifest",
        )
        name = row["name"]
        _require(
            isinstance(name, str) and bool(_SAFE_NAME.fullmatch(name)) and name.casefold() not in seen,
            "invalid_bundle_manifest",
        )
        seen.add(name.casefold())
        _row({key: value for key, value in row.items() if key != "name"}, f"reports/{name}.json")
        _require(row["status"] in ("present", "missing"), "invalid_bundle_manifest")
    _row(outer["producer_summary"], f"reports/{SUMMARY_FILENAME}")
    _require(outer["producer_summary"]["status"] in ("present", "absent"), "invalid_bundle_manifest")
    declared = (
        len(raw)
        + outer["targets"]["size_bytes"]
        + sum(row["size_bytes"] for row in [*reports, outer["producer_summary"]] if row["status"] == "present")
    )
    _require(declared <= MAX_TRANSPORT_BYTES, "transport_byte_limit")
    return outer


@dataclass(frozen=True)
class _HeldScreen:
    outer: bytes
    targets: bytes
    members: tuple[tuple[str, bytes], ...]
    protected_paths: tuple[Path, ...] = ()
    protected_roots: tuple[Path, ...] = ()


def _verify_held(held: _HeldScreen) -> dict[str, Any]:
    """Pure verification; even a forged carrier is structurally and cryptographically rechecked."""
    _require(type(held) is _HeldScreen, "invalid_held_bundle")
    outer = _outer(held.outer)
    _require(type(held.targets) is bytes and 0 < len(held.targets) <= MAX_TARGETS_BYTES, "invalid_targets")
    _require(type(held.members) is tuple and len(held.members) <= MAX_TARGETS + 1, "invalid_held_bundle")
    members: dict[str, bytes] = {}
    for member in held.members:
        _require(type(member) is tuple and len(member) == 2, "invalid_held_bundle")
        name, raw = member
        _require(
            type(name) is str and name not in members and type(raw) is bytes and len(raw) <= MAX_MEMBER_BYTES,
            "invalid_held_bundle",
        )
        members[name] = raw
    total = len(held.outer) + len(held.targets) + sum(len(raw) for raw in members.values())
    _require(total <= MAX_TRANSPORT_BYTES, "transport_byte_limit")
    _require(
        len(held.targets) == outer["targets"]["size_bytes"] and _sha(held.targets) == outer["targets"]["sha256"],
        "member_integrity_mismatch",
    )
    _, targets, _ = saved._manifest(held.targets)
    _require(
        [row["name"] for row in outer["reports"]] == [target.name for target in targets], "target_inventory_mismatch"
    )
    expected = set()
    for row in [*outer["reports"], outer["producer_summary"]]:
        if row["status"] == "present":
            member_name = row["path"].removeprefix("reports/")
            expected.add(member_name)
            _require(
                member_name in members
                and len(members[member_name]) == row["size_bytes"]
                and _sha(members[member_name]) == row["sha256"],
                "member_integrity_mismatch",
            )
    _require(set(members) == expected, "member_inventory_mismatch")
    summary = saved._summarize_held(held.targets, members, manifest_path="targets.json", reports_dir="reports")
    return {
        "bundle_schema_version": 1,
        "kind": "quantfit.screen-bundle-verification",
        "status": "verified_content",
        "exit_code": 0,
        "manifest_sha256": _sha(held.outer),
        "transport_bytes": total,
        "bundle_manifest": outer,
        "receiving_summary": summary,
        "source_authentication": "unverified",
        "scientific_go": False,
        "scope": SCOPE,
        "limits": {
            "transport_bytes": MAX_TRANSPORT_BYTES,
            "outer_manifest_bytes": MAX_OUTER_BYTES,
            "targets_bytes": MAX_TARGETS_BYTES,
            "report_bytes": MAX_MEMBER_BYTES,
            "max_targets": MAX_TARGETS,
        },
    }


def _capture_bundle(bundle_dir: str) -> _HeldScreen:
    root = Path(_canonical_receiving_path(bundle_dir))
    top = _scan(root, {"manifest.json": False, "targets.json": False, "reports": True})
    budget = _Budget()
    cache: _Cache = {}
    raw_outer = _hold(top["manifest.json"], MAX_OUTER_BYTES, budget, cache)
    outer = _outer(raw_outer)  # Charge the entire declared transport before any large member read.
    rows = [*outer["reports"], outer["producer_summary"]]
    present = {row["path"].removeprefix("reports/"): row for row in rows if row["status"] == "present"}
    inventory = _scan(top["reports"], dict.fromkeys(present, False))
    raw_targets = _hold(top["targets.json"], MAX_TARGETS_BYTES, budget, cache, expected=outer["targets"]["size_bytes"])
    held = tuple(
        (name, _hold(inventory[name], MAX_MEMBER_BYTES, budget, cache, expected=row["size_bytes"]))
        for name, row in present.items()
    )
    return _HeldScreen(
        raw_outer,
        raw_targets,
        held,
        (
            top["manifest.json"],
            top["targets.json"],
            *(top["reports"] / f"{row['name']}.json" for row in outer["reports"]),
            top["reports"] / SUMMARY_FILENAME,
        ),
        (root,),
    )


def _capture_source(manifest_path: str, reports_dir: str) -> _HeldScreen:
    manifest = Path(_canonical_receiving_path(manifest_path))
    root = Path(_canonical_receiving_path(reports_dir))
    budget = _Budget()
    cache: _Cache = {}
    raw_targets = _hold(manifest, MAX_TARGETS_BYTES, budget, cache)
    _, targets, _ = saved._manifest(raw_targets)
    allowed = {f"{target.name}.json": False for target in targets} | {SUMMARY_FILENAME: False}
    inventory = _scan(root, allowed, set())
    sizes = {name: _file_info(path, MAX_MEMBER_BYTES).st_size for name, path in inventory.items()}

    def record(name: str, absent: str) -> dict[str, Any]:
        return {
            "path": f"reports/{name}",
            "status": "present" if name in inventory else absent,
            "sha256": "0" * 64 if name in inventory else None,
            "size_bytes": sizes.get(name),
        }

    outer: dict[str, Any] = {
        "bundle_schema_version": 1,
        "kind": "quantfit.screen-bundle",
        "targets": {"path": "targets.json", "sha256": _sha(raw_targets), "size_bytes": len(raw_targets)},
        "reports": [{"name": target.name, **record(f"{target.name}.json", "missing")} for target in targets],
        "producer_summary": record(SUMMARY_FILENAME, "absent"),
    }
    # Hashes have fixed encoded length: reserve the exact final outer size before native allocation.
    outer_size = len(_encode(outer))
    _require(outer_size <= MAX_OUTER_BYTES, "invalid_bundle_manifest")
    budget.charge(outer_size)
    members = []
    for row in [*outer["reports"], outer["producer_summary"]]:
        if row["status"] == "present":
            name = row["path"].removeprefix("reports/")
            raw = _hold(inventory[name], MAX_MEMBER_BYTES, budget, cache, expected=row["size_bytes"])
            row["sha256"] = _sha(raw)
            members.append((name, raw))
    raw_outer = _encode(outer)
    _require(len(raw_outer) == outer_size, "source_changed")
    return _HeldScreen(raw_outer, raw_targets, tuple(members), (manifest, *(root / name for name in allowed)), (root,))
