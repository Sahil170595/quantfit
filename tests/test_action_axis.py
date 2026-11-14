"""Exercise the reference action with native saved selected-axis decisions."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_action_calibration import action_reader, action_shell

from quantfit.gate import evaluate_report

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("action_axis_fixture", ROOT / "tools/ci_axis_gate.py")
assert SPEC and SPEC.loader
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


def shell(script, **values):
    bash = shutil.which("bash") if os.name != "nt" else r"C:\Program Files\Git\bin\bash.exe"
    if not bash or not Path(bash).is_file():
        pytest.skip("Bash unavailable; hosted consumer-action executes the composite")
    env = dict(
        os.environ,
        BASELINE="",
        QUANT="",
        FROM_REPORT="synthetic.json",
        TIER="",
        THRESHOLD_PP="",
        AXIS_THRESHOLDS="over-refusal=30",
        EPS_UPPER="",
        EPS_SOURCE="",
        CALIBRATION_REPORT="",
        MAX_NEW_TOKENS="",
        HF_TOKEN_INPUT="",
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
    )
    env.update(values)
    return subprocess.run(
        [bash, "-s"], input=script, env=env, capture_output=True, text=True, encoding="utf-8", check=False
    )


def native_decision(tmp_path, **counts):
    source = tmp_path / "report.json"
    FIXTURE.native_report(**counts).to_json(str(source))
    return evaluate_report(str(source), axis_thresholds={"over-refusal": 0.30})


def test_native_saved_axis_positive(tmp_path):
    decision = native_decision(tmp_path, safe_flips=1)
    assert decision["exit_code"] == 3
    assert evaluate_report(str(tmp_path / "report.json"), threshold=0.30)["exit_code"] == 0


def test_action_accepts_selected_axis_without_a_legacy_threshold():
    completed = shell(action_shell("Validate inputs"))
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_action_reader_exposes_native_axis_and_correct_summary(tmp_path):
    decision = native_decision(tmp_path, safe_flips=1)
    outputs, summary = action_reader(tmp_path, decision)
    axes = json.loads(outputs["axis-results-json"])
    assert axes["over-refusal"]["exit_code"] == 3
    assert axes["over-refusal"]["flagged_flips"] == 1
    assert "over-refusal" in summary and "selected" in summary.lower()
    assert "over-refusal (UNGATED)" not in summary
    assert outputs["printed-mde-pp"] == outputs["resolution-proven"] == "unknown"


def test_legacy_default_retains_its_outputs_and_summary(tmp_path):
    completed = shell(action_shell("Validate inputs"), AXIS_THRESHOLDS="", TIER="smoke")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    native_decision(tmp_path)
    decision = evaluate_report(str(tmp_path / "report.json"), threshold=0.30)
    outputs, summary = action_reader(tmp_path, decision)
    assert outputs["axis-results-json"] == "{}"
    assert outputs["printed-mde-pp"] != "unknown"
    assert outputs["resolution-proven"] == "false" and "dangerous axis" in summary


@pytest.mark.parametrize(
    "entries",
    ["over-refusal=30", "refusal-robustness=3e1\nover-refusal=30\n", "over-refusal=30\r\n"],
)
def test_action_admits_native_entries_and_record_separators(entries):
    completed = shell(action_shell("Validate inputs"), AXIS_THRESHOLDS=entries)
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize(
    "values",
    [
        {"TIER": "smoke"},
        {"THRESHOLD_PP": "30"},
        {"AXIS_THRESHOLDS": "over-refusal=30\nover-refusal=15"},
        {"AXIS_THRESHOLDS": "refusal_robustness=30"},
        {"AXIS_THRESHOLDS": "over-refusal=30\n\nrefusal-robustness=30"},
        {"AXIS_THRESHOLDS": "\n"},
        {"AXIS_THRESHOLDS": "over-refusal=" + "1" * 513},
    ],
)
def test_action_refuses_complete_input_shape_before_running(values):
    completed = shell(action_shell("Validate inputs"), **values)
    assert completed.returncode == 2, completed.stdout + completed.stderr


def native_shell(script, **values):
    # Execute the action's shell with the same Python that owns this test process.
    prefix = 'python() { "$QF_TEST_PYTHON" -B "$@"; }; quantfit() { python -m quantfit.cli "$@"; };\n'
    return shell(
        prefix + script,
        QF_TEST_PYTHON=Path(sys.executable).as_posix(),
        PYTHONPATH="",
        HF_HUB_OFFLINE="1",
        **values,
    )


@pytest.mark.parametrize("code", [0, 2, 3, 4, 5])
def test_actual_saved_action_shell_native_json_junit_and_receiving(tmp_path, code):
    work = tmp_path / f"case-{code}"
    helper = ROOT / "tools/ci_action_axis.py"
    prepared = subprocess.run(
        [sys.executable, "-B", str(helper), "prepare", "--root", str(work), "--code", str(code)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    policy = "over-refusal=nan" if code == 2 else "over-refusal=0.01" if code == 5 else "over-refusal=30"
    outputs = work / "outputs.txt"
    summary = work / "summary.md"
    values = {
        "AXIS_THRESHOLDS": policy,
        "FROM_REPORT": (work / "source.json").as_posix(),
        "REPORT": (work / "drift.json").as_posix(),
        "GATE_OUT": (work / "gate.json").as_posix(),
        "JUNIT": (work / "junit.xml").as_posix(),
        "GITHUB_OUTPUT": outputs.as_posix(),
        "GITHUB_STEP_SUMMARY": summary.as_posix(),
    }
    for name in (
        "Validate inputs",
        "Preflight — the installed quantfit must expose the gate contract",
        "Run quantfit gate",
    ):
        completed = native_shell(action_shell(name), **values)
        assert completed.returncode == 0, (name, completed.stdout, completed.stderr)
    completed = native_shell(action_shell("Read the gate artifact"), EXIT_CODE=str(code), **values)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    actual = dict(line.split("=", 1) for line in outputs.read_text(encoding="utf-8").splitlines() if "=" in line)
    checked = subprocess.run(
        [sys.executable, "-B", str(helper), "check", "--root", str(work), "--code", str(code)],
        env=dict(
            os.environ,
            ACTION_OUTCOME="success" if code == 0 else "failure",
            ACTION_CODE=actual["exit-code"],
            ACTION_VERDICT=actual["verdict"],
            ACTION_AXIS_RESULTS=actual["axis-results-json"],
            ACTION_MDE=actual["printed-mde-pp"],
            ACTION_PROVEN=actual["resolution-proven"],
            ACTION_UNGATED=actual["ungated-axis-regressed"],
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    surfaced = native_shell(action_shell("Surface the exit code"), CODE=str(code), **values)
    assert surfaced.returncode == code, surfaced.stdout + surfaced.stderr
    assert "dangerous flips reached" not in summary.read_text(encoding="utf-8")


def test_both_axes_argv_stays_separate_and_has_no_shell_evaluation(tmp_path):
    source = tmp_path / "source.json"
    FIXTURE.native_report().to_json(str(source))
    outputs = tmp_path / "outputs"
    common = {
        "FROM_REPORT": source.as_posix(),
        "REPORT": (tmp_path / "report.json").as_posix(),
        "GATE_OUT": (tmp_path / "gate.json").as_posix(),
        "JUNIT": (tmp_path / "junit.xml").as_posix(),
        "GITHUB_OUTPUT": outputs.as_posix(),
    }
    script = action_shell("Run quantfit gate")
    completed = native_shell(script, AXIS_THRESHOLDS="refusal-robustness=3e1\r\nover-refusal=30\r\n", **common)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    gate = json.loads((tmp_path / "gate.json").read_bytes())
    assert set(gate["axis_results"]) == {"refusal-robustness", "over-refusal"}
    assert gate["policy"]["axis_thresholds"] == {"refusal-robustness": 0.30, "over-refusal": 0.30}
    sentinel = tmp_path / "command-executed"
    completed = native_shell(script, AXIS_THRESHOLDS=f"over-refusal=$(touch {sentinel.as_posix()})", **common)
    assert completed.returncode == 0 and not sentinel.exists()
    assert outputs.read_text(encoding="utf-8").endswith("exit-code=2\n")
    assert json.loads((tmp_path / "gate.json").read_bytes()) == gate


@pytest.mark.parametrize("field,value", [("flagged_flips", True), ("verdict", "PASS\nPRIVATE_SENTINEL")])
def test_axis_output_rejects_bad_types_without_relaying_extra_fields(tmp_path, field, value):
    decision = native_decision(tmp_path, safe_flips=1)
    decision["axis_results"]["over-refusal"][field] = value
    decision["axis_results"]["over-refusal"]["private_path"] = "PRIVATE_SENTINEL"
    outputs, summary = action_reader(tmp_path, decision)
    assert json.loads(outputs["axis-results-json"]) is None
    assert "PRIVATE_SENTINEL" not in json.dumps(outputs) + summary


@pytest.mark.parametrize("value", [float("nan"), 10**1000, 1e308])
def test_unprintable_axis_mde_does_not_expand_or_crash_the_reader(tmp_path, value):
    decision = native_decision(tmp_path)
    decision["axis_results"]["over-refusal"]["resolution"]["printed_mde"] = value
    outputs, _ = action_reader(tmp_path, decision)
    assert outputs["axis-results-json"] == "null"


def test_both_selected_axes_keep_native_conditional_results_and_ignore_private_extras(tmp_path):
    source = tmp_path / "report.json"
    FIXTURE.native_report(safe_flips=1).to_json(str(source))
    decision = evaluate_report(
        str(source),
        axis_thresholds={"refusal-robustness": 0.30, "over-refusal": 0.30},
        eps_upper=0.005,
        eps_source="hypothetical fixture",
    )
    assert decision["exit_code"] == 0 and decision["resolution_is_a_floor"] is False
    for row in decision["axis_results"].values():
        row["extra_private_field"] = "PRIVATE_SENTINEL"
    # A selected decision cannot supply legacy scalar resolution semantics.
    decision["resolution"]["printed_mde"] = 0.1
    decision["resolution"]["verdict"] = "resolved"
    outputs, summary = action_reader(tmp_path, decision)
    axes = json.loads(outputs["axis-results-json"])
    assert set(axes) == {"refusal-robustness", "over-refusal"}
    for axis, row in axes.items():
        native = decision["axis_results"][axis]
        assert row["exit_code"] == native["exit_code"]
        assert row["printed_mde_pp"] == native["resolution"]["printed_mde"] * 100
    assert outputs["mde-is-floor"] == "false"
    assert outputs["printed-mde-pp"] == outputs["resolution-status"] == "unknown"
    assert "PRIVATE_SENTINEL" not in json.dumps(outputs) + summary


def test_upload_opt_out_and_hosted_saved_cases_use_the_existing_job_population():
    yaml = pytest.importorskip("yaml")
    action = yaml.safe_load((ROOT / ".github/actions/quantfit-gate/action.yml").read_text(encoding="utf-8"))
    uploader = next(step for step in action["runs"]["steps"] if step.get("id") == "upload")
    assert uploader["if"] == "always() && inputs.artifact-name != ''"
    assert action["inputs"]["artifact-name"]["default"] == "quantfit-gate"
    workflow = yaml.safe_load((ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8"))
    consumer = workflow["jobs"]["consumer-action"]
    matrix = consumer["strategy"]["matrix"]
    assert matrix["code"] == [0, 2, 3, 4, 5] and len(matrix["include"]) == 4
    axis = next(step for step in consumer["steps"] if step.get("id") == "axis-gate")
    assert axis["uses"] == "./.github/actions/quantfit-gate" and axis["continue-on-error"] is True
    assert axis["with"]["artifact-name"] == axis["with"]["tier"] == ""
    assert "matrix.calibration == 'none'" in axis["if"] and "matrix.replay == 'none'" in axis["if"]
