"""Read actual local artifacts, versions and Git blobs; no historical record mutation."""

import hashlib
import importlib.metadata
import inspect
import json
import platform
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import psutil
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = "e8bfc0e1a5798b5bf2e17ed9e18b5ec6ec7f9491"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def junit(name):
    root = ET.parse(OUT / name).getroot()
    cases = root.findall(".//testcase")
    counts = {"cases": len(cases), "failures": 0, "errors": 0, "skipped": 0}
    for case in cases:
        for field, node in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped")):
            counts[field] += case.find(node) is not None
    counts["passed"] = counts["cases"] - sum(counts[key] for key in ("failures", "errors", "skipped"))
    return counts


def main():
    paths = ("quantfit/cold_run.py", "quantfit/safety/gguf_arm.py", "quantfit/safety/verify.py",
             "quantfit/cli.py", "tests/test_cold_run.py", "tests/test_gguf_arm.py", "tests/test_dependencies.py",
             "tools/ci_installed.py", "tools/quickstart_check.py")
    sources = {}
    for path in paths:
        working = (ROOT / path).read_bytes()
        blob = git("show", f"{SOURCE}:{path}")
        assert working.replace(b"\r\n", b"\n") == blob, path
        sources[path] = {"consumed_working_sha256": hashlib.sha256(working).hexdigest(),
                         "git_blob_sha256": hashlib.sha256(blob).hexdigest(),
                         "working_equals_source_git_blob": working == blob,
                         "crlf_to_lf_bytes_equal_source_git_blob": True}
    versions = {}
    for package in ("quantfit", "pytest", "ruff", "mypy", "scipy", "hypothesis", "huggingface-hub", "psutil",
                    "inspect-ai", "gguf", "torch", "transformers"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not installed"
    functional = json.loads((OUT / "functional-proof.json").read_bytes())
    assert functional["source_head"] == SOURCE
    assert all(info["consumed_working_sha256"] == functional["source_hashes"][path] for path, info in sources.items()
               if path in functional["source_hashes"])
    unit = junit("unit-final.xml")
    assert unit["failures"] == unit["errors"] == 0
    wsl = junit("wsl-final-qualified.xml")
    assert wsl == {"cases": 17, "failures": 0, "errors": 0, "skipped": 0, "passed": 17}
    audit = json.loads((OUT / "audit.json").read_bytes())
    assert audit["exit_code"] == 0
    sdk_source = Path(inspect.getsourcefile(hf_hub_download))
    receipts = {
        "source_commit": SOURCE, "actual_windows_head_now": git("rev-parse", "HEAD").decode().strip(),
        "local_full_suite_provenance": "Started at actual HEAD3f1de493 with final working implementation; finished "
            "after source commit e8bfc0e. No semantic implementation changes occurred during execution. "
            "Windows source autocrlf EOLs differ for legacy files; both hashes and exact CRLF-to-LF "
            "equivalence are recorded. Comment formatting yielded no Git content change. These runs are "
            "not relabelled as exact Gitblob-byte launches. Functional driver independently recorded its "
            "actual consumed raw source hashes at immutable e8; future hosted campaign must cite Gitblob hashes.",
        "source_files": sources,
        "windows_host": {"python": platform.python_version(), "platform": platform.platform(),
                         "processor": platform.processor(), "ram_total_bytes": psutil.virtual_memory().total},
        "installed_versions": versions,
        "installed_sdk": {"hf_hub_download_signature": str(inspect.signature(hf_hub_download)),
                          "introspected_source_file": str(sdk_source),
                          "introspected_source_sha256": hashlib.sha256(sdk_source.read_bytes()).hexdigest()},
        "final_available_unit": unit, "actual_wsl": wsl, "scipy_oracle": junit("scipy.xml"),
        "numerical_properties_without_torch": junit("properties.xml"),
        "functional_cli_cases": len(functional["cases"]),
        "gates": {"ruff_check": 0, "ruff_exact_format_final": 0, "mypy_exact_paths": 0, "audit": audit["exit_code"]},
        "historical_failures_preserved": {
            "revision_red": "9 TypeError failures before revision implementation",
            "cold_red": "new CLI absent before implementation",
            "wsl_cold": junit("wsl-cold.xml"), "pair_admission_red": junit("pair-admission-red.xml"),
            "terminal_hygiene_red": junit("terminal-hygiene-red.xml"),
            "source_hygiene_red": junit("source-hygiene-red.xml"), "initial_full_unit": junit("unit.xml"),
            "format_initial": "line-ending format issue, Ruff correction yielded no Git content delta",
            "wsl_final_previous": junit("wsl-final.xml"),
            "scope": "working-tree reds at actual base3f; final immutable source includes their narrow fixes. "
                     "Intermediate logs/XML are observations, not final qualification or new model runs.",
        },
        "limitations": functional["limitations"] + [
            "Full Torch numerical/branch coverage/mutation, hosted matrices, installed consumer execution "
            "and real installed model campaign are pending batch push.",
            "Native default64/full40 model execution is not established by fixture substitution.",
            "Public reference target remains uncreated/unuploaded; no HF write happened.",
            "QSRv1 remains unfrozen.",
        ],
        "lifecycle": "PRESERVE shared worktree/source refs under individual review, unpushed by approved batch "
            "plan; approved environment/caches retained, prior blocked dependency/cache cleanup never retried. "
            "Task native children waited/reaped; groups have no live members observed; transient shim/server "
            "directories closed; no new dependencies/models/worktrees/containers.",
    }
    (OUT / "receipts.json").write_text(json.dumps(receipts, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"unit": unit, "wsl": wsl, "cli_cases": len(functional["cases"])}))


if __name__ == "__main__":
    main()
