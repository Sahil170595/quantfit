"""Owned CPU GGUF server lifecycle shared with Inspect; no inspect_ai import."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import httpx

from quantfit.inspect_errors import InspectTaskError, _require
from quantfit.safety import gguf_arm as ga

_MAX_HTTP_BYTES = 1024 * 1024


async def _bounded_json(response) -> dict:
    _require(
        response.headers.get("content-encoding", "identity").lower() == "identity", "compressed owned response refused"
    )
    raw = bytearray()
    async for chunk in response.aiter_raw(chunk_size=16384):
        _require(len(raw) + len(chunk) <= _MAX_HTTP_BYTES, "owned GGUF response exceeds bound")
        raw.extend(chunk)
    return json.loads(raw)


def _observe_server_metadata(props, arm) -> dict:
    _require(isinstance(props, dict) and isinstance(props.get("model_path"), str), "invalid GGUF served metadata")
    _require(
        Path(props["model_path"]).resolve() == arm.path.resolve(),
        "served GGUF model path differs from resolved weights",
    )
    _require(
        type(props["total_slots"]) is int
        and props["total_slots"] == 1
        and type(props["default_generation_settings"]["n_ctx"]) is int
        and props["default_generation_settings"]["n_ctx"] == 4096,
        "served GGUF slot/context policy differs from applied argv",
    )
    build, template = props["build_info"], props["chat_template"]
    _require(
        isinstance(build, str) and bool(build) and isinstance(template, str),
        "served GGUF build/template observation unavailable",
    )
    return {
        "served_model_verified": True,
        "served_build": build,
        "served_template_sha256": hashlib.sha256(template.encode()).hexdigest(),
        "native_context_size": 4096,
        "total_slots": 1,
    }


def _completion_result(payload, chat: bool) -> tuple[str, str]:
    """Keep actual endpoint termination facts; absence is unknown, never clean stop."""
    if chat:
        choice = payload["choices"][0]
        output, reason = choice["message"]["content"], choice.get("finish_reason")
        reasons = {"length": "max_tokens", "stop": "stop"}
    else:
        output, reason = payload["content"], payload.get("stop_type")
        reasons = {"limit": "max_tokens", "eos": "stop", "word": "stop"}
    _require(isinstance(output, str), "invalid GGUF result kind")
    return output.strip(), reasons.get(reason, "unknown") if isinstance(reason, str) else "unknown"


class OwnedGgufServer:
    def __init__(self, arm, binary: Path, threads: int):
        self.arm, self.binary, self.threads = arm, binary, threads
        self.port, self.closed, self.cleanup = ga._free_port(), False, None
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("LLAMA_ARG_")
            and k not in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_TOKEN"}
        }
        self.proc = subprocess.Popen(
            [
                str(binary),
                *ga.CPU_OFFLOAD_ARGV,
                "-m",
                str(arm.path),
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--threads",
                str(threads),
                "--ctx-size",
                "4096",
                "--parallel",
                "1",
                "--temp",
                "0",
                "--log-disable",
                *(["--jinja"] if arm.chat_template else []),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
        self.facts = None

    async def _observe(self, client) -> dict:
        _require(self.proc.poll() is None, "owned GGUF server exited")
        try:
            async with client.stream("GET", f"http://127.0.0.1:{self.port}/props", timeout=10) as response:
                response.raise_for_status()
                props = await _bounded_json(response)
            return _observe_server_metadata(props, self.arm)
        except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError):
            raise InspectTaskError("cannot validate owned GGUF served metadata (no raw payload retained)") from None

    async def complete(self, prompt: str, max_tokens: int) -> tuple[str, str]:
        _require(not self.closed, "GGUF server already closed")
        try:
            async with httpx.AsyncClient(
                timeout=ga._REQUEST_TIMEOUT_S, trust_env=False, headers={"Accept-Encoding": "identity"}
            ) as client:
                if self.facts is None:
                    deadline = time.monotonic() + ga._READY_TIMEOUT_S
                    while True:
                        _require(self.proc.poll() is None, "owned GGUF server exited during load")
                        try:
                            async with client.stream(
                                "GET", f"http://127.0.0.1:{self.port}/health", timeout=5
                            ) as health:
                                if health.status_code == 200:
                                    break
                        except httpx.HTTPError:
                            pass
                        _require(time.monotonic() < deadline, "owned GGUF load deadline exceeded")
                        await asyncio.sleep(1)
                    self.facts = await self._observe(client)
                _require(await self._observe(client) == self.facts, "served GGUF metadata changed")
                req = ga.completion_request(self.port, prompt, self.arm.chat_template, max_tokens)
                async with client.stream("POST", req.full_url, content=req.data, headers=dict(req.headers)) as response:
                    response.raise_for_status()
                    payload = await _bounded_json(response)
                return _completion_result(payload, self.arm.chat_template)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise InspectTaskError("owned GGUF request failed; raw output discarded") from None

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        from quantfit.cold_run import _close_group

        self.cleanup = _close_group(self.proc)
        _require(
            self.cleanup["direct_child_reaped"] and self.cleanup["no_live_group_members_observed"] is True,
            "owned GGUF process group cleanup failed; no report qualifies",
        )
