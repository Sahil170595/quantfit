"""Optional conditional resolution over one held native screen and named calibrations."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quantfit import resolution
from quantfit import saved_screen as saved
from quantfit.bundle import _json, _no_links, _read
from quantfit.junit import screen_to_junit
from quantfit.reproduce import (
    _canonical_receiving_path,
    _publish_reproduction_outputs,
    _ReproductionOutputs,
    _validate_reproduction_outputs,
)
from quantfit.safety.calibration_binding import MAX_CALIBRATION_BYTES, BoundCalibration, load_bound_calibration_bytes
from quantfit.safety.gguf_arm import is_gguf_ref
from quantfit.screen import Target

MAX_TOTAL_CALIBRATION_BYTES = 64 * 1024 * 1024
MAX_ANALYSIS_WORK_UNITS = resolution.MAX_PROBES**2
SCOPE = (
    "Optional per-target conditional resolution only; native flags, prevalence, human status, control "
    "caveats and exit code are unchanged. Calibration counts and stored/actual scope are checked, but "
    "human labels, directional-error assumptions, independence, source/weight identity and sensitivity "
    "are not authenticated. Missing calibration is not a new gate failure; pending calibration has no "
    "observed-report match. No pooling, new safety verdict or scientific GO."
)


@dataclass(frozen=True)
class _HeldCalibrations:
    root: Path
    members: tuple[tuple[str, bytes], ...]
    allowed: frozenset[str]


def _inventory(root: Path, allowed: frozenset[str]) -> dict[str, Path]:
    _no_links(root)
    saved._require(root.is_dir(), "invalid_calibrations_directory")
    members: dict[str, Path] = {}
    total = 0
    with os.scandir(root) as scan:
        for entry in scan:
            saved._require(
                entry.name in allowed and entry.name not in members and len(members) < len(allowed),
                "unsupported_calibration_member",
            )
            path = root / entry.name
            _no_links(path)
            info = path.lstat()
            saved._require(
                stat.S_ISREG(info.st_mode) and info.st_size <= MAX_CALIBRATION_BYTES, "invalid_calibration_member"
            )
            total += info.st_size
            saved._require(total <= MAX_TOTAL_CALIBRATION_BYTES, "calibration_byte_limit")
            members[entry.name] = path
    return members


def _hold_calibrations(root: Path, allowed: frozenset[str]) -> _HeldCalibrations:
    remaining = MAX_TOTAL_CALIBRATION_BYTES
    members = []
    for name, path in _inventory(root, allowed).items():
        saved._require(remaining > 0, "calibration_byte_limit")
        raw = _read(path, min(MAX_CALIBRATION_BYTES, remaining))
        saved._require(len(raw) <= remaining, "calibration_byte_limit")
        members.append((name, raw))
        remaining -= len(raw)
    return _HeldCalibrations(root, tuple(members), allowed)


def _target_binding(target: Target, calibration: BoundCalibration) -> None:
    expected_engine = "llama.cpp" if target.stratum == "gguf" else "transformers"
    for arm, model in (("baseline", target.baseline), ("quantized", target.quant)):
        identity = calibration.identity[arm]
        saved._require(
            identity["model"] == model
            and is_gguf_ref(identity["model"]) == (target.stratum == "gguf")
            and identity["engine"]["name"] == expected_engine,
            "calibration_target_mismatch",
        )
        device = identity["engine"].get("device")
        saved._require(
            device is None or (device == "cpu" if target.stratum == "gguf" else device in ("cpu", "cuda")),
            "calibration_target_mismatch",
        )


def _summarize_inputs(native: saved._HeldScreenInputs, calibrations: _HeldCalibrations) -> dict[str, Any]:
    """Pure held receiving/preflight followed by the single authoritative analysis path."""
    result: dict[str, Any] = saved._summarize_held(
        native.manifest, dict(native.members), manifest_path=native.manifest_path, reports_dir=native.reports_dir
    )
    _, targets, _ = saved._manifest(native.manifest)
    allowed = {f"{target.name}.json" for target in targets}
    saved._require(
        type(calibrations.members) is tuple and len(calibrations.members) <= saved.MAX_TARGETS,
        "invalid_calibration_inputs",
    )
    raw_calibrations: dict[str, bytes] = {}
    for entry in calibrations.members:
        saved._require(type(entry) is tuple and len(entry) == 2, "invalid_calibration_inputs")
        name, raw = entry
        saved._require(
            type(name) is str
            and name in allowed
            and name not in raw_calibrations
            and type(raw) is bytes
            and len(raw) <= MAX_CALIBRATION_BYTES,
            "invalid_calibration_inputs",
        )
        raw_calibrations[name] = raw
    saved._require(
        sum(len(raw) for raw in raw_calibrations.values()) <= MAX_TOTAL_CALIBRATION_BYTES, "calibration_byte_limit"
    )
    reports = dict(native.members)
    prepared: list[tuple[Target, dict[str, Any], bytes | None, bytes | None, BoundCalibration | None]] = []
    work = 0
    for index, target in enumerate(targets):
        member = f"{target.name}.json"
        report_raw, calibration_raw = reports.get(member), raw_calibrations.get(member)
        calibration = None
        if calibration_raw is not None:
            _json(calibration_raw)  # Aggregate privacy/duplicate-key checks before authoritative bound receiving.
            calibration = load_bound_calibration_bytes(calibration_raw)
            _target_binding(target, calibration)
            if report_raw is not None:
                report = resolution.parse_report_bytes(report_raw)
                calibration.match_report(report)
                resolution._axes(report)  # All structural/count/probe resource checks, without resolution math.
                work += report.probe_dataset["n_probes"] ** 2
                saved._require(work <= MAX_ANALYSIS_WORK_UNITS, "resolution_work_limit")
        prepared.append((target, result["report_bindings"][index], report_raw, calibration_raw, calibration))
    rows = []
    for target, binding, report_raw, calibration_raw, calibration in prepared:
        analysis = None
        if report_raw is not None and calibration_raw is not None:
            _, analysis = resolution.analyze_resolution_bytes(report_raw, calibration_raw)
            status = "analyzed"
        else:
            status = (
                "pending_report_missing"
                if calibration_raw is not None
                else "calibration_missing"
                if report_raw is not None
                else "report_and_calibration_missing"
            )
        rows.append(
            {
                "name": target.name,
                "native_report_sha256": binding["sha256"],
                "calibration": {
                    "member": f"{target.name}.json",
                    "status": "present" if calibration_raw is not None else "missing",
                    "sha256": hashlib.sha256(calibration_raw).hexdigest() if calibration_raw is not None else None,
                    "size_bytes": len(calibration_raw) if calibration_raw is not None else None,
                },
                "status": status,
                "binding_fingerprint": calibration.fingerprint if calibration is not None else None,
                "analysis": analysis,
            }
        )
    counts = {
        f"n_{status}": sum(row["status"] == status for row in rows)
        for status in ("analyzed", "calibration_missing", "pending_report_missing", "report_and_calibration_missing")
    }
    result["conditional_resolution"] = {
        "screen_resolution_schema_version": 1,
        "kind": "quantfit.screen-resolution",
        "rows": rows,
        "coverage": {"n_targets": len(rows), **counts, "complete": counts["n_analyzed"] == len(rows)},
        "analysis_work_units": work,
        "limits": {
            "calibration_bytes": MAX_CALIBRATION_BYTES,
            "total_calibration_bytes": MAX_TOTAL_CALIBRATION_BYTES,
            "max_targets": saved.MAX_TARGETS,
            "max_analysis_probes": resolution.MAX_PROBES,
            "max_analysis_work_units": MAX_ANALYSIS_WORK_UNITS,
        },
        "assumptions_verified": False,
        "human_labels_authenticated": False,
        "source_authentication": "unverified",
        "scientific_go": False,
        "scope": SCOPE,
    }
    return result


def summarize_screen_with_resolution(
    manifest_path: str,
    reports_dir: str,
    *,
    calibrations_dir: str,
    out_path: str | None = None,
    junit_path: str | None = None,
) -> dict[str, Any]:
    phase = "invalid_resolution_input"
    try:
        native = saved._hold_screen_inputs(manifest_path, reports_dir, out_path=out_path, junit_path=junit_path)
        root = Path(_canonical_receiving_path(calibrations_dir))
        saved._require(root != Path(native.reports_dir), "invalid_calibrations_directory")
        _, targets, _ = saved._manifest(native.manifest)
        allowed = frozenset(f"{target.name}.json" for target in targets)
        plan = _ReproductionOutputs(
            (*native.plan.sources, *(root / name for name in sorted(allowed))),
            (*native.plan.roots, root),
            native.plan.targets,
        )
        phase = "unsafe_output"
        _validate_reproduction_outputs(plan)
        phase = "invalid_calibration"
        calibrations = _hold_calibrations(root, allowed)
        result = _summarize_inputs(native, calibrations)
        phase = "output_failure"
        buffers = []
        if out_path is not None:
            buffers.append(
                (plan.targets[0], (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
            )
        if junit_path is not None:
            buffers.append((plan.targets[-1], screen_to_junit(result).encode()))

        def recheck() -> None:
            saved._inventory(Path(native.reports_dir), set(native.allowed))
            _inventory(root, allowed)

        _publish_reproduction_outputs(plan, buffers, recheck=recheck)
        return result
    except saved.SavedScreenError:
        raise
    except (KeyboardInterrupt, RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, ImportError):
        raise saved.SavedScreenError(phase) from None
