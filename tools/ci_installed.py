"""Exercise installed distribution outside checkout and reject source shadowing."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


def _pytest_code(checkout: Path) -> str:
    """Keep installed application provenance in the same process as fixture tests."""
    return f"""
import pathlib, sys, quantfit, pytest
checkout = pathlib.Path({str(checkout)!r}).resolve()
def guard():
    assert checkout not in {{pathlib.Path(p or '.').resolve() for p in sys.path}}, 'checkout root injected into pytest'
    for name, module in tuple(sys.modules.items()):
        if name == 'quantfit' or name.startswith('quantfit.'):
            origin = getattr(module, '__file__', None)
            assert origin and not pathlib.Path(origin).resolve().is_relative_to(checkout), 'source-shadowed application: ' + name
class Guard:
    def pytest_sessionstart(self, session): guard()
    def pytest_sessionfinish(self, session, exitstatus): guard()
guard()
code = pytest.main(sys.argv[1:], plugins=[Guard()])
guard()
raise SystemExit(code)
"""


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
            "assert quantfit.__version__ == m.version('quantfit'); "
            "assert [(e.name,e.value) for e in m.distribution('quantfit').entry_points if e.group=='inspect_ai'] "
            "== [('quantfit','quantfit._inspect_registry')]; print(quantfit.__file__)"
        )
        subprocess.run([sys.executable, "-c", code], cwd=sandbox, env=env, check=True)
        # Exact historical producer bytes, with disposable input copies removed
        # before relocated verification. Original native locators are never followed.
        producer = checkout / "validation/2026-10-09-phi4-public-candidate/producer"
        reports = [sandbox / f"original-{i}.json" for i in range(1, 4)]
        original_t0 = sandbox / "original-t0.json"
        held = [(producer / f"run-{i}/report.json").read_bytes() for i in range(1, 4)]
        held_t0 = (producer / "native-t0.json").read_bytes()
        for path, raw in zip(reports, held, strict=True):
            path.write_bytes(raw)
        original_t0.write_bytes(held_t0)
        replay_bundle = sandbox / "replicate-bundle"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantfit.cli",
                "bundle",
                "replay-create",
                "--reports",
                *map(str, reports),
                "--t0",
                str(original_t0),
                "--out",
                str(replay_bundle),
                "--json",
            ],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        for path in [*reports, original_t0]:
            path.unlink()
        moved_replay = sandbox / "relocated-replicates"
        replay_bundle.rename(moved_replay)
        completed = subprocess.run(
            [sys.executable, "-m", "quantfit.cli", "bundle", "replay-verify", "--bundle", str(moved_replay), "--json"],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        replay = json.loads(completed.stdout)["result"]
        assert replay["integrity_verified"] is True
        assert replay["original_t0"]["protocol_pass"] is replay["receiving_t0"]["protocol_pass"] is True
        assert replay["producer_locations_verified"] is replay["scientific_claims_verified"] is False
        assert replay["receiving_t0"]["independent_execution_verified"] is False
        assert (moved_replay / "t0.json").read_bytes() == held_t0
        for i, raw in enumerate(held, 1):
            copied = (moved_replay / f"report-{i}.json").read_bytes()
            assert copied == raw
            assert json.loads(copied)["drift"]["over_refusal"]["overrefusal_regressions"] == 2
        # Actual installed offline customer path: preserve the original Phi4
        # negative aggregate while its dangerous-axis-only floor gate returns0.
        replay_source = checkout / "validation/2026-10-09-phi4-public-candidate/producer/run-1/report.json"
        bound_fixture = checkout / "validation/2026-10-08-calibration-aware-outputs"
        for label, source, expected_code, calibration in (
            ("negative-phi4", replay_source, 0, None),
            ("bound-policy-refusal", bound_fixture / "drift.json", 5, bound_fixture / "calibration.json"),
        ):
            copied, gate_path, junit = (
                sandbox / f"{label}-{kind}" for kind in ("report.json", "gate.json", "junit.xml")
            )
            command = [
                sys.executable,
                "-m",
                "quantfit.cli",
                "gate",
                "--from-report",
                str(source),
                "--tier",
                "smoke",
                "--report",
                str(copied),
                "--out",
                str(gate_path),
                "--junit",
                str(junit),
                "--json",
            ]
            if calibration is not None:
                command += ["--calibration-report", str(calibration)]
            completed = subprocess.run(command, cwd=sandbox, env=env, capture_output=True, text=True, check=False)
            assert completed.returncode == expected_code, completed.stdout + completed.stderr
            replay = json.loads(completed.stdout)["result"]
            assert copied.read_bytes() == source.read_bytes()
            assert replay["source_evidence"]["report_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
            assert replay["source_evidence"]["inference_performed"] is False
            if calibration is None:
                assert replay["ungated_axis_regressed"] is True and replay["over_refusal"]["flips"] == 2
                assert "REGRESSION DETECTED" in replay["underlying_run_verdict"]
            else:
                assert replay["drift"] is None and replay["eps"]["actual_run_matched"] is True
                assert replay["eps"]["assumptions_verified"] is replay["eps"]["measured"] is False
            bundle = sandbox / f"{label}-bundle"
            create = [
                sys.executable,
                "-m",
                "quantfit.cli",
                "bundle",
                "create",
                "--report",
                str(copied),
                "--gate",
                str(gate_path),
                "--out",
                str(bundle),
                "--json",
            ]
            if calibration is not None:
                create += ["--calibration-report", str(calibration)]
            subprocess.run(create, cwd=sandbox, env=env, check=True)
            moved = sandbox / f"{label}-relocated"
            bundle.rename(moved)
            verified = subprocess.run(
                [sys.executable, "-m", "quantfit.cli", "bundle", "verify", "--bundle", str(moved), "--json"],
                cwd=sandbox,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            assert json.loads(verified.stdout)["result"]["integrity_verified"] is True
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
        # Only sibling test helpers are visible; checkout application imports
        # remain forbidden before/during/after this same pytest process.
        config = sandbox / "pytest.ini"
        config.write_text(f"[pytest]\npythonpath = {shlex.quote((checkout / 'tests').as_posix())}\n", encoding="utf-8")
        tests = [
            "test_calibration_binding.py",
            "test_gate.py",
            "test_resolution.py",
            "test_calibrated_modelcard.py",
            "test_action_calibration.py",
            "test_saved_report_gate.py",
            "test_replay_bundle.py",
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
                "-c",
                _pytest_code(checkout),
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
