"""Frozen native GGUF reruns with separate aggregate comparison and assessment."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantfit import __version__
from quantfit.backends.gguf import _sha256, llama_server_bin
from quantfit.bundle import _json, _no_links, _read, _report
from quantfit.cold_run import cold_run
from quantfit.evidence import _promoter
from quantfit.reference_assessment import (
    MAX_TARGET_BYTES,
    SUPPORTED_PROFILE,
    SUPPORTED_SPEC,
    _assess_bundle_held,
    _target,
)
from quantfit.replay_bundle import (
    BUNDLE_SCHEMA,
    ROLES,
    _result,
    _validate,
    _verified_bundle,
    _write_member,
)
from quantfit.replay_bundle import (
    SCOPE as BUNDLE_SCOPE,
)
from quantfit.reproduce import (
    _bundle_comparison_held,
    _canonical_receiving_path,
    _compare_views,
    _prepare_reproduction_outputs,
    _ReproductionOutputs,
    _validate_reproduction_outputs,
)
from quantfit.resolution import MAX_REPORT_BYTES
from quantfit.safety import gguf_arm
from quantfit.safety.verify import (
    DECODE_CHAT_TEMPLATE_POLICY,
    JUDGE_INPUT_CONTRACT,
    JUDGE_MODEL_ID,
    JUDGE_REVISION,
    PROBE_DATASET_ID,
    PROBE_DATASET_REVISION,
    PROBE_SPLIT,
)

SCOPE = (
    "Observed fresh native child processes and exact aggregate bytes only. Native measurement exits, "
    "comparison and receiving reference assessment remain separate. No physical-host or independent-execution "
    "authentication, human-label truth, sensitivity, registry admission or scientific GO is established. "
    "Local GGUF Hub lineage remains unknown."
)


def _require(value: bool, category: str = "execution_recipe_mismatch") -> None:
    if not value:
        raise RuntimeError(category)


def _encode(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _runner_supported() -> bool:
    return os.name == "posix"


def _execution_target(raw: bytes) -> dict[str, Any]:
    target = _target(raw)
    _require(target["spec_version"] == SUPPORTED_SPEC and target["profile"] == SUPPORTED_PROFILE)
    arms = target["arms"]
    _require(arms["baseline"]["model"] != arms["quantized"]["model"] or arms["baseline"] == arms["quantized"])
    for name in ("baseline", "quantized"):
        arm = target["arms"][name]
        _require(all(arm[k] is not None for k in ("model", "resolved_dtype", "artifact_sha256", "size_bytes")))
        _require(gguf_arm.is_gguf_ref(arm["model"]))
        if arm["model"].startswith("hf:"):
            _require(isinstance(arm["revision"], str))
        else:
            _require(arm["revision"] is None)
            _no_links(Path(arm["model"]).absolute())
        gguf_arm.validate_revision(arm["model"], arm["revision"])
    _require(target["arms"]["baseline"]["resolved_dtype"] in gguf_arm.UNQUANTIZED_FILE_TYPES)
    expected = {
        "judge": {"id": JUDGE_MODEL_ID, "revision": JUDGE_REVISION, "input_contract": JUDGE_INPUT_CONTRACT},
        "probe_dataset": {
            "id": PROBE_DATASET_ID,
            "revision": PROBE_DATASET_REVISION,
            "split": PROBE_SPLIT,
            "n_probes": 40,
        },
        "decode": {"max_new_tokens": 64, "do_sample": False, "chat_template": DECODE_CHAT_TEMPLATE_POLICY},
    }
    _require(all(target[group] == values for group, values in expected.items()))
    _require(all(value is not None for value in target["engine"].values()))
    return target


def _asset(path: Path) -> Path:
    # Hub snapshot symlinks are an SDK-supported cache layout; guard the real blob too.
    real = path.resolve(strict=True)
    _require(stat.S_ISREG(real.stat().st_mode))
    return real


def _recipe_guard(recipe: dict[str, Any]) -> Callable[[gguf_arm.ResolvedGguf, Path, int], None]:
    _require(set(recipe) == {"target", "weights", "executable"})
    declaration = _execution_target(_encode(recipe["target"]))
    _require(isinstance(recipe["weights"], dict) and set(recipe["weights"]) == {"baseline", "quantized"})
    _require(all(isinstance(path, str) for path in (*recipe["weights"].values(), recipe["executable"])))

    def guard(arm: gguf_arm.ResolvedGguf, server: Path, threads: int) -> None:
        candidates = [name for name in ("baseline", "quantized") if arm.ref == declaration["arms"][name]["model"]]
        _require(bool(candidates))
        _require(type(threads) is int and threads == declaration["engine"]["threads"])
        _require(str(_asset(server)) == recipe["executable"])
        _require(_sha256(server) == declaration["engine"]["binary_sha256"])
        _require(
            any(
                str(_asset(arm.path)) == recipe["weights"][name]
                and arm.revision == declaration["arms"][name]["revision"]
                and arm.file_type == declaration["arms"][name]["resolved_dtype"]
                and arm.sha256 == declaration["arms"][name]["artifact_sha256"]
                and _sha256(arm.path) == declaration["arms"][name]["artifact_sha256"]
                and arm.path.stat().st_size == declaration["arms"][name]["size_bytes"]
                for name in candidates
            )
        )

    return guard


def _load_execution_guard(path: str, sha256: str) -> Callable[[gguf_arm.ResolvedGguf, Path, int], None]:
    """Read one bounded child recipe, bind its bytes, then guard each native server."""
    try:
        raw = _read(Path(path), MAX_TARGET_BYTES)
        _require(hashlib.sha256(raw).hexdigest() == sha256)
        return _recipe_guard(_json(raw))
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError):
        raise RuntimeError("execution_recipe_mismatch") from None


def _bundle_buffers(held: dict[str, bytes], root: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    original, receiving = _validate(held, [str(root / ROLES[f"replicate-{i}"]) for i in range(1, 4)])
    manifest = {
        "bundle_schema": BUNDLE_SCHEMA,
        "quantfit_version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scientific_claims_verified": False,
        "scope": BUNDLE_SCOPE,
        "files": [
            {
                "role": role,
                "path": ROLES[role],
                "sha256": hashlib.sha256(held[role]).hexdigest(),
                "size_bytes": len(held[role]),
            }
            for role in ROLES
        ],
    }
    return _result(root, manifest, original=original, receiving=receiving), {
        **{ROLES[k]: held[k] for k in ROLES},
        "manifest.json": _encode(manifest),
    }


def _discard_stage(stage: Path, names: list[str]) -> None:
    _no_links(stage)
    directories = {stage}
    for name in ["manifest.json", *[name for name in names if name != "manifest.json"]]:
        path = stage / name
        _no_links(path)
        path.unlink(missing_ok=True)
        directories.update(p for p in path.parents if p == stage or p.is_relative_to(stage))
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        if directory.exists():
            directory.rmdir()


def rerun_candidate(
    bundle_path: str, target: str, out_path: str, *, timeout_seconds: float = 3600
) -> dict[str, object]:
    """Run one frozen three-child recipe; publish a new closed aggregate directory."""
    result: dict[str, Any] = {
        "reference_replay_schema_version": 1,
        "quantfit_version": __version__,
        "exit_code": 2,
        "status": "preflight_refused",
        "error": None,
        "output_path": None,
        "reference_assessment": None,
        "fresh_assessment": None,
        "comparison": None,
        "cold_run": None,
        "original_native_exits": [],
        "fresh_native_exits": [],
        "execution_observations": None,
        "producer_locations_verified": False,
        "independent_execution_verified": False,
        "physical_hosts_authenticated": False,
        "human_labels_authenticated": False,
        "sensitivity_established": False,
        "scientific_go": False,
        "scope": SCOPE,
    }
    phase = "invalid_timeout"
    stage: Path | None = None
    stage_identity: tuple[int, int] | None = None
    destination: Path | None = None
    staged: list[str] = []
    try:
        _require(
            type(timeout_seconds) in (int, float) and 0 < timeout_seconds <= 3600 and math.isfinite(timeout_seconds)
        )
        phase = "unsupported_runner"
        _require(_runner_supported())
        phase = "unsafe_output"
        bundle_path, target, out_path = (_canonical_receiving_path(p) for p in (bundle_path, target, out_path))
        destination = Path(out_path)
        _require(not destination.exists() and destination.parent.is_dir())
        _prepare_reproduction_outputs([target], [bundle_path], [out_path])
        promote = _promoter()
        phase = "invalid_inputs"
        target_bytes = _read(Path(target), MAX_TARGET_BYTES)
        declaration = _target(target_bytes)
        verified, original = _verified_bundle(bundle_path)
        _require(verified["integrity_verified"] is True)
        assessment: dict[str, Any] = _assess_bundle_held(bundle_path, target_bytes, verified, original)
        result["reference_assessment"] = assessment
        result["original_native_exits"] = assessment["native_exits"]
        phase = "execution_recipe_mismatch"
        _require(
            all(row["pass"] is not False for name, row in assessment["criteria"].items() if name.startswith("run-"))
        )
        _execution_target(target_bytes)  # Reject missing/moving facts before invoking the resolver.
        arms = declaration["arms"]
        base, quant = gguf_arm.resolve_pair(
            arms["baseline"]["model"],
            arms["quantized"]["model"],
            None,
            baseline_revision=arms["baseline"]["revision"],
            quant_revision=arms["quantized"]["revision"],
        )
        server = llama_server_bin()
        recipe: dict[str, Any] = {
            "target": declaration,
            "weights": {"baseline": str(_asset(base.path)), "quantized": str(_asset(quant.path))},
            "executable": str(_asset(server)),
        }
        guard = _recipe_guard(recipe)
        for arm in (base, quant):
            guard(arm, server, gguf_arm._threads())
        sources = [target, *recipe["weights"].values(), recipe["executable"]]
        plan = _prepare_reproduction_outputs(sources, [bundle_path], [out_path])
        result["execution_observations"] = {
            "weight_files": [
                {
                    "arm": name,
                    "sha256": arms[name]["artifact_sha256"],
                    "size_bytes": arms[name]["size_bytes"],
                    "resolved_revision": arms[name]["revision"],
                }
                for name in ("baseline", "quantized")
            ],
            "binary_sha256": declaration["engine"]["binary_sha256"],
            "threads": declaration["engine"]["threads"],
            "cpu_offload": dict(gguf_arm.CPU_OFFLOAD_CONTROLS),
            "local_hub_lineage_known": False,
        }
        phase = "native_operational_failure"
        cold: dict[str, Any] | None = None
        fresh: dict[str, bytes] = {}
        with tempfile.TemporaryDirectory(prefix="quantfit-replay-private-", dir=destination.parent) as private:
            private_root = Path(private)
            recipe_raw = _encode(recipe)
            recipe_path = private_root / "recipe.json"
            _no_links(recipe_path)
            _write_member(recipe_path, recipe_raw)
            _validate_reproduction_outputs(plan)
            try:
                cold = cold_run(
                    base.ref,
                    quant.ref,
                    str(private_root / "native"),
                    timeout_seconds=timeout_seconds,
                    max_new_tokens=64,
                    baseline_revision=base.revision,
                    quant_revision=quant.revision,
                    _execution_recipe=(str(recipe_path), hashlib.sha256(recipe_raw).hexdigest()),
                )
            except (KeyboardInterrupt, RuntimeError, OSError, ValueError, TypeError, ImportError):
                receipt = private_root / "native/cold-run.json"
                if receipt.is_file():
                    cold = json.loads(_read(receipt, MAX_REPORT_BYTES))
                result["error"] = "native_operational_failure"
            result["cold_run"] = cold
            if cold is not None:
                result["fresh_native_exits"] = [r.get("native_exit_code") for r in cold["runs"]]
                for index in range(1, 4):
                    path = private_root / f"native/run-{index}/report.json"
                    if path.is_file():
                        raw = _read(path, MAX_REPORT_BYTES)
                        report = _report(raw)
                        run = cold["runs"][index - 1]
                        observed_hash = hashlib.sha256(raw).hexdigest()
                        _require(run["report"]["sha256"] == observed_hash)
                        _require(run.get("final_report", run["report"])["sha256"] == observed_hash)
                        _require(
                            type(run["native_exit_code"]) is int
                            and run["native_exit_code"]
                            == (
                                3
                                if report.drift["regression_detected"]
                                else 4
                                if report.drift["unmeasurable_axes"]
                                else 0
                            )
                        )
                        for name in ("baseline", "quantized"):
                            observed = getattr(report, name)
                            _require(
                                all(
                                    getattr(observed, k) == arms[name][k]
                                    for k in ("model", "revision", "artifact_sha256", "resolved_dtype")
                                )
                            )
                            _require(
                                all(
                                    type(observed.engine.get(k)) is type(v) and observed.engine[k] == v
                                    for k, v in declaration["engine"].items()
                                )
                            )
                        for group in ("judge", "probe_dataset", "decode"):
                            _require(
                                all(
                                    type(getattr(report, group).get(k)) is type(v) and getattr(report, group)[k] == v
                                    for k, v in declaration[group].items()
                                )
                            )
                        fresh[f"replicate-{index}"] = raw
                if cold.get("t0") is not None:
                    fresh["t0"] = _read(private_root / "native/t0.json", MAX_REPORT_BYTES)
            for arm in (base, quant):
                guard(arm, server, gguf_arm._threads())
        _validate_reproduction_outputs(plan)
        files = {"target.json": target_bytes, "reference-assessment.json": _encode(assessment)}
        _, original_files = _bundle_buffers(original, destination / "original")
        files.update({f"original/{name}": raw for name, raw in original_files.items()})
        if cold is not None:
            files["native-cold-run.json"] = _encode(cold)
        complete = (
            cold is not None
            and cold.get("exit_code") in (0, 3)
            and len(cold["runs"]) == 3
            and all(
                r.get("status") == "completed"
                and r.get("cleanup", {}).get("direct_child_reaped") is True
                and r.get("cleanup", {}).get("no_live_group_members_observed") is True
                for r in cold["runs"]
            )
        )
        if complete and set(fresh) == set(ROLES) and result["error"] is None:
            fresh_verified, fresh_files = _bundle_buffers(fresh, destination / "fresh")
            fresh_assessment: dict[str, Any] = _assess_bundle_held(
                str(destination / "fresh"), target_bytes, fresh_verified, fresh
            )
            ref_view, ref_t0, ref_evidence = _bundle_comparison_held(verified, original, "reference")
            cand_view, cand_t0, cand_evidence = _bundle_comparison_held(fresh_verified, fresh, "candidate")
            comparison = _compare_views(ref_view, cand_view, t0_ref=ref_t0, t0_cand=cand_t0, same_path=False)
            comparison["bundle_evidence"] = {"reference": ref_evidence, "candidate": cand_evidence}
            result.update(fresh_assessment=fresh_assessment, comparison=comparison)
            result["exit_code"] = (
                3
                if fresh_assessment["t0"]["protocol_pass"] is not True
                or fresh_assessment["full_report_repeatability"]["pass"] is not True
                else comparison["exit_code"]
            )
            result["status"] = (
                "fresh_disagreement"
                if result["exit_code"] == 3 and comparison["exit_code"] != 3
                else comparison["outcome"]
            )
            files.update({f"fresh/{name}": raw for name, raw in fresh_files.items()})
            files.update({"fresh-assessment.json": _encode(fresh_assessment), "comparison.json": _encode(comparison)})
        else:
            result.update(exit_code=2, status="native_operational_failure", error="native_operational_failure")
            files.update(
                {f"failed-report-{role[-1]}.json": raw for role, raw in fresh.items() if role.startswith("replicate-")}
            )
        phase = "publication_failure"
        result["output_path"] = out_path
        files["replay.json"] = _encode(result)
        manifest = {
            "reference_replay_schema_version": 1,
            "exit_code": result["exit_code"],
            "status": result["status"],
            "files": [
                {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
                for name, raw in files.items()
            ],
            "scientific_go": False,
            "scope": SCOPE,
        }
        files["manifest.json"] = _encode(manifest)  # Advertisement is written last.
        stage = Path(tempfile.mkdtemp(prefix=".quantfit-replay-", dir=destination.parent))
        observed_stage = stage.stat()
        stage_identity = (observed_stage.st_dev, observed_stage.st_ino)
        for name, raw in files.items():
            _validate_reproduction_outputs(plan)
            _no_links(stage)
            path = stage / name
            _no_links(path.parent)
            path.parent.mkdir(parents=True, exist_ok=True)
            _validate_reproduction_outputs(_ReproductionOutputs(plan.sources, plan.roots, (path,)))
            staged.append(name)
            _write_member(path, raw)
        _validate_reproduction_outputs(plan)
        _require(not destination.exists(), "unsafe_output")
        _require(
            {p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file()} == set(files), "unsafe_output"
        )
        for name, raw in files.items():
            path = stage / name
            _validate_reproduction_outputs(_ReproductionOutputs(plan.sources, plan.roots, (path,)))
            _require(_read(path, MAX_REPORT_BYTES) == raw, "publication_failure")
        for arm in (base, quant):
            guard(arm, server, gguf_arm._threads())
        promote(stage, destination)
        stage = None
        return result
    except (KeyboardInterrupt, RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, ImportError):
        result.update(exit_code=2, status="operational_failure", error=phase, output_path=None)
        cleanup = stage
        if stage_identity is not None and destination is not None:
            try:
                _no_links(destination)
                if destination.exists():
                    observed = destination.stat()
                    if (observed.st_dev, observed.st_ino) == stage_identity:
                        cleanup = destination  # Exclusive promotion moved this owned directory before failing.
            except (KeyboardInterrupt, RuntimeError, OSError):
                result.update(error="cleanup_failure", preserved_stage=str(destination))
        if cleanup is not None:
            try:
                _discard_stage(cleanup, staged)
            except (KeyboardInterrupt, RuntimeError, OSError):
                result.update(error="cleanup_failure", preserved_stage=str(cleanup))
        return result
