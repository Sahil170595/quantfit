"""Offline policy replay over synthetic aggregates; no new inference or science proof."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from test_calibrated_modelcard import card_fixture
from test_calibration_binding import report_fixture
from test_gate import _drift

from quantfit.bundle import BundleError, create_bundle, verify_bundle
from quantfit.cli import main
from quantfit.gate import GateError, evaluate_report


def saved(tmp_path, **counts):
    report = report_fixture()
    report = replace(report, drift=_drift(safe_n=28, **counts).to_dict())
    path = tmp_path / "source.json"
    report.to_json(str(path))
    return path


@pytest.fixture(autouse=True)
def no_inference(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline replay attempted inference or a Hub operation")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)


@pytest.mark.parametrize(
    "counts,threshold,code,phase",
    [
        ({}, 0.30, 0, "observed_counts"),
        ({"unsafe_flips": 1}, 0.30, 3, "observed_counts"),
        ({"unsafe_refused": 0}, 0.30, 4, "observed_counts"),
        ({"unsafe_refused": 1}, 0.30, 5, "observed_counts"),
        ({"unsafe_flips": 1}, 0.0001, 5, "policy_preflight"),
        ({"safe_flips": 2}, 0.30, 0, "observed_counts"),
    ],
)
def test_states_and_exact_saved_bytes(tmp_path, counts, threshold, code, phase):
    source = saved(tmp_path, **counts)
    original = source.read_bytes()
    copy, out = tmp_path / "copied.json", tmp_path / "gate.json"
    decision = evaluate_report(str(source), threshold=threshold, report_path_out=str(copy), out_path=str(out))
    assert decision["exit_code"] == code
    assert decision["source_evidence"] == {
        "kind": "saved_report",
        "report_sha256": hashlib.sha256(original).hexdigest(),
        "evaluation_phase": phase,
        "inference_performed": False,
    }
    assert source.read_bytes() == copy.read_bytes() == original
    assert json.loads(out.read_bytes()) == decision
    assert "Offline policy replay" in decision["headline"]
    assert "before loading any model" not in decision["headline"]
    if phase == "policy_preflight":
        assert decision["drift"] is None
        assert decision["resolution"]["stage"] == "pre_run"
    else:
        assert decision["drift"] == json.loads(original)["drift"]
    if counts.get("safe_flips"):
        assert decision["ungated_axis_regressed"] is True
        assert "REGRESSION DETECTED (over-refusal axis)" in decision["headline"]
    bundle = tmp_path / "bundle"
    create_bundle(str(copy), str(bundle), gate_path=str(out))
    assert verify_bundle(str(bundle))["integrity_verified"] is True


def test_bound_precheck_matches_recorded_scope_and_portable_bundle(tmp_path):
    source, calibration = card_fixture(tmp_path)
    gate = tmp_path / "gate.json"
    decision = evaluate_report(str(source), tier="smoke", calibration_report=calibration, out_path=str(gate))
    assert decision["exit_code"] == 5 and decision["drift"] is None
    assert decision["eps"]["actual_run_matched"] is True
    assert decision["eps"]["binding_status"] == "actual_run_matched"
    assert decision["eps"]["measured"] is decision["eps"]["assumptions_verified"] is False
    assert "not freshly observed" in decision["eps"]["statement"]
    bundle = tmp_path / "bundle"
    create_bundle(str(source), str(bundle), calibration_path=calibration, gate_path=str(gate))
    moved = tmp_path / "relocated"
    shutil.move(bundle, moved)
    result = verify_bundle(str(moved))
    assert result["integrity_verified"] is True
    assert result["declared_results"]["gate"]["actual_run_matched"] is True
    with pytest.raises(BundleError):
        create_bundle(None, str(tmp_path / "disconnected"), calibration_path=calibration, gate_path=str(gate))


@pytest.mark.parametrize("change", ["hash", "phase", "boolean", "unknown", "message", "statement"])
def test_replay_claim_corruptions_refused(tmp_path, change):
    source, calibration = card_fixture(tmp_path)
    gate = tmp_path / "gate.json"
    decision = evaluate_report(str(source), tier="smoke", calibration_report=calibration)
    if change == "hash":
        decision["source_evidence"]["report_sha256"] = "a" * 64
    elif change == "phase":
        decision["source_evidence"]["evaluation_phase"] = "observed_counts"
    elif change == "boolean":
        decision["source_evidence"]["inference_performed"] = 0
    elif change == "unknown":
        decision["source_evidence"]["human_verified"] = True
    elif change == "message":
        decision["message"] = "verified pre-deployment safety"
    else:
        decision["eps"]["statement"] = "Human labels authenticated"
    gate.write_text(json.dumps(decision), encoding="utf-8")
    with pytest.raises(BundleError):
        create_bundle(str(source), str(tmp_path / "bundle"), calibration_path=calibration, gate_path=str(gate))


@pytest.mark.parametrize(
    "kind", ["counts", "verdict", "ci", "raw", "duplicate", "nonfinite", "sampled", "regressed", "axes"]
)
def test_bad_saved_aggregate_produces_no_decision(tmp_path, kind):
    source = saved(tmp_path)
    data = json.loads(source.read_bytes())
    if kind == "counts":
        data["drift"]["refusal_robustness"]["at_risk"] = 10
    elif kind == "verdict":
        data["drift"]["verdict"] = "SAFE (forged)"
    elif kind == "ci":
        data["drift"]["refusal_robustness"]["flip_rate_wilson95"] = [0, 0.001]
    elif kind == "raw":
        data["env"]["response"] = "private"
    elif kind == "sampled":
        data["decode"]["do_sample"] = True
    elif kind == "regressed":
        data["drift"]["regression_detected"] = True
    elif kind == "axes":
        data["drift"]["unmeasurable_axes"] = ["refusal-robustness"]
    source.write_text(json.dumps(data), encoding="utf-8")
    if kind == "duplicate":
        source.write_bytes(b'{"schema_version":2,"schema_version":2}')
    if kind == "nonfinite":
        source.write_bytes(b'{"schema_version":NaN}')
    out = tmp_path / "gate.json"
    with pytest.raises(GateError):
        evaluate_report(str(source), tier="smoke", out_path=str(out))
    assert not out.exists()


@pytest.mark.parametrize("output", ["report_path_out", "out_path"])
@pytest.mark.parametrize("link", ["direct", "hard", "symbolic"])
def test_input_output_aliases_refused_without_change(tmp_path, output, link):
    source = saved(tmp_path)
    original = source.read_bytes()
    target = tmp_path / "alias.json"
    if link == "direct":
        target = source
    elif link == "hard":
        os.link(source, target)
    else:
        try:
            target.symlink_to(source)
        except OSError:
            pytest.skip("symbolic link creation unavailable")
    with pytest.raises(GateError):
        evaluate_report(str(source), tier="smoke", **{output: str(target)})
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "extra",
    [
        ["--baseline", "a"],
        ["--quant", "b"],
        ["--max-new-tokens", "64"],
        ["--token", "unused"],
        ["--baseline-cache", "unused"],
    ],
)
def test_cli_refuses_explicit_live_options(tmp_path, capsys, extra):
    source = saved(tmp_path)
    assert main(["gate", "--from-report", str(source), "--tier", "smoke", *extra, "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["result"] is None


def test_cli_junit_uses_recorded_arms_and_precheck_preserves_source(tmp_path, capsys):
    source = saved(tmp_path, unsafe_flips=1)
    copied, junit = tmp_path / "copied.json", tmp_path / "junit.xml"
    assert (
        main(
            [
                "gate",
                "--from-report",
                str(source),
                "--threshold",
                "0.01",
                "--report",
                str(copied),
                "--junit",
                str(junit),
                "--json",
            ]
        )
        == 5
    )
    capsys.readouterr()
    xml = ET.parse(junit)
    assert all(case.get("classname") == "base->quant" for case in xml.findall(".//testcase"))
    assert xml.find(".//failure").get("type") == "ThresholdUnresolvable"
    assert copied.read_bytes() == source.read_bytes()


def test_held_report_bytes_used_after_path_substitution(tmp_path, monkeypatch):
    from quantfit import bundle

    source = saved(tmp_path, safe_flips=2)
    original = source.read_bytes()
    validate = bundle._report

    def substitute(raw):
        report = validate(raw)
        source.write_bytes(b"changed after consumption")
        return report

    monkeypatch.setattr(bundle, "_report", substitute)
    copy = tmp_path / "copy.json"
    decision = evaluate_report(str(source), tier="smoke", report_path_out=str(copy))
    assert decision["source_evidence"]["report_sha256"] == hashlib.sha256(original).hexdigest()
    assert copy.read_bytes() == original and decision["ungated_axis_regressed"] is True


def test_held_calibration_bytes_and_mismatch_refusal(tmp_path, monkeypatch):
    from quantfit.safety import calibration_binding

    source, calibration = card_fixture(tmp_path)
    raw = Path(calibration).read_bytes()
    load = calibration_binding.load_bound_calibration_bytes

    def substitute(data, **kwargs):
        bound = load(data, **kwargs)
        Path(calibration).write_bytes(b"substituted after validation")
        return bound

    monkeypatch.setattr(calibration_binding, "load_bound_calibration_bytes", substitute)
    decision = evaluate_report(str(source), tier="smoke", calibration_report=calibration)
    assert decision["eps"]["source_sha256"] == hashlib.sha256(raw).hexdigest()
    mismatch = json.loads(raw)
    mismatch["binding"]["identity"]["quantized"]["model"] = "another-model"
    Path(calibration).write_text(json.dumps(mismatch), encoding="utf-8")
    with pytest.raises(GateError):
        evaluate_report(str(source), tier="smoke", calibration_report=calibration)


def test_junit_cannot_overwrite_input_or_other_output(tmp_path, capsys):
    source = saved(tmp_path)
    raw = source.read_bytes()
    for target, extra in [(source, []), (tmp_path / "gate.json", ["--out", str(tmp_path / "gate.json")])]:
        assert (
            main(["gate", "--from-report", str(source), "--tier", "smoke", "--junit", str(target), *extra, "--json"])
            == 2
        )
        assert json.loads(capsys.readouterr().out)["result"] is None
    assert source.read_bytes() == raw


def test_replay_action_reader_outputs_source_and_phase(tmp_path):
    from test_action_calibration import action_reader

    source, calibration = card_fixture(tmp_path)
    decision = evaluate_report(str(source), tier="smoke", calibration_report=calibration)
    outputs, summary = action_reader(tmp_path, decision)
    assert outputs["evaluation-phase"] == "policy_preflight"
    assert outputs["inference-performed"] == "false"
    assert outputs["replay-source-sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert outputs["actual-run-matched"] == "true"
    assert "not measurement chronology" in summary


@pytest.mark.parametrize("limit", ["", "64"])
def test_real_action_route_calls_cli_without_live_generation(tmp_path, limit):
    from test_action_calibration import action_shell

    bash = shutil.which("bash") if os.name != "nt" else r"C:\Program Files\Git\bin\bash.exe"
    if not bash or not Path(bash).is_file():
        pytest.skip("Bash unavailable")
    source = saved(tmp_path, safe_flips=2)
    wrapper = tmp_path / "quantfit"
    wrapper.write_text('#!/usr/bin/env bash\nexec "$QF_TEST_PYTHON" -m quantfit.cli "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    out, copy, junit = tmp_path / "gate.json", tmp_path / "copy.json", tmp_path / "junit.xml"
    env = dict(
        os.environ,
        PATH=os.pathsep.join((str(tmp_path), str(Path(sys.executable).parent), os.environ["PATH"])),
        QF_TEST_PYTHON=sys.executable,
        FROM_REPORT=str(source),
        BASELINE="",
        QUANT="",
        TIER="smoke",
        THRESHOLD_PP="",
        EPS_UPPER="",
        EPS_SOURCE="",
        CALIBRATION_REPORT="",
        MAX_NEW_TOKENS=limit,
        HF_TOKEN_INPUT="",
        HF_TOKEN="",
        REPORT=str(copy),
        GATE_OUT=str(out),
        JUNIT=str(junit),
        GITHUB_OUTPUT=str(tmp_path / "outputs"),
    )
    validated = subprocess.run(
        [bash, "-s"], input=action_shell("Validate inputs"), env=env, capture_output=True, text=True, check=False
    )
    assert validated.returncode == (2 if limit else 0), validated.stdout + validated.stderr
    if limit:
        assert not out.exists()
        return
    preflight = subprocess.run(
        [bash, "-s"],
        input=action_shell("Preflight — the installed quantfit must expose the gate contract"),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr
    ran = subprocess.run(
        [bash, "-s"], input=action_shell("Run quantfit gate"), env=env, capture_output=True, text=True, check=False
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert "--baseline" not in ran.stdout and "--max-new-tokens" not in ran.stdout
    decision = json.loads(out.read_bytes())
    assert decision["exit_code"] == 0 and decision["ungated_axis_regressed"] is True
    assert copy.read_bytes() == source.read_bytes()


def test_action_missing_saved_capability_refuses_only_opt_in(tmp_path):
    from test_action_calibration import action_shell

    bash = shutil.which("bash") if os.name != "nt" else r"C:\Program Files\Git\bin\bash.exe"
    if not bash or not Path(bash).is_file():
        pytest.skip("Bash unavailable")
    wrapper = tmp_path / "quantfit"
    wrapper.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' '--baseline --quant --tier --threshold --eps-upper --eps-source --report --out --max-new-tokens --junit'\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    for replay in ("", "source.json"):
        env = dict(
            os.environ,
            PATH=os.pathsep.join((str(tmp_path), str(Path(sys.executable).parent), os.environ["PATH"])),
            FROM_REPORT=replay,
            CALIBRATION_REPORT="",
            REPORT="out.json",
            GATE_OUT="gate.json",
            JUNIT="junit.xml",
        )
        result = subprocess.run(
            [bash, "-s"],
            input=action_shell("Preflight — the installed quantfit must expose the gate contract"),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == (2 if replay else 0), result.stdout + result.stderr
