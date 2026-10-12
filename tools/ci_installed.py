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
        fixture = checkout / "validation/2026-10-08-calibration-aware-outputs"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantfit.cli",
                "emit",
                "model-card",
                "--report",
                str(fixture / "drift.json"),
                "--calibration-report",
                str(fixture / "calibration.json"),
                "--json",
            ],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        card = json.loads(completed.stdout)["result"]["fragment"]
        for name in ("drift.json", "calibration.json"):
            assert hashlib.sha256((fixture / name).read_bytes()).hexdigest() in card
        assert "### Conditional resolution from bound calibration" in card
        assert "human labels: **unverified**" in card
        assert "no safety verdict, research GO or sensitivity-control result" in card
        fixture = checkout / "validation/2026-10-05-reference-cli"
        # Git text checkout can change LF/CRLF. Declare the actual sandbox bytes
        # for this synthetic CI case; committed historical receipts stay intact.
        reference_bytes = (fixture / "synthetic-bytes.json").read_bytes()
        reference_path = sandbox / "reference.json"
        reference_path.write_bytes(reference_bytes)
        changed_path = sandbox / "reference-changed.json"
        changed_path.write_bytes((fixture / "synthetic-changed-bytes.json").read_bytes())
        registry = json.loads((fixture / "synthetic-registry.json").read_text(encoding="utf-8"))
        registry["reports"][0]["report_sha256"] = hashlib.sha256(reference_bytes).hexdigest()
        registry_path = sandbox / "reference-registry.json"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        for command, expected in (
            (["references", "list", "--json"], 0),
            (
                [
                    "references",
                    "verify",
                    "--registry",
                    str(registry_path),
                    "--slug",
                    "fixture",
                    "--report",
                    str(reference_path),
                    "--json",
                ],
                0,
            ),
            (
                [
                    "references",
                    "verify",
                    "--registry",
                    str(registry_path),
                    "--slug",
                    "fixture",
                    "--report",
                    str(changed_path),
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
            if command[1] == "verify":
                result = document["result"]
                assert result["expected_sha256"] == hashlib.sha256(reference_bytes).hexdigest()
                assert result["actual_sha256"] == hashlib.sha256(Path(command[-2]).read_bytes()).hexdigest()
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
