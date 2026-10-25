"""Aggregate-only CLI renderer for the explicit retained-label modes."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from quantfit.safety.retained_labels import extract_labels, ingest_retained_labels

Emit = Callable[[argparse.Namespace, str, int, dict[str, Any], Callable[[], None]], int]


def dispatch_retained(args: argparse.Namespace, emit: Emit) -> int:
    if args.calibrate_cmd == "extract":
        result = extract_labels(args.sheet, args.key, out_path=args.out, receipt_path=args.receipt)
        command = "calibrate extract"
        message = f"Retained {result['n_rows']} private labels; aggregate receipt published."
    else:
        report = ingest_retained_labels(args.retained_labels, args.retention_receipt, args.key, out_path=args.out)
        result = {
            field: report[field]
            for field in ("calibration_schema", "n_labeled", "n_unusable", "unmeasured_arms", "source")
        }
        result["binding_fingerprint"] = report["binding"]["fingerprint"] if report["binding"] is not None else None
        command = "calibrate ingest"
        message = f"Calibration schema 3 completed: {report['n_labeled']} rows, {report['n_unusable']} unusable."

    def human() -> None:
        print(message)
        print("Hashes do not authenticate label truth, rater identity, independence or scientific GO.")

    return emit(args, command, 0, result, human)
