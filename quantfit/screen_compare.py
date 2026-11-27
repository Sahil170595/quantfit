"""Offline descriptive transitions between two exact declared screen populations."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from quantfit import __version__
from quantfit.bundle import _report
from quantfit.reproduce import (
    _canonical_receiving_path,
    _publish_reproduction_outputs,
    _ReproductionOutputs,
    _validate_reproduction_outputs,
)
from quantfit.screen_bundle_inputs import (
    MAX_TARGETS,
    MAX_TRANSPORT_BYTES,
    _Cache,
    _capture_bundle,
    _HeldScreen,
    _scan,
    _verify_held,
)

AXES = ("refusal_robustness", "over_refusal")
IDENTITY_FIELDS = ("revision", "artifact_sha256", "resolved_dtype")
ARMS = ("baseline", "quantized")
BASIS = "declared_target_and_compatible_protocol"
SCOPE = (
    "Descriptive flags for exactly the same declared targets and compatible recorded protocol only. "
    "Apparent clearance is neither confirmed correction nor causal improvement. Original at-risk "
    "denominators, unconfirmed flags and missing/unmeasured evidence remain separate. No pooled counts, "
    "statistical comparison, source/weight/physical-host authentication, independence, human confirmation, "
    "calibrated sensitivity or scientific GO. Matching identity declarations never establish same weights."
)
_UNAVAILABLE = {"unknown", "unavailable", "unverified", "not_recorded", "none", "null", "auto"}


class ScreenComparisonError(RuntimeError):
    """Categorical operational refusal; no input/provider diagnostics are reflected."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _require(condition: bool, category: str = "invalid_screen_comparison") -> None:
    if not condition:
        raise ScreenComparisonError(category)


def _observation(row: dict[str, Any], axis: str) -> dict[str, Any]:
    if row["status"] == "missing_evidence":
        return {
            "present": False,
            "measured": False,
            "flagged": None,
            "flips": None,
            "at_risk": None,
            "flip_rate_wilson95": None,
            "mde_at_80pct_power": None,
        }
    block = row[axis]
    return {
        "present": True,
        "measured": block["at_risk"] > 0,
        "flagged": block["flips"] > 0,
        "flips": block["flips"],
        "at_risk": block["at_risk"],
        "flip_rate_wilson95": list(block["flip_rate_wilson95"]),
        "mde_at_80pct_power": block["mde_at_80pct_power"],
    }


def _axis_decision(
    reference: dict[str, Any], candidate: dict[str, Any], protocol: bool | None, identity: str
) -> dict[str, Any]:
    if not reference["present"] or not candidate["present"]:
        suffix = (
            "both"
            if not reference["present"] and not candidate["present"]
            else "reference"
            if not reference["present"]
            else "candidate"
        )
        status = f"missing_{suffix}"
    elif protocol is False:
        status = "incompatible_scope"
    elif identity == "incompatible":
        status = "incompatible_target_identity"
    elif not reference["measured"] or not candidate["measured"]:
        suffix = (
            "both"
            if not reference["measured"] and not candidate["measured"]
            else "reference"
            if not reference["measured"]
            else "candidate"
        )
        status = f"unmeasured_{suffix}"
    else:
        _require(protocol is True)
        status = "matched"
    transition = None
    if status == "matched":
        transition = (
            "persisting_flag"
            if reference["flagged"] and candidate["flagged"]
            else "apparent_clearance"
            if reference["flagged"]
            else "newly_flagged"
            if candidate["flagged"]
            else "no_flag"
        )
    return {"status": status, "transition": transition, "comparison_basis": BASIS if status == "matched" else None}


def _protocol_match(reference: dict[str, Any], candidate: dict[str, Any], stratum: str) -> bool | None:
    left = reference["protocol_by_stratum"].get(stratum)
    right = candidate["protocol_by_stratum"].get(stratum)
    return None if left is None or right is None else left == right


def _identity(reference: bytes | None, candidate: bytes | None) -> dict[str, Any]:
    reports = [_report(raw) if raw is not None else None for raw in (reference, candidate)]
    differences = []
    unavailable: dict[str, list[str]] = {arm: [] for arm in ARMS}
    for arm in ARMS:
        for field in IDENTITY_FIELDS:
            values = [getattr(getattr(report, arm), field) if report is not None else None for report in reports]
            if any(
                not isinstance(value, str) or not value.strip() or value.strip().casefold() in _UNAVAILABLE
                for value in values
            ):
                unavailable[arm].append(field)
            elif values[0] != values[1]:
                differences.append({"arm": arm, "field": field})
    return {
        "state": "incompatible"
        if differences
        else "unavailable"
        if any(unavailable.values())
        else "compatible_declarations",
        "differences": differences,
        "unavailable_fields": unavailable,
        "same_weights_established": False,
    }


def _identity_requirement(rows: list[dict[str, Any]]) -> dict[str, int | bool]:
    unavailable = sum(row["identity"]["state"] == "unavailable" for row in rows)
    incompatible = sum(row["identity"]["state"] == "incompatible" for row in rows)
    return {
        "met": unavailable == incompatible == 0,
        "unavailable_targets": unavailable,
        "incompatible_targets": incompatible,
    }


def _exit_code(rows: list[dict[str, Any]], *, identity_met: bool = True) -> int:
    axes = [axis for row in rows for axis in row["axes"].values()]
    if any(axis[side]["flagged"] is True for axis in axes for side in ("reference", "candidate")):
        return 3
    return 4 if not identity_met or any(axis["status"] != "matched" for axis in axes) else 0


def _compare_held(
    reference: _HeldScreen, candidate: _HeldScreen, verified: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    _require(reference.targets == candidate.targets, "target_manifest_mismatch")
    if verified is None:
        verified = {"reference": _verify_held(reference), "candidate": _verify_held(candidate)}
    screens = {side: result["receiving_summary"] for side, result in verified.items()}
    native = {"reference": dict(reference.members), "candidate": dict(candidate.members)}
    rows = []
    for index, original in enumerate(screens["reference"]["rows"]):
        name, stratum = original["name"], original["stratum"]
        bindings = {side: screen["report_bindings"][index] for side, screen in screens.items()}
        both = all(binding["status"] == "validated" for binding in bindings.values())
        identity = _identity(native["reference"].get(f"{name}.json"), native["candidate"].get(f"{name}.json"))
        protocol = _protocol_match(screens["reference"], screens["candidate"], stratum)
        axes = {}
        for axis in AXES:
            observations = {side: _observation(screen["rows"][index], axis) for side, screen in screens.items()}
            axes[axis] = {
                **observations,
                **_axis_decision(observations["reference"], observations["candidate"], protocol, identity["state"]),
            }
        rows.append(
            {
                "name": name,
                "stratum": stratum,
                "bindings": bindings,
                "identical_report_bytes": bindings["reference"]["sha256"] == bindings["candidate"]["sha256"]
                if both
                else None,
                "protocol_match": protocol,
                "identity": identity,
                "axes": axes,
            }
        )
    return {
        "screen_comparison_schema_version": 1,
        "kind": "quantfit.screen-comparison",
        "quantfit_version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "exit_code": _exit_code(rows),
        "inputs": {
            side: {
                "bundle_manifest_sha256": result["manifest_sha256"],
                "targets_sha256": result["bundle_manifest"]["targets"]["sha256"],
                "transport_bytes": result["transport_bytes"],
            }
            for side, result in verified.items()
        },
        "screens": screens,
        "rows": rows,
        "comparison_basis": BASIS,
        "source_authentication": "unverified",
        "same_weights_established": False,
        "independent_execution_verified": False,
        "weights_authenticated": False,
        "physical_hosts_authenticated": False,
        "human_labels_authenticated": False,
        "sensitivity_established": False,
        "scientific_go": False,
        "assumptions": [
            "The identical target manifest is a declaration, not authenticated execution identity.",
            "Unknown identity facts permit descriptive declared-target transitions only.",
            "Original sensitivity and resolution caveats remain attached to both screens.",
        ],
        "scope": SCOPE,
        "limits": {
            "bundle_transport_bytes": MAX_TRANSPORT_BYTES,
            "combined_logical_transport_bytes": 2 * MAX_TRANSPORT_BYTES,
            "max_targets": MAX_TARGETS,
        },
    }


def _recheck(held: _HeldScreen) -> None:
    root = held.protected_roots[0]
    _scan(root, {"manifest.json": False, "targets.json": False, "reports": True})
    _scan(root / "reports", dict.fromkeys((name for name, _ in held.members), False))


def _source(bundle_path: str | None, archive: tuple[str, str] | None) -> tuple[str, str | None]:
    _require((bundle_path is None) != (archive is None), "invalid_screen_comparison_input")
    if archive is not None:
        path, pin = archive
        _require(type(pin) is str, "invalid_screen_comparison_input")
        return _canonical_receiving_path(path), pin
    assert bundle_path is not None
    return _canonical_receiving_path(bundle_path), None


def _hold_comparison_input(
    source: tuple[str, str | None], cache: _Cache
) -> tuple[_HeldScreen, Callable[[], dict[str, Any]], Callable[[], None]]:
    path, pin = source
    if pin is None:
        screen = _capture_bundle(path, cache=cache)
        return screen, lambda: _verify_held(screen), lambda: _recheck(screen)

    from quantfit.bundle_archive_kinds import _receive_contents, _screen_payload

    held, files, _, verified = _receive_contents(path, pin, "screen")
    screen = replace(_screen_payload(files), protected_paths=(held.path,))
    return screen, lambda: verified, held.check


def compare_screen_bundles(
    reference_bundle: str | None = None,
    candidate_bundle: str | None = None,
    *,
    reference_archive: tuple[str, str] | None = None,
    candidate_archive: tuple[str, str] | None = None,
    out_path: str | None = None,
    junit_path: str | None = None,
    require_compatible_identity: bool = False,
) -> dict[str, Any]:
    """Compare held directory or (screen ZIP path, SHA-256) inputs without extracting."""
    phase = "invalid_screen_comparison_input"
    try:
        _require(type(require_compatible_identity) is bool, phase)
        ref_source = _source(reference_bundle, reference_archive)
        cand_source = _source(candidate_bundle, candidate_archive)
        outputs = tuple(Path(_canonical_receiving_path(path)) for path in (out_path, junit_path) if path is not None)
        if outputs and (reference_archive is not None or candidate_archive is not None):
            sources = (ref_source, cand_source)
            phase = "unsafe_output"
            _validate_reproduction_outputs(
                _ReproductionOutputs(
                    tuple(Path(path) for path, pin in sources if pin is not None),
                    tuple(Path(path) for path, pin in sources if pin is None),
                    outputs,
                )
            )
            phase = "invalid_screen_comparison_input"
        cache: _Cache = {}
        reference, verify_reference, check_reference = _hold_comparison_input(ref_source, cache)
        candidate, verify_candidate, check_candidate = (
            (reference, verify_reference, check_reference)
            if ref_source == cand_source
            else _hold_comparison_input(cand_source, cache)
        )
        plan = _ReproductionOutputs(
            (*reference.protected_paths, *candidate.protected_paths),
            (*reference.protected_roots, *candidate.protected_roots),
            outputs,
        )
        phase = "unsafe_output"
        _validate_reproduction_outputs(plan)
        phase = "invalid_screen_comparison_input"
        _require(reference.targets == candidate.targets, "target_manifest_mismatch")
        result = _compare_held(reference, candidate, {"reference": verify_reference(), "candidate": verify_candidate()})
        if require_compatible_identity:
            requirement = _identity_requirement(result["rows"])
            result["screen_comparison_schema_version"] = 2
            result["identity_requirement"] = requirement
            result["exit_code"] = _exit_code(result["rows"], identity_met=requirement["met"] is True)
        phase = "output_failure"
        buffers = []
        if out_path is not None:
            buffers.append(
                (outputs[0], (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
            )
        if junit_path is not None:
            from quantfit.screen_compare_junit import screen_comparison_to_junit

            buffers.append((outputs[-1], screen_comparison_to_junit(result).encode()))
        if buffers:

            def recheck() -> None:
                check_reference()
                if candidate is not reference:
                    check_candidate()

            _publish_reproduction_outputs(plan, buffers, recheck=recheck)
        return result
    except ScreenComparisonError:
        raise
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, ImportError, BadZipFile):
        raise ScreenComparisonError(phase) from None
