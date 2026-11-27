import json

import pytest

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
