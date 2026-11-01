"""The same complete native acceptance runs against installed distributions."""

import importlib.util
from pathlib import Path


def test_complete_two_judge_native_acceptance(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("installed_judges_consumer", root / "tools/ci_calibration_judges.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    result = helper.run(root, tmp_path)
    assert result["positive_cases"] == len(result["cases"]) == 16
    assert result["adverse_cases"] == len(result["adverse"]) == 32
    assert result["os_cli_utf8_lf_parity"] is True
