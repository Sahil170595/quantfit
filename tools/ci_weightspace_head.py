"""Validate affine composition on held-out raw texts with no donor artifact present."""

import json
import tempfile
from importlib.metadata import version
from pathlib import Path

import numpy as np
from safetensors.numpy import load_file

from quantfit.weightspace import compile_head, predict_head


def fixture():
    recipient = np.array([[0, 0], [1, 0], [0, 1], [1, 1], [2, 1], [1, 2]], dtype="f8")
    donor = np.column_stack([recipient, recipient[:, 0] - recipient[:, 1] + 1])
    return {
        "recipient_anchors": recipient.tolist(),
        "donor_anchors": donor.tolist(),
        "donor_weight": [[1, 0, 1], [0, 2, -1]],
        "donor_bias": [-1, 0.5],
        "vocabulary": ["alpha", "beta"],
        "labels": ["first", "second"],
    }


def check(root):
    spec = fixture()
    donor_path = root / "compiler.json"
    donor_path.write_text(json.dumps(spec), encoding="utf8")
    info = compile_head(out=root / "run", **json.loads(donor_path.read_bytes()))
    shuffled = {**spec, "donor_anchors": list(reversed(spec["donor_anchors"]))}
    compile_head(out=root / "shuffled", **shuffled)
    donor_path.unlink()
    tensors = load_file(root / "run" / "weights.safetensors")
    np.testing.assert_allclose(tensors["weight"], [[2, -1], [-1, 3]], atol=1e-6)
    np.testing.assert_allclose(tensors["bias"], [0, -0.5], atol=1e-6)
    correct, wrong, errors, shuffled_errors = 0, 0, [], []
    for text, x, y in [
        ("Alpha alpha OOV alpha beta", 3, 1),
        ("beta BETA beta alpha", 1, 3),
        ("beta beta", 0, 2),
        ("ALPHA alpha", 2, 0),
    ]:
        expected = [2 * x - y, -x + 3 * y - 0.5]
        predicted = predict_head(root / "run" / "manifest.json", text)
        shuffled_out = predict_head(root / "shuffled" / "manifest.json", text)
        correct += int(predicted["class_index"] == int(np.argmax(expected)))
        wrong += int(shuffled_out["class_index"] == int(np.argmax(expected)))
        shuffled_errors.extend(abs(p - q) for p, q in zip(expected, shuffled_out["logits"]))
        errors.extend(abs(p - q) for p, q in zip(expected, predicted["logits"]))
    assert correct == 4 and max(errors) < 1e-6 and max(shuffled_errors) > 1.0
    return {
        k: info[k] for k in ("anchor_count", "fit_rank", "donor_parameters", "recipient_parameters", "cold_bytes")
    } | {
        "held_out_cases": 4,
        "correct": correct,
        "shuffled_correct": wrong,
        "shuffled_max_logit_error": max(shuffled_errors),
        "max_logit_error": max(errors),
        "donor_file_present": donor_path.exists(),
    }


def main():
    with tempfile.TemporaryDirectory() as td:
        print(json.dumps({"version": version("quantfit"), **check(Path(td))}))


if __name__ == "__main__":
    main()
