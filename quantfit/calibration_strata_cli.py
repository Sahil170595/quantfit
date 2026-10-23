"""Aggregate-only renderer for descriptive calibration strata."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from quantfit.safety.calibration_strata import analyze_calibration_strata

Emit = Callable[[argparse.Namespace, str, int, dict[str, Any], Callable[[], None]], int]


def dispatch_strata(args: argparse.Namespace, emit: Emit) -> int:
    result = analyze_calibration_strata(
        args.capture,
        args.key,
        sheet_path=args.sheet,
        retained_labels_path=args.retained_labels,
        retention_receipt_path=args.retention_receipt,
        out_path=args.out,
    )

    def human() -> None:
        print(f"Descriptive calibration groups completed: {result['n_pairs']} pairs / {result['n_rows']} rows.")
        for name, group in result["observed_at_risk"].items():
            print(f"{name}: {group['n_pairs_selected']} observed-at-risk pairs; read per-arm usable denominators.")
        print("No calibration replacement, human authentication, sensitivity or scientific GO.")

    return emit(args, "calibrate strata", 0, result, human)
