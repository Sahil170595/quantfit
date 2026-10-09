"""Actual offline CLI exercise over explicitly synthetic aggregate fixture bytes."""

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
RECORD = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else Path(__file__).resolve().parent
SOURCE = ROOT / "validation/2026-10-08-calibration-aware-outputs"
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
commands = []


def write(name, value):
    (RECORD / name).write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def cli(name, arguments, expected=0):
    command = [sys.executable, "-m", "quantfit.cli", *arguments, "--json"]
    completed = subprocess.run(command, cwd=ROOT, env=ENV, capture_output=True, text=True, check=False)
    commands.append({"argv": command, "cwd": str(ROOT), "exit_code": completed.returncode, "expected": expected})
    assert completed.returncode == expected, (completed.stdout, completed.stderr)
    result = json.loads(completed.stdout)
    write(name, result)
    return result["result"]


def main():
    for name in ("drift.json", "calibration.json"):
        (RECORD / name).write_bytes((SOURCE / name).read_bytes())
    report, calibration, resolution, gate = [RECORD / name for name in
                                            ("drift.json", "calibration.json", "resolution.json", "gate.json")]
    cli("resolution-result.json", ["resolution", "--report", str(report), "--calibration-report", str(calibration),
                                   "--out", str(resolution)])
    requested = RECORD / "unobserved-report.json"
    negative = cli("gate-result.json", ["gate", "--baseline", "base", "--quant", "quant", "--threshold", "0.01",
                                       "--calibration-report", str(calibration), "--report", str(requested),
                                       "--out", str(gate)], 5)
    assert negative["drift"] is None and not requested.exists()
    assert negative["eps"]["actual_run_matched"] is False
    original = RECORD / "original-bundle"
    created = cli("create-result.json", ["bundle", "create", "--report", str(report), "--calibration-report",
                                          str(calibration), "--resolution", str(resolution), "--gate", str(gate),
                                          "--out", str(original)])
    relocated = RECORD / "relocated"
    original.rename(relocated)
    verified = cli("verify-result.json", ["bundle", "verify", "--bundle", str(relocated)])
    assert verified["integrity_verified"] and verified["declared_results"] == created["declared_results"]
    assert verified["scientific_claims_verified"] is False
    gate_only = RECORD / "gate-only-original"
    cli("gate-only-create.json", ["bundle", "create", "--gate", str(gate), "--calibration-report", str(calibration),
                                  "--out", str(gate_only)])
    gate_only.rename(RECORD / "gate-only-relocated")
    standalone = cli("gate-only-verify.json", ["bundle", "verify", "--bundle", str(RECORD / "gate-only-relocated")])
    assert "report" not in standalone["declared_results"]
    assert standalone["declared_results"]["gate"]["actual_run_matched"] is False
    tampered = RECORD / "tampered"
    shutil.copytree(relocated, tampered)
    with (tampered / "report.json").open("ab") as stream:
        stream.write(b" ")
    mismatch = cli("tampered-result.json", ["bundle", "verify", "--bundle", str(tampered)], 3)
    assert mismatch["integrity_verified"] is False
    traversal = RECORD / "unsafe-layout"
    shutil.copytree(relocated, traversal)
    manifest = json.loads((traversal / "manifest.json").read_bytes())
    manifest["files"][0]["path"] = "../drift.json"
    (traversal / "manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))
    cli("unsafe-layout-result.json", ["bundle", "verify", "--bundle", str(traversal)], 2)
    # No completion/label text is generated, written or published in this exercise.
    # Empty raw-like shapes still demonstrate that renaming cannot bypass the roles.
    renamed = RECORD / "renamed-raw.json"
    renamed.write_bytes(b'{"cache_schema":1,"entries":[]}\n')
    cli("renamed-refusal.json", ["bundle", "create", "--report", str(renamed), "--out", str(RECORD / "refused")], 2)
    assert not (RECORD / "refused").exists()
    members = []
    for entry in verified["manifest"]["files"]:
        raw = (relocated / entry["path"]).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assert entry["sha256"] == digest
        members.append({"path": str((relocated / entry["path"]).relative_to(RECORD)), "sha256": digest,
                        "size_bytes": len(raw)})
    missing = []
    versions = {}
    for package in ("pytest", "ruff", "mypy", "scipy", "hypothesis", "torch", "transformers", "inspect-ai"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            missing.append(package)
    write("run.json", {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "hardware": {"platform": platform.platform(), "machine": platform.machine(), "processor": platform.processor(),
                     "logical_cpus": os.cpu_count(), "physical_cpus": psutil.cpu_count(logical=False),
                     "ram_bytes": psutil.virtual_memory().total, "python": platform.python_version(), "executable": sys.executable},
        "installed_versions": versions, "missing_optional_packages": missing,
        "synthetic": True, "source_fixture_directory": str(SOURCE), "models_loaded": False,
        "human_labels_authenticated": False, "assumptions_verified": False, "scientific_claims_verified": False,
        "commands": commands, "relocated_member_bytes": members,
        "limitations": ["Fixture-derived aggregates; no generation or human adjudication occurred.",
                        "No sensitivity control, T0, cross-hardware, safety verdict, GO or independent reproduction.",
                        "Hosted full numerical/runtime and installed wheel/sdist gates remain pending.",
                        "Manifest declarations have no authenticated origin or signature."]
    })
    print(f"{len(commands)} actual offline CLI invocations accepted; negative decisions remained negative")


if __name__ == "__main__":
    main()
