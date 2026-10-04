"""Audit the actual installed graph, including CPU Torch's upstream release version.

PyPI's advisory service cannot look up the separate PyTorch index's '+cpu' version.
Only that known local suffix is normalized; no dependency is silently omitted.
This checks release advisories, not the integrity of a vendor's binary build.
"""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    requirements = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        if name.lower() == "quantfit":  # candidate source is not a dependency advisory
            continue
        version = dist.version
        if name.lower() == "torch" and version.endswith("+cpu"):
            print(f"advisory lookup: installed torch {version} -> public release {version.removesuffix('+cpu')}")
            version = version.removesuffix("+cpu")
        requirements.append(f"{name}=={version}")
    with tempfile.TemporaryDirectory(prefix="quantfit-audit-") as name:
        path = Path(name) / "installed.txt"
        path.write_text("\n".join(sorted(set(requirements))) + "\n", encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--strict",
                "--disable-pip",
                "--no-deps",
                "--progress-spinner",
                "off",
                "-r",
                str(path),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
