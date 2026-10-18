"""Exclusive, manifest-last screen handoff with conservative owned cleanup."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from quantfit.bundle import _no_links, _read
from quantfit.screen_bundle_inputs import ScreenBundleError, _require, _scan


def _identity(path: Path) -> tuple[int, int]:
    _no_links(path)
    info = path.lstat()
    return info.st_dev, info.st_ino


def _directory_owned(path: Path, identity: tuple[int, int]) -> bool:
    try:
        return _identity(path) == identity and stat.S_ISDIR(path.lstat().st_mode)
    except (OSError, RuntimeError):
        return False


@dataclass(frozen=True)
class _Owned:
    path: Path
    identity: tuple[int, int]
    raw: bytes


def _file_owned(member: _Owned) -> bool:
    try:
        return _identity(member.path) == member.identity and _read(member.path, len(member.raw)) == member.raw
    except (OSError, RuntimeError):
        return False


def _write_member(path: Path, raw: bytes, owned: list[_Owned]) -> None:
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        info = os.fstat(stream.fileno())
        member = _Owned(path, (info.st_dev, info.st_ino), raw)
        owned.append(member)
        _require(stream.write(raw) == len(raw), "publication_failed")
        stream.flush()
    _require(_file_owned(member), "publication_ownership_changed")


def _cleanup(root: Path, root_id: tuple[int, int], reports_id: tuple[int, int] | None, owned: list[_Owned]) -> bool:
    """Never recurse: uncertain identities, bytes or inventory retain the destination."""
    try:
        if not _directory_owned(root, root_id):
            return False
        # Revoke readiness first only when its exact bytes and identity remain ours.
        manifest = next((member for member in owned if member.path == root / "manifest.json"), None)
        if manifest is not None:
            if not _file_owned(manifest) or not _directory_owned(root, root_id):
                return False
            manifest.path.unlink()
            owned.remove(manifest)
        root_members = {member.path.name: False for member in owned if member.path.parent == root}
        if reports_id is not None:
            if not _directory_owned(root / "reports", reports_id):
                return False
            root_members["reports"] = True
        _scan(root, root_members)
        if reports_id is not None:
            _scan(
                root / "reports",
                {member.path.name: False for member in owned if member.path.parent == root / "reports"},
            )
        if not all(_file_owned(member) for member in owned):
            return False
        for member in reversed(owned):
            if (
                not _directory_owned(root, root_id)
                or reports_id is not None
                and not _directory_owned(root / "reports", reports_id)
                or not _file_owned(member)
            ):
                return False
            member.path.unlink()
        if reports_id is not None:
            _scan(root / "reports", {})
            if not _directory_owned(root / "reports", reports_id) or not _directory_owned(root, root_id):
                return False
            (root / "reports").rmdir()
        _scan(root, {})
        if not _directory_owned(root, root_id):
            return False
        root.rmdir()
        return True
    except (OSError, RuntimeError):
        return False


def _publish(root: Path, files: tuple[tuple[str, bytes], ...]) -> None:
    """Reserve final root exclusively; original members first, outer manifest last.

    Mode bits are owner-only where supported; Windows uses inherited ACL behavior.
    Ordinary identity checks do not close hostile concurrent path-rename races.
    """
    _no_links(root)
    root.mkdir(mode=0o700)  # No exists-check/rename replacement boundary.
    root_id = _identity(root)
    reports_id = None
    owned: list[_Owned] = []
    try:
        (root / "reports").mkdir(mode=0o700)
        reports_id = _identity(root / "reports")
        for relative, raw in files:
            _require(
                _directory_owned(root, root_id) and _directory_owned(root / "reports", reports_id),
                "publication_ownership_changed",
            )
            _write_member(root / relative, raw, owned)
        _require(
            _directory_owned(root, root_id) and all(_file_owned(member) for member in owned),
            "publication_ownership_changed",
        )
        _scan(root, {"manifest.json": False, "targets.json": False, "reports": True})
        _scan(root / "reports", {member.path.name: False for member in owned if member.path.parent == root / "reports"})
    except BaseException as exc:
        cleaned = _cleanup(root, root_id, reports_id, owned)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise ScreenBundleError("publication_failed" if cleaned else "publication_failed_preserved") from None
