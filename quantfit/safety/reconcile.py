"""Bounded descriptive reconciliation of two private sheets against one shared key."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from quantfit import __version__
from quantfit.bundle import _read
from quantfit.reproduce import (
    _canonical_receiving_path,
    _publish_reproduction_outputs,
    _ReproductionOutputs,
    _validate_reproduction_outputs,
)
from quantfit.safety import calibrate

MAX_KEY_BYTES = 2 * 1024 * 1024
MAX_SHEET_BYTES = 8 * 1024 * 1024
MAX_TOTAL_INPUT_BYTES = MAX_KEY_BYTES + 2 * MAX_SHEET_BYTES
MAX_PAIRS = 4096
MAX_IDS = 2 * MAX_PAIRS
MAX_CSV_RECORDS = 2 * MAX_IDS + 1
SCOPE = (
    "Descriptive per-arm agreement counts on two sheets joined to one declared key only. "
    "Completion digests and complete row coverage are checked; key/source provenance, rater identities, "
    "independent labeling and human truth are not authenticated. Identical bytes are a self-control, "
    "not evidence of independent agreement. Unusable labels retain separate denominators. No arm pooling, "
    "consensus labels, judge-error estimate, statistical recalibration, inference, sensitivity claim or scientific GO."
)


class LabelReconciliationError(RuntimeError):
    """Categorical refusal without caller paths, row identities or private parser diagnostics."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise LabelReconciliationError(category)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "invalid_key")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise LabelReconciliationError("invalid_key")


def _float(value: str) -> float:
    result = float(value)
    _require(math.isfinite(result), "invalid_key")
    return result


def _population(raw: bytes) -> int:
    """Syntax and finite declared population only; the existing SDK owns key/binding validity."""
    payload = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_nonfinite, parse_float=_float)
    _require(type(payload) is dict, "invalid_key_population")
    capture, ids = payload.get("capture"), payload.get("ids")
    _require(type(capture) is dict and type(ids) is dict, "invalid_key_population")
    n = capture.get("n_pairs")
    _require(type(n) is int and 0 < n <= MAX_PAIRS and 0 < len(ids) <= MAX_IDS, "invalid_key_population")
    _require(len(ids) == 2 * n, "invalid_key_population")
    population = set()
    for entry in ids.values():
        _require(type(entry) is dict, "invalid_key_population")
        pair, arm = entry.get("pair"), entry.get("arm")
        _require(
            type(pair) is int and 0 <= pair < n and type(arm) is str and arm in calibrate.ARMS,
            "invalid_key_population",
        )
        population.add((pair, arm))
    _require(population == {(pair, arm) for pair in range(n) for arm in calibrate.ARMS}, "invalid_key_population")
    return cast(int, n)


def _hold(plan: _ReproductionOutputs) -> tuple[bytes, bytes, bytes]:
    cache: dict[Path, bytes] = {}
    snapshots = []
    remaining = MAX_TOTAL_INPUT_BYTES
    for path, limit in zip(plan.sources, (MAX_SHEET_BYTES, MAX_SHEET_BYTES, MAX_KEY_BYTES), strict=True):
        if path not in cache:
            cache[path] = _read(path, min(limit, remaining))
        raw = cache[path]
        _require(len(raw) <= limit and len(raw) <= remaining, "input_byte_limit")
        remaining -= len(raw)  # Both declared occurrences count, including one sheet supplied twice.
        snapshots.append(raw)
    return snapshots[0], snapshots[1], snapshots[2]


def _arm_counts(ids: dict[str, Any], a: dict[str, Any], b: dict[str, Any], arm: str) -> dict[str, Any]:
    matrix = [[0] * 3 for _ in range(3)]
    positions = {label: index for index, label in enumerate(calibrate.HUMAN_LABELS)}
    for row_id, entry in ids.items():
        if entry["arm"] == arm:
            matrix[positions[a[row_id]["human_label"]]][positions[b[row_id]["human_label"]]] += 1
    both_usable = sum(matrix[i][j] for i in (0, 1) for j in (0, 1))
    agreement = matrix[0][0] + matrix[1][1]
    return {
        "matrix": matrix,
        "n_rows": sum(map(sum, matrix)),
        "n_both_usable": both_usable,
        "n_usable_agreement": agreement,
        "n_usable_disagreement": both_usable - agreement,
        "n_one_unusable": matrix[0][2] + matrix[1][2] + matrix[2][0] + matrix[2][1],
        "n_both_unusable": matrix[2][2],
        "usable_agreement_rate": agreement / both_usable if both_usable else None,
    }


def reconcile_labels(
    sheet_a_path: str, sheet_b_path: str, key_path: str, *, out_path: str | None = None
) -> dict[str, Any]:
    """Return only aggregate disagreement counts; successful completion is never a gate result."""
    phase = "unsafe_output"
    try:
        sources = tuple(Path(_canonical_receiving_path(path)) for path in (sheet_a_path, sheet_b_path, key_path))
        targets = (Path(_canonical_receiving_path(out_path)),) if out_path is not None else ()
        plan = _ReproductionOutputs(sources, (), targets)
        _validate_reproduction_outputs(plan)
        phase = "invalid_input"
        a_raw, b_raw, key_raw = _hold(plan)
        phase = "invalid_key"
        n = _population(key_raw)
        key = calibrate._read_key("key", data=key_raw)
        phase = "invalid_sheet"
        a = calibrate._join("sheet_a", "key", key["ids"], data=a_raw, max_records=MAX_CSV_RECORDS)
        b = calibrate._join("sheet_b", "key", key["ids"], data=b_raw, max_records=MAX_CSV_RECORDS)
        result = {
            "label_reconciliation_schema_version": 1,
            "kind": "quantfit.label-reconciliation",
            "quantfit_version": __version__,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "n_pairs": n,
            "n_rows": 2 * n,
            "inputs": {
                role: {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
                for role, raw in (("sheet_a", a_raw), ("sheet_b", b_raw), ("key", key_raw))
            },
            "label_order": list(calibrate.HUMAN_LABELS),
            "arms": {arm: _arm_counts(key["ids"], a, b, arm) for arm in calibrate.ARMS},
            "identical_sheet_bytes": a_raw == b_raw,
            "rater_identity_verified": False,
            "human_labels_authenticated": False,
            "independence_verified": False,
            "consensus_calibration": False,
            "scientific_go": False,
            "limits": {
                "key_bytes": MAX_KEY_BYTES,
                "sheet_bytes": MAX_SHEET_BYTES,
                "total_input_bytes": MAX_TOTAL_INPUT_BYTES,
                "max_pairs": MAX_PAIRS,
                "max_ids": MAX_IDS,
                "max_csv_records": MAX_CSV_RECORDS,
            },
            "scope": SCOPE,
        }
        phase = "output_failure"
        if out_path is not None:
            raw_result = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
            _publish_reproduction_outputs(plan, [(plan.targets[0], raw_result)])
        return result
    except LabelReconciliationError:
        raise
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
        raise LabelReconciliationError(phase) from None
