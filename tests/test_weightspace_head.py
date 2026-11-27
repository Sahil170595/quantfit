import json
import subprocess
import sys

import numpy as np
import pytest
from safetensors.numpy import save_file

from quantfit.weightspace import WeightspaceError, compile_head, predict_head
from tools.ci_weightspace_head import check, fixture


def test_analytic_compiler_with_shuffled_control(tmp_path):
    assert check(tmp_path)["recipient_parameters"] == 6


@pytest.mark.parametrize(
    "replacement",
    [
        {"labels": []},
        {"vocabulary": ["ALPHA", "beta"]},
        {"donor_anchors": []},
        {"recipient_anchors": [[0, 0]]},
        {"donor_weight": [[1, 2], [3, 4]]},
        {"lowercase": 1},
        {"donor_bias": [1]},
        {"recipient_anchors": [[0, 0, 0]] * 6, "vocabulary": ["a", "b", "c"]},
    ],
)
def test_reject_invalid_compile_contract(tmp_path, replacement):
    with pytest.raises(WeightspaceError):
        compile_head(out=tmp_path / "out", **(fixture() | replacement))
    assert not (tmp_path / "out").exists()


def test_tie_order_and_corruption(tmp_path):
    spec = fixture() | {"donor_weight": [[0, 0, 0], [0, 0, 0]], "donor_bias": [1, 1], "labels": ["zz", "aa"]}
    compile_head(out=tmp_path / "ok", **spec)
    manifest = tmp_path / "ok" / "manifest.json"
    assert predict_head(manifest, "OOV")["label"] == "zz"
    doc = json.loads(manifest.read_bytes())
    doc["identities"]["classes"] = "0" * 64
    manifest.write_text(json.dumps(doc), encoding="utf8")
    with pytest.raises(WeightspaceError, match="identity"):
        predict_head(manifest, "alpha")


def test_float32_dot_then_bias_agrees_with_cli(tmp_path):
    from quantfit.weightspace._tensors import identity, records, sha, unpack

    root = tmp_path / "bundle"
    compile_head(out=root, **fixture())
    path = root / "weights.safetensors"
    save_file({"weight": np.array([[2**24, 1], [0, 0]], "f4"), "bias": np.array([-(2**24), 0.5], "f4")}, path)
    manifest = root / "manifest.json"
    doc = json.loads(manifest.read_bytes())
    raw = path.read_bytes()
    ts = unpack(raw)
    doc["tensors"] = records(ts)
    doc["identities"].update(target=identity(ts), recipient=identity(ts))
    doc["files"][0].update(size_bytes=len(raw), sha256=sha(raw))
    manifest.write_text(json.dumps(doc), encoding="utf8")
    result = predict_head(manifest, "alpha beta")
    assert result["class_index"] == 1 and result["logits"] == [0.0, 0.5]
    p = subprocess.run(
        [
            sys.executable,
            "-m",
            "quantfit.cli",
            "weightspace",
            "predict-head",
            "--artifact",
            str(manifest),
            "--input-text",
            "alpha beta",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    response = json.loads(p.stdout)
    assert response["result"] == result
