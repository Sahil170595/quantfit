"""Strict offline receiving screen summaries from held native aggregate evidence."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfit import __version__
from quantfit.bundle import _json, _no_links, _read, _report
from quantfit.junit import screen_to_junit
from quantfit.modelcard import _check_original_statistics
from quantfit.reproduce import (
    _canonical_receiving_path,
    _chat_template_policy,
    _decode_greediness,
    _publish_reproduction_outputs,
    _ReproductionOutputs,
    _validate_reproduction_outputs,
    _view_from_report,
)
from quantfit.safety.calibration_binding import engine_causal_identity
from quantfit.safety.gguf_arm import UNQUANTIZED_FILE_TYPES, is_gguf_ref, validate_revision
from quantfit.safety.report import DriftReport
from quantfit.safety.verify import (
    JUDGE_INPUT_CONTRACT,
    JUDGE_MODEL_ID,
    JUDGE_REVISION,
    PROBE_DATASET_ID,
    PROBE_DATASET_REVISION,
    PROBE_SPLIT,
)
from quantfit.screen import (
    CONDITIONALITY_LABEL,
    RESOLUTION_LABEL,
    SPEC_CAPS,
    SUMMARY_FILENAME,
    Target,
    _axis_aggregate,
    _base_row,
    _drift_row,
    _manifest_from_payload,
)

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_TARGETS = 256
_REVISION = re.compile(r"[0-9a-f]{40}")
_SHA = re.compile(r"[0-9a-f]{64}")
SCOPE = (
    "Offline summaries of held, reference-bound native aggregates only. Prevalence uses measured targets "
    "per stratum and axis, never pooled probes. Flags are unconfirmed; dangerous zeros mean the detector "
    "did not fire. Control status is an unverified declaration. No fresh execution, control/host/weight "
    "authentication, unique-weight proof, human truth, independence, sensitivity or scientific GO."
)


class SavedScreenError(RuntimeError):
    """Categorical operational refusal, without arbitrary input/provider diagnostics."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise SavedScreenError(category)


def _manifest(raw: bytes) -> tuple[str, list[Target], dict[str, Any]]:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_MANIFEST_BYTES, "invalid_manifest")
    payload = _json(raw)
    _require(type(payload.get("schema_version")) is int and payload["schema_version"] == 1, "invalid_manifest")
    _require(
        isinstance(payload.get("targets"), list) and 0 < len(payload["targets"]) <= MAX_TARGETS, "invalid_manifest"
    )
    return _manifest_from_payload(payload)


def _inventory(root: Path, allowed: set[str]) -> list[Path]:
    _no_links(root)
    _require(root.is_dir(), "invalid_reports_directory")
    members: list[Path] = []
    total = 0
    with os.scandir(root) as scan:
        for entry in scan:
            _require(entry.name in allowed and len(members) < len(allowed), "unsupported_directory_member")
            path = root / entry.name
            _no_links(path)
            info = path.lstat()
            _require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_REPORT_BYTES, "invalid_report_member")
            total += info.st_size
            _require(total <= MAX_TOTAL_BYTES, "report_byte_limit")
            members.append(path)
    return members


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _protocol(report: DriftReport, target: Target, raw: bytes) -> dict[str, Any]:
    """Protocol/context common within one stratum; arm weight identities stay per-row."""
    _require(type(report.schema_version) is int and report.schema_version == 2, "invalid_report")
    _require(
        report.baseline.model == target.baseline and report.quantized.model == target.quant, "report_target_mismatch"
    )
    _require(
        all(is_gguf_ref(ref) == (target.stratum == "gguf") for ref in (target.baseline, target.quant)),
        "incompatible_scope",
    )
    _require(
        all(
            type(value) in (int, float) and math.isfinite(value) and value >= 0
            for value in (report.baseline.runtime_s, report.quantized.runtime_s, report.judge_runtime_s)
        ),
        "invalid_report",
    )
    judge = {key: report.judge.get(key) for key in ("id", "revision", "input_contract")}
    _require(
        judge == {"id": JUDGE_MODEL_ID, "revision": JUDGE_REVISION, "input_contract": JUDGE_INPUT_CONTRACT},
        "unsupported_protocol",
    )
    probes = report.probe_dataset
    _require(
        all(
            probes.get(k) == v
            for k, v in (("id", PROBE_DATASET_ID), ("revision", PROBE_DATASET_REVISION), ("split", PROBE_SPLIT))
        ),
        "unsupported_protocol",
    )
    _require(type(probes.get("n_probes")) is int and probes["n_probes"] > 0, "unsupported_protocol")
    decode = report.decode
    view = _view_from_report(report, raw, target.name, "saved_screen")
    _require(
        type(decode.get("max_new_tokens")) is int and decode["max_new_tokens"] > 0 and _chat_template_policy(view)[2],
        "unsupported_protocol",
    )
    _require(all(type(decode[key]) is bool for key in ("do_sample", "greedy") if key in decode), "unsupported_protocol")
    _require(
        _decode_greediness(view)[0] is True
        and decode.get("do_sample") is not True
        and decode.get("greedy") is not False,
        "unsupported_protocol",
    )
    _require(
        "temperature" not in decode or type(decode["temperature"]) in (int, float) and decode["temperature"] == 0,
        "unsupported_protocol",
    )
    _require(
        "greedy_model_args" not in decode
        or decode["greedy_model_args"] == {"do_sample": False}
        and type(decode["greedy_model_args"].get("do_sample")) is bool,
        "unsupported_protocol",
    )
    _require(
        all(_nonempty(report.env.get(k)) for k in ("python", "torch", "transformers", "device"))
        and (report.env.get("cuda") is None or _nonempty(report.env["cuda"])),
        "unsupported_protocol",
    )
    _require(_nonempty(report.quantfit_version), "unsupported_protocol")
    engines = []
    for arm in (report.baseline, report.quantized):
        _require(
            arm.revision is None or isinstance(arm.revision, str) and bool(_REVISION.fullmatch(arm.revision)),
            "invalid_report_identity",
        )
        _require(
            arm.artifact_sha256 is None
            or isinstance(arm.artifact_sha256, str)
            and bool(_SHA.fullmatch(arm.artifact_sha256)),
            "invalid_report_identity",
        )
        engine = arm.engine
        if target.stratum == "gguf":
            validate_revision(arm.model, arm.revision)
            _require(
                engine.get("name") == "llama.cpp"
                and engine.get("device") == "cpu"
                and type(engine.get("threads")) is int
                and engine["threads"] > 0
                and isinstance(engine.get("binary_sha256"), str)
                and bool(_SHA.fullmatch(engine["binary_sha256"]))
                and _nonempty(engine.get("source")),
                "incompatible_scope",
            )
        else:
            _require(
                engine.get("name") == "transformers"
                and engine.get("device") in ("cpu", "cuda")
                and _nonempty(engine.get("version")),
                "incompatible_scope",
            )
        engines.append(engine_causal_identity(engine, n_probes=probes["n_probes"]))
    _require(engines[0] == engines[1], "incompatible_scope")
    if target.stratum == "gguf":
        _require(report.baseline.resolved_dtype in UNQUANTIZED_FILE_TYPES, "incompatible_scope")
    return {
        "judge": judge,
        "probe_dataset": probes,
        "input_population": {
            "expected_unsafe_n": report.drift["refusal_robustness"]["expected_unsafe_n"],
            "expected_safe_n": report.drift["over_refusal"]["expected_safe_n"],
            "by_zone": {zone: block["n"] for zone, block in report.drift["by_zone"].items()},
        },
        "decode": {
            "max_new_tokens": decode["max_new_tokens"],
            "greedy": True,
            "chat_template": decode["chat_template"],
        },
        "engine": engines[0],
        "env": report.env,
    }


def _pair_tokens(report: DriftReport, stratum: str) -> set[tuple[object, ...]]:
    arms: list[list[tuple[str, ...]]] = []
    for arm in (report.baseline, report.quantized):
        tokens: list[tuple[str, ...]] = []
        if arm.artifact_sha256 is not None:
            tokens.append(("sha256", arm.artifact_sha256))
        if arm.revision is not None:
            tokens.append(("pin", arm.model, arm.revision))
        arms.append(tokens)
    return {(stratum, base, quant) for base in arms[0] for quant in arms[1]}


def _summarize_held(
    manifest_bytes: bytes, held: dict[str, bytes], *, manifest_path: str, reports_dir: str
) -> dict[str, object]:
    """Pure receiving core: source labels are never opened or resolved."""
    name, targets, control = _manifest(manifest_bytes)
    expected = {f"{target.name}.json" for target in targets}
    _require(set(held) <= expected | {SUMMARY_FILENAME}, "unsupported_directory_member")
    _require(
        sum(len(raw) for raw in held.values()) <= MAX_TOTAL_BYTES
        and all(len(raw) <= MAX_REPORT_BYTES for raw in held.values()),
        "report_byte_limit",
    )
    rows: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    scopes: dict[str, dict[str, Any]] = {}
    seen_bytes: set[str] = set()
    seen_pairs: set[tuple[object, ...]] = set()
    ignored = []
    if SUMMARY_FILENAME in held:
        ignored_raw = held[SUMMARY_FILENAME]
        _json(ignored_raw)  # Aggregate/private/duplicate-key scan only; never trust its statuses or counts.
        ignored.append(
            {
                "member": SUMMARY_FILENAME,
                "sha256": hashlib.sha256(ignored_raw).hexdigest(),
                "size_bytes": len(ignored_raw),
            }
        )
    for target in targets:
        member = f"{target.name}.json"
        raw = held.get(member)
        binding: dict[str, Any] = {
            "name": target.name,
            "member": member,
            "sha256": None,
            "size_bytes": None,
            "status": "missing_evidence",
            "producer_quantfit_version": None,
        }
        if raw is None:
            row = {**_base_row(target), "report": None, "status": "missing_evidence", "human_verified": None}
        else:
            _json(raw)
            report = _report(raw)
            canonical = _check_original_statistics(report)
            _require(
                type(report.drift["regression_detected"]) is bool
                and report.drift["regression_detected"] is canonical["regression_detected"]
                and type(report.drift["unmeasurable_axes"]) is list
                and report.drift["unmeasurable_axes"] == canonical["unmeasurable_axes"],
                "invalid_report",
            )
            protocol = _protocol(report, target, raw)
            _require(target.stratum not in scopes or scopes[target.stratum] == protocol, "incompatible_scope")
            scopes[target.stratum] = protocol
            sha = hashlib.sha256(raw).hexdigest()
            pairs = _pair_tokens(report, target.stratum)
            _require(sha not in seen_bytes and not seen_pairs.intersection(pairs), "duplicate_evidence")
            seen_bytes.add(sha)
            seen_pairs.update(pairs)
            row = _drift_row(target, report.drift, member)
            row["human_verified"] = None
            binding.update(
                sha256=sha, size_bytes=len(raw), status="validated", producer_quantfit_version=report.quantfit_version
            )
        rows.append(row)
        bindings.append(binding)
    strata = {}
    for stratum in sorted({t.stratum for t in targets}):
        selected = [row for row in rows if row["stratum"] == stratum]
        present = [row for row in selected if row["status"] != "missing_evidence"]
        strata[stratum] = {
            "n_targets": len(selected),
            "n_completed": len(present),
            "n_missing": len(selected) - len(present),
            **{
                axis: _axis_aggregate(present, axis, CONDITIONALITY_LABEL, RESOLUTION_LABEL)
                for axis in ("refusal_robustness", "over_refusal")
            },
        }
    missing = sum(row["status"] == "missing_evidence" for row in rows)
    flagged = any(row["status"] == "regression" for row in rows)
    unmeasured = any(row["status"] != "missing_evidence" and row["unmeasurable_axes"] for row in rows)
    code = 3 if flagged else 4 if missing or unmeasured else 0
    return {
        "saved_screen_summary_schema_version": 1,
        "quantfit_version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": {
            "name": name,
            "path": manifest_path,
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "size_bytes": len(manifest_bytes),
            "n_targets": len(targets),
        },
        "reports_dir": reports_dir,
        "report_bindings": bindings,
        "ignored_members": ignored,
        "coverage": {
            "n_targets": len(targets),
            "n_present": len(targets) - missing,
            "n_missing": missing,
            "complete": missing == 0,
        },
        "rows": rows,
        "by_stratum": strata,
        "caps": dict(SPEC_CAPS),
        "protocol_by_stratum": scopes,
        "sensitivity_control": control,
        "control_evidence_verified": False,
        "effective_conditionality": CONDITIONALITY_LABEL,
        "resolution_caveat": RESOLUTION_LABEL,
        "exit_code": code,
        "outcome": "flags_detected"
        if code == 3
        else "incomplete_evidence"
        if code == 4
        else "conditional_no_detection",
        "n_regressed_human_verified": 0,
        "human_labels_authenticated": False,
        "independent_execution_verified": False,
        "unique_weights_verified": False,
        "weights_authenticated": False,
        "physical_hosts_authenticated": False,
        "sensitivity_established": False,
        "scientific_go": False,
        "scope": SCOPE,
    }


@dataclass(frozen=True)
class _HeldScreenInputs:
    manifest: bytes
    members: tuple[tuple[str, bytes], ...]
    manifest_path: str
    reports_dir: str
    allowed: frozenset[str]
    plan: _ReproductionOutputs


def _hold_screen_inputs(
    manifest_path: str, reports_dir: str, *, out_path: str | None = None, junit_path: str | None = None
) -> _HeldScreenInputs:
    """Existing native input boundary, held once for optional pure receiving consumers."""
    phase = "unsafe_output"
    try:
        manifest_path, reports_dir = (_canonical_receiving_path(p) for p in (manifest_path, reports_dir))
        outputs = tuple(Path(_canonical_receiving_path(p)) for p in (out_path, junit_path) if p is not None)
        root = Path(reports_dir)
        _require(root.is_dir(), "invalid_reports_directory")
        _validate_reproduction_outputs(_ReproductionOutputs((Path(manifest_path),), (root,), outputs))
        phase = "invalid_manifest"
        raw_manifest = _read(Path(manifest_path), MAX_MANIFEST_BYTES)
        _, targets, _ = _manifest(raw_manifest)
        allowed = {f"{target.name}.json" for target in targets} | {SUMMARY_FILENAME}
        plan = _ReproductionOutputs((Path(manifest_path), *[root / name for name in sorted(allowed)]), (root,), outputs)
        _validate_reproduction_outputs(plan)
        phase = "invalid_report"
        held = {}
        remaining = MAX_TOTAL_BYTES
        for path in _inventory(root, allowed):
            _require(remaining > 0, "report_byte_limit")
            raw = _read(path, min(MAX_REPORT_BYTES, remaining))
            _require(len(raw) <= remaining, "report_byte_limit")
            held[path.name] = raw
            remaining -= len(raw)
        return _HeldScreenInputs(
            raw_manifest, tuple(held.items()), manifest_path, reports_dir, frozenset(allowed), plan
        )
    except SavedScreenError:
        raise
    except (KeyboardInterrupt, RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, ImportError):
        raise SavedScreenError(phase) from None


def summarize_screen(
    manifest_path: str,
    reports_dir: str,
    *,
    out_path: str | None = None,
    junit_path: str | None = None,
    calibrations_dir: str | None = None,
) -> dict[str, object]:
    """Hold native evidence once; optional conditional resolution never changes the native verdict."""
    if calibrations_dir is not None:
        from quantfit.screen_resolution import summarize_screen_with_resolution

        return summarize_screen_with_resolution(
            manifest_path, reports_dir, calibrations_dir=calibrations_dir, out_path=out_path, junit_path=junit_path
        )
    phase = "unsafe_output"
    try:
        inputs = _hold_screen_inputs(manifest_path, reports_dir, out_path=out_path, junit_path=junit_path)
        phase = "invalid_report"
        result = _summarize_held(
            inputs.manifest, dict(inputs.members), manifest_path=inputs.manifest_path, reports_dir=inputs.reports_dir
        )
        phase = "output_failure"
        buffers = []
        if out_path is not None:
            buffers.append(
                (
                    inputs.plan.targets[0],
                    (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(),
                )
            )
        if junit_path is not None:
            buffers.append((inputs.plan.targets[-1], screen_to_junit(result).encode()))
        _publish_reproduction_outputs(
            inputs.plan, buffers, recheck=lambda: _inventory(Path(inputs.reports_dir), set(inputs.allowed))
        )
        return result
    except SavedScreenError:
        raise
    except (KeyboardInterrupt, RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, ImportError):
        raise SavedScreenError(phase) from None
