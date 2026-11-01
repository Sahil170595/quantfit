"""Native CLI rendering for the fixed two-judge diagnostic."""

from __future__ import annotations

import argparse

from quantfit.safety.calibration_judges import COMMAND, _analyze


def dispatch_judges(args: argparse.Namespace) -> int:
    from quantfit.cli import _emit

    result, encoded = _analyze(
        args.capture_a,
        args.key_a,
        args.capture_b,
        args.key_b,
        sheet_a=args.sheet_a,
        retained_labels_a=args.retained_labels_a,
        retention_receipt_a=args.retention_receipt_a,
        sheet_b=args.sheet_b,
        retained_labels_b=args.retained_labels_b,
        retention_receipt_b=args.retention_receipt_b,
        out_path=args.out,
    )

    def human() -> None:
        print(f"Descriptive two-judge diagnostics completed: {result['n_pairs']} canonical pairs per judge.")
        print("Read each arm's whole-flag and usable-truth denominators separately.")
        print("No preferred judge, independence, calibration replacement, sensitivity or scientific GO.")

    return _emit(args, COMMAND, 0, result, human, encoded_json=encoded)
