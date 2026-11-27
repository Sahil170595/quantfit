import json

import numpy as np
import pytest
from safetensors.numpy import load_file

from quantfit.weightspace import WeightspaceError, decode, encode

CODEC = "task-vector-v1"


@pytest.mark.parametrize("scale", [1.0, 0.0, -1.0, 0.5])
def test_task_vector_build_and_apply(tmp_path, scale):
    a = {"w": np.array([2, -0.0, 4.5], "f4"), "counter": np.array(9, "i4")}
    b = {**a, "w": np.array([3, -1.0, 7.0], "f4")}
    enc = encode(a, b, tmp_path / "bundle", codec=CODEC)
    out = tmp_path / "out.safetensors"
    result = decode(a, tmp_path / "bundle" / "manifest.json", out, scale=scale)
    oracle = (a["w"].astype("f8") + scale * (b["w"].astype("f8") - a["w"].astype("f8"))).astype("f4")
    actual = load_file(out)
    np.testing.assert_array_equal(actual["w"], oracle)
    assert actual["counter"] == 9 and result["scale"] == scale
    if scale == 0:
        assert actual["w"].tobytes() == a["w"].tobytes()
    assert enc["changed_tensors"] == 1 and enc["max_abs_error"] == 0


def test_reject_wrong_base_dtype_and_degree(tmp_path):
    a = {"x": np.array([1.0], "f4")}
    b = {"x": np.array([3.0], "f4")}
    enc = encode(a, b, tmp_path / "bundle", codec=CODEC)
    doc = json.loads((tmp_path / "bundle" / "manifest.json").read_bytes())
    assert enc["identities"]["reconstructed"] == enc["identities"]["target"] and doc["codec"]["exact"] is False
    for base, scale in [(b, 1), (a, float("nan")), (a, True)]:
        with pytest.raises(WeightspaceError):
            decode(base, tmp_path / "bundle" / "manifest.json", tmp_path / "out", scale=scale)
    with pytest.raises(WeightspaceError):
        encode({"x": np.array([1], "i4")}, {"x": np.array([2], "i4")}, tmp_path / "int", codec=CODEC)
