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
        # Installed capability/early refusal only. Actual installed GGUF generation and
        # three-run T0 will be qualified by the hosted reference campaign against
        # the recorded cold_run/gguf_arm/verify source hashes; these cases load no models.
        for command in (
            ["cold-run", "--baseline", "unsupported-HF", "--quant", "unsupported-HF", "--out", "unused-cold"],
            [
                "verify-safety",
                "--baseline",
                "unsupported-HF",
                "--quant",
                "unsupported-HF",
                "--baseline-revision",
                "a" * 40,
            ],
        ):
            refused = subprocess.run(
                [sys.executable, "-m", "quantfit.cli", *command, "--json"],
                cwd=sandbox,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert refused.returncode == 2
            assert json.loads(refused.stdout)["exit_code"] == 2
        assert not (sandbox / "unused-cold").exists()
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
        bundle = sandbox / "aggregate-bundle"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantfit.cli",
                "bundle",
                "create",
                "--report",
                str(fixture / "drift.json"),
                "--calibration-report",
                str(fixture / "calibration.json"),
                "--resolution",
                str(fixture / "resolution.json"),
                "--gate",
                str(fixture / "pre-run/gate.json"),
                "--out",
                str(bundle),
                "--json",
            ],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout
        created = json.loads(completed.stdout)["result"]
        assert created["integrity_verified"] is True and created["scientific_claims_verified"] is False
        relocated = sandbox / "relocated-bundle"
        bundle.rename(relocated)
        completed = subprocess.run(
            [sys.executable, "-m", "quantfit.cli", "bundle", "verify", "--bundle", str(relocated), "--json"],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        verified = json.loads(completed.stdout)["result"]
        assert verified["integrity_verified"] is True and verified["scientific_claims_verified"] is False
        assert verified["declared_results"] == created["declared_results"]
        assert verified["declared_results"]["gate"]["exit_code"] == 5
        assert verified["declared_results"]["gate"]["actual_run_matched"] is False
        for member in verified["manifest"]["files"]:
            assert member["sha256"] == hashlib.sha256((relocated / member["path"]).read_bytes()).hexdigest()
        # Tampering changes the byte contract, even if the edited JSON still parses.
        with (relocated / "report.json").open("ab") as stream:
            stream.write(b" ")
        completed = subprocess.run(
            [sys.executable, "-m", "quantfit.cli", "bundle", "verify", "--bundle", str(relocated), "--json"],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 3
        assert json.loads(completed.stdout)["result"]["integrity_verified"] is False
        negative = sandbox / "negative-bundle"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantfit.cli",
                "bundle",
                "create",
                "--gate",
                str(fixture / "pre-run/gate.json"),
                "--calibration-report",
                str(fixture / "calibration.json"),
                "--out",
                str(negative),
                "--json",
            ],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        created = json.loads(completed.stdout)["result"]
        assert created["scientific_claims_verified"] is False and "report" not in created["declared_results"]
        moved_negative = sandbox / "relocated-negative"
        negative.rename(moved_negative)
        completed = subprocess.run(
            [sys.executable, "-m", "quantfit.cli", "bundle", "verify", "--bundle", str(moved_negative), "--json"],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        verified = json.loads(completed.stdout)["result"]
        assert verified["integrity_verified"] is True and verified["scientific_claims_verified"] is False
        assert verified["declared_results"] == created["declared_results"]
        assert verified["declared_results"]["gate"]["exit_code"] == 5
        assert verified["declared_results"]["gate"]["actual_run_matched"] is False
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
