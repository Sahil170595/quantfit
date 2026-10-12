"""Run the action's real artifact reader; synthetic gates prove propagation only."""

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from test_calibration_binding import calibration_fixture, report_fixture, write_calibration

from quantfit.gate import run_gate

_ACTION = Path(__file__).resolve().parents[1] / ".github/actions/quantfit-gate/action.yml"


def action_shell(name):
    section = _ACTION.read_text(encoding="utf-8").split(f"    - name: {name}", 1)[1]
    block = section.split("      run: |\n", 1)[1].split("\n    - name:", 1)[0]
    return textwrap.dedent(block)


@pytest.mark.parametrize("eps", [("0.1", "assumed"), ("", "assumed")])
def test_action_rejects_operator_calibration_conflict_before_loading(tmp_path, eps):
    bash = shutil.which("bash") if os.name != "nt" else r"C:\Program Files\Git\bin\bash.exe"
    if not bash or not Path(bash).is_file():
        pytest.skip("Bash unavailable; hosted consumer-action qualifies shell execution")
    env = dict(
        os.environ,
        BASELINE="base",
        QUANT="quant",
        TIER="smoke",
        THRESHOLD_PP="",
        EPS_UPPER=eps[0],
        EPS_SOURCE=eps[1],
        CALIBRATION_REPORT="synthetic.json",
    )
    completed = subprocess.run(
        [bash, "-s"],
        input=action_shell("Validate inputs"),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 2


@pytest.mark.parametrize("fault", ["unsupported", "junit-alias", "none"])
def test_action_calibration_preflight_precedes_measurement(tmp_path, fault):
    bash = shutil.which("bash") if os.name != "nt" else r"C:\Program Files\Git\bin\bash.exe"
    if not bash or not Path(bash).is_file():
        pytest.skip("Bash unavailable; hosted consumer-action qualifies shell execution")
    flags = "--baseline --quant --tier --threshold --eps-upper --eps-source --report --out --max-new-tokens --junit"
    if fault != "unsupported":
        flags += " --calibration-report"
    stub = tmp_path / "quantfit"
    stub.write_text(f"#!/usr/bin/env bash\nprintf '%s\\n' '{flags}'\n", encoding="utf-8")
    stub.chmod(0o755)
    calibration = tmp_path / "calibration.json"
    calibration.write_text("{}", encoding="utf-8")
    env = dict(os.environ)
    env.update(
        PATH=os.pathsep.join((str(tmp_path), str(Path(sys.executable).parent), env["PATH"])),
        CALIBRATION_REPORT=str(calibration),
        REPORT=str(tmp_path / "drift.json"),
        GATE_OUT=str(tmp_path / "gate.json"),
        JUNIT=str(calibration if fault == "junit-alias" else tmp_path / "junit.xml"),
    )
    command = action_shell("Preflight — the installed quantfit must expose the gate contract")
    completed = subprocess.run(
        [bash, "-s"], input=command, env=env, capture_output=True, text=True, encoding="utf-8", check=False
    )
    assert completed.returncode == (0 if fault == "none" else 2 if fault == "unsupported" else 1), completed
    assert ("gate flag contract OK" in completed.stdout) == (fault == "none")
    assert calibration.read_text(encoding="utf-8") == "{}"


def action_reader(tmp_path, decision):
    action = _ACTION.read_text(encoding="utf-8")
    section = action.split("    - name: Read the gate artifact", 1)[1]
    code = re.search(r"python - <<'PY'\n(.*?)\n        PY", section, re.DOTALL)
    assert code
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps(decision), encoding="utf-8")
    outputs, summary = tmp_path / "outputs.txt", tmp_path / "summary.md"
    env = dict(os.environ, GATE_OUT=str(gate), REPORT="", EXIT_CODE=str(decision["exit_code"]))
    env.update(GITHUB_OUTPUT=str(outputs), GITHUB_STEP_SUMMARY=str(summary))
    subprocess.run([sys.executable, "-c", textwrap.dedent(code[1])], env=env, check=True, capture_output=True)
    single = dict(line.split("=", 1) for line in outputs.read_text(encoding="utf-8").splitlines() if "=" in line)
    return single, summary.read_text(encoding="utf-8")


def test_prerun_binding_never_reads_as_observed_or_authenticated(tmp_path):
    calibration = write_calibration(tmp_path, calibration_fixture(report_fixture()))
    decision = run_gate("base", "quant", tier="smoke", calibration_report=calibration)
    assert decision["exit_code"] == 5
    outputs, summary = action_reader(tmp_path, decision)
    assert outputs["eps-mode"] == "bound_calibration_report"
    assert outputs["binding-status"] == "scope_validated_actual_run_unobserved"
    assert outputs["actual-run-matched"] == "false"
    assert outputs["assumptions-verified"] == "false"
    assert outputs["human-labels-verified"] == "false"
    assert outputs["calibration-sha256"] == decision["eps"]["source_sha256"]
    assert outputs["calibration-scope-fingerprint"] == decision["eps"]["scope_fingerprint"]
    assert "conditional" in summary and "A1" in summary and "A2" in summary and "A3" in summary
    assert "no research GO" in summary and "sensitivity" in summary


def test_missing_bound_fields_remain_unknown_and_cannot_claim_truth(tmp_path):
    decision = run_gate("base", "quant", threshold=0.001)
    decision["eps"] = {"mode": "bound_calibration_report", "source": "synthetic"}
    outputs, summary = action_reader(tmp_path, decision)
    assert outputs["binding-status"] == "unknown"
    assert outputs["actual-run-matched"] == "unknown"
    assert outputs["assumptions-verified"] == "unknown"
    assert outputs["human-labels-verified"] == "unknown"
    assert "no research GO" in summary


def test_floor_gate_has_no_calibration_binding(tmp_path):
    outputs, summary = action_reader(tmp_path, run_gate("base", "quant", threshold=0.001))
    assert outputs["binding-status"] == "not_applicable"
    assert outputs["actual-run-matched"] == "not_applicable"
    assert outputs["mde-is-floor"] == "true"
    assert "no epsilon was folded in" in summary
