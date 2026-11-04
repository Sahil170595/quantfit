"""Private retained-label IO: bounded held reads and exclusive, write-once publication.

Checks detect ordinary link/identity changes; they are not a transaction against a
hostile filesystem. A failed pair publication may leave a newly created output.
"""

from __future__ import annotations

import ntpath
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from quantfit.bundle import _no_links


class RetainedLabelsError(RuntimeError):
    """Categorical boundary: never reflect private paths or native parser values."""


def require(condition: bool) -> None:
    if not condition:
        raise RetainedLabelsError("invalid_retained_labels")


def canonical(path: str | Path) -> Path:
    original = Path(path).absolute()
    if os.name == "nt":
        devices = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        for part in original.parts[1:]:
            if part in {".", ".."}:
                continue
            require(":" not in part and not part.endswith((".", " ")))
            require(part.split(".")[0].upper() not in devices)
    _no_links(original)
    return original.resolve()


def _identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _stamp(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (*_identity(value), value.st_size, value.st_mtime_ns, value.st_nlink)


def _ancestors(path: Path) -> tuple[tuple[Path, tuple[int, int]], ...]:
    result = []
    for parent in path.parents:
        _no_links(parent)
        value = parent.stat()
        require(stat.S_ISDIR(value.st_mode))
        result.append((parent, _identity(value)))
    return tuple(result)


def _check_ancestors(ancestors: tuple[tuple[Path, tuple[int, int]], ...]) -> None:
    for path, expected in ancestors:
        _no_links(path)
        require(_identity(path.stat()) == expected)


@dataclass(frozen=True)
class HeldFile:
    path: Path
    data: bytes
    stamp: tuple[int, int, int, int, int]
    ancestors: tuple[tuple[Path, tuple[int, int]], ...]

    def check(self) -> None:
        _check_ancestors(self.ancestors)
        _no_links(self.path)
        require(_stamp(self.path.lstat()) == self.stamp)


def hold(path: str | Path, limit: int) -> HeldFile:
    target = canonical(path)
    ancestors = _ancestors(target)
    before = target.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= limit)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(target, flags)
    try:
        opened = os.fstat(fd)
        require(stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1 and _stamp(opened) == _stamp(before))
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            raw = handle.read(limit + 1)
            require(len(raw) <= limit and _stamp(os.fstat(handle.fileno())) == _stamp(before))
        held = HeldFile(target, raw, _stamp(before), ancestors)
        held.check()
        return held
    finally:
        if fd >= 0:
            os.close(fd)


@dataclass(frozen=True)
class Target:
    path: Path
    ancestors: tuple[tuple[Path, tuple[int, int]], ...]
    name_identity: tuple[int, int, str]

    def check(self) -> None:
        _check_ancestors(self.ancestors)
        _no_links(self.path)
        require(not self.path.exists())


def admit_outputs(paths: tuple[str, ...], inputs: tuple[HeldFile, ...]) -> tuple[Target, ...]:
    result = []
    names = set()
    for raw in paths:
        path = canonical(raw)
        ancestors = _ancestors(path)
        parent = path.parent.stat()
        name_identity = (*_identity(parent), ntpath.normcase(path.name))
        require(name_identity not in names)
        names.add(name_identity)
        for held in inputs:
            source_identity = (*_identity(held.path.parent.stat()), ntpath.normcase(held.path.name))
            require(name_identity != source_identity)
            held.check()
        target = Target(path, ancestors, name_identity)
        target.check()
        result.append(target)
    return tuple(result)


def publish(outputs: tuple[tuple[Target, bytes], ...], inputs: tuple[HeldFile, ...]) -> None:
    """Serialize before entry; stage all bytes, then exclusively create each target.

    No rollback deletes a published file. Every successful return includes file
    flush/fsync/close and owned-stage removal; interruption or second-output failure
    is an error even when an earlier new output remains visible.
    """
    stages: list[tuple[Path, tuple[int, int]]] = []
    try:
        for target, raw in outputs:
            target.check()
            fd, name = tempfile.mkstemp(prefix=".quantfit-retain-", dir=target.path.parent)
            try:
                path = Path(name)
                stages.append((path, _identity(os.fstat(fd))))
                with os.fdopen(fd, "wb") as handle:
                    fd = -1
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
            finally:
                if fd >= 0:
                    os.close(fd)
        for held in inputs:
            held.check()
        for target, _ in outputs:
            target.check()
        for (target, raw), (stage, identity) in zip(outputs, stages, strict=True):
            require(_identity(stage.lstat()) == identity)
            require(hold(stage, len(raw)).data == raw)
            target.check()
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(target.path, flags, 0o600)
            try:
                created = os.fstat(fd)
                require(stat.S_ISREG(created.st_mode) and created.st_nlink == 1)
                _check_ancestors(target.ancestors)
                require(_identity(target.path.lstat()) == _identity(created))
                with os.fdopen(fd, "wb") as handle:
                    fd = -1
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                _check_ancestors(target.ancestors)
                require(_identity(target.path.lstat()) == _identity(created))
            finally:
                if fd >= 0:
                    os.close(fd)
    finally:
        cleanup_failed = False
        for path, identity in stages:
            # Never unlink a changed path or any published output. Still attempt
            # closure of every other attested stage after a cleanup failure.
            try:
                if path.exists():
                    require(_identity(path.lstat()) == identity)
                    path.unlink()
            except (OSError, RuntimeError):
                cleanup_failed = True
        require(not cleanup_failed)
