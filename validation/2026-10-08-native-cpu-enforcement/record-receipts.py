"""Observe source blobs, local gates and actual functional records; no model claim."""

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
SOURCE = "b745506c49f017fc17ba6372629835d37fc535d7"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def junit(name):
    cases = ET.parse(OUT / name).getroot().findall(".//testcase")
    result = {"cases": len(cases)}
    for name, node in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped")):
        result[name] = sum(case.find(node) is not None for case in cases)
    result["passed"] = result["cases"] - sum(result[k] for k in ("failures", "errors", "skipped"))
    return result


def main():
    sources = {}
    for path in ("quantfit/cold_run.py", "quantfit/safety/gguf_arm.py", "quantfit/safety/verify.py",
                 "quantfit/cli.py", "quantfit/bundle.py", "tests/test_cold_run.py", "tests/test_gguf_arm.py",
                 "tests/test_bundle.py", "tools/ci_cpu_acceptance.py", "tools/ci_installed.py",
                 ".github/workflows/validate.yml"):
        working = (ROOT / path).read_bytes()
        blob = git("show", f"{SOURCE}:{path}")
        assert working.replace(b"\r\n", b"\n") == blob, path
        sources[path] = {"consumed_working_sha256": hashlib.sha256(working).hexdigest(),
                         "git_blob_sha256": hashlib.sha256(blob).hexdigest(),
                         "working_equals_source_git_blob": working == blob,
                         "crlf_to_lf_bytes_equal_source_git_blob": True}
    versions = {}
    for name in ("quantfit", "pytest", "ruff", "mypy", "scipy", "hypothesis", "huggingface-hub", "psutil",
                 "inspect-ai", "gguf", "torch", "transformers"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not installed"
    functional = json.loads((OUT / "functional-proof.json").read_bytes())
    assert functional["source_head"] == SOURCE
    for path, sha in functional["source_hashes"].items():
        assert sources[path]["consumed_working_sha256"] == sha
    unit, wsl = junit("unit.xml"), junit("wsl.xml")
    assert unit["failures"] == unit["errors"] == wsl["failures"] == wsl["errors"] == 0
    assert wsl["passed"] == 17 and wsl["skipped"] == 0
    audit = json.loads((OUT / "audit.json").read_bytes())
    assert audit["exit_code"] == 0
    payload = {
        "source_commit": SOURCE, "actual_windows_head_now": git("rev-parse", "HEAD").decode().strip(),
        "source_files": sources,
        "suite_provenance": "Final full available unit and all final gates/WSL functional calls executed "
            "with immutable source HEAD b745. Actual consumed working bytes can differ from canonical "
            "Git blobs only by verified legacy CRLF-to-LF equivalence; both SHA256 values are retained. "
            "No implementation changes occurred during these runs.",
        "windows_host": {"python": platform.python_version(), "platform": platform.platform(),
                         "processor": platform.processor(), "ram_total_bytes": psutil.virtual_memory().total},
        "installed_versions": versions, "final_available_unit": unit, "actual_wsl": wsl,
        "focused": junit("focused.xml"), "argv_red": junit("argv-red.xml"),
        "numerical_properties_without_torch": junit("properties.xml"),
        "gates": {"ruff_check": 0, "ruff_exact_format": 0, "mypy_exact_paths": 0, "audit": 0},
        "functional_cli_cases": len(functional["cases"]),
        "functional_fresh_native_children": sum(c["fresh_pid_count"] for c in functional["cases"]),
        "cpu_controls": {"argv": ["--device", "none", "--n-gpu-layers", "0", "--no-op-offload"],
                         "engine": {"offload_device": "none", "n_gpu_layers": 0, "op_offload": False},
                         "actual_cached_binary_help": "supported-flags.json",
                         "model_execution_observed_locally": False},
        "historical_proof": "Original cold-replicate-runner evidence and prior source85a unchanged. "
            "argv-red records the actual missing --device assertion before the CPU repair; it is a "
            "hermetic fake-process/local HTTP fixture, not observed GPU execution.",
        "hosted_installed_cold_consumer": {
            "status": "implemented; not executed locally; hosted qualification pending publication",
            "path": "tools/ci_cpu_acceptance.py", "backend": "gguf",
            "source_model": "HuggingFaceTB/SmolLM2-135M-Instruct",
            "source_revision": "12fd25f77366fa6b3b4b768ec3050bf629380bac",
            "max_new_tokens": 64, "probe_count": 40, "fresh_runs": 3,
            "child_timeout_seconds": 600,
            "source_binding": "Installed measurement module bytes must equal canonical HEAD Git blobs.",
            "negative_results": "Native exits0/3/4 and T0 disagreement remain aggregate evidence; "
                "outer0/3 qualifies execution correctness. Operational2 fails and no partial directory uploads.",
        },
        "parallel_hosted_blocker": "Quant2 PR121 installed wheel/sdist refusal independently reproduced "
            "by root as a one-ULP Windows/Linux derived MDE difference. Isolated Quant2 fix/review/replay "
            "is pending; no unrelated portability change is included here.",
        "limitations": functional["limitations"] + [
            "CPU offload controls are supported/applied in native argv and declared in bound provenance; "
            "local model execution/residency and GPU-capable behavior remain unobserved.",
            "Full Torch numerical/coverage/mutation matrices and real installed hosted cold consumer "
            "remain pending. No model/Hub downloads, dependency installation, public HF creation/upload.",
            "QSRv1 remains unfrozen; integrity/functional checks establish no scientific GO.",
        ],
        "lifecycle": "PRESERVE shared worktree/ref and approved environment for sequential batch; prior "
            "blocked cleanup not retried. Actual fixture children waited/reaped, no live owned group "
            "members observed, transient shims removed; no new worktrees/dependency copies/models/containers.",
    }
    (OUT / "receipts.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"unit": unit, "wsl": wsl, "functional_cases": len(functional["cases"])}))


if __name__ == "__main__":
    main()
