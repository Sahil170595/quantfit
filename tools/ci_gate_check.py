"""Verify the real consumer action's step outcome, outputs and CLI JUnit."""

import json
import os
from pathlib import Path
from xml.etree import ElementTree as ET

code = int(os.environ["EXPECTED_CODE"])
expected_outcome = "success" if code == 0 else "failure"
assert os.environ["ACTION_OUTCOME"] == expected_outcome, os.environ["ACTION_OUTCOME"]
assert os.environ["ACTION_CODE"] == str(code), os.environ["ACTION_CODE"]
root = Path(os.environ["CASE_DIR"])
if code == 2:
    assert not (root / "gate.json").exists(), "operational errors must not masquerade as decisions"
else:
    decision = json.loads((root / "gate.json").read_text())
    assert decision["exit_code"] == code
    assert decision["verdict"] == {0: "PASS", 3: "FAIL", 4: "UNMEASURABLE", 5: "UNRESOLVABLE"}[code]
    assert os.environ["ACTION_VERDICT"] == decision["verdict"]
    junit = ET.parse(root / "junit.xml").getroot()
    if code == 3:
        assert junit.findall(".//failure")
    if code in (4, 5):
        assert junit.findall(".//skipped"), "no-answer outcome must carry no-verdict JUnit state"
    if code == 0:
        assert not junit.findall(".//failure")
    if code != 5:
        report = json.loads((root / "drift.json").read_text())
        assert report["schema_version"] == 2
        assert report["baseline"]["engine"]["name"] == "fixture"
print(f"consumer action faithfully propagated CLI exit {code}: {expected_outcome}; fixtures, not sensitivity")
