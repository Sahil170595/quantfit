"""Offline descriptive transitions between two exact declared screen populations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def _exit_code(rows: list[dict[str, Any]]) -> int:
    axes = [axis for row in rows for axis in row["axes"].values()]
    if any(axis[side]["flagged"] is True for axis in axes for side in ("reference", "candidate")):
        return 3
    return 4 if any(axis["status"] != "matched" for axis in axes) else 0


def _compare_held(reference: _HeldScreen, candidate: _HeldScreen) -> dict[str, Any]:
    _require(reference.targets == candidate.targets, "target_manifest_mismatch")
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


def compare_screen_bundles(
    reference_bundle: str, candidate_bundle: str, *, out_path: str | None = None, junit_path: str | None = None
) -> dict[str, Any]:
    """Compare strict held originals; publish optional JSON/XML atomically per file."""
    phase = "invalid_screen_comparison_input"
    try:
        reference_path, candidate_path = (
            _canonical_receiving_path(path) for path in (reference_bundle, candidate_bundle)
        )
        cache: _Cache = {}
        reference = _capture_bundle(reference_path, cache=cache)
        candidate = reference if reference_path == candidate_path else _capture_bundle(candidate_path, cache=cache)
        outputs = tuple(Path(_canonical_receiving_path(path)) for path in (out_path, junit_path) if path is not None)
        plan = _ReproductionOutputs(
            (*reference.protected_paths, *candidate.protected_paths),
            (*reference.protected_roots, *candidate.protected_roots),
            outputs,
        )
        phase = "unsafe_output"
        _validate_reproduction_outputs(plan)
        phase = "invalid_screen_comparison_input"
        result = _compare_held(reference, candidate)
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
                _recheck(reference)
                if candidate is not reference:
                    _recheck(candidate)

            _publish_reproduction_outputs(plan, buffers, recheck=recheck)
        return result
    except ScreenComparisonError:
        raise
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, ImportError):
        raise ScreenComparisonError(phase) from None
