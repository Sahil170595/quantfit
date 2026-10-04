"""Kill selected scientific/quantization decision mutants using existing tests.

Copies source and tests into an ephemeral directory; never rewrites the checkout.
The exact replacements are deliberately small and reviewed, not an overall score.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUTANTS = (
    (
        "quantfit/safety/mde.py",
        "if _binom_sf(k, pairs, q) <= alpha:",
        "if _binom_sf(k, pairs, q) >= alpha:",
        "tests/test_numerical_properties.py",
    ),
    (
        "quantfit/policy/probe.py",
        "torch.round(w / scale)",
        "torch.floor(w / scale)",
        "tests/test_numerical_properties.py",
    ),
    ("quantfit/policy/probe.py", "qmax = 2 ** (bits - 1) - 1", "qmax = 1", "tests/test_probe.py"),
)


def main() -> None:
    results = []
    for file, before, after, test in MUTANTS:
        with tempfile.TemporaryDirectory(prefix="quantfit-mutant-") as name:
            root = Path(name)
            shutil.copytree(ROOT / "quantfit", root / "quantfit", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(ROOT / "tests", root / "tests", ignore=shutil.ignore_patterns("__pycache__"))
            path = root / file
            source = path.read_text(encoding="utf-8")
            if source.count(before) != 1:
                raise SystemExit(f"mutant anchor changed: {file}: {before!r}; review the mutation")
            path.write_text(source.replace(before, after), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", test, "-q", "--maxfail=1", "-o", "addopts="],
                cwd=root,
                env={**os.environ, "PYTHONPATH": str(root)},
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            # Pytest 1 means assertions failed. Collection/setup errors do not kill a mutant.
            killed = proc.returncode == 1 and " failed" in proc.stdout and "ERROR" not in proc.stdout
            results.append({"file": file, "mutation": after, "killed": killed})
            print(proc.stdout[-1800:] if not killed else f"KILLED: {file}: {after}")
    print(json.dumps(results, indent=2))
    if not all(row["killed"] for row in results):
        raise SystemExit("a selected mutant survived or did not reach assertions")


if __name__ == "__main__":
    main()
