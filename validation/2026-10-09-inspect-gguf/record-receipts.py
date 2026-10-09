"""Count final JUnit independently and bind qualification to actual source bytes."""

import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FINAL_SOURCE = "6bf34b4ed80b076bb647ad23bc4b859f063d0ebf"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def counts(name):
    cases = ET.parse(OUT / name).findall(".//testcase")
    value = {"cases": len(cases), "passed": 0, "skipped": 0, "failed": 0, "errors": 0}
    for case in cases:
        kind = next((k for k in ("skipped", "failure", "error") if case.find(k) is not None), None)
        value[{None: "passed", "skipped": "skipped", "failure": "failed", "error": "errors"}[kind]] += 1
    return value


def main():
    observed = git("rev-parse", "HEAD").decode().strip()
    assert observed == FINAL_SOURCE
    sources = {}
    names = [p.decode() for p in git("diff", "--name-only", "2b1045d", "HEAD").splitlines()
             if p.startswith((b"quantfit/", b"tests/", b"tools/", b"pyproject.toml", b".github/"))]
    for name in names:
        working, blob = (ROOT / name).read_bytes(), git("show", "HEAD:" + name)
        assert working.replace(b"\r\n", b"\n") == blob
        sources[name] = {"git_blob_ref": FINAL_SOURCE + ":" + name,
                         "git_blob_oid": git("rev-parse", "HEAD:" + name).decode().strip(),
                         "consumed_working_sha256": sha(working), "canonical_git_blob_sha256": sha(blob),
                         "raw_equal": working == blob, "exact_crlf_to_lf_equivalence": True}
    final = counts("final-unit.xml")
    log = (OUT / "final-unit.log").read_text(encoding="utf-8-sig")
    summary = re.search(r"(\d+) passed, (\d+) skipped", log)
    assert summary and final["passed"] == int(summary[1]) and final["skipped"] == int(summary[2])
    assert final["failed"] == final["errors"] == 0
    audit = json.loads((OUT / "final-audit.json").read_bytes())
    assert audit["exit_code"] == 0 and audit["result"]["ok"] is True
    props = counts("final-properties.xml")
    assert props["passed"] == 2 and props["errors"] == props["failed"] == 0
    current = json.loads((OUT / "qualified-synthetic/synthetic-run.json").read_bytes())
    assert current["source_head_observed"] == FINAL_SOURCE and current["native_requests"] == 0
    cli = json.loads((OUT / "qualified-synthetic/synthetic-cli.json").read_bytes())
    assert cli["actual_exit"] == 3 and cli["envelope"]["result"]["observation_receipt"]["calls"] == [40, 40]
    cpu = json.loads(subprocess.run(["powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json -Compress"],
        capture_output=True, text=True, check=True).stdout)
    receipt = {
        "qualification_source_head_observed": FINAL_SOURCE, "source_tree_observed": git("rev-parse", "HEAD^{tree}").decode().strip(),
        "scope": "actual Windows unit/numerical properties and synthetic public SDK/CLI; installed native CPU proof pending hosted",
        "hardware": {"system": platform.system(), "machine": platform.machine(), "processor": platform.processor(),
                     "cpu_observed_cim": cpu,
                     "ram_total_bytes": psutil.virtual_memory().total, "gpu_execution_observed": False},
        "versions": {n: importlib.metadata.version(n) for n in ("quantfit", "inspect-ai", "httpx", "gguf", "pytest", "ruff", "mypy", "scipy", "hypothesis", "psutil")},
        "python": platform.python_version(), "full_available_unit": final, "numerical_properties": props,
        "independent_count_method": "one XML testcase count/classification; agrees with separate pytest summary regex",
        "source_hashes": sources,
        "gate_exits_observed": {"unit": 0, "properties": 0, "exact_ruff_check": 0, "exact_ruff_format": 0, "exact_mypy": 0, "audit": 0},
        "exact_invocations": [
            "tools/ci/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-09-inspect-gguf/final-unit.xml",
            "tools/ci/.venv/Scripts/python.exe -m pytest tests/test_numerical_properties.py -q -k 'not rtn' --junitxml=validation/2026-10-09-inspect-gguf/final-properties.xml",
            "tools/ci/.venv/Scripts/python.exe -m ruff check quantfit tests tools",
            "tools/ci/.venv/Scripts/python.exe -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture",
            "tools/ci/.venv/Scripts/python.exe -m mypy --strict quantfit/spec.py quantfit/engines/base.py",
            "tools/ci/.venv/Scripts/python.exe -m quantfit.cli audit --json",
            "tools/ci/.venv/Scripts/python.exe validation/2026-10-09-inspect-gguf/run-synthetic.py --out validation/2026-10-09-inspect-gguf/qualified-synthetic",
        ],
        "historical_runs": {"f72_full_available": {"source_head": "f72d1d964ffd22240dde57106cd2fc08d499041a", **counts("unit.xml")},
                            "778_packaging_metadata": {"source_head": "7782f4efba7e6e08ba7f07328a7a6b630a74427f", **counts("metadata-checks.xml")},
                            "1c8_full_failed_old_cap_sentinel": {"source_head": "1c8e71eacdcf6eec103fd1fe7e013a643653d41f", **counts("1c8-final-unit.xml"),
                                                                "scope": "single stale less-than syntax assertion rejected exact269 pin; no production false-pass"},
                            "9f_interrupted_full_suite": {"source_head": "9f936f4324b0348f2afb05ed6d697bb382b16ec3", "completed": False,
                                                           "log": "superseded-9f-unit-interrupted.log", "observed_exit": -1,
                                                           "reason": "stopped owned Python wrapper/direct child77500/52524 after report alias defect demonstrated; no final results claimed"}},
        "fixture_result": {"public_sdk_calls": [40, 40], "judge_fixture_batches": [80], "actual_negative_exit": 3,
                           "native_requests": 0, "models_loaded": 0, "binding_human_labels_verified": False, "bundle_scientific_claims_verified": False},
        "hosted_required_unrun_local": ["actual installed wheel entrypoint discovery", "real GGUF full40 and real80-label judge",
                                       "actual Linux synthetic socket cancellation and process-group cleanup", "Torch numerical RTN/coverage/mutations"],
        "wsl": "UNRUN; prior global sharing-violation resources preserved, no launch/repair/shutdown/dismount attempt",
        "new_dependency_or_model_installs": False, "new_worktrees": False, "raw_captures_retained": False,
        "scientific_go": False, "human_labels_authenticated": False, "assumptions_verified": False,
        "limitations": ["Synthetic files/server facts and judge flags are declared fixtures, not native execution or human labels.",
                        "RAM admission is a conservative estimate, not peak RSS; two resident servers cannot imply Phi4 memory equivalence.",
                        "No sensitivity, T0, native-generation parity, GPU/crosshardware or independent reproduction; QSRv1 remains unfrozen."],
    }
    (OUT / "receipts.json").write_bytes((json.dumps(receipt, indent=2, allow_nan=False) + "\n").encode())
    print(json.dumps({"source": FINAL_SOURCE, "unit": final, "properties": props, "source_files": len(sources)}))


if __name__ == "__main__":
    main()
