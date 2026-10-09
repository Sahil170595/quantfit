"""Final corrected source qualification; do not rewrite initial 1f run records."""

import ast
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def count(name):
    cases = ET.parse(OUT / name).findall(".//testcase")
    value = {"cases": len(cases), "passed": 0, "skipped": 0, "failed": 0, "errors": 0}
    for case in cases:
        label = next((key for key in ("skipped", "failure", "error") if case.find(key) is not None), None)
        value[{None: "passed", "skipped": "skipped", "failure": "failed", "error": "errors"}[label]] += 1
    return value


head = git("rev-parse", "HEAD").decode().strip()
assert head == "72c32123bc4d92dd081401d52f91ec614e06e3a9"
files = {}
for name in ("tools/ci_reference_campaign.py", "tests/test_reference_campaign.py", "docs/reference-campaign-v0.md", ".github/workflows/ci.yml", ".gitattributes"):
    raw, blob = (ROOT / name).read_bytes(), git("show", "HEAD:" + name)
    assert raw.replace(b"\r\n", b"\n") == blob
    files[name] = {"source_git_blob_ref": head + ":" + name, "consumed_working_sha256": hashlib.sha256(raw).hexdigest(),
                   "canonical_git_blob_sha256": hashlib.sha256(blob).hexdigest(), "raw_equal": raw == blob,
                   "exact_crlf_to_lf_equivalence": True}
unit, props = count("corrected-unit.xml"), count("corrected-properties.xml")
summary = re.search(r"(\d+) passed, (\d+) skipped", (OUT / "corrected-unit.log").read_text(encoding="utf-8-sig"))
assert summary and unit["passed"] == int(summary[1]) and unit["skipped"] == int(summary[2])
assert unit["failed"] == unit["errors"] == props["failed"] == props["errors"] == 0 and props["passed"] == 2
audit = json.loads((OUT / "corrected-audit.json").read_bytes())
assert audit["exit_code"] == 0 and audit["result"]["ok"] is True
def analysis(blob):
    return ast.dump(next(node for node in ast.parse(blob).body if isinstance(node, ast.FunctionDef) and node.name == "assess_reports"), include_attributes=False)
same_analysis = analysis(git("show", "1f58bdd:tools/ci_reference_campaign.py")) == analysis(git("show", "HEAD:tools/ci_reference_campaign.py"))
assert same_analysis
record = {"qualification_source_head_observed": head, "tree_observed": git("rev-parse", "HEAD^{tree}").decode().strip(),
          "source_hashes": files, "full_available_unit": unit, "numerical_properties": props,
          "independent_count_method": "XML testcase classification matched independent pytest summary",
          "focused_terminal_with_persistent_storage": count("terminal-persistent-fixed.xml"),
          "terminal_red_actual": count("terminal-red.xml"),
          "observed_gate_exits": {"unit": 0, "properties": 0, "exact_lint": 0, "exact_format": 0, "exact_mypy": 0, "audit": 0},
          "earlier_1f_synthetic_analysis_body_ast_unchanged": same_analysis,
          "historical_1f_receipts_preserved": "local-receipts.json; source1f full1807/32 remains historical, not final domain qualification",
          "terminal_correction": "Remove standalone positive T0/success receipt; revoke assessment and mark original native observations nonqualifying. Failed metadata rewrite withholds earlier copies; exact validated reports/cards and private native originals remain.",
          "raw_models_or_adjudication_used": False, "new_installs_or_worktrees": False,
          "scientific_go": False, "human_labels_authenticated": False,
          "actual_hosted_campaign_and_publication": "PENDING; these corrected local units are not new native/public-byte evidence",
          "limitations": ["Synthetic fault paths include all-writes storage failure; no false successful receipt is claimed if storage cannot write one.",
                          "No native/hosted model, sensitivity, human, T4/crosshardware or independent reproduction proof.",
                          "QSRv1 unfrozen; WSL preserved without retry or repair."]}
(OUT / "corrected-local-receipts.json").write_bytes((json.dumps(record, indent=2, sort_keys=True) + "\n").encode())
print(json.dumps({"source": head, "unit": unit, "properties": props, "focused": record["focused_terminal_with_persistent_storage"]}))
