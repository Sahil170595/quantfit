"""Independently compare installed arithmetic task-vector outputs with scalar calculations."""

import json
import struct
import tempfile
from importlib.metadata import version
from pathlib import Path

import numpy as np
from safetensors.numpy import load_file

from quantfit.weightspace import decode, encode


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        a = [-1.5, 2.0, 10.5, 0.25]
        b = [-3.0, 4.25, -1.0, 0.5]
        original = {"w": np.asarray(a, dtype="<f4"), "n": np.array(2, dtype="<i8")}
        target = {**original, "w": np.asarray(b, dtype="<f4")}
        encoded = encode(original, target, root / "bundle", codec="task-vector-v1")
        errors = []
        for idx, scale in enumerate((-1, 0, 0.25, 1)):
            out = root / f"{idx}.safetensors"
            decode(original, root / "bundle" / "manifest.json", out, scale=scale)
            wanted = [struct.unpack("<f", struct.pack("<f", x + scale * (y - x)))[0] for x, y in zip(a, b)]
            obs = load_file(out)
            errors.append(float(np.max(np.abs(obs["w"] - wanted))))
            assert obs["n"] == 2
        assert max(errors) == 0
        print(
            json.dumps(
                {
                    "version": version("quantfit"),
                    "scales_checked": 4,
                    "coefficients_per_scale": len(a),
                    "changed_tensors": encoded["changed_tensors"],
                    "max_abs_error_against_scalar": max(errors),
                    "source_target_digest": encoded["identities"]["target"],
                    "unit_scale_digest": encoded["identities"]["reconstructed"],
                }
            )
        )


if __name__ == "__main__":
    main()
