"""Qualify frozen atomic source without rewriting any earlier receipt."""

import ast
import hashlib
import json
import platform
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
EXPECTED = "65005c59604a64bc6dc1ffad6b8aceb710c7aded"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def count(name):
    cases = ET.parse(OUT / name).findall(".//testcase")
    result = {"cases": len(cases), "passed": 0, "skipped": 0, "failed": 0, "errors": 0}
    for case in cases:
        label = next((key for key in ("skipped", "failure", "error") if case.find(key) is not None), None)
        result[{None: "passed", "skipped": "skipped", "failure": "failed", "error": "errors"}[label]] += 1
    return result


def analysis(raw):
    return ast.dump(next(node for node in ast.parse(raw).body if isinstance(node, ast.FunctionDef) and node.name == "assess_reports"), include_attributes=False)


head = git("rev-parse", "HEAD").decode().strip()
assert head == EXPECTED
files = {}
for name in ("tools/ci_reference_campaign.py", "tests/test_reference_campaign.py", "docs/reference-campaign-v0.md", ".github/workflows/ci.yml", ".gitattributes"):
    raw, blob = (ROOT / name).read_bytes(), git("show", "HEAD:" + name)
    assert raw.replace(b"\r\n", b"\n") == blob
    files[name] = {"git_blob_ref": head + ":" + name, "consumed_working_sha256": hashlib.sha256(raw).hexdigest(), "canonical_git_blob_sha256": hashlib.sha256(blob).hexdigest(), "raw_equal": raw == blob, "exact_crlf_to_lf_equivalence": True}
unit, props, focused, red = map(count, ("atomic-unit.xml", "atomic-properties.xml", "atomic-focused-final.xml", "atomic-actual-red.xml"))
summary = re.search(r"(\d+) passed, (\d+) skipped", (OUT / "atomic-unit.log").read_text(encoding="utf-8-sig"))
assert summary and unit["passed"] == int(summary[1]) and unit["skipped"] == int(summary[2])
assert all(value["failed"] == value["errors"] == 0 for value in (unit, props, focused))
assert props["passed"] == 2 and focused["passed"] == 44 and red["failed"] == 2
assert json.loads((OUT / "atomic-audit.json").read_bytes())["exit_code"] == 0
same_analysis = analysis(git("show", "1f58bdd:tools/ci_reference_campaign.py")) == analysis(git("show", "HEAD:tools/ci_reference_campaign.py"))
assert same_analysis
result = {
    "qualification_source_head_observed": head,
    "tree_observed": git("rev-parse", "HEAD^{tree}").decode().strip(),
    "platform": platform.platform(), "python": platform.python_version(),
    "source_hashes": files, "full_available_unit": unit,
    "numerical_properties": props, "focused": focused,
    "independent_count_method": "XML testcase classification matched independently parsed pytest summary",
    "exact_old_source_partial_stream_red": red,
    "actual_red_provenance": "atomic-actual-red.json",
    "observed_gate_exits": {"unit": 0, "properties": 0, "exact_lint": 0, "exact_format": 0, "exact_mypy": 0, "audit": 0},
    "earlier_1f_analysis_body_ast_unchanged": same_analysis,
    "correction": "Same-directory owned temporary files, complete byte write and close before atomic replace; all public buffers use this helper. Handled failures remove temporary files. Explicit upload paths exclude temporary files.",
    "historical_records_unchanged": "1f/72c qualification and domain reds remain historical. Initial fd-wrapper and scenario-shadowing harness failures are preserved separately, not promoted into evidence of the source defect.",
    "actual_hosted_campaign_and_publication": "PENDING",
    "local_models_loaded": 0, "new_installs_or_worktrees": False,
    "scientific_go": False, "human_labels_authenticated": False,
    "limitations": ["Actual-main terminal tests use synthetic weights/runtime/CLI observations and real aggregate primitives/stream writes; no new native model or public-byte proof.", "Full Torch numerical and installed native candidate qualification remain hosted-only.", "Global WSL preserved without launch, repair or cleanup retry. QSRv1 remains unfrozen."]
}
(OUT / "atomic-local-receipts.json").write_bytes((json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
print(json.dumps({"source": head, "unit": unit, "properties": props, "focused": focused, "red": red}))
