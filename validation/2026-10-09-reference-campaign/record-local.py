"""Independently count actual local qualification and bind consumed source bytes."""

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


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def counts(name):
    cases = ET.parse(OUT / name).findall(".//testcase")
    result = {"cases": len(cases), "passed": 0, "skipped": 0, "failed": 0, "errors": 0}
    for case in cases:
        state = next((key for key in ("skipped", "failure", "error") if case.find(key) is not None), None)
        result[{None: "passed", "skipped": "skipped", "failure": "failed", "error": "errors"}[state]] += 1
    return result


head = git("rev-parse", "HEAD").decode().strip()
source = {}
for relative in ("tools/ci_reference_campaign.py", "tests/test_reference_campaign.py", ".github/workflows/ci.yml", "docs/reference-campaign-v0.md", ".gitattributes"):
    working, blob = (ROOT / relative).read_bytes(), git("show", "HEAD:" + relative)
    assert working.replace(b"\r\n", b"\n") == blob
    source[relative] = {"consumed_working_sha256": hashlib.sha256(working).hexdigest(),
                        "canonical_git_blob_sha256": hashlib.sha256(blob).hexdigest(),
                        "git_blob_ref": head + ":" + relative, "raw_equal": working == blob,
                        "exact_crlf_to_lf_equivalence": True}
unit, properties = counts("unit.xml"), counts("properties.xml")
summary = re.search(r"(\d+) passed, (\d+) skipped", (OUT / "unit.log").read_text(encoding="utf-8-sig"))
assert summary and unit["passed"] == int(summary[1]) and unit["skipped"] == int(summary[2])
assert unit["failed"] == unit["errors"] == properties["failed"] == properties["errors"] == 0
assert properties["passed"] == 2
audit = json.loads((OUT / "audit.json").read_bytes())
assert audit["exit_code"] == 0 and audit["result"]["ok"] is True
fixture = json.loads((OUT / "synthetic-run.json").read_bytes())
assert fixture["source_head_observed"] == head and fixture["models_loaded"] == 0
value = {"qualification_source_head_observed": head, "tree_observed": git("rev-parse", "HEAD^{tree}").decode().strip(),
         "source_hashes": source, "python": platform.python_version(), "system": platform.system(),
         "processor": platform.processor(), "ram_total_bytes": psutil.virtual_memory().total,
         "versions": {name: importlib.metadata.version(name) for name in ("pytest", "ruff", "mypy", "scipy", "hypothesis", "psutil", "inspect-ai", "huggingface-hub")},
         "full_available_unit": unit, "numerical_properties": properties,
         "independent_count_method": "XML testcase classification matched independently parsed pytest summary",
         "observed_gate_exits": {"unit": 0, "properties": 0, "exact_lint": 0, "exact_format": 0, "exact_mypy": 0, "audit": 0},
         "historical_failed_test_premise": {"file": "focused.xml", **counts("focused.xml"),
                                           "finding": "Existing T0 already binds quantfit_version; the corrected fixture tests a genuinely omitted engine observation without weakening T0."},
         "scaffold_measurement_status": "Actual hosted candidate measurement and public dataset publication NOT YET RUN",
         "local_models_loaded": 0, "new_installs_or_worktrees": False,
         "scientific_go": False, "human_labels_authenticated": False,
         "limitations": ["Only local unit/SciPy/aggregate fixtures qualified; no new native model, hosted resource or public-byte proof.",
                         "Linux/process and complete Torch numerical/installed candidate qualification remain hosted-only.",
                         "Global WSL resources preserved; no launch/repair attempt."]}
(OUT / "local-receipts.json").write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())
print(json.dumps({"source": head, "unit": unit, "properties": properties}))
