"""Version-contained observations for the optional Inspect HF CLI.

No optional imports occur until use. This is an internal adapter, not another
model-argument surface: only Hub repos at immutable commits can enter it.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import re
import threading
import time
from pathlib import Path
from typing import Any

from quantfit.inspect_task import VERIFIED_INSPECT_AI_VERSION, InspectTaskError, _require
from quantfit.safety.report import ArmRun

RUN_LOCK = threading.Lock()
_PRECISIONS = {"torch.float32", "torch.float16", "torch.bfloat16", "torch.float64"}
_FILES = ["*.json", "*.safetensors", "*.bin", "*.txt", "*.model", "*.tiktoken", "*.jinja"]


def _inspect_version() -> str:
    return importlib.metadata.version("inspect-ai")


def _provider_type():
    from inspect_ai.model._providers.hf import HuggingFaceAPI

    return HuggingFaceAPI


def _snapshot(repo: str, revision: str, token: str | None) -> Path:
    from httpx import HTTPError
    from huggingface_hub import HfApi, snapshot_download
    from huggingface_hub.errors import HfHubHTTPError, HFValidationError

    try:
        resolved = HfApi(token=token).model_info(repo, revision=revision).sha
        _require(resolved == revision, "Hub did not resolve the requested immutable revision")
        path = Path(snapshot_download(repo, revision=resolved, token=token, allow_patterns=_FILES))
    except (HfHubHTTPError, HFValidationError, HTTPError) as exc:
        raise InspectTaskError(f"cannot resolve immutable HF arm {repo}@{revision}: {exc}") from exc
    # The cache snapshot name, not a config field that is absent for local loads,
    # identifies the resolver receipt. Observed loader paths are checked separately.
    _require(path.name == revision and path.parent.name == "snapshots", "Hub returned no immutable snapshot identity")
    return path


def _manifest(path: Path) -> str:
    records = []
    for file in sorted(path.rglob("*")):
        if file.is_file():
            digest = hashlib.sha256()
            with file.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            records.append((file.relative_to(path).as_posix(), digest.hexdigest()))
    _require(bool(records) and (path / "config.json").is_file(), "snapshot lacks model configuration/files")
    return hashlib.sha256(json.dumps(records, separators=(",", ":")).encode()).hexdigest()


def _path_matches(value: Any, path: Path) -> bool:
    return isinstance(value, str) and bool(value) and Path(value).resolve() == path.resolve()


def _metadata_hash(value: Any, name: str) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise InspectTaskError(f"actual {name} metadata is not finite JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


class HfRunObserver:
    """Observe real loaded HF objects and actual weight-model generate invocations.

    Calls must be serial in an otherwise exclusive Inspect HF process. Inspect
    0.3.269's global queue is not keyed by model; the solver therefore uses one
    sample at a time. The weight-method wrapper additionally refuses wrong-arm
    routing, cached returns, retries, and overlapping calls. Same-object memoized
    arms share one wrapper while retaining separate logical-arm counters.
    """

    def __init__(self, specs: tuple[str, str], revisions: tuple[str, str], get_model, token: str | None):
        _require(
            _inspect_version() == VERIFIED_INSPECT_AI_VERSION,
            f"observed HF runner requires inspected inspect-ai {VERIFIED_INSPECT_AI_VERSION}; port before upgrading",
        )
        _require(
            isinstance(revisions, (tuple, list)) and len(revisions) == 2, "both immutable HF revisions are required"
        )
        for spec, revision in zip(specs, revisions, strict=True):
            _require(
                isinstance(spec, str) and re.fullmatch(r"hf/[\w.-]+/[\w.-]+", spec) is not None,
                "observed runner supports hf/org/repo only",
            )
            _require(
                isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision) is not None,
                "each arm requires an immutable 40-character lowercase HF commit revision",
            )
        self.specs, self.revisions = specs, tuple(revisions)
        self.models: list[Any] = []
        self.paths: list[Path] = []
        self.manifests: list[str] = []
        self.facts: list[dict] = []
        self.active_arm: int | None = None
        self.calls = [0, 0]
        self.runtime = [0.0, 0.0]
        self.wall_runtime = [0.0, 0.0]
        self._originals: list[tuple[Any, Any]] = []
        try:
            for spec, revision in zip(specs, revisions, strict=True):
                path = _snapshot(spec[3:], revision, token)
                self.paths.append(path)
                self.manifests.append(_manifest(path))
                # These source arguments are constructed only here, never admitted
                # to check_model_args's user allowlist. Same immutable path pins
                # the tokenizer/template as well as the model weights.
                model = get_model(
                    spec,
                    api_key=token,
                    model_path=str(path),
                    tokenizer_path=str(path),
                    do_sample=False,
                )
                self.models.append(model)
                self.facts.append(self._observe(len(self.models) - 1))
            for model in self.models:
                weights = model.api.model
                if any(old is weights for old, _ in self._originals):
                    continue
                original = weights.generate
                self._originals.append((weights, original))
                weights.generate = self._wrapper(weights, original)
        except BaseException:
            # Resource restoration, not error suppression; the original exception
            # propagates unchanged, including cancellation.
            self.close()
            raise

    def _observe(self, arm: int) -> dict:
        provider = self.models[arm].api
        _require(isinstance(provider, _provider_type()), "loaded provider is not the inspected HF implementation")
        weights, tokenizer = provider.model, provider.tokenizer
        _require(weights is not None and tokenizer is not None, "loaded HF observation unavailable")
        _require(
            _path_matches(getattr(weights, "name_or_path", None), self.paths[arm]),
            "actual loaded weights source differs from immutable snapshot",
        )
        _require(
            _path_matches(getattr(tokenizer, "name_or_path", None), self.paths[arm]),
            "actual tokenizer source differs from immutable weights snapshot",
        )
        dtype = str(getattr(weights, "dtype", None))
        _require(dtype in _PRECISIONS, "actual loaded precision is unavailable or unsupported")
        device = str(getattr(weights, "device", ""))
        _require(
            re.fullmatch(r"cpu|mps(?::\d+)?|cuda:\d+", device) is not None,
            "actual loaded device unavailable or unsupported",
        )
        commit = getattr(weights.config, "_commit_hash", None)
        _require(commit in (None, self.revisions[arm]), "loaded config revision contradicts immutable snapshot")
        _require(provider.do_sample is False, "loaded provider does not apply greedy generation")
        template = getattr(tokenizer, "chat_template", None)
        _require(template is None or isinstance(template, (str, dict)), "unsupported actual tokenizer chat template")
        template_hash = _metadata_hash(template, "tokenizer template")
        quantization = getattr(weights.config, "quantization_config", None)
        if hasattr(quantization, "to_dict"):
            quantization = quantization.to_dict()
        _require(
            quantization is None or isinstance(quantization, dict), "unsupported actual quantization configuration"
        )
        method = quantization.get("quant_method") if quantization else None
        _require(method is None or isinstance(method, str), "unsupported actual quantization method metadata")
        return {
            "dtype": dtype,
            "device": device,
            "config_commit_hash": commit,
            "tokenizer_template_sha256": template_hash,
            "quantization_config_sha256": _metadata_hash(quantization, "quantization configuration")
            if quantization is not None
            else None,
            "quantization_method": method,
        }

    def _wrapper(self, weights, original):
        def generate(*args, **kwargs):
            arm = self.active_arm
            _require(arm in (0, 1), "actual weight generate occurred outside the observed arm call")
            _require(self.models[arm].api.model is weights, "actual generate routed to another arm's weights")
            started = time.perf_counter()
            output = original(*args, **kwargs)
            elapsed = time.perf_counter() - started
            self.calls[arm] += 1
            self.runtime[arm] += elapsed
            return output

        return generate

    async def generate(self, arm: int, prompt, config):
        _require(self.active_arm is None, "concurrent HF arm calls are refused")
        _require(self._observe(arm) == self.facts[arm], "loaded HF precision/source changed during evaluation")
        before = self.calls[arm]
        self.active_arm = arm
        started = time.perf_counter()
        try:
            output = await self.models[arm].generate(prompt, config=config)
        finally:
            self.wall_runtime[arm] += time.perf_counter() - started
            self.active_arm = None
        _require(
            self.calls[arm] == before + 1,
            "exactly one actual weight generate is required per arm/probe; cache/retries refused",
        )
        _require(self._observe(arm) == self.facts[arm], "loaded HF precision/source changed inside actual generation")
        return output

    def finish(self, n_probes: int) -> tuple[ArmRun, ArmRun]:
        arms = []
        for arm in (0, 1):
            _require(self.calls[arm] == n_probes, "actual generate count does not match the full pinned corpus")
            _require(
                _manifest(self.paths[arm]) == self.manifests[arm], "immutable snapshot bytes changed during evaluation"
            )
            _require(
                math.isfinite(self.runtime[arm]) and self.runtime[arm] > 0,
                "measured actual generation runtime unavailable",
            )
            facts = self.facts[arm]
            arms.append(
                ArmRun(
                    model=self.specs[arm],
                    revision=self.revisions[arm],
                    resolved_dtype=facts["dtype"],
                    runtime_s=self.wall_runtime[arm],
                    artifact_sha256=None,
                    engine={
                        "name": "inspect_ai:hf",
                        "inspect_ai_version": VERIFIED_INSPECT_AI_VERSION,
                        "transformers_version": importlib.metadata.version("transformers"),
                        "torch_version": importlib.metadata.version("torch"),
                        "device": facts["device"],
                        "source_repo": self.specs[arm][3:],
                        "revision_observation": "Hub resolved commit + observed model/tokenizer snapshot load paths + unchanged content manifest",
                        "config_commit_hash": facts["config_commit_hash"],
                        "snapshot_manifest_sha256": self.manifests[arm],
                        "tokenizer_revision": self.revisions[arm],
                        "tokenizer_template_sha256": facts["tokenizer_template_sha256"],
                        "quantization_config_sha256": facts["quantization_config_sha256"],
                        "quantization_method": facts["quantization_method"],
                        "generate_calls": self.calls[arm],
                        "weight_generate_host_wall_s": self.runtime[arm],
                        "runtime_scope": "sum of sequential Inspect Model.generate wall time; includes provider queue wait/tokenization/decode; excludes downloads/model/judge loading",
                        "weight_runtime_scope": "host wall time inside actual loaded weight model.generate; not GPU kernel timing",
                        "max_samples": 1,
                        "do_sample": False,
                    },
                )
            )
        self.close()
        return arms[0], arms[1]

    def close(self) -> None:
        for weights, original in self._originals:
            weights.generate = original
        self._originals.clear()
        for model in self.models:
            close = getattr(model.api, "close", None)
            if callable(close):
                close()
