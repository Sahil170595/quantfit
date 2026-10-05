"""Strict calibration scope and aggregate validation; binding does not authenticate human labels.

Report schema 2 and QSR v0 are unchanged. This consumer never invents old capture
provenance or pools arm error rates. Matching scope is conditional evidence, not a
GO decision, a sensitivity control, or proof of independent judge errors.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from quantfit.safety.report import ArmRun, DriftReport

IDENTITY_SCHEMA = 1
BOUND_SCHEMA = 2
MAX_CALIBRATION_BYTES = 2 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVISION = re.compile(r"[0-9a-f]{40}")


class CalibrationBindingError(RuntimeError):
    """Missing, inconsistent or mismatched calibration evidence (operational exit 2)."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CalibrationBindingError(message)


def _text(value, name: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{name} must be a non-empty string")
    return value


def _count(value, name: str) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0, f"{name} must be a non-negative integer"
    )
    return value


def _canonical(value) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError) as exc:
        raise CalibrationBindingError(f"identity must be finite JSON data: {exc}") from exc


def identity_fingerprint(identity: dict) -> str:
    _require(isinstance(identity, dict), "identity must be an object")
    return hashlib.sha256(_canonical(identity)).hexdigest()


def _arm_identity(arm: ArmRun) -> dict:
    _text(arm.model, "arm.model")
    if arm.revision is not None:
        _require(bool(_REVISION.fullmatch(arm.revision)), "arm revision must be an immutable 40-hex commit, not main")
    if arm.artifact_sha256 is not None:
        _require(bool(_SHA256.fullmatch(arm.artifact_sha256)), "arm artifact_sha256 must be lowercase 64-hex")
    _require(
        arm.revision is not None or arm.artifact_sha256 is not None, "arm weights have insufficient immutable identity"
    )
    dtype = _text(arm.resolved_dtype, "arm.resolved_dtype")
    _require(dtype.strip().lower() != "auto", "arm precision must be observed, not auto")
    engine = {key: value for key, value in arm.engine.items() if key not in {"baseline_cache", "runtime_s"}}
    name = _text(engine.get("name"), "engine.name")
    if name == "llama.cpp":
        digest = engine.get("binary_sha256")
        _require(
            isinstance(digest, str) and bool(_SHA256.fullmatch(digest)),
            "llama.cpp engine needs the actual binary_sha256",
        )
        _require(_count(engine.get("threads"), "engine.threads") > 0, "engine.threads must be positive")
    elif name == "transformers":
        _text(engine.get("version"), "engine.version")
    elif name.startswith("inspect_ai:"):
        _text(engine.get("inspect_ai"), "engine.inspect_ai")
        _require(engine.get("provider") == "hf", "fixture or unobserved Inspect providers cannot bind calibration")
    else:
        raise CalibrationBindingError(f"engine {name!r} has no observed calibration identity contract")
    return {
        "model": arm.model,
        "revision": arm.revision,
        "artifact_sha256": arm.artifact_sha256,
        "resolved_dtype": dtype,
        "engine": engine,
    }


def measurement_identity(report: DriftReport) -> dict:
    """Extract causal scope; timestamps, runtimes and cache-hit metadata are outputs."""
    _require(isinstance(report, DriftReport), "measurement_identity requires a DriftReport")
    _require(
        type(report.schema_version) is int and report.schema_version == 2,
        "measurement identity requires report schema 2",
    )
    judge = {key: report.judge.get(key) for key in ("id", "revision", "input_contract")}
    for key, value in judge.items():
        _text(value, f"judge.{key}")
    _require(bool(_REVISION.fullmatch(judge["revision"])), "judge revision must be an immutable commit")
    probes = {key: report.probe_dataset.get(key) for key in ("id", "revision", "split", "n_probes")}
    for key in ("id", "revision", "split"):
        _text(probes[key], f"probe_dataset.{key}")
    _require(bool(_REVISION.fullmatch(probes["revision"])), "probe dataset revision must be an immutable commit")
    _require(_count(probes["n_probes"], "probe_dataset.n_probes") > 0, "probe count must be positive")
    decode = dict(report.decode)
    _require(_count(decode.get("max_new_tokens"), "decode.max_new_tokens") > 0, "token budget must be positive")
    _require(decode.get("do_sample") is False or decode.get("greedy") is True, "decode must declare greedy generation")
    _require("do_sample" not in decode or decode["do_sample"] is False, "conflicting or invalid do_sample fact")
    _require("greedy" not in decode or decode["greedy"] is True, "conflicting or invalid greedy fact")
    _text(decode.get("chat_template"), "decode.chat_template")
    decode.pop("do_sample", None)
    decode["greedy"] = True
    env = dict(report.env)
    _require(
        set(env) == {"python", "torch", "transformers", "cuda", "device"}, "unsupported environment identity fields"
    )
    for key in ("python", "torch", "transformers", "device"):
        _text(env.get(key), f"env.{key}")
    _require(
        env["cuda"] is None or isinstance(env["cuda"], str) and bool(env["cuda"].strip()),
        "env.cuda must be a non-empty version or null",
    )
    identity = {
        "identity_schema": IDENTITY_SCHEMA,
        "schema_version": 2,
        "judge": judge,
        "probe_dataset": probes,
        "decode": decode,
        "baseline": _arm_identity(report.baseline),
        "quantized": _arm_identity(report.quantized),
        "env": env,
    }
    # Deep copy prevents downstream mutations of the source report from changing scope.
    return json.loads(_canonical(identity))


def validate_binding(binding: dict) -> dict:
    """Validate producer metadata too, before it can survive a key/calibration round trip."""
    _require(
        isinstance(binding, dict) and set(binding) == {"identity", "fingerprint"},
        "binding must contain identity and fingerprint",
    )
    identity = binding["identity"]
    keys = {"identity_schema", "schema_version", "judge", "probe_dataset", "decode", "baseline", "quantized", "env"}
    _require(isinstance(identity, dict) and set(identity) == keys, "binding identity has an unsupported shape")
    _require(
        type(identity["identity_schema"]) is int and identity["identity_schema"] == IDENTITY_SCHEMA,
        "unsupported identity schema",
    )
    _require(
        type(identity["schema_version"]) is int and identity["schema_version"] == 2, "binding requires report schema 2"
    )
    try:
        report = DriftReport(
            schema_version=2,
            quantfit_version="binding",
            created_utc="binding",
            judge=identity["judge"],
            probe_dataset=identity["probe_dataset"],
            decode=identity["decode"],
            env=identity["env"],
            baseline=ArmRun(**identity["baseline"], runtime_s=0.0),
            quantized=ArmRun(**identity["quantized"], runtime_s=0.0),
            judge_runtime_s=0.0,
            drift={},
        )
        normalized = measurement_identity(report)
    except (TypeError, RuntimeError) as exc:
        raise CalibrationBindingError(f"invalid binding identity: {exc}") from exc
    _require(normalized == identity, "binding identity is not canonical or contains omitted scope fields")
    fingerprint = binding["fingerprint"]
    _require(
        isinstance(fingerprint, str) and fingerprint == identity_fingerprint(identity), "binding fingerprint mismatch"
    )
    return {"identity": normalized, "fingerprint": fingerprint}


def _same_numbers(actual, expected, name: str) -> None:
    if isinstance(expected, dict):
        _require(isinstance(actual, dict) and set(actual) == set(expected), f"{name} has inconsistent fields")
        for key, value in expected.items():
            _same_numbers(actual[key], value, f"{name}.{key}")
    elif isinstance(expected, list):
        _require(isinstance(actual, list) and len(actual) == len(expected), f"{name} has inconsistent interval")
        for index, value in enumerate(expected):
            _same_numbers(actual[index], value, f"{name}[{index}]")
    elif expected is None:
        _require(actual is None, f"{name} must be null when unmeasured")
    elif type(expected) is int:
        _require(type(actual) is int and actual == expected, f"{name} has inconsistent count")
    else:
        _require(
            type(actual) in (int, float)
            and math.isfinite(actual)
            and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12),
            f"{name} has inconsistent finite statistic",
        )


def _validated_arm(block, name: str, n_pairs: int) -> float:
    from quantfit.safety.calibrate import _arm_block

    _require(isinstance(block, dict), f"{name} must contain calibration counts")
    counts = {
        key: _count(block.get(key), f"{name}.{key}")
        for key in ("n", "n_unusable", "human_refusals", "human_compliances")
    }
    direction = block.get("direction")
    _require(isinstance(direction, dict), f"{name}.direction must be an object")
    for key in ("judge_refusal_human_compliance", "judge_compliance_human_refusal"):
        counts[key] = _count(direction.get(key), f"{name}.{key}")
    _require(counts["n"] + counts["n_unusable"] == n_pairs, f"{name} counts do not cover the entire captured arm")
    _require(
        counts["human_refusals"] + counts["human_compliances"] == counts["n"], f"{name} human denominator mismatch"
    )
    _require(
        counts["judge_compliance_human_refusal"] <= counts["human_refusals"]
        and counts["judge_refusal_human_compliance"] <= counts["human_compliances"],
        f"{name} errors exceed directional denominators",
    )
    try:
        expected = _arm_block(counts)
    except ArithmeticError as exc:
        raise CalibrationBindingError(f"{name} counts cannot produce finite calibration statistics") from exc
    _same_numbers(block, expected, name)
    upper = expected["mde_epsilon_upper"]
    _require(upper is not None, f"{name} has an unmeasured error direction; not a paired bound")
    return upper


@dataclass(frozen=True)
class BoundCalibration:
    identity: dict
    fingerprint: str
    eps_baseline_upper: float
    eps_quant_upper: float
    source_sha256: str
    eps_source: str

    def match_report(self, report: DriftReport) -> None:
        _require(identity_fingerprint(self.identity) == self.fingerprint, "calibration scope was mutated")
        _require(
            measurement_identity(report) == self.identity, "calibration scope does not match the actual run report"
        )


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate calibration JSON key {key!r}")
        result[key] = value
    return result


def _nonfinite(value):
    raise CalibrationBindingError(f"non-finite calibration JSON value {value!r}")


def _finite_float(value):
    result = float(value)
    _require(math.isfinite(result), f"non-finite calibration numeric literal {value!r}")
    return result


def load_bound_calibration(path: str, *, report: DriftReport | None = None) -> BoundCalibration:
    """Read counts, recompute Wilson bounds and authenticate scope, never label truth."""
    try:
        with Path(path).open("rb") as handle:
            data = handle.read(MAX_CALIBRATION_BYTES + 1)
        _require(len(data) <= MAX_CALIBRATION_BYTES, "calibration report exceeds the 2 MiB aggregate limit")
        payload = json.loads(data, object_pairs_hook=_pairs, parse_constant=_nonfinite, parse_float=_finite_float)
    except (OSError, UnicodeError, ValueError) as exc:
        raise CalibrationBindingError(f"unreadable calibration report {path}: {exc}") from exc
    _require(
        isinstance(payload, dict)
        and type(payload.get("calibration_schema")) is int
        and payload["calibration_schema"] == BOUND_SCHEMA,
        "automatic calibration needs bound schema 2; legacy evidence is unbound",
    )
    keys = {
        "calibration_schema",
        "quantfit_version",
        "created_utc",
        "n_labeled",
        "n_unusable",
        "unmeasured_arms",
        "baseline",
        "quantized",
        "arm_epsilon_delta",
        "label",
        "binding",
        "source",
    }
    _require(set(payload) == keys, "bound calibration has unsupported or missing fields")
    for key in ("quantfit_version", "created_utc", "label"):
        _text(payload[key], key)
    binding = validate_binding(payload.get("binding"))
    source = payload.get("source")
    _require(
        isinstance(source, dict) and set(source) == {"capture_sha256", "key_sha256", "sheet_sha256"},
        "bound calibration must record its source artifact hashes",
    )
    for key, value in source.items():
        _require(isinstance(value, str) and bool(_SHA256.fullmatch(value)), f"source.{key} must be lowercase SHA256")
    n_pairs = binding["identity"]["probe_dataset"]["n_probes"]
    eps_b = _validated_arm(payload.get("baseline"), "baseline", n_pairs)
    eps_q = _validated_arm(payload.get("quantized"), "quantized", n_pairs)
    _require(
        _count(payload.get("n_labeled"), "n_labeled") == 2 * n_pairs,
        "calibration must label both complete captured arms",
    )
    unusable = payload["baseline"]["n_unusable"] + payload["quantized"]["n_unusable"]
    _require(_count(payload.get("n_unusable"), "n_unusable") == unusable, "unusable total mismatch")
    _require(payload.get("unmeasured_arms") == [], "unmeasured arms cannot bind a paired decision")
    delta = payload.get("arm_epsilon_delta")
    _require(isinstance(delta, dict) and set(delta) == {"delta", "note"}, "arm_epsilon_delta has unsupported fields")
    _text(delta["note"], "arm_epsilon_delta.note")
    _same_numbers(
        delta.get("delta"), payload["quantized"]["epsilon"] - payload["baseline"]["epsilon"], "arm_epsilon_delta.delta"
    )
    digest = hashlib.sha256(data).hexdigest()
    bound = BoundCalibration(
        binding["identity"],
        binding["fingerprint"],
        eps_b,
        eps_q,
        digest,
        f"bound calibration report SHA256 {digest}; scope {binding['fingerprint']}; label truth not authenticated",
    )
    if report is not None:
        bound.match_report(report)
    return bound
