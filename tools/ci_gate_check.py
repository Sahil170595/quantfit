"""Verify the real consumer action's step outcome, outputs and CLI JUnit."""

import hashlib
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
    if os.environ.get("CALIBRATED") == "1":
        assert code in (0, 5)
        assert os.environ["ACTION_BINDING"] == (
            "actual_run_matched" if code == 0 else "scope_validated_actual_run_unobserved"
        )
        assert os.environ["ACTION_MATCHED"] == ("true" if code == 0 else "false")
        assert decision["eps"]["actual_run_matched"] is (code == 0)
        assert os.environ["ACTION_ASSUMPTIONS"] == os.environ["ACTION_HUMAN"] == "false"
        calibration = Path(os.environ["CALIBRATION_FILE"])
        assert os.environ["ACTION_CALIBRATION_HASH"] == hashlib.sha256(calibration.read_bytes()).hexdigest()
    assert decision["verdict"] == {0: "PASS", 3: "FAIL", 4: "UNMEASURABLE", 5: "UNRESOLVABLE"}[code]
    assert os.environ["ACTION_VERDICT"] == decision["verdict"]
    junit = ET.parse(root / "junit.xml").getroot()
    if code == 3:
        assert junit.findall(".//failure")
    if code == 4:
        assert junit.findall(".//skipped"), "unmeasured axis must carry no-verdict JUnit state"
    if code == 5:
        failures = junit.findall(".//failure")
        assert any(f.get("type") == "ThresholdUnresolvable" for f in failures)
        assert decision["resolution"]["stage"] == "pre_run"
        assert decision["drift"] is None
    if code == 0:
        assert not junit.findall(".//failure")
    if code != 5:
        report = json.loads((root / "drift.json").read_text())
        assert report["schema_version"] == 2
        if os.environ.get("CALIBRATED") != "1":
            assert report["baseline"]["engine"]["name"] == "fixture"
print(f"consumer action faithfully propagated CLI exit {code}: {expected_outcome}; fixtures, not sensitivity")
