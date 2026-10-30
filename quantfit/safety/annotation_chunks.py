"""Private blank-template partitioning and complete, explicitly labeled collection."""

from __future__ import annotations

import csv
import os
from typing import Any

from quantfit import __version__
from quantfit.safety import calibrate
from quantfit.safety.label_review import _csv
from quantfit.safety.reconcile import MAX_CSV_RECORDS, MAX_IDS, MAX_KEY_BYTES, MAX_SHEET_BYTES
from quantfit.safety.retained_labels import MAX_RECEIPT_BYTES, _binding, _encode, _json, _key, _scope
from quantfit.safety.retention_io import HeldFile, admit_outputs, canonical, hold, publish, require

MAX_PARTS = 128
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_INPUT_BYTES = 2 * MAX_SHEET_BYTES + MAX_KEY_BYTES + MAX_MANIFEST_BYTES + 512 * MAX_PARTS
MAX_OUTPUT_BYTES = MAX_SHEET_BYTES + MAX_MANIFEST_BYTES
# Source and reconstructed full sheet each use the native limit; returned parts
# have at most twice their assigned rows plus one header each, including blanks.
MAX_TOTAL_CSV_RECORDS = 3 * MAX_CSV_RECORDS + MAX_PARTS
MANIFEST_NAME = "annotation.chunkmanifest.json"
SCOPE = (
    "Local partition and collection of supplied native labeling sheets only. "
    "No capture is read; capture scope/digest are key declarations. Only blinded parts may be shared "
    "under the existing single named second-annotator carve-out; never share this manifest or key. "
    "No automatic labeling, sending, ingestion, rater authentication, independence, human truth or scientific GO. "
    "Manifest-last exclusive publication is not a directory transaction; earlier new outputs may remain after failure."
)
LIMITS = {"human_labels_authenticated": False, "rater_identity_verified": False, "scientific_go": False}


class AnnotationChunksError(RuntimeError):
    """Categorical error boundary for private parser, filesystem and label values."""


def _held(paths: tuple[str, ...], limits: tuple[int, ...]) -> tuple[HeldFile, ...]:
    names = tuple(canonical(path) for path in paths)
    require(len({os.path.normcase(str(path)) for path in names}) == len(names))
    remaining = MAX_INPUT_BYTES
    result = []
    for path, limit in zip(names, limits, strict=True):
        require(remaining > 0)
        item = hold(path, min(limit, remaining))
        remaining -= len(item.data)
        result.append(item)
    return tuple(result)


def _blank(inputs: tuple[HeldFile, ...]) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    key, n = _key(inputs[1].data)
    rows = calibrate._read_sheet("private template", data=inputs[0].data, max_records=MAX_CSV_RECORDS)
    require(len(rows) == len(key["ids"]) <= MAX_IDS)
    seen: set[str] = set()
    for row in rows:
        ident = row["id"]
        require(ident in key["ids"] and ident not in seen and row["human_label"] == "")
        require(calibrate._completion_sha256(row["completion"]) == key["ids"][ident]["completion_sha256"])
        seen.add(ident)
    require(seen == set(key["ids"]))
    return rows, key, n


def _annotator(role: str, name: str | None) -> dict[str, str | None]:
    require(role in {"maintainer", "named_second"})
    require(name is None or type(name) is str and 0 < len(name) <= 120 and name == name.strip())
    require(name is None or all(ord(char) >= 32 and ord(char) != 127 for char in name))
    require(role != "named_second" or name is not None)
    return {"role": role, "name": name}


def _preparation(
    inputs: tuple[HeldFile, ...], size: int, annotator: dict[str, str | None], version: str
) -> tuple[dict[str, Any], tuple[bytes, ...], list[dict[str, Any]]]:
    require(type(size) is int and 1 <= size <= MAX_IDS)
    rows, key, n = _blank(inputs)
    count = (len(rows) + size - 1) // size
    require(1 <= count <= MAX_PARTS)
    parts: list[bytes] = []
    records: list[dict[str, Any]] = []
    total = 0
    for offset in range(0, len(rows), size):
        assigned = rows[offset : offset + size]
        raw = _csv([(row["id"], row["completion"], "") for row in assigned])
        total += len(raw)
        require(total <= MAX_OUTPUT_BYTES)
        index = len(parts) + 1
        parts.append(raw)
        records.append(
            {
                "index": index,
                "filename": f"part-{index:04d}.labels.csv",
                "ids": [row["id"] for row in assigned],
                "blank_sheet": _binding(raw),
            }
        )
    fingerprint, capture = _scope(key)
    manifest = {
        "annotation_chunk_schema": 1,
        "quantfit_version": version,
        "inputs": {"sheet": _binding(inputs[0].data), "key": _binding(inputs[1].data)},
        "rows_per_part": size,
        "n_pairs": n,
        "n_rows": len(rows),
        "n_parts": count,
        "parts": records,
        "annotator_declared": annotator,
        "binding_fingerprint": fingerprint,
        "capture_sha256_declared": capture,
        "limits": dict(LIMITS),
        "scope": SCOPE,
    }
    encoded = _encode(manifest)
    require(len(encoded) <= MAX_MANIFEST_BYTES and total + len(encoded) <= MAX_OUTPUT_BYTES)
    return manifest, tuple(parts), rows


def _summary(manifest: dict[str, Any], raw_manifest: bytes) -> dict[str, Any]:
    return {
        "annotation_chunks_schema": 1,
        "quantfit_version": __version__,
        "inputs": manifest["inputs"],
        "manifest": _binding(raw_manifest),
        "n_pairs": manifest["n_pairs"],
        "n_rows": manifest["n_rows"],
        "n_parts": manifest["n_parts"],
        "annotator_declared": manifest["annotator_declared"],
        "parts": [
            {"index": part["index"], "n_rows": len(part["ids"]), "blank_sheet": part["blank_sheet"]}
            for part in manifest["parts"]
        ],
        "limits": dict(LIMITS),
        "scope": SCOPE,
    }


def prepare_annotation_chunks(
    sheet_path: str,
    key_path: str,
    *,
    out_dir: str,
    rows_per_part: int = 100,
    annotator_role: str = "maintainer",
    annotator_name: str | None = None,
) -> dict[str, Any]:
    """Publish every blank partition and a PRIVATE manifest last into an empty existing directory."""
    try:
        require(type(rows_per_part) is int and 1 <= rows_per_part <= MAX_IDS)
        declared = _annotator(annotator_role, annotator_name)
        directory = canonical(out_dir)
        require(directory.is_dir() and not any(directory.iterdir()))
        inputs = _held((sheet_path, key_path), (MAX_SHEET_BYTES, MAX_KEY_BYTES))
        manifest, parts, _ = _preparation(inputs, rows_per_part, declared, __version__)
        raw_manifest = _encode(manifest)
        paths = tuple(str(directory / part["filename"]) for part in manifest["parts"]) + (
            str(directory / MANIFEST_NAME),
        )
        targets = admit_outputs(paths, inputs)
        publish(tuple(zip(targets, (*parts, raw_manifest), strict=True)), inputs)
        return _summary(manifest, raw_manifest)
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
        raise AnnotationChunksError("invalid_annotation_chunks") from None


def collect_annotation_chunks(
    sheet_path: str, key_path: str, manifest_path: str, part_paths: tuple[str, ...], *, out_path: str, receipt_path: str
) -> dict[str, Any]:
    """Verify every returned partition and publish a NEW complete native sheet and aggregate receipt."""
    try:
        require(type(part_paths) is tuple and 1 <= len(part_paths) <= MAX_PARTS)
        inputs = _held(
            (sheet_path, key_path, manifest_path, *part_paths),
            (MAX_SHEET_BYTES, MAX_KEY_BYTES, MAX_MANIFEST_BYTES, *(MAX_SHEET_BYTES for _ in part_paths)),
        )
        manifest = _json(inputs[2].data)
        version = manifest["quantfit_version"]
        require(type(version) is str and 0 < len(version) <= 64)
        declared = manifest["annotator_declared"]
        require(type(declared) is dict and set(declared) == {"role", "name"})
        expected, _, rows = _preparation(
            inputs, manifest["rows_per_part"], _annotator(declared["role"], declared["name"]), version
        )
        # Canonical JSON preserves bool/int/float distinctions, unlike dict equality.
        require(_encode(expected) == _encode(manifest) and len(part_paths) == manifest["n_parts"])
        key, _ = _key(inputs[1].data)
        labels: dict[str, str] = {}
        filled = []
        for assigned, held in zip(manifest["parts"], inputs[3:], strict=True):
            subset = {ident: key["ids"][ident] for ident in assigned["ids"]}
            joined = calibrate._join(
                "private returned part", "private key", subset, data=held.data, max_records=2 * len(subset) + 1
            )
            require(not labels.keys() & joined.keys())
            labels.update({ident: row["human_label"] for ident, row in joined.items()})
            filled.append(
                {
                    "index": assigned["index"],
                    "n_rows": len(joined),
                    "blank_sheet": assigned["blank_sheet"],
                    "filled_sheet": _binding(held.data),
                }
            )
        require(set(labels) == set(key["ids"]))
        full = _csv([(row["id"], row["completion"], labels[row["id"]]) for row in rows])
        calibrate._join("private collected sheet", "private key", key["ids"], data=full, max_records=MAX_CSV_RECORDS)
        receipt = {
            **_summary(manifest, inputs[2].data),
            "parts": filled,
            "output_sheet": _binding(full),
            "n_unusable": sum(label == "unusable" for label in labels.values()),
        }
        raw_receipt = _encode(receipt)
        require(len(raw_receipt) <= MAX_RECEIPT_BYTES and len(full) + len(raw_receipt) <= MAX_OUTPUT_BYTES)
        targets = admit_outputs((out_path, receipt_path), inputs)
        publish(((targets[0], full), (targets[1], raw_receipt)), inputs)
        return receipt
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
        raise AnnotationChunksError("invalid_annotation_chunks") from None
