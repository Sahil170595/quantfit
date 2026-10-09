"""Bounded anonymous retrieval of one fixed approved public aggregate snapshot."""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.util
import hashlib
import math
import os
import re
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlsplit

import httpx
from huggingface_hub import hf_hub_url
from huggingface_hub.utils import build_hf_headers

from quantfit._evidence_validation import EvidenceError, require
from quantfit._evidence_validation import validate_held as _validate_held
from quantfit.bundle import _no_links, _read
from quantfit.evidence_profile import INVENTORY, PREFIX

REPO = "Crusadersk/quantfit-reference-reports"
REVISION = "3a4ff4e086f9d72ad828134873b01fa19b550059"
ENDPOINT = "https://huggingface.co"
_PATHS = tuple(p for p, _, _ in INVENTORY)


def _inventory() -> tuple[tuple[str, int, str], ...]:
    require(tuple(p for p, _, _ in INVENTORY) == _PATHS and len(set(_PATHS)) == 12, "unsupported fixed inventory")
    for path, size, sha in INVENTORY:
        require(
            PurePosixPath(path).as_posix() == path
            and not PurePosixPath(path).is_absolute()
            and all(part not in (".", "..") for part in path.split("/"))
            and "\\" not in path,
            "unsafe evidence path",
        )
        require(
            type(size) is int
            and 0 < size <= 22783
            and isinstance(sha, str)
            and re.fullmatch("[0-9a-f]{64}", sha) is not None,
            "invalid trusted size/hash declaration",
        )
    require(sum(n for _, n, _ in INVENTORY) <= 78390, "unsupported total evidence size")
    return INVENTORY


def _url(url: str, path: str) -> None:
    value = urlsplit(url)
    allowed = {f"/datasets/{REPO}/resolve/{REVISION}/{path}", f"/api/resolve-cache/datasets/{REPO}/{REVISION}/{path}"}
    require(
        value.scheme == "https"
        and value.hostname == "huggingface.co"
        and value.port in (None, 443)
        and value.username is None
        and value.password is None
        and not value.fragment
        and value.path in allowed,
        "unsupported public evidence redirect",
    )


async def _download(timeout_seconds: float) -> dict[str, bytes]:
    headers = {**build_hf_headers(token=False), "Accept-Encoding": "identity"}
    require(not any(k.lower() in ("authorization", "cookie") for k in headers), "anonymous headers required")
    timeout = httpx.Timeout(min(10.0, timeout_seconds), connect=min(5.0, timeout_seconds))
    held = {}
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=timeout) as client:
        for path, size, sha in _inventory():
            url = hf_hub_url(REPO, path, repo_type="dataset", revision=REVISION, endpoint=ENDPOINT)
            for hop in range(4):
                _url(url, path)
                client.cookies.clear()  # Never replay cookies from a previous aggregate/redirect.
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        require(hop < 3 and "location" in response.headers, "public redirect limit exceeded")
                        url = urljoin(url, response.headers["location"])
                        _url(url, path)
                        continue
                    require(
                        response.status_code == 200,
                        f"public evidence HTTP status {response.status_code} refused for {path}",
                    )
                    require(
                        response.headers.get("content-encoding", "identity").lower() == "identity",
                        "compressed evidence refused",
                    )
                    body = bytearray()
                    async for chunk in response.aiter_raw(chunk_size=1024):
                        require(len(body) + len(chunk) <= size, f"public evidence exceeds trusted byte cap for {path}")
                        body.extend(chunk)
                    raw = bytes(body)
                    require(
                        len(raw) == size and hashlib.sha256(raw).hexdigest() == sha,
                        f"public evidence size/hash differs for {path}",
                    )
                    held[path] = raw
                    break
    return held


async def _bounded_download(timeout_seconds: float) -> dict[str, bytes]:
    return await asyncio.wait_for(_download(timeout_seconds), timeout=timeout_seconds)


def _promoter() -> Callable[[Path, Path], None]:
    if os.name == "nt":
        return os.rename  # Windows rename atomically refuses any existing destination.
    require(sys.platform.startswith("linux"), "exclusive atomic publication supports Linux and Windows only")
    library = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
    require(hasattr(library, "renameat2"), "native exclusive rename capability unavailable")
    rename = library.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int

    def promote(source: Path, destination: Path) -> None:
        if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code))

    return promote


def _write(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        require(stream.write(raw) == len(raw), "incomplete evidence write")
        stream.flush()
    require(_read(path, len(raw)) == raw, "persisted evidence bytes differ")


def _cleanup(stage: Path) -> None:
    _no_links(stage)
    directories = {stage}
    for name in _PATHS:
        path = stage / name
        _no_links(path)
        path.unlink(missing_ok=True)
        directories.update(parent for parent in path.parents if parent == stage or parent.is_relative_to(stage))
    for path in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        if path.exists():
            path.rmdir()


def _publish(target: Path, held: dict[str, bytes], promote: Callable[[Path, Path], None]) -> None:
    stage = Path(tempfile.mkdtemp(prefix=".quantfit-evidence-", dir=target.parent))
    try:
        for name in _PATHS:
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            _no_links(path)
            _write(path, held[name])
        _no_links(target)
        promote(stage, target)
    except BaseException:
        _cleanup(stage)
        raise


def fetch_evidence(out_path: str, *, timeout_seconds: float = 120) -> dict:
    """Retrieve exactly twelve pinned originals; scientific flags remain separate."""
    try:
        require(
            type(timeout_seconds) in (int, float) and math.isfinite(timeout_seconds) and 0 < timeout_seconds <= 600,
            "timeout must be a finite positive number no larger than 600 seconds",
        )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise EvidenceError("synchronous fetch API cannot run inside an active event loop")
        target = Path(out_path).absolute()
        _no_links(target)
        target = target.resolve()
        require(
            not target.exists() and target.parent.is_dir(), "evidence requires a new directory with an existing parent"
        )
        _inventory()
        promote = _promoter()  # Capability refusal precedes HTTP; no unsafe rename fallback.
        held = asyncio.run(_bounded_download(float(timeout_seconds)))
        paths = [str(target / PREFIX / f"run-{i}/report.json") for i in range(1, 4)]
        original, analysis = _validate_held(held, paths)
        _publish(target, held, promote)
        return {
            "evidence_schema_version": 1,
            "exit_code": 0,
            "integrity_verified": True,
            "output_path": str(target),
            "repo": REPO,
            "repo_type": "dataset",
            "revision": REVISION,
            "files": [
                {"path": p, "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                for p, raw in held.items()
            ],
            "original_t0": original,
            "receiving_analysis": analysis,
            "producer_locations_verified": False,
            "reference_registered": False,
            "human_labels_authenticated": False,
            "scientific_go": False,
            "scope": "Exact approved public aggregate bytes only. No new inference, label/host authentication, independent execution, sensitivity or scientific GO. Original flags remain unconfirmed; dangerous zero means the detector did not fire.",
        }
    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        asyncio.TimeoutError,
        httpx.HTTPError,
    ) as exc:
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError("bounded public evidence retrieval or validation failed") from exc
