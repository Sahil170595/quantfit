"""Cold orchestration acceptance: synthetic aggregate child reports, never model evidence."""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from quantfit.cli import main

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "validation/2026-10-08-calibration-aware-outputs/drift.json"


def synthetic_children(tmp_path, monkeypatch, mode="regression"):
    """The production runner/CLI/processes are real; only verify_safety is substituted."""
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "sitecustomize.py").write_text(
        """import json, os, sys, time, subprocess
from pathlib import Path
import quantfit.safety.verify as verify
def fake(baseline_model_id, quant_path, **kwargs):
    mode = os.environ["QF_SYNTHETIC_MODE"]
    index = int(Path(kwargs["report_path"]).parent.name.split("-")[-1])
    if mode == "operational":
        raise RuntimeError("private output must not enter receipt")
    if mode == "timeout":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        Path(os.environ["QF_CHILD_PIDS"]).open("a").write(str(child.pid)+"\\n")
        print("secret raw output", flush=True)
        time.sleep(60)
    p = json.loads(Path(os.environ["QF_SYNTHETIC_REPORT"]).read_bytes())
    p["created_utc"] = str(time.time_ns())
    for key, model, dtype in (("baseline", baseline_model_id, "F16"), ("quantized", quant_path, "Q4_K_M")):
        p[key].update(model=model, resolved_dtype=dtype, artifact_sha256="d"*64, revision=None)
        p[key]["engine"] = dict(name="llama.cpp", binary_sha256="e"*64, threads=2, device="cpu", source="QUANTFIT_LLAMACPP (user-provided build; tag not verified by quantfit)")
    if mode == "disagreement" and index == 3:
        p["drift"]["by_zone"]["borderline"]["quant_refused"] += 1
        axis = p["drift"]["over_refusal"]
        axis["quant_refused"] += 1
        axis["overrefusal_regressions"] += 1
        axis["flip_rate_wilson95"] = verify.wilson_interval(axis["overrefusal_regressions"], axis["at_risk"])
    if mode in ("null", "unmeasured"):
        unsafe = 0 if mode == "unmeasured" else 10
        zones = dict(clear_unsafe=dict(n=12, baseline_refused=unsafe, quant_refused=unsafe),
                     clear_safe=dict(n=12, baseline_refused=2, quant_refused=2),
                     borderline=dict(n=16, baseline_refused=2, quant_refused=2))
        p["drift"] = verify.SafetyDrift(40, 12, unsafe, unsafe, 0, 28, 4, 4, 0, zones).to_dict()
    if mode == "cache":
        p["baseline"]["engine"]["baseline_cache"] = dict(served=True, fingerprint="f"*64)
    if mode == "different-binary":
        p["quantized"]["engine"]["binary_sha256"] = "a"*64
    if mode == "different-threads":
        p["quantized"]["engine"]["threads"] = 3
    if mode == "quantized-baseline":
        p["baseline"]["resolved_dtype"] = "Q4_K_M"
    if mode == "raw":
        p["drift"]["completion"] = "never published"
    Path(kwargs["report_path"]).write_text(json.dumps(p), encoding="utf-8")
    class Drift:
        regression_detected = p["drift"]["regression_detected"]
        unmeasurable_axes = p["drift"]["unmeasurable_axes"]
        def summary(self): return "synthetic regression"
    return Drift()
verify.verify_safety = fake
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(shim), str(ROOT), os.environ.get("PYTHONPATH", "")]))
    monkeypatch.setenv("QF_SYNTHETIC_MODE", mode)
    monkeypatch.setenv("QF_SYNTHETIC_REPORT", str(SOURCE))
    monkeypatch.setenv("QF_CHILD_PIDS", str(tmp_path / "pids"))
    return tmp_path / "pids"


def test_cold_run_rejects_non_gguf_and_windows_without_starting(tmp_path, capsys):
    assert main(["cold-run", "--baseline", "base", "--quant", "q", "--out", str(tmp_path / "no"), "--json"]) == 2
    assert not (tmp_path / "no").exists()
    if os.name == "nt":
        assert (
            main(["cold-run", "--baseline", "b.gguf", "--quant", "q.gguf", "--out", str(tmp_path / "no"), "--json"])
            == 2
        )
        assert "POSIX" in capsys.readouterr().out


@pytest.mark.skipif(os.name != "posix", reason="cold-run requires POSIX process-session containment")
@pytest.mark.parametrize(
    "mode,code,t0",
    [
        ("regression", 0, True),
        ("null", 0, True),
        ("unmeasured", 0, True),
        ("disagreement", 3, False),
        ("operational", 2, None),
        ("raw", 2, None),
        ("cache", 2, None),
        ("different-binary", 2, None),
        ("different-threads", 2, None),
        ("quantized-baseline", 2, None),
    ],
)
def test_actual_three_fresh_children_preserve_negative_and_operational(tmp_path, monkeypatch, mode, code, t0):
    from quantfit.cold_run import cold_run

    synthetic_children(tmp_path, monkeypatch, mode)
    result = cold_run("b.gguf", "q.gguf", str(tmp_path / "runs"), timeout_seconds=10)
    assert result["exit_code"] == code
    assert len(result["runs"]) == 3
    assert len({r["pid"] for r in result["runs"]}) == 3
    assert all(r["cleanup"]["direct_child_reaped"] for r in result["runs"])
    assert all(r["cleanup"]["no_live_group_members_observed"] is True for r in result["runs"])
    assert result["independent_execution_verified"] is False
    assert result["scientific_go"] is False
    assert (result["t0"]["protocol_pass"] if result["t0"] else None) is t0
    if mode in {"regression", "disagreement"}:
        assert [r["native_exit_code"] for r in result["runs"]] == [3, 3, 3]
    if mode == "null":
        assert [r["native_exit_code"] for r in result["runs"]] == [0, 0, 0]
    if mode == "unmeasured":
        assert [r["native_exit_code"] for r in result["runs"]] == [4, 4, 4]
        assert all(r["report"]["unmeasurable_axes"] == ["refusal-robustness"] for r in result["runs"])
    assert "private output" not in json.dumps(result)
    assert not list((tmp_path / "runs").rglob("*.log"))


@pytest.mark.skipif(os.name != "posix", reason="cold-run requires POSIX process-session containment")
def test_timeout_kills_actual_owned_descendants_and_discards_output(tmp_path, monkeypatch):
    import psutil

    from quantfit.cold_run import cold_run

    pids = synthetic_children(tmp_path, monkeypatch, "timeout")
    result = cold_run("b.gguf", "q.gguf", str(tmp_path / "runs"), timeout_seconds=1)
    assert result["exit_code"] == 2 and result["t0"] is None
    assert len(result["runs"]) == 3
    assert all(r["status"] == "timeout" and r["cleanup"]["direct_child_reaped"] for r in result["runs"])
    assert all(r["cleanup"]["no_live_group_members_observed"] is True for r in result["runs"])
    for pid in pids.read_text().splitlines():
        assert not psutil.pid_exists(int(pid)) or psutil.Process(int(pid)).status() == psutil.STATUS_ZOMBIE
    assert "secret raw" not in json.dumps(result)
    assert not list((tmp_path / "runs").rglob("*.log"))


@pytest.mark.skipif(os.name != "posix", reason="cold-run requires POSIX process-session containment")
def test_report_substitution_cannot_leave_positive_t0(tmp_path, monkeypatch):
    import quantfit.cold_run as runner

    synthetic_children(tmp_path, monkeypatch)
    original = runner.within_hardware_identical

    def substituted(paths, **kwargs):
        assert not kwargs  # no positive artifact may be written before source comparison
        path = Path(paths[0])
        data = json.loads(path.read_bytes())
        data["created_utc"] = "substituted-after-observation"
        path.write_text(json.dumps(data), encoding="utf-8")
        return original(paths)

    monkeypatch.setattr(runner, "within_hardware_identical", substituted)
    result = runner.cold_run("b.gguf", "q.gguf", str(tmp_path / "runs"), timeout_seconds=10)
    assert result["exit_code"] == 2 and result["status"] == "aggregate_provenance_failure"
    assert result["t0"] is None and not (tmp_path / "runs/t0.json").exists()
    assert (tmp_path / "runs/run-1/report.json").exists()  # valid negative aggregate preserved
    assert result["runs"][0]["source_bytes_changed"] is True


@pytest.mark.skipif(os.name != "posix", reason="cold-run requires POSIX process-session containment")
def test_raw_substitution_after_t0_read_is_removed_before_handback(tmp_path, monkeypatch):
    import quantfit.cold_run as runner

    synthetic_children(tmp_path, monkeypatch)
    original = runner.within_hardware_identical

    def substituted(paths):
        t0 = original(paths)
        path = Path(paths[0])
        data = json.loads(path.read_bytes())
        data["completion"] = "local raw data must never remain"
        path.write_text(json.dumps(data), encoding="utf-8")
        return t0

    monkeypatch.setattr(runner, "within_hardware_identical", substituted)
    result = runner.cold_run("b.gguf", "q.gguf", str(tmp_path / "runs"), timeout_seconds=10)
    assert result["exit_code"] == 2 and result["t0"] is None
    assert not (tmp_path / "runs/run-1/report.json").exists()
    assert not (tmp_path / "runs/t0.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="cold-run requires POSIX process-session containment")
def test_cancellation_closes_child_session_and_keeps_partial_receipt(tmp_path, monkeypatch):
    from quantfit.cold_run import cold_run

    synthetic_children(tmp_path, monkeypatch, "timeout")
    original = subprocess.Popen.wait
    interrupted = False

    def cancel_once(proc, *args, **kwargs):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            time.sleep(0.5)
            raise KeyboardInterrupt
        return original(proc, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "wait", cancel_once)
    with pytest.raises(KeyboardInterrupt):
        cold_run("b.gguf", "q.gguf", str(tmp_path / "runs"), timeout_seconds=10)
    result = json.loads((tmp_path / "runs/cold-run.json").read_bytes())
    assert len(result["runs"]) == 1 and result["t0"] is None
    assert result["runs"][0]["status"] == "cancelled"
    assert result["runs"][0]["cleanup"]["direct_child_reaped"]
    assert result["runs"][0]["cleanup"]["no_live_group_members_observed"]
    assert not list((tmp_path / "runs").rglob("*.log"))


@pytest.mark.skipif(os.name != "posix", reason="cold-run requires POSIX process-session containment")
@pytest.mark.parametrize("fault", ["cancel-after-raw", "cleanup-failure-after-raw"])
def test_terminal_failures_remove_actual_raw_child_report(tmp_path, monkeypatch, fault):
    import quantfit.cold_run as runner

    synthetic_children(tmp_path, monkeypatch, "raw")
    if fault == "cancel-after-raw":
        original = subprocess.Popen.wait
        interrupted = False

        def cancel_once(proc, *args, **kwargs):
            nonlocal interrupted
            code = original(proc, *args, **kwargs)
            if not interrupted:
                interrupted = True
                raise KeyboardInterrupt
            return code

        monkeypatch.setattr(subprocess.Popen, "wait", cancel_once)
        with pytest.raises(KeyboardInterrupt):
            runner.cold_run("b.gguf", "q.gguf", str(tmp_path / "runs"), timeout_seconds=10)
    else:
        original = runner._close_group

        def failed(proc):
            value = original(proc)  # actual process cleanup still happens in this test
            value["no_live_group_members_observed"] = False  # bounded control-flow failure injection
            return value

        monkeypatch.setattr(runner, "_close_group", failed)
        result = runner.cold_run("b.gguf", "q.gguf", str(tmp_path / "runs"), timeout_seconds=10)
        assert result["exit_code"] == 2
    assert not (tmp_path / "runs/run-1/report.json").exists()
    assert not (tmp_path / "runs/t0.json").exists()
    saved = json.loads((tmp_path / "runs/cold-run.json").read_bytes())
    assert saved["t0"] is None and saved["runs"][0]["report"] is None
