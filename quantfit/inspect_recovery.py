"""Pinned offline restoration of a completed, corrected native Inspect aggregate."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from quantfit.bundle import _json, _report
from quantfit.corpus_gate import _admit_publication_paths, _local_model_inputs
from quantfit.resolution import MAX_REPORT_BYTES
from quantfit.safety.calibration_binding import _canonical, identity_fingerprint, measurement_identity, validate_binding
from quantfit.safety.retention_io import HeldFile, admit_outputs, canonical, hold

MAX_CHECKPOINT_BYTES = 2 * MAX_REPORT_BYTES + 64 * 1024
SCOPE = (
    "Completed corrected native Inspect aggregate only; no raw logs, prompts, completions, Probe objects "
    "or extra protected-input/observer paths are checkpointed. Native model locators remain unchanged. "
    "Source, loaded observation and runtime fields are preserved, "
    "not remeasured or authenticated. Recovery performs no evaluation, generation, scoring, judging or asset lookup. "
    "A hash binds bytes, not human truth, source authenticity, sensitivity or scientific GO."
)


class InspectRecoveryError(RuntimeError):
    """Categorical unsafe/malformed checkpoint or publication refusal."""


class InspectPublicationError(InspectRecoveryError):
    """Report publication/cleanup failed after a completed checkpoint was published."""

    def __init__(self, receipt: dict[str, Any]) -> None:
        self.receipt: dict[str, Any] = json.loads(json.dumps(receipt, allow_nan=False))
        super().__init__("inspect_report_publication_failed_checkpoint_saved")


def _require(condition: bool) -> None:
    if not condition:
        raise InspectRecoveryError("invalid_inspect_recovery")


def _binding(raw: bytes) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def admit_recovery_paths(
    report_path: str, recovery_out: str, protected_inputs: tuple[str, ...] = (), *, log_dir: str | None = None
) -> None:
    """Known roles before work; report may replace an unrelated regular file, checkpoint is fresh."""
    try:
        _require(type(report_path) is str and bool(report_path) and type(recovery_out) is str and bool(recovery_out))
        # Native GGUF reading follows model symlinks. Resolve only known live
        # model roles for alias protection; never alter their execution refs.
        roles = []
        for source in protected_inputs:
            models = _local_model_inputs((source,))
            roles.append(str(models[0]) if models else source)
        _admit_publication_paths(roles, (report_path, recovery_out))
        admit_outputs((recovery_out,), ())
        if log_dir is not None:
            root = canonical(log_dir)
            _require(not any(canonical(path).is_relative_to(root) for path in (report_path, recovery_out)))
    except (OSError, RuntimeError, ValueError, TypeError):
        raise InspectRecoveryError("invalid_inspect_recovery_paths") from None


def _facts(raw: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    _require(0 < len(raw) <= MAX_REPORT_BYTES)
    _json(raw)  # Duplicate-key, nonfinite and private-field refusal before native receiving.
    report = _report(raw)
    _require(report.baseline.engine["name"] == report.quantized.engine["name"])
    _require(report.baseline.engine["name"] in {"inspect_ai:hf", "inspect_ai:quantfit_gguf"})
    from quantfit.inspect_task import inspect_decode

    provider = report.baseline.engine["name"].partition(":")[2]
    _require(_canonical(report.decode) == _canonical(inspect_decode(provider, report.decode["max_new_tokens"])))
    identity = measurement_identity(report)
    binding = {"identity": identity, "fingerprint": identity_fingerprint(identity)}
    observation = {
        "n_probes": report.probe_dataset["n_probes"],
        "baseline_generate_calls": report.baseline.engine["generate_calls"],
        "quantized_generate_calls": report.quantized.engine["generate_calls"],
        "baseline_runtime_s": report.baseline.runtime_s,
        "quantized_runtime_s": report.quantized.runtime_s,
        "judge_runtime_s": report.judge_runtime_s,
        "native_exit_code": 3 if report.drift["regression_detected"] else 4 if report.drift["unmeasurable_axes"] else 0,
    }
    _require(
        all(
            type(observation[key]) in (int, float) and math.isfinite(observation[key]) and observation[key] >= 0
            for key in ("baseline_runtime_s", "quantized_runtime_s", "judge_runtime_s")
        )
    )
    _require(
        all(
            type(observation[key]) is int for key in ("n_probes", "baseline_generate_calls", "quantized_generate_calls")
        )
    )
    return binding, observation


def _encode(payload: dict[str, Any]) -> bytes:
    raw = (json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _require(len(raw) <= MAX_CHECKPOINT_BYTES)
    return raw


def _receive(raw: bytes) -> tuple[bytes, dict[str, Any]]:
    _require(0 < len(raw) <= MAX_CHECKPOINT_BYTES)
    value = _json(raw)
    _require(set(value) == {"inspect_recovery_schema", "report_json", "report", "binding", "observation", "scope"})
    _require(type(value["inspect_recovery_schema"]) is int and value["inspect_recovery_schema"] == 1)
    _require(
        value["scope"] == SCOPE and type(value["report_json"]) is str and len(value["report_json"]) <= MAX_REPORT_BYTES
    )
    report_raw = value["report_json"].encode("utf-8")
    binding, observation = _facts(report_raw)
    validate_binding(value["binding"])
    _require(_canonical(value["report"]) == _canonical(_binding(report_raw)))
    _require(_canonical(value["binding"]) == _canonical(binding))
    _require(_canonical(value["observation"]) == _canonical(observation))
    receipt = {
        "inspect_recovery_receipt_schema": 1,
        "checkpoint": _binding(raw),
        "report": _binding(report_raw),
        **observation,
        "checkpoint_saved": True,
        "report_published": False,
        "scientific_claims_verified": False,
        "scope": SCOPE,
    }
    return report_raw, receipt


def _exclusive(path: str, raw: bytes, inputs: tuple[HeldFile, ...]) -> None:
    """Stage+fsync then atomic no-replace link in the target's existing parent."""
    target = admit_outputs((path,), inputs)[0]
    stage: Path | None = None
    identity: tuple[int, int] | None = None
    descriptor, name = tempfile.mkstemp(prefix=".quantfit-recovery-", dir=target.path.parent)
    try:
        stage = Path(name)
        info = os.fstat(descriptor)
        identity = info.st_dev, info.st_ino
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            _require(stream.write(raw) == len(raw))
            stream.flush()
            os.fsync(stream.fileno())
        held_stage = hold(stage, len(raw))
        _require(held_stage.data == raw)
        current = stage.lstat()
        _require((current.st_dev, current.st_ino) == identity)
        for item in inputs:
            item.check()
        held_stage.check()
        target.check()
        os.link(stage, target.path, follow_symlinks=False)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if stage is None or identity is None:
            raise InspectRecoveryError("recovery_stage_preserved") from None
        info = stage.lstat()
        _require((info.st_dev, info.st_ino) == identity)
        stage.unlink()


def _checkpoint_report(raw: bytes, out_path: str) -> tuple[HeldFile, dict[str, Any]]:
    """Internal writer seam: exact already-assembled report only, never a run/log projection."""
    try:
        binding, observation = _facts(raw)
        encoded = _encode(
            {
                "inspect_recovery_schema": 1,
                "report_json": raw.decode("utf-8"),
                "report": _binding(raw),
                "binding": binding,
                "observation": observation,
                "scope": SCOPE,
            }
        )
        _, receipt = _receive(encoded)
        _exclusive(out_path, encoded, ())
        held = hold(out_path, MAX_CHECKPOINT_BYTES)
        _require(held.data == encoded)
        return held, receipt
    except InspectRecoveryError:
        raise
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, RecursionError):
        raise InspectRecoveryError("invalid_inspect_recovery") from None


def recover_inspect_report(checkpoint_path: str, expected_sha256: str, *, out_path: str) -> dict[str, Any]:
    """Validate one pinned checkpoint and exclusively restore the exact report bytes offline."""
    try:
        _require(type(expected_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None)
        _admit_publication_paths((checkpoint_path,), (out_path,))
        admit_outputs((out_path,), ())
        held = hold(checkpoint_path, MAX_CHECKPOINT_BYTES)
        _require(hashlib.sha256(held.data).hexdigest() == expected_sha256)
        raw, receipt = _receive(held.data)
        _exclusive(out_path, raw, (held,))
        return {**receipt, "report_published": True}
    except InspectRecoveryError:
        raise
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, RecursionError):
        raise InspectRecoveryError("invalid_inspect_recovery") from None
