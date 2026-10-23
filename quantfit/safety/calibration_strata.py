"""Descriptive native-Wilson calibration groupings; never replacement calibration."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from typing import Any

from quantfit import __version__
from quantfit.safety import calibrate
from quantfit.safety.calibration_inputs import ZONES, CalibrationRow, load_calibration_inputs
from quantfit.safety.retained_labels import _encode
from quantfit.safety.retention_io import admit_outputs, publish

STRATA_SCHEMA = 1
MAX_STRATA_BYTES = 256 * 1024
SCOPE = (
    "Descriptive grouping of supplied labels against captured judge observations only. "
    "Zone is a transparency grouping, not an independent statistical stratum. Observed-at-risk "
    "pair selection uses expected and baseline judge flag, independently of label usability. "
    "Per-arm and directional denominators remain separate; no pooled 2n inference, A1 transfer, "
    "calibration replacement, gate wiring, human authentication, sensitivity or scientific GO."
)


class CalibrationStrataError(RuntimeError):
    """Categorical diagnostic refusal; no paths or private parser values."""


def _group(rows: tuple[CalibrationRow, ...]) -> dict[str, Any]:
    arms = {}
    for arm in calibrate.ARMS:
        selected = [row for row in rows if row.arm == arm]
        usable = [row for row in selected if row.human_label != calibrate.LABEL_UNUSABLE]
        counts = {
            "n": len(usable),
            "n_unusable": len(selected) - len(usable),
            "human_refusals": sum(row.human_label == calibrate.LABEL_REFUSAL for row in usable),
            "human_compliances": sum(row.human_label == calibrate.LABEL_COMPLIANCE for row in usable),
            calibrate.DIR_JUDGE_REFUSAL_HUMAN_COMPLIANCE: sum(
                row.judge_refusal and row.human_label == calibrate.LABEL_COMPLIANCE for row in usable
            ),
            calibrate.DIR_JUDGE_COMPLIANCE_HUMAN_REFUSAL: sum(
                not row.judge_refusal and row.human_label == calibrate.LABEL_REFUSAL for row in usable
            ),
        }
        arms[arm] = calibrate._arm_block(counts)
    return {
        "n_pairs_selected": len({row.pair for row in rows}),
        "n_rows_selected": len(rows),
        "arms": arms,
        "unmeasured_arms": [arm for arm in calibrate.ARMS if arms[arm]["n"] == 0],
    }


def _cohort(rows: tuple[CalibrationRow, ...]) -> dict[str, Any]:
    return {**_group(rows), "zones": {zone: _group(tuple(row for row in rows if row.zone == zone)) for zone in ZONES}}


def analyze_calibration_strata(
    capture_path: str,
    key_path: str,
    *,
    sheet_path: str | None = None,
    retained_labels_path: str | None = None,
    retention_receipt_path: str | None = None,
    out_path: str,
) -> dict[str, Any]:
    """Compute fixed aggregate diagnostics, including empty/all-unusable groups (exit 0)."""
    try:
        held = load_calibration_inputs(
            capture_path,
            key_path,
            sheet_path=sheet_path,
            retained_labels_path=retained_labels_path,
            retention_receipt_path=retention_receipt_path,
        )
        dangerous = {
            row.pair for row in held.rows if row.arm == "baseline" and row.expected == "unsafe" and row.judge_refusal
        }
        overrefusal = {
            row.pair for row in held.rows if row.arm == "baseline" and row.expected == "safe" and not row.judge_refusal
        }
        result = {
            "calibration_strata_schema": STRATA_SCHEMA,
            "kind": "quantfit.calibration-strata",
            "quantfit_version": __version__,
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_pairs": held.n_pairs,
            "n_rows": len(held.rows),
            "label_mode": held.label_mode,
            "inputs": held.public_inputs(),
            "original_sheet": held.original_sheet,
            "binding_fingerprint": held.binding_fingerprint,
            "capture_digest_matches_key": True,
            "capture_metadata_matches_key": True,
            "all_rows": _cohort(held.rows),
            "observed_at_risk": {
                "dangerous": _cohort(tuple(row for row in held.rows if row.pair in dangerous)),
                "overrefusal": _cohort(tuple(row for row in held.rows if row.pair in overrefusal)),
            },
            "human_labels_authenticated": False,
            "rater_identity_verified": False,
            "independence_verified": False,
            "source_authenticity_verified": False,
            "sensitivity_verified": False,
            "scientific_go": False,
            "replaces_calibration": False,
            "gate_eligible": False,
            "scope": SCOPE,
        }
        raw = _encode(result)
        if len(raw) > MAX_STRATA_BYTES:
            raise CalibrationStrataError("invalid_calibration_strata")
        target = admit_outputs((out_path,), held.inputs)[0]
        publish(((target, raw),), held.inputs)
        return result
    except (
        KeyboardInterrupt,
        RuntimeError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        ImportError,
        csv.Error,
    ):
        raise CalibrationStrataError("invalid_calibration_strata") from None
