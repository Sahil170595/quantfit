"""Aggregate-only CLI for private annotation partitioning and collection."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from quantfit.safety.annotation_chunks import collect_annotation_chunks, prepare_annotation_chunks

Emit = Callable[[argparse.Namespace, str, int, dict[str, Any], Callable[[], None]], int]


def dispatch_chunks(args: argparse.Namespace, emit: Emit) -> int:
    if args.chunks_cmd == "prepare":
        result = prepare_annotation_chunks(
            args.sheet,
            args.key,
            out_dir=args.out_dir,
            rows_per_part=args.rows_per_part,
            annotator_role=args.annotator_role,
            annotator_name=args.annotator_name,
        )
    else:
        result = collect_annotation_chunks(
            args.sheet, args.key, args.manifest, tuple(args.part), out_path=args.out, receipt_path=args.receipt
        )

    def human() -> None:
        print(f"Annotation {args.chunks_cmd}: {result['n_rows']} rows across {result['n_parts']} parts.")
        print("Private text stays local; no automatic labeling, sharing, ingestion or scientific GO.")

    return emit(args, f"calibrate chunks {args.chunks_cmd}", 0, result, human)
