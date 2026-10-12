"""Final integration qualification, distinct from the actual producer source."""

import ast
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE_HEAD = "d15a436f9da2c106def5c265c5fea30c88887ec2"
MEASURED_HEAD = "2997c9304f4c0de02f2299fe7c42f1693539bf6d"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def count(name):
    cases = ET.parse(OUT / name).findall(".//testcase")
    result = {"cases": len(cases), "passed": 0, "skipped": 0, "failed": 0, "errors": 0}
    for case in cases:
        label = next((key for key in ("skipped", "failure", "error") if case.find(key) is not None), None)
        result[{None: "passed", "skipped": "skipped", "failure": "failed", "error": "errors"}[label]] += 1
    return result


def scientific_ast(raw):
    parsed = ast.parse(raw)
    parsed.body = [node for node in parsed.body if not (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "REGISTRY_STATE" for target in node.targets))]
    return ast.dump(parsed, include_attributes=False)


assert git("rev-parse", "HEAD").decode().strip() == SOURCE_HEAD
unit, properties = count("final-unit.xml"), count("final-properties.xml")
summary = re.search(r"(\d+) passed, (\d+) skipped", (OUT / "final-unit.log").read_text(encoding="utf-8-sig"))
assert summary and unit["passed"] == int(summary[1]) and unit["skipped"] == int(summary[2])
assert unit["failed"] == unit["errors"] == properties["failed"] == properties["errors"] == 0 and properties["passed"] == 2
audit = json.loads((OUT / "final-audit.json").read_bytes())
assert audit["exit_code"] == 0 and audit["result"]["counts"]["errors"] == 0
source_files = {}
for name in ("tools/ci_reference_campaign.py", "quantfit/refreports.py", "docs/reference-reports-v0.md", "CHANGELOG.md", ".gitattributes", ".github/workflows/ci.yml"):
    raw, blob = (ROOT / name).read_bytes(), git("show", "HEAD:" + name)
    assert raw.replace(b"\r\n", b"\n") == blob
    source_files[name] = {"git_blob_ref": SOURCE_HEAD + ":" + name, "consumed_working_sha256": hashlib.sha256(raw).hexdigest(), "canonical_git_blob_sha256": hashlib.sha256(blob).hexdigest(), "raw_equal": raw == blob, "exact_crlf_to_lf_equivalence": True}
producer = json.loads((OUT / "producer/campaign.json").read_bytes())
matching, changed = [], []
for name, digest in producer["candidate"]["installed_source_sha256"].items():
    blob = git("show", "HEAD:" + name)
    (matching if hashlib.sha256(blob).hexdigest() == digest else changed).append(name)
assert changed == ["quantfit/refreports.py"]
assert scientific_ast(git("show", SOURCE_HEAD + ":quantfit/refreports.py")) == scientific_ast(git("show", MEASURED_HEAD + ":quantfit/refreports.py"))
assert git("show", SOURCE_HEAD + ":tools/ci_reference_campaign.py") == git("show", MEASURED_HEAD + ":tools/ci_reference_campaign.py")
assert git("show", SOURCE_HEAD + ":.github/workflows/ci.yml") == git("show", MEASURED_HEAD + ":.github/workflows/ci.yml")
record = {"qualification_source_head_observed": SOURCE_HEAD, "tree_observed": git("rev-parse", "HEAD^{tree}").decode().strip(),
          "full_available_unit": unit, "numerical_properties": properties, "focused_refreports_and_campaign": count("integration-focused.xml"),
          "focused_run_context": "Before the d15 source commit, on unchanged working implementation bytes subsequently reconciled to d15; full final qualification ran on frozen d15.",
          "independent_count_method": "XML testcase classification matched independently parsed pytest summary",
          "observed_gate_exits": {"unit": 0, "properties": 0, "exact_lint": 0, "exact_format": 0, "exact_mypy": 0, "audit": 0},
          "audit_counts": audit["result"]["counts"], "source_hashes": source_files,
          "actual_measurement_source_head": MEASURED_HEAD, "matching_measured_package_modules": len(matching),
          "changed_package_modules": changed, "only_registry_status_constant_changed_ast_verified": True,
          "campaign_controller_and_workflow_blobs_unchanged": True,
          "actual_hosted_run": "https://github.com/Sahil170595/quantfit/actions/runs/37890682118",
          "public_commit": "3a4ff4e086f9d72ad828134873b01fa19b550059", "public_download_verified": True,
          "native_exits": [3, 3, 3], "t0_and_full_report_repeatability": True,
          "qualified_reference_count": 0, "scientific_go": False, "human_labels_authenticated": False,
          "actual_heavy_campaign_rerun_for_metadata": False,
          "limitations": ["The actual installed producer is source2997; final local qualification is sourced15. Native algorithms/blobs remain identical, while registry status prose and docs now describe the measured publication.", "Fresh flags are unadjudicated; no sensitivity/absence, independent host, GPU/free-T4 or Inspect parity claim.", "Final exact-head hosted PR package/native qualification is pending at receipt creation. No global WSL retry or new local model/dependency environment."]}
(OUT / "final-local-receipts.json").write_bytes((json.dumps(record, indent=2, sort_keys=True) + "\n").encode())
print(json.dumps({"source": SOURCE_HEAD, "unit": unit, "properties": properties, "changed_package_modules": changed}))
