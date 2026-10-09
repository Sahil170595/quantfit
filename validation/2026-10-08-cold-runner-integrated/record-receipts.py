"""Read the combined candidate's actual local evidence and exact source ancestry."""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = "e139a4708c896a03cbb259ac24571f9594b2c604"
CPU = "b745506c49f017fc17ba6372629835d37fc535d7"
PARENTS = ("425bf92b96b8416caceda80bceb81744eee6243d", "f684ddb0bb848b9e936718d3cd1a88a57c95ab9f")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def junit(path):
    cases = ET.parse(OUT / path).getroot().findall(".//testcase")
    counts = {"cases": len(cases)}
    for key, node in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped")):
        counts[key] = sum(case.find(node) is not None for case in cases)
    counts["passed"] = counts["cases"] - sum(counts[key] for key in ("failures", "errors", "skipped"))
    return counts


def main():
    assert git("show", "-s", "--format=%P", SOURCE).decode().strip().split() == list(PARENTS)
    for parent in PARENTS:
        git("merge-base", "--is-ancestor", parent, SOURCE)
    sources = {}
    for path in ("quantfit/cold_run.py", "quantfit/safety/gguf_arm.py", "quantfit/safety/verify.py",
                 "quantfit/cli.py", "quantfit/bundle.py", "quantfit/safety/calibration_binding.py",
                 "tests/test_cold_run.py", "tests/test_gguf_arm.py", "tests/test_bundle.py",
                 "tools/ci_cpu_acceptance.py", "tools/ci_installed.py", ".github/workflows/validate.yml"):
        working, blob = (ROOT / path).read_bytes(), git("show", f"{SOURCE}:{path}")
        assert working.replace(b"\r\n", b"\n") == blob, path
        sources[path] = {"consumed_working_sha256": hashlib.sha256(working).hexdigest(),
                         "git_blob_sha256": hashlib.sha256(blob).hexdigest(),
                         "working_equals_source_git_blob": working == blob,
                         "crlf_to_lf_bytes_equal_source_git_blob": True}
    unchanged = ("quantfit/cold_run.py", "quantfit/safety/gguf_arm.py", "quantfit/safety/verify.py",
                 "tools/ci_cpu_acceptance.py")
    for path in unchanged:
        assert git("show", f"{CPU}:{path}") == git("show", f"{SOURCE}:{path}")
    assert git("show", f"{PARENTS[1]}:quantfit/safety/calibration_binding.py") == git(
        "show", f"{SOURCE}:quantfit/safety/calibration_binding.py")
    unit, properties = junit("unit.xml"), junit("properties.xml")
    assert unit["failures"] == unit["errors"] == properties["failures"] == properties["errors"] == 0
    audit = json.loads((OUT / "audit.json").read_bytes())
    assert audit["exit_code"] == 0
    final_audit = json.loads((OUT / "audit-final.json").read_bytes())
    assert final_audit["exit_code"] == 0
    versions = {}
    for name in ("quantfit", "pytest", "ruff", "mypy", "scipy", "hypothesis", "psutil", "torch", "transformers"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not installed"
    wsl = junit("wsl-final.xml") if (OUT / "wsl-final.xml").exists() else None
    if wsl:
        assert wsl == {"cases": 17, "failures": 0, "errors": 0, "skipped": 0, "passed": 17}
    failures = []
    for name in ("wsl.log", "wsl-retry.log"):
        data = (OUT / name).read_bytes()
        failures.append({"artifact": name, "sha256": hashlib.sha256(data).hexdigest(),
                         "actual_exit": -1, "test_process_started": False,
                         "decoded_error": data.decode("utf-16-le").strip()})
    receipt = {
        "source_commit": SOURCE, "source_parents": PARENTS,
        "actual_windows_head_now": git("rev-parse", "HEAD").decode().strip(),
        "source_files": sources, "both_reviewed_parents_reachable": True,
        "merge_conflict": "Only .gitattributes; retained all original scoped JSON rules and added this new record.",
        "native_measurement_blobs_unchanged_from_cpu_source": list(unchanged),
        "full_available_unit": unit, "numerical_properties_without_torch": properties,
        "actual_wsl_combined": wsl, "wsl_launch_failures_preserved": failures,
        "combined_posix_gate": "UNRUN locally: two startup sharing violations, zero tests started. "
            "Root explicitly reassigned new combined POSIX cold-suite and real installed64/full40x3 "
            "consumer qualification to actual hosted Linux; pending publication. No more WSL launch "
            "retries, shared service shutdown, repair or disk dismount authorized/performed here.",
        "prior_linux_evidence": "Historical b745 WSL17 is retained with unchanged native blobs; f684 "
            "bundle correction's Linux66pass1skip proves its own typed numeric path. Neither is relabelled "
            "as an actual new combined WSL run.",
        "gates": {"ruff_check": 0, "ruff_exact_format": 0, "mypy_exact_paths": 0, "audit": 0},
        "post_record_audit": {"artifact": "audit-final.json", "actual_exit": final_audit["exit_code"]},
        "ruff_warning": "Shared cache write Access denied warning; exact format command returned0 and104files formatted.",
        "windows_host": {"python": platform.python_version(), "platform": platform.platform(),
                         "processor": platform.processor(), "ram_total_bytes": psutil.virtual_memory().total},
        "installed_versions": versions,
        "provenance": "All combined final tests/gates consume immutable e139 source; actual working raw hashes "
            "and canonical Gitblob hashes are separately recorded, with explicit CRLF-to-LF equivalence. "
            "Prior source/CPU/bundle receipts are not relabelled or modified.",
        "limitations": ["No model execution/download or new package installation in this combined qualification.",
                        "Hosted installed cold/model execution, full Torch/coverage/mutation remain pending.",
                        "No human-label authentication, sensitivity, GPU/crosshardware or independent reproduction/GO.",
                        "QSRv1 remains unfrozen; public HF destination not created/uploaded."],
        "lifecycle": "PRESERVE shared worktree/local ref under sequential review; approved env/prior blocked "
            "cache retained without cleanup retry. Local unit child processes completed; no model/server/task "
            "containers or new worktree/dependency copies. WSL service/disk are shared, not killed/unmounted here.",
    }
    (OUT / "receipts.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"unit": unit, "properties": properties, "actual_wsl_combined": wsl}))


if __name__ == "__main__":
    main()
