"""Aggregate-only renderers for explicit local review prepare/apply leaves."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from quantfit.safety.label_review import apply_label_review, prepare_label_review

Emit = Callable[[argparse.Namespace, str, int, dict[str, Any], Callable[[], None]], int]


def dispatch_review(args: argparse.Namespace, emit: Emit) -> int:
    if args.review_cmd == "prepare":
        result = prepare_label_review(
            args.sheet_a, args.sheet_b, args.key, review_path=args.sheet, receipt_path=args.receipt
        )
    else:
        result = apply_label_review(
            args.sheet_a,
            args.sheet_b,
            args.key,
            args.review,
            args.preparation,
            out_path=args.out,
            receipt_path=args.receipt,
        )

    def human() -> None:
        if args.review_cmd == "prepare":
            print(
                f"Review preparation completed: {result['n_selected']} of {result['n_rows']} rows require explicit supplied judgments."
            )
        else:
            print(
                f"Review application completed: {result['n_reviewed']} supplied judgments; {result['n_changed_vs_a']} normalized-label changes vs sheet A."
            )
        print(
            "Private sheets remain local; no automatic ingestion, rater authentication, independent adjudication or scientific GO."
        )

    return emit(args, f"calibrate review {args.review_cmd}", 0, result, human)
