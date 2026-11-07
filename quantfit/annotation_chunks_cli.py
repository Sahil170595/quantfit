"""Aggregate-only CLI for private annotation partitioning and collection."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from quantfit.safety.annotation_chunks import (
    AnnotationChunksError,
    collect_annotation_chunks,
    prepare_annotation_chunks,
    validate_annotation_returns,
)

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
    elif args.chunks_cmd == "collect":
        result = collect_annotation_chunks(
            args.sheet, args.key, args.manifest, tuple(args.part), out_path=args.out, receipt_path=args.receipt
        )
    elif args.chunks_cmd == "validate":
        parts = []
        for entry in args.part:
            index, separator, path = entry.partition("=")
            if not (separator and path and index.isascii() and index.isdecimal() and 1 <= len(index) <= 3):
                raise AnnotationChunksError("invalid_annotation_returns")
            if str(int(index)) != index:
                raise AnnotationChunksError("invalid_annotation_returns")
            parts.append((int(index), path))
        result = validate_annotation_returns(args.sheet, args.key, args.manifest, tuple(parts), out_path=args.out)
    else:
        from quantfit.safety.annotation_packets import prepare_annotation_packets

        result = prepare_annotation_packets(args.sheet, args.key, args.manifest, out_dir=args.out_dir)

    def human() -> None:
        if args.chunks_cmd == "validate":
            print(
                f"Validated {result['n_received_rows']} returned rows; missing parts: {len(result['missing_part_indices'])}."
            )
            print(f"Full part coverage: {str(result['complete']).lower()}; collection and ingestion are separate.")
        else:
            print(f"Annotation {args.chunks_cmd}: {result['n_rows']} rows across {result['n_parts']} parts.")
        print("Private text stays local; no automatic labeling, sharing, ingestion or scientific GO.")

    return emit(args, f"calibrate chunks {args.chunks_cmd}", 0, result, human)
