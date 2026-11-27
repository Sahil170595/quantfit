"""Exercise the installed exact codec on a fitted CPU classifier. Emits only aggregate evidence."""

import json
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

import numpy as np
from safetensors.numpy import load_file, save_file


def main():
    from quantfit import weightspace

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        # Fit a deterministic least-squares classifier, then fit a new target on shifted features.
        train = np.array([[-3, 1], [-2, 2], [-1, -2], [1, 0], [2, 2], [3, -1]], dtype=np.float64)
        labels = np.eye(2)[(train[:, 0] > 0).astype(int)]
        design = np.column_stack((train, np.ones(len(train))))

        def fitted(y):
            params = np.linalg.lstsq(design, y, rcond=None)[0].astype("<f4")
            return {"weight": params[:-1].T.copy(), "bias": params[-1].copy()}

        base, target = fitted(labels), fitted(labels[:, ::-1])
        src, wanted = root / "base.safetensors", root / "target.safetensors"
        save_file(base, src)
        save_file(target, wanted)
        result = weightspace.encode(src, wanted, root / "bundle")
        exe = Path(sys.executable).parent / ("quantfit.exe" if sys.platform == "win32" else "quantfit")
        out = root / "recovered.safetensors"
        cmd = [
            str(exe),
            "weightspace",
            "decode",
            "--base",
            str(src),
            "--artifact",
            str(root / "bundle" / "manifest.json"),
            "--out",
            str(out),
            "--json",
        ]
        native = json.loads(subprocess.check_output(cmd, cwd=root))
        actual = load_file(out)
        test = np.array([[-2, -3], [-0.5, 2], [0.5, 3], [2, -2]], dtype="<f4")
        expected = test @ target["weight"].T + target["bias"]
        observed = test @ actual["weight"].T + actual["bias"]
        assert np.array_equal(expected, observed) and np.unique(expected.argmax(axis=1)).size == 2
        assert all(actual[k].tobytes() == target[k].tobytes() for k in target)
        assert native["result"]["logical_sha256"] == result["identities"]["target"]
        print(
            json.dumps(
                {
                    "version": version("quantfit"),
                    "example": "least-squares-two-class",
                    "fit_cases": len(train),
                    "held_out_cases": len(test),
                    "matching_argmax": int(np.sum(expected.argmax(axis=1) == observed.argmax(axis=1))),
                    "max_abs_logit_error": float(np.max(np.abs(expected - observed))),
                    "exact_tensors": len(target),
                    "logical_sha256": result["identities"]["target"],
                    "cold_bytes": result["cold_bytes"],
                    "incremental_bytes": result["incremental_bytes"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
