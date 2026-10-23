"""Fixed aggregate renderer for paired calibration diagnostics."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from quantfit.safety.calibration_paired import analyze_calibration_paired

Emit = Callable[[argparse.Namespace, str, int, dict[str, Any], Callable[[], None]], int]


def dispatch_paired(args: argparse.Namespace, emit: Emit) -> int:
    result = analyze_calibration_paired(
        args.capture,
        args.key,
        sheet_path=args.sheet,
        retained_labels_path=args.retained_labels,
        retention_receipt_path=args.retention_receipt,
        out_path=args.out,
    )

    def human() -> None:
        coverage = result["coverage"]
        print(
            f"Descriptive paired diagnostics completed: {result['n_pairs']} pairs; {coverage['n_pairs_both_usable']} with two usable labels."
        )
        print("Read separate whole-judge/common-usable populations and source at-risk denominators.")
        print("No independence inference, bias correction, calibration replacement, sensitivity or scientific GO.")

    return emit(args, "calibrate paired", 0, result, human)
