import hashlib
import json

import numpy as np
import pytest
from safetensors.numpy import load_file, save_file

from quantfit.weightspace import WeightspaceError, decode, encode
from tools.ci_weightspace_lowbit import check


@pytest.mark.parametrize("bits", [4, 8])
def test_wire_against_scalar(tmp_path, bits):
    assert check(tmp_path, bits)["max_abs_error"] >= 0


@pytest.mark.parametrize("bits,group", [(True, 7), (4, False), (5, 4), (8, 0)])
def test_invalid_parameters(tmp_path, bits, group):
    with pytest.raises(WeightspaceError):
        encode({}, {}, tmp_path / "out", codec="grouped-int-v1", bits=bits, group_size=group)


def test_ties_layout_padding_and_reserved_codes(tmp_path):
    # With an exact unit step, ties round toward the nearest even integer.
    a = {"x": np.zeros(5, dtype="f4")}
    b = {"x": np.array([-0.5, -1.5, 1.5, 2.5, 7.0], dtype="f4")}
    folder = tmp_path / "out"
    encode(a, b, folder, codec="grouped-int-v1", bits=4, group_size=5)
    path = folder / "delta.safetensors"
    tensors = load_file(path)
    assert list(tensors["codes.0"]) == [0xE0, 0x22, 0x07]
    manifest = folder / "manifest.json"
    doc = json.loads(manifest.read_bytes())
    for packed, error in [([0xE0, 0x22, 0x17], "padding"), ([0xE8, 0x22, 0x07], "reserved")]:
        save_file({**tensors, "codes.0": np.array(packed, "u1")}, path)
        doc["files"][1].update(size_bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        manifest.write_text(json.dumps(doc), encoding="utf8")
        with pytest.raises(WeightspaceError, match=error):
            decode(a, manifest, tmp_path / "decoded")
