"""Optional calibration context never rewrites the native screen verdict."""

import json
import sys
from types import SimpleNamespace

import pytest

from quantfit.cli import main


@pytest.mark.parametrize("code", [0, 3, 4])
@pytest.mark.parametrize("calibrations", [False, True])
def test_screen_summary_calibrations_are_optional_and_native_exit_is_unchanged(monkeypatch, capsys, code, calibrations):
    calls = []
    result = {"exit_code": code, "outcome": "original native observation"}
    if calibrations:
        result["conditional_resolution"] = {"coverage": {"n_targets": 2, "n_analyzed": 0, "complete": False}}

    def summarize(targets, reports, **kwargs):
        calls.append((targets, reports, kwargs))
        return result

    monkeypatch.setitem(sys.modules, "quantfit.saved_screen", SimpleNamespace(summarize_screen=summarize))
    args = [
        "screen-summary",
        "--targets",
        "targets.json",
        "--reports-dir",
        "reports",
        "--out",
        "summary.json",
        "--junit",
        "summary.xml",
    ]
    expected = {"out_path": "summary.json", "junit_path": "summary.xml"}
    if calibrations:
        args += ["--calibrations-dir", "calibrations"]
        expected["calibrations_dir"] = "calibrations"
    assert main([*args, "--json"]) == code
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert document["command"] == "screen-summary" and document["exit_code"] == code
    assert document["result"] == result and captured.err == ""
    assert calls == [("targets.json", "reports", expected)]
