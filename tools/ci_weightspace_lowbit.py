"""Compare packed bytes and reconstructed tensors with a scalar reference."""

import json
import tempfile
from importlib.metadata import version
from pathlib import Path

import numpy as np
from safetensors.numpy import load_file

from quantfit.weightspace import decode, encode


def check(root, bits):
    bound = (1 << (bits - 1)) - 1
    values = [float(q) for q in range(-bound, bound + 1)] + [0.0] * (2 * bound + 1) + [0.25, -0.5, 1.75]
    width = 2 * bound + 1
    arr = np.asarray(values, dtype="<f4")
    original = {"w": np.zeros_like(arr)}
    folder = root / str(bits)
    receipt = encode(original, {"w": arr}, folder, codec="grouped-int-v1", bits=bits, group_size=width)
    payload = load_file(folder / "delta.safetensors")
    ref, codes, scales = [], [], []
    for i in range(0, len(values), width):
        block = values[i : i + width]
        step = max(map(abs, block)) / bound
        scales.append(step)
        for v in block:
            code = max(-bound, min(bound, round(v / step))) if step else 0
            codes.append(code)
            ref.append(np.float32(code * step))
    expected = (
        bytes(q % 256 for q in codes)
        if bits == 8
        else bytes(
            (codes[i] % 16) | ((codes[i + 1] % 16) << 4 if i + 1 < len(codes) else 0) for i in range(0, len(codes), 2)
        )
    )
    assert expected == payload["codes.0"].tobytes()
    assert scales == list(payload["scales.0"])
    out = root / f"decoded-{bits}.safetensors"
    decode(original, folder / "manifest.json", out)
    np.testing.assert_array_equal(load_file(out)["w"], ref)
    assert sum(p.stat().st_size for p in folder.iterdir()) == receipt["cold_bytes"]
    error = float(np.max(np.abs(arr.astype("f8") - np.asarray(ref, "f8"))))
    assert error == receipt["max_abs_error"]
    return {
        "bits": bits,
        "elements": len(values),
        "packed_code_bytes": len(expected),
        "max_abs_error": error,
        "cold_bytes": receipt["cold_bytes"],
        "incremental_bytes": receipt["incremental_bytes"],
    }


def main():
    with tempfile.TemporaryDirectory() as td:
        print(json.dumps({"version": version("quantfit"), "trials": [check(Path(td), b) for b in (4, 8)]}))


if __name__ == "__main__":
    main()
