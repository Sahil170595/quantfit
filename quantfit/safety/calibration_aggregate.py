"""Shared native per-arm calibration arithmetic; no input or output IO."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import quantfit
from quantfit.safety.calibrate import (
    _DELTA_NOTE,
    ARMS,
    CALIBRATION_LABEL,
    CALIBRATION_SCHEMA,
    DIR_JUDGE_COMPLIANCE_HUMAN_REFUSAL,
    DIR_JUDGE_REFUSAL_HUMAN_COMPLIANCE,
    KEY_SCHEMA,
    LABEL_REFUSAL,
    LABEL_UNUSABLE,
    _arm_block,
    _qualified_label,
    _require,
)
from quantfit.safety.verify import ARM_BASELINE, ARM_QUANTIZED


def aggregate_labels(
    key: dict[str, Any],
    labels: dict[str, str],
    source: dict[str, str | None],
    *,
    schema: int = CALIBRATION_SCHEMA,
    sheet_path: str = "retained labels",
) -> dict[str, Any]:
    ids = key["ids"]
    counts = {
        arm: {
            "n": 0,
            "n_unusable": 0,
            "human_refusals": 0,
            "human_compliances": 0,
            DIR_JUDGE_REFUSAL_HUMAN_COMPLIANCE: 0,
            DIR_JUDGE_COMPLIANCE_HUMAN_REFUSAL: 0,
        }
        for arm in ARMS
    }
    for row_id, label in labels.items():
        # The arm is resolved BEFORE the unusable branch: an unusable row belongs to
        # the arm it came from, and pooling those counts hid which side went dark.
        arm = counts[ids[row_id]["arm"]]
        if label == LABEL_UNUSABLE:
            arm["n_unusable"] += 1
            continue
        judge_refusal = ids[row_id]["judge_refusal"]
        arm["n"] += 1
        if label == LABEL_REFUSAL:
            arm["human_refusals"] += 1
            if not judge_refusal:
                arm[DIR_JUDGE_COMPLIANCE_HUMAN_REFUSAL] += 1
        else:
            arm["human_compliances"] += 1
            if judge_refusal:
                arm[DIR_JUDGE_REFUSAL_HUMAN_COMPLIANCE] += 1

    blocks = {arm: _arm_block(counts[arm]) for arm in ARMS}
    unmeasured_arms = [arm for arm in ARMS if blocks[arm]["n"] == 0]
    _require(
        len(unmeasured_arms) < len(ARMS),
        f"every labeled row in {sheet_path} is unusable — nothing was measured, so this is not a calibration "
        f"sample. A report here would stamp a schema and a scope label on an empty measurement.",
    )

    baseline_eps = blocks[ARM_BASELINE]["epsilon"]
    quant_eps = blocks[ARM_QUANTIZED]["epsilon"]
    report = {
        "calibration_schema": schema,
        "quantfit_version": quantfit.__version__,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_labeled": len(labels),  # every sheet row; all of them carry a label by now
        "n_unusable": sum(blocks[arm]["n_unusable"] for arm in ARMS),
        "unmeasured_arms": unmeasured_arms,
        ARM_BASELINE: blocks[ARM_BASELINE],
        ARM_QUANTIZED: blocks[ARM_QUANTIZED],
        "arm_epsilon_delta": {
            "delta": None if baseline_eps is None or quant_eps is None else quant_eps - baseline_eps,
            "note": _DELTA_NOTE,
        },
        "label": CALIBRATION_LABEL if not unmeasured_arms else _qualified_label(unmeasured_arms),
        "binding": key.get("binding") if key["key_schema"] == KEY_SCHEMA else None,
        "source": source,
    }
    return report
