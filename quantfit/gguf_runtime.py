"""One bounded native CPU usability request using the shared owned server."""

from __future__ import annotations

import asyncio
import math
import os
import re
import sys
from pathlib import Path

from quantfit.gguf_server import OwnedGgufServer
from quantfit.gguf_structure import UnsupportedGguf, identity
from quantfit.inspect_errors import InspectTaskError, _require
from quantfit.safety import gguf_arm as ga

_PROMPT = "The capital of France is"


def _supported() -> bool:
    return os.name == "posix" and sys.platform.startswith("linux") and Path("/proc").is_dir()


async def _native(
    path: Path, selected: dict, file_identity: tuple, timeout_seconds: float, max_new_tokens: int
) -> dict:
    _require(_supported(), "native GGUF verification requires Linux/POSIX group observation before provisioning")
    _require(identity(path.stat()) == file_identity, "model identity changed after structural scan")
    architecture = selected.get("general.architecture")
    _require(isinstance(architecture, str) and bool(architecture), "native usability needs recorded model architecture")
    import psutil

    _require(
        psutil.virtual_memory().available >= 2 * path.stat().st_size + 1024**3,
        "available RAM below conservative native GGUF estimate",
    )
    binary, threads = ga.llama_server_bin(), ga._threads()
    model_sha, binary_sha = ga._sha256(path), ga._sha256(binary)
    _require(identity(path.stat()) == file_identity, "model identity changed before native load")
    arm = ga.ResolvedGguf(
        str(path),
        path,
        None,
        model_sha,
        architecture,
        "GGUF",
        bool(selected.get("tokenizer.chat_template")),
        selected.get("general.name"),
    )
    server = None
    try:
        server = OwnedGgufServer(arm, binary, threads)
        output, reason = await asyncio.wait_for(server.complete(_PROMPT, max_new_tokens), timeout=timeout_seconds)
        _require(isinstance(output, str) and bool(output.strip()), "native GGUF produced no nonempty output")
        count = len(output.strip())
        del output  # No generated text or digest enters receipts.
        _require(
            identity(path.stat()) == file_identity and ga._sha256(path) == model_sha,
            "model bytes changed during native usability",
        )
        _require(ga._sha256(binary) == binary_sha, "native binary bytes changed during usability")
        facts = dict(server.facts or {})
        _require(
            set(facts)
            == {"served_model_verified", "served_build", "served_template_sha256", "native_context_size", "total_slots"}
            and facts["served_model_verified"] is True
            and type(facts["native_context_size"]) is int
            and facts["native_context_size"] == 4096
            and type(facts["total_slots"]) is int
            and facts["total_slots"] == 1
            and isinstance(facts["served_build"], str)
            and 0 < len(facts["served_build"]) <= 512
            and isinstance(facts["served_template_sha256"], str)
            and re.fullmatch("[0-9a-f]{64}", facts["served_template_sha256"]) is not None,
            "native served metadata facts are unverified",
        )
    finally:
        if server is not None:
            server.close()
    _require(
        server.cleanup is not None
        and server.cleanup["direct_child_reaped"] is True
        and server.cleanup["no_live_group_members_observed"] is True,
        "native owned cleanup is unverified",
    )
    return {
        "requested": True,
        "status": "pass",
        "exit_code": 0,
        "requests_observed": 1,
        "output_characters": count,
        "termination": reason,
        "max_new_tokens": max_new_tokens,
        "model_sha256_before": model_sha,
        "model_sha256_after": model_sha,
        "binary_sha256_before": binary_sha,
        "binary_sha256_after": binary_sha,
        "engine": {
            "name": "llama.cpp",
            "device": "cpu",
            **ga.CPU_OFFLOAD_CONTROLS,
            "threads": threads,
            "binary_sha256": binary_sha,
            **facts,
        },
        "cleanup": server.cleanup,
        "served_bytes_authenticated": False,
    }


def verify_runtime(
    path: str, selected: dict, file_identity: tuple, *, timeout_seconds: float, max_new_tokens: int
) -> dict:
    try:
        _require(
            type(timeout_seconds) in (int, float) and math.isfinite(timeout_seconds) and 0 < timeout_seconds <= 1800,
            "native timeout must be finite positive and at most1800seconds",
        )
        _require(type(max_new_tokens) is int and 1 <= max_new_tokens <= 64, "native token budget must be integer1..64")
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise UnsupportedGguf("synchronous native API cannot run in an active event loop")
        return asyncio.run(_native(Path(path), selected, file_identity, float(timeout_seconds), max_new_tokens))
    except (UnsupportedGguf, InspectTaskError) as exc:
        return {
            "requested": True,
            "status": "unverified",
            "exit_code": 2,
            "platform_supported": _supported(),
            "reason": str(exc),
            "scope": "Native usability did not qualify; no raw output/error payload retained.",
        }
    except asyncio.TimeoutError:
        return {
            "requested": True,
            "status": "unverified",
            "exit_code": 2,
            "platform_supported": _supported(),
            "reason": "native load/request deadline exceeded",
        }
    except (OSError, RuntimeError, ValueError, TypeError, KeyError):
        return {
            "requested": True,
            "status": "unverified",
            "exit_code": 2,
            "platform_supported": _supported(),
            "reason": "native setup/request/provenance/cleanup failed; raw diagnostics discarded",
            "scope": "Native load/request/provenance/cleanup did not qualify; no raw output/error payload retained.",
        }
