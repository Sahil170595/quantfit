"""Native CLI rendering for the fixed two-judge diagnostic."""

from __future__ import annotations

import argparse

from quantfit.safety.calibration_judges import (
    COMMAND,
    COMPARE_OBSERVED_COMMAND,
    OBSERVE_COMMAND,
    _analyze,
    _compare_observed,
    _observe,
)


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


def dispatch_observation(args: argparse.Namespace) -> int:
    from quantfit.cli import _emit

    if args.calibrate_cmd == "observe-judge":
        command = OBSERVE_COMMAND
        result, encoded = _observe(args.report, args.capture, args.key, out_path=args.out)
    else:
        command = COMPARE_OBSERVED_COMMAND
        result, encoded = _compare_observed(
            args.report,
            args.capture,
            args.key,
            args.observation,
            observation_sha256=args.observation_sha256,
            sheet_path=args.sheet,
            retained_labels_path=args.retained_labels,
            retention_receipt_path=args.retention_receipt,
            out_path=args.out,
        )

    def human() -> None:
        print(f"{command}: {result['n_pairs']} complete pairs.")
        if command == OBSERVE_COMMAND:
            print(f"Private observation SHA256 {result['observation']['sha256']}")
        else:
            print("Descriptive comparison only. No calibration or gate decision.")

    return _emit(args, command, 0, result, human, encoded_json=encoded)
