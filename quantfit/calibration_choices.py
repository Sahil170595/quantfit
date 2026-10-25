"""Whole-population descriptive sensitivity over explicitly named calibration choices."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from quantfit import saved_screen as saved
from quantfit import screen_resolution as native
from quantfit.bundle import _read
from quantfit.junit import screen_to_junit
from quantfit.reproduce import (
    _canonical_receiving_path,
    _publish_reproduction_outputs,
    _ReproductionOutputs,
    _validate_reproduction_outputs,
)
from quantfit.safety.calibration_binding import MAX_CALIBRATION_BYTES
from quantfit.safety.report import DriftReport
from quantfit.screen_requirement import AXES, _check_axis, validate_requirement

MAX_VARIANTS = 8
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
SCOPE = (
    "Descriptive envelope over only the explicitly supplied named choices and complete original target population. "
    "Missing/unattainable results remain visible; minima/maxima use attainable matched values only. "
    "No pooling, preferred/best rater, independent rater samples, rater-population confidence interval or universal worst case. "
    "Identical payloads under different names are copies, not independent evidence. Native flags/outcomes remain recorded; "
    "only an explicit all-choice conditional ceiling changes receiving qualification. No authenticated labels, source, "
    "assumptions, independence, sensitivity or scientific GO."
)


def validate_variants(variants: dict[str, str | None]) -> tuple[tuple[str, str | None], ...]:
    saved._require(type(variants) is dict and 0 < len(variants) <= MAX_VARIANTS, "invalid_calibration_variants")
    for name, path in variants.items():
        saved._require(type(name) is str and bool(_NAME.fullmatch(name)), "invalid_calibration_variants")
        saved._require(path is None or type(path) is str and bool(path.strip()), "invalid_calibration_variants")
    return tuple(variants.items())


def parse_variant_options(options: list[str]) -> dict[str, str | None]:
    saved._require(type(options) is list and 0 < len(options) <= MAX_VARIANTS, "invalid_calibration_variants")
    result = {}
    for option in options:
        saved._require(type(option) is str and "=" in option, "invalid_calibration_variants")
        name, _, path = option.partition("=")
        saved._require(name not in result, "invalid_calibration_variants")
        result[name] = None if path == "-" else path
    validate_variants(result)
    return result


def _inventories(roots: tuple[tuple[str, Path | None], ...], allowed: frozenset[str]) -> dict[str, dict[str, Path]]:
    """ALL advertised bytes admitted before any calibration payload is held."""
    total = 0
    inventories = {}
    for name, root in roots:
        members = native._inventory(root, allowed) if root is not None else {}
        for path in members.values():
            total += path.lstat().st_size
            saved._require(total <= native.MAX_TOTAL_CALIBRATION_BYTES, "calibration_byte_limit")
        inventories[name] = members
    return inventories


def _hold_variants(
    roots: tuple[tuple[str, Path | None], ...], inventories: dict[str, dict[str, Path]], allowed: frozenset[str]
) -> list[tuple[str, native._HeldCalibrations]]:
    remaining = native.MAX_TOTAL_CALIBRATION_BYTES
    buffers: dict[Path, bytes] = {}
    result = []
    for name, root in roots:
        members = []
        for member, path in sorted(inventories[name].items()):
            saved._require(remaining > 0, "calibration_byte_limit")
            if path not in buffers:
                buffers[path] = _read(path, min(MAX_CALIBRATION_BYTES, remaining))
            raw = buffers[path]
            saved._require(len(raw) <= remaining, "calibration_byte_limit")
            remaining -= len(raw)  # Charge logical variant occurrences, including copies/aliases.
            members.append((member, raw))
        result.append((name, native._HeldCalibrations(root, tuple(members), allowed)))
    return result


def _envelopes(targets: list[Any], rows: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    result = []
    for target in targets:
        cells = [row for row in rows if row["name"] == target.name]
        axes = {}
        for axis in AXES:
            observed = [row["analysis"]["axes"][axis] for row in cells if row["analysis"] is not None]
            measurable = [item for item in observed if item["measurable"] is True]
            attainable = [item for item in measurable if item["detectable_at_target_power"] is True]
            values = [item["resolution"]["effective_mde"] * 100 for item in attainable]
            axes[axis] = {
                "expected": k,
                "analyzed": len(observed),
                "measurable": len(measurable),
                "attainable": len(attainable),
                "incomplete": len(attainable) != k,
                "effective_mde_pp_min": min(values) if values else None,
                "effective_mde_pp_max": max(values) if values else None,
            }
        result.append({"name": target.name, "axes": axes})
    return result


def _requirements(result: dict[str, Any], rows: list[dict[str, Any]], ceiling: float | None) -> dict[str, Any]:
    native_exit, native_outcome = result["exit_code"], result["outcome"]
    reasons = []
    if ceiling is None:
        reasons.append("not_requested")
    elif native_exit in (3, 4):
        reasons.append("native_flags_detected" if native_exit == 3 else "native_evidence_incomplete")
    checked_rows = []
    for row in rows:
        checked: dict[str, dict[str, Any]] = {}
        for axis in AXES:
            if ceiling is None:
                checked[axis] = {"requirement_met": None, "reasons": ["not_requested"]}
            else:
                checked[axis] = _check_axis(
                    row["analysis"]["axes"][axis] if row["analysis"] is not None else None,
                    row["native_report_sha256"] is not None,
                    row["calibration"]["status"] == "present",
                    ceiling,
                )
                reasons.extend(checked[axis]["reasons"])
        checked_rows.append(
            {
                "name": row["name"],
                "variant": row["variant"],
                "native_report_sha256": row["native_report_sha256"],
                "calibration_sha256": row["calibration"]["sha256"],
                "axes": checked,
                "requirement_met": all(item["requirement_met"] for item in checked.values())
                if ceiling is not None
                else None,
            }
        )
    code = (
        native_exit
        if ceiling is None or native_exit in (3, 4)
        else 4
        if "calibration_missing" in reasons
        else 5
        if reasons
        else 0
    )
    return {
        "calibration_choice_requirement_schema_version": 1,
        "required_conditional_resolution_pp": ceiling,
        "native_exit_code": native_exit,
        "native_outcome": native_outcome,
        "qualification_exit_code": code,
        "requirement_met": code == 0 if ceiling is not None else None,
        "rows": checked_rows,
        "reasons": list(dict.fromkeys(reasons)),
        "scientific_go": False,
        "scope": SCOPE,
    }


def append_variant_junit_cases(suite: ET.Element, requirement: dict[str, Any]) -> None:
    requested = requirement["required_conditional_resolution_pp"] is not None
    for row in requirement["rows"]:
        for axis in AXES:
            case = ET.SubElement(
                suite,
                "testcase",
                {
                    "classname": "quantfit.screen-summary.calibration-choice",
                    "name": f"{row['name']}:{row['variant']}:{axis}:requirement",
                },
            )
            if not requested:
                ET.SubElement(case, "skipped", {"message": "not_requested"})
            elif not row["axes"][axis]["requirement_met"]:
                ET.SubElement(
                    case,
                    "failure",
                    {"type": "CalibrationChoiceRequirement", "message": ", ".join(row["axes"][axis]["reasons"])},
                )
    overall = ET.SubElement(
        suite,
        "testcase",
        {"classname": "quantfit.screen-summary.calibration-choice", "name": "overall:calibration-choice-requirement"},
    )
    if not requested:
        ET.SubElement(overall, "skipped", {"message": "not_requested"})
    elif not requirement["requirement_met"]:
        ET.SubElement(
            overall, "failure", {"type": "CalibrationChoiceRequirement", "message": ", ".join(requirement["reasons"])}
        )


def summarize_screen_with_variants(
    manifest_path: str,
    reports_dir: str,
    *,
    calibration_variants: dict[str, str | None],
    out_path: str | None = None,
    junit_path: str | None = None,
    required_conditional_resolution_pp: float | None = None,
) -> dict[str, Any]:
    variants = validate_variants(calibration_variants)
    ceiling = validate_requirement(required_conditional_resolution_pp)
    phase = "invalid_calibration_variants"
    try:
        held_native = saved._hold_screen_inputs(manifest_path, reports_dir, out_path=out_path, junit_path=junit_path)
        _, targets, _ = saved._manifest(held_native.manifest)
        allowed = frozenset(f"{target.name}.json" for target in targets)
        roots = tuple(
            (name, Path(_canonical_receiving_path(path)) if path is not None else None) for name, path in variants
        )
        saved._require(
            all(root != Path(held_native.reports_dir) for _, root in roots if root is not None),
            "invalid_calibrations_directory",
        )
        actual_roots = tuple(root for _, root in roots if root is not None)
        plan = _ReproductionOutputs(
            (*held_native.plan.sources, *(root / name for root in actual_roots for name in sorted(allowed))),
            (*held_native.plan.roots, *actual_roots),
            held_native.plan.targets,
        )
        phase = "unsafe_output"
        _validate_reproduction_outputs(plan)
        phase = "invalid_calibration"
        inventories = _inventories(roots, allowed)
        calibrations = _hold_variants(roots, inventories, allowed)
        result: dict[str, Any] = saved._summarize_held(
            held_native.manifest,
            dict(held_native.members),
            manifest_path=held_native.manifest_path,
            reports_dir=held_native.reports_dir,
        )
        prepared = []
        work = 0
        parsed_reports: dict[str, DriftReport] = {}
        for name, held in calibrations:
            item = native._prepare_rows(
                held_native,
                result,
                held,
                work_limit=native.MAX_ANALYSIS_WORK_UNITS - work,
                parsed_reports=parsed_reports,
            )
            work += item.work
            prepared.append((name, item))
        # No native conditional analysis can run until ALL named choices have
        # passed scope/count/combined work and held-byte admission above.
        analyzed = [(name, native._analyze_rows(item, use_prepared=True)) for name, item in prepared]
        rows = [
            {"variant": name, **member_rows[index]} for index in range(len(targets)) for name, member_rows in analyzed
        ]
        copies: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            digest = row["calibration"]["sha256"]
            if digest is not None:
                copies.setdefault(digest, []).append({"variant": row["variant"], "name": row["name"]})
        count = sum(row["analysis"] is not None for row in rows)
        result["calibration_choice_sensitivity"] = {
            "calibration_choice_schema_version": 1,
            "variants": [name for name, _ in variants],
            "variant_bindings": [
                {"name": name, "status": "declared_missing" if root is None else "provided"} for name, root in roots
            ],
            "rows": rows,
            "coverage": {
                "expected": len(rows),
                "expected_targets": len(targets),
                "expected_variants": len(variants),
                "analyzed": count,
                "complete": count == len(rows),
                "unit": "target_variant_pairs",
            },
            "envelopes": _envelopes(targets, rows, len(variants)),
            "digest_copy_groups": [
                {"calibration_sha256": digest, "members": members}
                for digest, members in copies.items()
                if len(members) > 1
            ],
            "analysis_work_units": work,
            "limits": {
                "max_variants": MAX_VARIANTS,
                "max_targets": saved.MAX_TARGETS,
                "combined_calibration_bytes": native.MAX_TOTAL_CALIBRATION_BYTES,
                "max_analysis_work_units": native.MAX_ANALYSIS_WORK_UNITS,
                "combined_output_bytes": MAX_OUTPUT_BYTES,
            },
            "human_labels_authenticated": False,
            "assumptions_verified": False,
            "scientific_go": False,
            "scope": SCOPE,
        }
        result["calibration_choice_requirement"] = _requirements(result, rows, ceiling)
        result["exit_code"] = result["calibration_choice_requirement"]["qualification_exit_code"]
        phase = "output_failure"
        buffers = []
        result_raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        junit_raw = screen_to_junit(result).encode() if junit_path is not None else b""
        saved._require(len(result_raw) + len(junit_raw) <= MAX_OUTPUT_BYTES, "variant_output_byte_limit")
        if out_path is not None:
            buffers.append((plan.targets[0], result_raw))
        if junit_path is not None:
            buffers.append((plan.targets[-1], junit_raw))

        def recheck() -> None:
            paths = saved._inventory(Path(held_native.reports_dir), set(held_native.allowed))
            saved._require(
                {path.name for path in paths} == {name for name, _ in held_native.members}, "report_inventory_changed"
            )
            current = _inventories(roots, allowed)
            saved._require(
                all(set(current[name]) == set(inventories[name]) for name, _ in roots), "calibration_inventory_changed"
            )

        _publish_reproduction_outputs(plan, buffers, recheck=recheck)
        return result
    except saved.SavedScreenError:
        raise
    except (KeyboardInterrupt, RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, ImportError):
        raise saved.SavedScreenError(phase) from None
