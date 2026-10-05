"""Record final source-checkout qualification; no model inference or human labels."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(args):
    result = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"qualification command failed: {args}: {result.stdout}\n{result.stderr}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", required=True)
    parser.add_argument("--inspect-report")
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    junit = folder / "final-coverage.junit.xml"
    junit_root = ET.parse(junit).getroot()
    cases = junit_root.findall(".//testcase")
    counts = {
        "cases": len(cases),
        "failed": sum(case.find("failure") is not None for case in cases),
        "errors": sum(case.find("error") is not None for case in cases),
        "skipped": sum(case.find("skipped") is not None for case in cases),
    }
    counts["passed"] = counts["cases"] - counts["failed"] - counts["errors"] - counts["skipped"]
    suite_totals = {
        key: sum(int(suite.get(key, "0")) for suite in junit_root.findall("testsuite"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    if suite_totals != {
        "tests": counts["cases"],
        "failures": counts["failed"],
        "errors": counts["errors"],
        "skipped": counts["skipped"],
    }:
        raise RuntimeError("JUnit declared totals differ from independent case counts")
    if not cases or counts["failed"] or counts["errors"]:
        raise RuntimeError(f"full suite failed: {counts}")
    coverage = json.loads(Path(args.coverage).read_text())
    gate_stdout = command(["tools/ci_coverage.py", args.coverage])
    files = {name.replace("\\", "/"): value for name, value in coverage["files"].items()}
    audit = json.loads(command(["-m", "quantfit.cli", "audit", "--json"]))
    if audit["result"]["counts"] != {"findings": 0, "errors": 0, "warnings": 0}:
        raise RuntimeError("repository audit has findings")
    (folder / "final-audit-stdout.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    lint = command(["-m", "ruff", "check", "quantfit", "tests", "tools"])
    format_paths = ["quantfit", "tests", *[str(path) for path in sorted((ROOT / "tools").glob("ci_*.py"))]]
    format_paths.append("tools/ci_gate_fixture")
    formatting = command(["-m", "ruff", "format", "--check", *format_paths])
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    prerequisite = subprocess.check_output(["git", "rev-parse", "9713b5"], cwd=ROOT, text=True).strip()
    receipt = {
        "date": "2026-10-05",
        "source_head": source,
        "prerequisite_head": prerequisite,
        "source_files_sha256": {
            path: sha(ROOT / path)
            for path in (
                "quantfit/cli.py",
                "quantfit/reproduce.py",
                "quantfit/safety/calibration_binding.py",
                "quantfit/gate.py",
                "tests/test_t0.py",
                "tests/test_reproduce.py",
                "tests/test_json_envelope.py",
                "tools/ci_coverage.py",
            )
        },
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu": json.loads((folder / "pins.json").read_text())["cpu"],
            "dependencies": {
                name: importlib.metadata.version(name)
                for name in ("pytest", "ruff", "torch", "transformers", "llmcompressor", "inspect-ai", "gguf", "psutil")
            },
            "ci_lock_sha256": sha(ROOT / "tools/ci/uv.lock"),
        },
        "suite": {
            **counts,
            "declared_totals": suite_totals,
            "deselected": 6,
            "junit": junit.name,
            "junit_sha256": sha(junit),
        },
        "coverage": {
            "totals": coverage["totals"],
            "modules": {
                name: files[name]["summary"]
                for name in ("quantfit/safety/mde.py", "quantfit/gate.py", "quantfit/safety/report.py")
            },
            "raw_sha256": sha(args.coverage),
            "gate_stdout": gate_stdout,
            "gate_exit": 0,
        },
        "audit": {"counts": audit["result"]["counts"], "exit": audit["exit_code"]},
        "ruff": {"check_exit": 0, "check_stdout": lint, "format_exit": 0, "format_stdout": formatting},
        "scope": "Synthetic offline source-checkout qualification; no hosted run, independent inference campaign, physical-host verification, or safety conclusion.",
    }
    if args.inspect_report:
        from quantfit.reproduce import _load, _t0_identity

        view = _load(args.inspect_report, "observed-Inspect-compatibility")
        identity, environment, fingerprint = _t0_identity(view)
        receipt["observed_inspect_compatibility"] = {
            "report_artifact": "validation/2026-10-05-inspect-cli/inspect-drift.json",
            "source_sha256": view.sha256,
            "measurement_identity": identity,
            "environment_identity": environment,
            "identity_sha256": fingerprint,
            "accepted": True,
            "independent_execution_verified": False,
            "scope": "Parsing/canonicalization of an existing actual report; no additional model execution or replicate campaign.",
        }
    violations = []
    import re

    def walk(value, location):
        if isinstance(value, dict):
            for key, item in value.items():
                if re.search(r"prompt|completion|response|text|generation", key, re.IGNORECASE):
                    violations.append(f"{location}.{key}")
                walk(item, f"{location}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{location}[{index}]")

    for path in folder.rglob("*.json"):
        walk(json.loads(path.read_text()), path.relative_to(ROOT).as_posix())
    walk(receipt, "final-checks")
    if violations:
        raise RuntimeError(f"forbidden aggregate keys: {violations}")
    receipt["aggregate_key_walk"] = {"json_files": len(list(folder.rglob("*.json"))) + 1, "violations": 0}
    (folder / "final-checks.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"suite": receipt["suite"], "coverage": coverage["totals"], "audit": receipt["audit"]}))


if __name__ == "__main__":
    main()
