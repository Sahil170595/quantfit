import hashlib
import json
import struct

import numpy as np
import pytest
from safetensors import deserialize
from safetensors.numpy import load_file, save_file

from quantfit.weightspace import WeightspaceError, decode, encode


def test_lossless_cancellation_signed_zero_and_canonical_identity(tmp_path):
    base = {"bias": np.array([0.5, -0.5], "f4"), "weight": np.array([[2**27, -0.0], [2, -1]], "f4")}
    target = {**base, "weight": np.array([[1, 0.0], [2, -1]], "f4")}
    result = encode(base, target, tmp_path / "bundle")
    manifest = tmp_path / "bundle" / "manifest.json"
    doc = json.loads(manifest.read_bytes())
    assert doc["identities"]["target"] == "17e5898dcb3c653f4a23e220337910d1353cf179c1cb88fd88fcdd9e385ae97d"
    assert doc["metadata"]["unchanged"] == ["bias"]
    assert result["cold_bytes"] == sum(p.stat().st_size for p in manifest.parent.iterdir())
    assert result["incremental_bytes"] == result["cold_bytes"] - (manifest.parent / "base.safetensors").stat().st_size
    path = tmp_path / "reconstructed.safetensors"
    receipt = decode(base, manifest, path)
    assert receipt["logical_sha256"] == doc["identities"]["target"]
    assert load_file(path)["weight"].tobytes() == struct.pack("<4f", 1, 0.0, 2, -1)
    assert load_file(path)["bias"].tobytes() == target["bias"].tobytes()


def test_invalid_evidence_and_existing_output(tmp_path):
    base = {"x": np.array([2], "f4")}
    target = {"x": np.array([3], "f4")}
    folder = tmp_path / "bundle"
    encode(base, target, folder)
    manifest = folder / "manifest.json"
    out = tmp_path / "out"
    with pytest.raises(WeightspaceError):
        decode(target, manifest, out)
    assert not out.exists()
    out.write_bytes(b"owned")
    with pytest.raises(WeightspaceError):
        decode(base, manifest, out)
    assert out.read_bytes() == b"owned"
    out.unlink()
    payload = folder / "delta.safetensors"
    original = payload.read_bytes()
    payload.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    with pytest.raises(WeightspaceError):
        decode(base, manifest, out)
    assert not out.exists()
    payload.write_bytes(original)
    doc = json.loads(manifest.read_bytes())
    doc["schema"] = "weightspace-manifest/v100"
    manifest.write_text(json.dumps(doc))
    with pytest.raises(WeightspaceError):
        decode(base, manifest, out)


def test_path_inputs_scalars_empty_and_bfloat(tmp_path):
    base = {"s": np.array(3, dtype="<i2"), "empty": np.array([], dtype="u1")}
    src = tmp_path / "a.safetensors"
    save_file(base, src)
    bundle = tmp_path / "bundle"
    encode(src, src, bundle)
    out = tmp_path / "recovered.safetensors"
    decode(src, bundle / "manifest.json", out)
    tensors = dict(deserialize(out.read_bytes()))
    assert tensors["s"]["shape"] == [] and tensors["empty"]["shape"] == [0]
    for arr in [base["s"], base["empty"]]:
        assert hashlib.sha256(arr.tobytes()).hexdigest() in (bundle / "manifest.json").read_text()


def test_refuse_incompatible_layout_and_alias(tmp_path):
    arr = np.ones(3)
    with pytest.raises(WeightspaceError):
        encode({"a": arr}, {"a": arr.reshape(3, 1)}, tmp_path / "wrong")
    with pytest.raises(WeightspaceError):
        encode({"a": arr, "b": arr}, {"a": arr, "b": arr}, tmp_path / "alias")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("mutate", ["codec_flag", "identity", "missing"])
def test_typed_invalid_codec_or_identity(tmp_path, mutate):
    base = {"x": np.ones(2, "f4")}
    encode(base, base, tmp_path / "bundle")
    manifest = tmp_path / "bundle" / "manifest.json"
    doc = json.loads(manifest.read_bytes())
    if mutate == "codec_flag":
        doc["codec"]["exact"] = 1
    elif mutate == "identity":
        doc["identities"]["donor"] = "bad"
    else:
        (tmp_path / "bundle" / "base.safetensors").unlink()
    manifest.write_text(json.dumps(doc))
    with pytest.raises(WeightspaceError):
        decode(base, manifest, tmp_path / "new.safetensors")
    assert not (tmp_path / "new.safetensors").exists()


def test_tensor_order_is_portable_but_duplicate_names_fail(tmp_path):
    model = {"b": np.ones(1, "f4"), "a": np.ones(1, "i8")}
    directory = tmp_path / "bundle"
    encode(model, model, directory)
    path = directory / "manifest.json"
    doc = json.loads(path.read_bytes())
    doc["tensors"].reverse()
    path.write_text(json.dumps(doc))
    assert decode(model, path, tmp_path / "out")["logical_sha256"] == doc["identities"]["target"]
    doc["tensors"].append(doc["tensors"][0])
    path.write_text(json.dumps(doc))
    with pytest.raises(WeightspaceError, match="duplicate"):
        decode(model, path, tmp_path / "second")
