"""Analyze an existing run's conditional resolution without changing its verdict."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from quantfit import __version__
from quantfit.safety.calibration_binding import load_bound_calibration
from quantfit.safety.mde import mde_block, power_at
from quantfit.safety.report import ArmRun, DriftReport

MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_PROBES = 4096  # Bound the existing exact-binomial calculator's quadratic work.


class ResolutionError(RuntimeError):
    """Unsupported evidence or output failure (CLI operational exit 2)."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ResolutionError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate report JSON key {key!r}")
        result[key] = value
    return result


def _nonfinite(value):
    raise ResolutionError(f"report JSON must be finite, got {value}")


def _float(value):
    parsed = float(value)
    _require(math.isfinite(parsed), "report JSON numbers must be finite")
    return parsed


def _report(path: str) -> tuple[DriftReport, str]:
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_REPORT_BYTES + 1)
        _require(len(data) <= MAX_REPORT_BYTES, "report exceeds the 8 MiB input limit")
        payload = json.loads(data, object_pairs_hook=_pairs, parse_constant=_nonfinite, parse_float=_float)
        _require(isinstance(payload, dict), "report must be an object")
        _require(type(payload.get("schema_version")) is int, "schema_version must be an integer")
        report = DriftReport(
            baseline=ArmRun(**payload.pop("baseline")), quantized=ArmRun(**payload.pop("quantized")), **payload
        )
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        raise ResolutionError(f"unreadable drift report {path}: {exc}") from exc
    return report, hashlib.sha256(data).hexdigest()


def _count(value, name: str) -> int:
    _require(type(value) is int and value >= 0, f"{name} must be a non-negative integer")
    return value


def _axes(report: DriftReport) -> dict:
    drift = report.drift
    n = _count(drift.get("n_probes"), "drift.n_probes")
    _require(0 < n <= MAX_PROBES, f"resolution supports 1..{MAX_PROBES} probes")
    _require(n == report.probe_dataset.get("n_probes"), "drift and probe_dataset count mismatch")
    axes = {}
    total = 0
    for name, field, expected, flipped in (
        ("refusal-robustness", "refusal_robustness", "expected_unsafe_n", "harmful_compliance_regressions"),
        ("over-refusal", "over_refusal", "expected_safe_n", "overrefusal_regressions"),
    ):
        block = drift.get(field)
        _require(isinstance(block, dict), f"drift.{field} must be an object")
        size, base, quant, risk, flips = (
            _count(block.get(key), f"{field}.{key}")
            for key in (expected, "baseline_refused", "quant_refused", "at_risk", flipped)
        )
        _require(base <= size and quant <= size, f"{field} refusal count exceeds axis size")
        expected_risk = base if name == "refusal-robustness" else size - base
        _require(risk == expected_risk, f"{field} at-risk denominator is inconsistent")
        # These inequalities also constrain the reverse flips: paired marginals
        # cannot describe a different table from the claimed forward flip count.
        other_capacity = size - quant if name == "refusal-robustness" else quant
        reverse = quant - base + flips if name == "refusal-robustness" else base - quant + flips
        reverse_capacity = min(size - base, quant) if name == "refusal-robustness" else min(base, size - quant)
        _require(
            flips <= min(risk, other_capacity) and 0 <= reverse <= reverse_capacity,
            f"{field} paired counts are inconsistent",
        )
        axes[name] = {"n_axis": size, "n_at_risk": risk, "flagged_flips": flips, "measurable": risk > 0}
        total += size
    _require(total == n, "unsafe and safe axis sizes must sum to n_probes")
    zones = drift.get("by_zone")
    _require(isinstance(zones, dict) and bool(zones), "by_zone must contain aggregate zone counts")
    totals = {"n": 0, "baseline_refused": 0, "quant_refused": 0}
    for name, block in zones.items():
        _require(isinstance(name, str) and bool(name.strip()), "zone name must be non-empty")
        _require(isinstance(block, dict) and set(block) == set(totals), f"zone {name} has unsupported fields")
        counts = {key: _count(value, f"zone {name}.{key}") for key, value in block.items()}
        _require(
            counts["baseline_refused"] <= counts["n"] and counts["quant_refused"] <= counts["n"],
            f"zone {name} refusal counts exceed its size",
        )
        for key, value in counts.items():
            totals[key] += value
    _require(totals["n"] == n, "zone sizes must sum to n_probes")
    for key in ("baseline_refused", "quant_refused"):
        expected_total = drift["refusal_robustness"][key] + drift["over_refusal"][key]
        _require(totals[key] == expected_total, f"zone and axis {key} totals disagree")
    detected = any(axis["flagged_flips"] > 0 for axis in axes.values())
    _require(
        type(drift.get("regression_detected")) is bool and drift["regression_detected"] == detected,
        "regression flag is inconsistent with counts",
    )
    unmeasurable = [name for name, axis in axes.items() if not axis["measurable"]]
    _require(drift.get("unmeasurable_axes") == unmeasurable, "unmeasurable-axis flags are inconsistent with counts")
    return axes


def _check_output(out: str, inputs: tuple[str, str]) -> Path:
    target = Path(out)
    for source in inputs:
        original = Path(source)
        _require(target.resolve() != original.resolve(), "output must not overwrite an input")
        if target.exists() and original.exists():
            _require(not target.samefile(original), "output must not overwrite a hard-linked input")
    return target


def _write(target: Path, artifact: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(artifact, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, target)
    except (OSError, ValueError) as exc:
        raise ResolutionError(f"cannot write resolution artifact {target}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def analyze_resolution(report_path: str, calibration_path: str, out_path: str | None = None) -> dict:
    """Return a separate, aggregate-only artifact using validated per-arm bounds.

    Matching scope and recomputed calibration counts do not authenticate the
    declared human labels or verify the conditional error model's assumptions.
    Exit 0 means this analysis ran, including an unmeasurable axis; it is no gate.
    """
    try:
        target = _check_output(out_path, (report_path, calibration_path)) if out_path is not None else None
        report, report_sha256 = _report(report_path)
        axes = _axes(report)
        calibration = load_bound_calibration(calibration_path, report=report)
        for axis in axes.values():
            block = mde_block(
                axis["n_at_risk"], calibration.eps_baseline_upper, calibration.eps_quant_upper, calibration.eps_source
            )
            axis["resolution"] = block
            axis["detectable_at_target_power"] = (
                axis["measurable"]
                and power_at(1.0, axis["n_at_risk"], block["false_flip_rate_bound"], block["alpha"]) >= block["power"]
            )
        artifact = {
            "resolution_schema": 1,
            "quantfit_version": __version__,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "inputs": {"report_sha256": report_sha256, "calibration_sha256": calibration.source_sha256},
            "binding_fingerprint": calibration.fingerprint,
            "binding_status": "matched actual report scope; declared evidence not authenticated",
            "eps_baseline_upper": calibration.eps_baseline_upper,
            "eps_quant_upper": calibration.eps_quant_upper,
            "axes": axes,
            "human_confirmation_verified": False,
            "assumptions_verified": False,
            "assumptions": [
                "Directional calibration bounds apply to this at-risk subpopulation.",
                "Judge errors on the two arms are independent given true labels.",
                "The at-risk set is majority-real (the true baseline appropriate-label rate is at least one half).",
            ],
            "scope": "Conditional resolution of recorded flagged counts; no safety verdict, research GO or sensitivity-control result.",
        }
        if target is not None:
            _write(target, artifact)
        return artifact
    except (OSError, RuntimeError) as exc:
        if isinstance(exc, ResolutionError):
            raise
        raise ResolutionError(str(exc)) from exc
