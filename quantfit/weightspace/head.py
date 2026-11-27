"""Compile an affine donor head into a standalone, smaller text classifier."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np

from quantfit.bundle import _read

from ._tensors import (
    MAX_FILE_BYTES,
    MAX_MANIFEST_BYTES,
    SCHEMA,
    WeightspaceError,
    canonical,
    checkpoint,
    identity,
    ordered_records,
    read_json,
    records,
    require,
    sha,
    unpack,
)
from ._vectors import values
from .codec import _artifacts, _public_io, file_record, publish

DECLARATION = {"id": "linear-recipient-v1", "exact": True, "parameters": {}}
PHASES = ["load", "inference"]


def numeric(value, rank, name):
    try:
        raw = np.asarray(value)
        require(raw.dtype.kind in "iuf", f"{name} must contain real numbers")
        arr = raw.astype("f8")
    except (ValueError, TypeError, OverflowError) as exc:
        raise WeightspaceError(f"invalid numerical array for {name}") from exc
    require(arr.ndim == rank and all(arr.shape) and np.isfinite(arr).all(), f"invalid shape or values for {name}")
    return arr


def affine(inputs, outputs):
    require(len(inputs) == len(outputs), "anchor counts must agree")
    design = np.column_stack((inputs, np.ones(len(inputs))))
    try:
        mapping, _, rank, _ = np.linalg.lstsq(design, outputs, rcond=None)
    except np.linalg.LinAlgError as exc:
        raise WeightspaceError("anchor least squares failed to converge") from exc
    require(np.isfinite(mapping).all(), "nonfinite affine fit")
    return mapping, int(rank)


def _names(names, field):
    require(isinstance(names, list) and names and all(isinstance(x, str) and x for x in names), f"invalid {field}")
    require(len(set(names)) == len(names), f"duplicate {field}")


def contract(vocabulary, labels, lowercase):
    _names(vocabulary, "vocabulary")
    _names(labels, "labels")
    require(type(lowercase) is bool, "lowercase must be Boolean")
    require(all(w.split() == [w] and (not lowercase or w == w.lower()) for w in vocabulary), "unreachable token")
    return {"schema": "word-count-v1", "vocabulary": vocabulary, "lowercase": lowercase}, {
        "schema": "ordered-labels-v1",
        "labels": labels,
    }


@_public_io
def compile_head(
    recipient_anchors, donor_anchors, donor_weight, donor_bias, out, *, vocabulary, labels, lowercase=True
):
    """Fit paired unlabeled features by row, compose the donor head and write a standalone directory."""
    transform, classes = contract(vocabulary, labels, lowercase)
    rec = numeric(recipient_anchors, 2, "recipient anchors")
    donor = numeric(donor_anchors, 2, "donor anchors")
    w, b = numeric(donor_weight, 2, "donor weight"), numeric(donor_bias, 1, "donor bias")
    require(w.shape == (len(labels), donor.shape[1]) and len(b) == len(labels), "donor head dimensions disagree")
    require(rec.shape[1] == len(vocabulary) < donor.shape[1], "recipient vocabulary must fit a strictly smaller head")
    mapping, rank = affine(rec, donor)
    with np.errstate(over="ignore", invalid="ignore"):
        small_w = (w @ mapping[:-1].T).astype("<f4")
        small_b = (b + w @ mapping[-1]).astype("<f4")
    require(np.isfinite(small_w).all() and np.isfinite(small_b).all(), "compiled recipient exceeds finite float32")
    raw, tensors = checkpoint({"weight": small_w, "bias": small_b}, MAX_FILE_BYTES)
    components = [
        ("weights.safetensors", "recipient", raw),
        ("transform.json", "transform", canonical(transform)),
        ("labels.json", "labels", canonical(classes)),
    ]
    target = identity(tensors)
    manifest = {
        "schema": SCHEMA,
        "codec": DECLARATION,
        "identities": {
            "target": target,
            "recipient": target,
            "transform": sha(components[1][2]),
            "classes": sha(components[2][2]),
        },
        "tensors": records(tensors),
        "files": [file_record(path, blob, role, PHASES) for path, role, blob in components],
    }
    receipt = publish(out, manifest, {path: blob for path, _, blob in components})
    return {
        **receipt,
        "anchor_count": len(rec),
        "fit_rank": rank,
        "donor_width": donor.shape[1],
        "recipient_width": rec.shape[1],
        "donor_parameters": w.size + b.size,
        "recipient_parameters": small_w.size + small_b.size,
    }


@_public_io
def predict_head(artifact, text):
    """Verify the three local inference artifacts and score one raw text input."""
    require(isinstance(text, str), "recipient input must be text")
    path = Path(artifact)
    doc = read_json(_read(path, MAX_MANIFEST_BYTES))
    require(
        doc.get("schema") == SCHEMA and canonical(doc.get("codec")) == canonical(DECLARATION),
        "invalid recipient declaration",
    )
    files = _artifacts(doc, path.parent, MAX_FILE_BYTES, roles=("recipient", "transform", "labels"), phases=PHASES)
    transform, classes = read_json(files["transform"]), read_json(files["labels"])
    require(
        transform.get("schema") == "word-count-v1" and classes.get("schema") == "ordered-labels-v1",
        "unsupported text profile",
    )
    vocab, labels, lowercase = transform.get("vocabulary"), classes.get("labels"), transform.get("lowercase")
    contract(vocab, labels, lowercase)
    tensors = unpack(files["recipient"])
    require(
        set(tensors) == {"weight", "bias"} and all(t.dtype == "F32" for t in tensors.values()),
        "expected F32 weight and bias",
    )
    ids = doc.get("identities")
    digest = identity(tensors)
    require(
        isinstance(ids, dict)
        and ids.get("target") == ids.get("recipient") == digest
        and ids.get("transform") == sha(files["transform"])
        and ids.get("classes") == sha(files["labels"]),
        "recipient identity mismatch",
    )
    require(
        canonical(ordered_records(doc.get("tensors"))) == canonical(records(tensors)),
        "recipient tensor inventory mismatch",
    )
    w, b = (values(tensors[key]).astype("<f4") for key in ("weight", "bias"))
    require(w.shape == (len(labels), len(vocab)) and b.shape == (len(labels),), "recipient dimensions mismatch")
    counts = Counter((text.lower() if lowercase else text).split())
    logits = w @ np.asarray([counts[token] for token in vocab], dtype="<f4") + b
    require(np.isfinite(logits).all(), "nonfinite recipient logits")
    idx = int(np.argmax(logits))
    return {"class_index": idx, "label": labels[idx], "logits": logits.tolist(), "recipient_sha256": digest}


def load_spec(path):
    return read_json(_read(Path(path), MAX_MANIFEST_BYTES))
