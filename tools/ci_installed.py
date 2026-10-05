"""Exercise installed distribution outside checkout and reject source shadowing."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="quantfit-installed-") as name:
        sandbox = Path(name)
        code = (
            "import pathlib, quantfit, importlib.metadata as m; "
            f"assert not pathlib.Path(quantfit.__file__).resolve().is_relative_to(pathlib.Path({str(checkout)!r})); "
            "assert quantfit.__version__ == m.version('quantfit'); print(quantfit.__file__)"
        )
        subprocess.run([sys.executable, "-c", code], cwd=sandbox, env=env, check=True)
        for command in (["--help"], ["list"], ["verify-safety", "--demo", "--json"]):
            subprocess.run([sys.executable, "-m", "quantfit.cli", *command], cwd=sandbox, env=env, check=True)
        fixture = checkout / "validation/2026-10-05-calibrated-resolution"
        output = sandbox / "resolution.json"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantfit.cli",
                "resolution",
                "--report",
                str(fixture / "drift.json"),
                "--calibration-report",
                str(fixture / "calibration.json"),
                "--out",
                str(output),
                "--json",
            ],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        artifact = json.loads(completed.stdout)["result"]
        assert artifact == json.loads(output.read_text(encoding="utf-8"))
        assert artifact["inputs"]["report_sha256"] == hashlib.sha256((fixture / "drift.json").read_bytes()).hexdigest()
        assert artifact["human_confirmation_verified"] is False
        fixture = checkout / "validation/2026-10-05-reference-cli"
        for command, expected in (
            (["references", "list", "--json"], 0),
            (
                [
                    "references",
                    "verify",
                    "--registry",
                    str(fixture / "synthetic-registry.json"),
                    "--slug",
                    "fixture",
                    "--report",
                    str(fixture / "synthetic-bytes.json"),
                    "--json",
                ],
                0,
            ),
            (
                [
                    "references",
                    "verify",
                    "--registry",
                    str(fixture / "synthetic-registry.json"),
                    "--slug",
                    "fixture",
                    "--report",
                    str(fixture / "synthetic-changed-bytes.json"),
                    "--json",
                ],
                3,
            ),
        ):
            completed = subprocess.run(
                [sys.executable, "-m", "quantfit.cli", *command],
                cwd=sandbox,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert completed.returncode == expected, (completed.stdout, completed.stderr)
            document = json.loads(completed.stdout)
            assert document["exit_code"] == expected
            assert document["result"]["publication_verified"] is False
        # Explicit config prevents pyproject's pythonpath=['.'] injecting the source.
        config = sandbox / "pytest.ini"
        config.write_text("[pytest]\n", encoding="utf-8")
        tests = [
            "test_calibration_binding.py",
            "test_gate.py",
            "test_junit.py",
            "test_junit_gate_screen.py",
            "test_report.py",
            "test_mde.py",
            "test_probe.py",
            "test_reference_cli.py",
        ]
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-c",
                str(config),
                "--import-mode=importlib",
                "-q",
                *[str(checkout / "tests" / t) for t in tests],
            ],
            cwd=sandbox,
            env=env,
            check=True,
        )
    print(f"installed artifact accepted: quantfit {importlib.metadata.version('quantfit')}")


if __name__ == "__main__":
    main()
