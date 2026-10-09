"""Public Inspect ModelAPI over owned CPU llama.cpp servers; no Python-llama claim.

Linux/POSIX group observation is required. Paired QSR retains two resident servers
with conservative RAM admission and closes both before loading the pinned judge.
Raw server output is discarded, not attached to errors or aggregate reports.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import os
import threading
import time
from pathlib import Path

from inspect_ai.model import ModelAPI, ModelOutput, modelapi

from quantfit import gguf_server as _shared_server
from quantfit.inspect_task import VERIFIED_INSPECT_AI_VERSION, _require, check_max_new_tokens
from quantfit.safety import gguf_arm as ga
from quantfit.safety.report import ArmRun

OwnedGgufServer = _shared_server.OwnedGgufServer
_completion_result = _shared_server._completion_result
_observe_server_metadata = _shared_server._observe_server_metadata
InspectTaskError = _shared_server.InspectTaskError
subprocess = _shared_server.subprocess
httpx = _shared_server.httpx

PROVIDER = "quantfit_gguf"
RUN_LOCK = threading.Lock()
_TRANSPORT_CONFIG = {"max_connections", "max_retries", "adaptive_connections"}


def _posix_supported() -> bool:
    return os.name == "posix" and Path("/proc").is_dir()


def _available_ram() -> int:
    import psutil

    return psutil.virtual_memory().available


def _validate_source(spec: str, revision: str | None) -> None:
    _require(spec.startswith(PROVIDER + "/"), "observed GGUF provider mismatch")
    ref = spec[len(PROVIDER) + 1 :]
    _require(bool(ref), "GGUF source path is missing")
    if ref.startswith("hf:"):
        _require(revision is not None, "Hub GGUF needs immutable revision")
        parts = ref[3:].split("/")
        _require(
            len(parts) >= 3
            and all(parts)
            and parts[-1].lower().endswith(".gguf")
            and not any(p in {".", ".."} for p in parts),
            "bad Hub GGUF source ref",
        )
    else:
        _require(Path(ref).is_file(), "local GGUF source file not found")
    ga.validate_revision(ref, revision)


def _config(config) -> int:
    values = config.model_dump(exclude_none=True)
    _require(
        set(values) <= {"temperature", "max_tokens", "cache"} | _TRANSPORT_CONFIG,
        "GGUF provider refuses unsupported generation config (including cache/sampling/system/fallback)",
    )
    _require(config.temperature in (None, 0), "GGUF provider requires greedy temperature0")
    _require(config.cache in (None, False), "GGUF provider refuses caching")
    _require(config.max_retries in (None, 0), "GGUF provider refuses retry overrides")
    _require(
        config.max_connections in (None, 1) and config.adaptive_connections in (None, False),
        "GGUF provider requires serial connections without adaptive concurrency",
    )
    tokens = 64 if config.max_tokens is None else config.max_tokens
    check_max_new_tokens(tokens)
    return tokens


class GgufModelAPI(ModelAPI):
    def __init__(self, model_name, base_url=None, api_key=None, config=None, *, revision=None, **kwargs):
        _require(_posix_supported(), "GGUF Inspect requires Linux/POSIX process-group observation")
        _require(
            importlib.metadata.version("inspect-ai") == VERIFIED_INSPECT_AI_VERSION,
            f"GGUF extension requires inspected inspect-ai {VERIFIED_INSPECT_AI_VERSION}",
        )
        _require(base_url is None and not kwargs, "GGUF provider refuses source/runtime overrides")
        if config is not None:
            _config(config)
        _validate_source(PROVIDER + "/" + model_name, revision)
        super().__init__(model_name, api_key=api_key)
        self.arm = ga._resolve(model_name, api_key, **({"revision": revision} if revision else {}))
        self.binary, self.threads = ga.llama_server_bin(), ga._threads()
        self.binary_sha256 = ga._sha256(self.binary)
        self.server, self.closed = None, False
        self.calls, self.request_calls, self.runtime_s = 0, 0, 0.0
        self._active = threading.Lock()

    def max_connections(self):
        return 1

    async def _request(self, prompt, max_tokens):
        _require(not self.closed, "GGUF provider already closed")
        if self.server is None:
            required = 2 * self.arm.path.stat().st_size + 1024**3
            _require(_available_ram() >= required, "available RAM below conservative single-GGUF estimate")
            self.server = OwnedGgufServer(self.arm, self.binary, self.threads)
        self.request_calls += 1
        return await self.server.complete(prompt, max_tokens)

    async def generate(self, input, tools, tool_choice, config):
        _require(not tools and tool_choice in (None, "auto", "none"), "GGUF provider does not support tools")
        _require(
            len(input) == 1 and input[0].role == "user" and isinstance(input[0].content, str),
            "GGUF provider requires one plain user probe; system/multimodal/multiturn refused",
        )
        tokens = _config(config)
        _require(self._active.acquire(blocking=False), "concurrent GGUF requests refused")
        started = time.perf_counter()
        try:
            output, stop_reason = await self._request(input[0].content, tokens)
            self.calls += 1
            self.runtime_s += time.perf_counter() - started
            return ModelOutput.from_content(model=self.model_name, content=output, stop_reason=stop_reason)
        except BaseException:
            # Async socket context has closed before terminating/reaping owned groups.
            self.close()
            raise
        finally:
            self._active.release()

    def close(self):
        self.closed = True
        if self.server is not None:
            self.server.close()


class GgufRunObserver:
    """Observe actual public Model.generate requests, identities and owned cleanup."""

    release_before_judge = True

    def __init__(self, specs, revisions, get_model, token):
        _require(isinstance(revisions, (tuple, list)) and len(revisions) == 2, "both GGUF pin slots required")
        self.specs, self.models = specs, []
        self.active_arm = None
        try:
            pairs = tuple(zip(specs, revisions, strict=True))
            for spec, revision in pairs:
                _validate_source(spec, revision)
            for spec, revision in pairs:
                self.models.append(get_model(spec, revision=revision, api_key=token, memoize=False))
            _require(all(isinstance(m.api, GgufModelAPI) for m in self.models), "unexpected loaded GGUF provider")
            baseline, quant = (m.api for m in self.models)
            _require(baseline.arm.file_type in ga.UNQUANTIZED_FILE_TYPES, "GGUF baseline must be unquantized")
            _require(baseline.arm.architecture == quant.arm.architecture, "GGUF architectures differ")
            _require(
                baseline.binary_sha256 == quant.binary_sha256 and baseline.threads == quant.threads,
                "GGUF arms need identical binary and threads",
            )
            # Conservative admission, not a measured resident-set/peak guarantee.
            self.required_ram_estimate_bytes = 2 * sum(m.api.arm.path.stat().st_size for m in self.models) + 2 * 1024**3
            self.observed_available_ram_bytes = _available_ram()
            _require(
                self.observed_available_ram_bytes >= self.required_ram_estimate_bytes,
                "available RAM below conservative two-resident GGUF estimate; use sequential native cold-run",
            )
        except BaseException:
            self.close()
            raise

    async def generate(self, arm, prompt, config):
        _require(self.active_arm is None, "concurrent observed GGUF arms refused")
        _config(config)  # Refuse requested overrides before applying managed transport pins.
        provider = self.models[arm].api
        before, requests = provider.calls, provider.request_calls
        self.active_arm = arm
        try:
            applied = config.model_copy(
                update={"cache": False, "max_retries": 0, "max_connections": 1, "adaptive_connections": False}
            )
            output = await self.models[arm].generate(prompt, config=applied)
        finally:
            self.active_arm = None
        _require(
            provider.calls == before + 1 and provider.request_calls == requests + 1,
            "exactly one real GGUF request required; cached/retried return refused",
        )
        return output

    def before_judge(self, n_probes):
        """Observe/close native groups before the pinned judge allocates memory."""
        self._observed_arms = self._finish_generation(n_probes)
        self._n_probes = n_probes

    def finish(self, n_probes):
        if hasattr(self, "_observed_arms"):
            _require(self._n_probes == n_probes, "GGUF final corpus changed")
            for model in self.models:
                _require(
                    ga._sha256(model.api.arm.path) == model.api.arm.sha256
                    and ga._sha256(model.api.binary) == model.api.binary_sha256,
                    "GGUF weights/binary bytes changed during evaluation",
                )
            return self._observed_arms
        return self._finish_generation(n_probes)

    def _finish_generation(self, n_probes):
        arms = []
        try:
            for spec, model in zip(self.specs, self.models, strict=True):
                provider = model.api
                _require(
                    provider.calls == provider.request_calls == n_probes, "GGUF actual calls must match complete corpus"
                )
                _require(
                    ga._sha256(provider.arm.path) == provider.arm.sha256
                    and ga._sha256(provider.binary) == provider.binary_sha256,
                    "GGUF weights/binary bytes changed during evaluation",
                )
                identity = ga._identity(provider.arm, provider.binary, provider.threads)
                arms.append(
                    ArmRun(
                        model=spec,
                        revision=provider.arm.revision,
                        resolved_dtype=provider.arm.file_type,
                        artifact_sha256=provider.arm.sha256,
                        runtime_s=provider.runtime_s,
                        engine={
                            **identity["engine"],
                            "name": "inspect_ai:quantfit_gguf",
                            "inspect_ai_version": VERIFIED_INSPECT_AI_VERSION,
                            "model_args": {},
                            **provider.server.facts,
                            "generate_calls": provider.calls,
                            "runtime_scope": "public Inspect generate wall time; owned native HTTP/load; not kernel timing",
                            "revision_observation": "resolved immutable Hub snapshot (local has no revision) + actual file SHA256; unchanged postrun bytes",
                        },
                    )
                )
        finally:
            self.close()
        return tuple(arms)

    def close(self):
        error = None
        for model in self.models:
            try:
                model.api.close()
            except (OSError, RuntimeError, subprocess.TimeoutExpired, KeyboardInterrupt, asyncio.CancelledError) as exc:
                error = error or exc
        if error is not None:
            raise error

    def receipt(self):
        return {
            "resident_model_servers": 2,
            "required_ram_estimate_bytes": self.required_ram_estimate_bytes,
            "observed_available_ram_bytes": self.observed_available_ram_bytes,
            "ram_scope": "conservative admission estimate 2*sum(weights)+2GiB; not observed peak RSS",
            "arm_weight_bytes": [m.api.arm.path.stat().st_size for m in self.models],
            "calls": [m.api.calls for m in self.models],
            "request_calls": [m.api.request_calls for m in self.models],
            "native_processes": [
                {
                    "pid": getattr(getattr(m.api.server, "proc", None), "pid", None),
                    "cleanup": getattr(m.api.server, "cleanup", None),
                }
                for m in self.models
            ],
            "closed_before_judge": all(m.api.closed for m in self.models),
            "raw_server_output_retained": False,
            "scientific_go": False,
            "human_labels_authenticated": False,
        }

    def report_inputs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(str(path.resolve()) for m in self.models for path in (m.api.arm.path, m.api.binary)))


# Keep the original class for a real observed-provider type check. Inspect's
# supported decorator registers its wrapper; get_model resolves the global name.
_REGISTERED_PROVIDER = modelapi(name=PROVIDER)(GgufModelAPI)
