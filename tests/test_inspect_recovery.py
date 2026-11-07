"""Completed native Inspect aggregates can be recovered without raw logs or reruns."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import test_inspect_gguf as _gguf_fixtures

gguf_fixture = _gguf_fixtures.fixture


@pytest.fixture
def completed(gguf_fixture, monkeypatch, tmp_path, request):
    import quantfit.inspect_task as task
    from quantfit.safety import report, verify

    _, _, arms, servers, _ = gguf_fixture
    probes = [
        verify.Probe(f"PRIVATE_FIXTURE_{i}", "clear_unsafe" if i < 20 else "clear_safe", "unsafe" if i < 20 else "safe")
        for i in range(40)
    ]
    monkeypatch.setattr(verify, "_load_probes", lambda token, **kwargs: probes)
    source_options = {}
    selected = getattr(request, "param", "default")
    kind, outcome = selected if type(selected) is tuple else (selected, 4)
    if kind == "hub":
        source_options["probe_corpus"] = verify.ProbeCorpus("controlled/rows", "a" * 40, "train")
    elif kind == "local":
        from quantfit.probe_bundle import LocalProbeCorpus, prepare_probe_bundle

        rows, bundle = tmp_path / "private-rows.json", tmp_path / "private-bundle.json"
        rows.write_text(
            json.dumps([{"prompt": p.prompt, "zone": p.zone, "expected": p.expected} for p in probes]), encoding="utf-8"
        )
        prepared = prepare_probe_bundle(str(rows), out_path=str(bundle))
        source_options.update(probe_corpus=LocalProbeCorpus(prepared["sha256"]), probe_bundle_path=str(bundle))
    batches = []

    def judge(outputs, token):
        assert all(server.closed for server in servers)
        batches.append(len(outputs))
        if outcome == 4:
            flags = [True] * len(outputs)
        else:
            baseline = [True] * 20 + [False] * 20
            quantized = baseline if outcome == 0 else [not flag for flag in baseline]
            flags = baseline + quantized
        return flags, 0.1

    monkeypatch.setattr(verify, "_classify_refusals", judge)
    monkeypatch.setattr(
        report,
        "environment_fingerprint",
        lambda: {
            "python": "synthetic",
            "torch": "synthetic-not-used",
            "transformers": "synthetic-not-used",
            "cuda": None,
            "device": "cpu",
        },
    )
    run = task.qsr_eval(
        *(f"quantfit_gguf/{a.ref}" for a in arms),
        max_new_tokens=64,
        log_dir=str(tmp_path / "private-logs"),
        display="none",
        max_samples=1,
        **source_options,
    )
    assert batches == [80] and len(run.outcomes) == 40 and all(s.closed for s in servers)
    return run


def test_existing_completed_native_report_is_valid(completed, tmp_path):
    from quantfit.bundle import _report

    out = tmp_path / "native.json"
    completed.write_report(str(out), *completed.observed_arms, 64)
    report = _report(out.read_bytes())
    assert report.probe_dataset["n_probes"] == 40
    assert report.baseline.engine["generate_calls"] == report.quantized.engine["generate_calls"] == 40


def test_checkpoint_survives_only_final_replace_failure_and_offline_recovers(completed, tmp_path, monkeypatch):
    from quantfit.inspect_recovery import InspectPublicationError, recover_inspect_report

    out, checkpoint, restored = tmp_path / "native.json", tmp_path / "checkpoint.json", tmp_path / "recovered.json"
    out.write_bytes(b"PREVIOUS_REPORT_SENTINEL")
    real_replace = os.replace

    def failed(source, target):
        if Path(target) == out:
            raise OSError("controlled final publication failure")
        return real_replace(source, target)

    monkeypatch.setattr(os, "replace", failed)
    with pytest.raises(InspectPublicationError) as caught:
        completed.write_report(str(out), *completed.observed_arms, 64, recovery_out=str(checkpoint))
    receipt = caught.value.receipt
    assert checkpoint.is_file() and out.read_bytes() == b"PREVIOUS_REPORT_SENTINEL"
    assert receipt["checkpoint"]["sha256"] == hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    assert receipt["n_probes"] == 40
    raw = checkpoint.read_bytes()
    assert b"PRIVATE_FIXTURE_" not in raw and b"synthetic base" not in raw and b"private-logs" not in raw
    monkeypatch.setattr("quantfit.inspect_task.qsr_eval", lambda *a, **kw: pytest.fail("recovery reran Inspect"))
    monkeypatch.setattr(
        "quantfit.safety.verify._classify_refusals", lambda *a, **kw: pytest.fail("recovery reran judge")
    )
    monkeypatch.setattr("quantfit.safety.verify._load_probes", lambda *a, **kw: pytest.fail("recovery reloaded corpus"))
    result = recover_inspect_report(str(checkpoint), receipt["checkpoint"]["sha256"], out_path=str(restored))
    assert (
        result["report"]["sha256"] == hashlib.sha256(restored.read_bytes()).hexdigest() == receipt["report"]["sha256"]
    )


def test_actual_cli_declares_recovery_opt_in(tmp_path):
    out, checkpoint = tmp_path / "report.json", tmp_path / "checkpoint.json"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "quantfit.cli",
            "inspect-run",
            "--recovery-out",
            str(checkpoint),
            "--report",
            str(out),
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1"),
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["exit_code"] == 2 and not result.stderr
    assert not checkpoint.exists() and not out.exists()


@pytest.mark.parametrize("completed", ["default", "hub", "local"], indirect=True)
def test_source_domains_exact_unicode_and_offline_source_deletion(completed, tmp_path, monkeypatch):
    from dataclasses import replace

    from quantfit.inspect_recovery import recover_inspect_report
    from quantfit.safety.report import DriftReport

    out, checkpoint, restored = tmp_path / "native.json", tmp_path / "checkpoint.json", tmp_path / "restored.json"
    arms = tuple(
        replace(arm, engine={**arm.engine, "served_build": "controlled λ 漢字"}) for arm in completed.observed_arms
    )
    completed.write_report(str(out), *arms, 64, recovery_out=str(checkpoint))
    receipt = completed.recovery_receipt
    assert receipt["report_published"] and receipt["n_probes"] == 40
    original = out.read_bytes()
    report = DriftReport.from_json(str(out))
    assert report.baseline.engine["served_build"] == "controlled λ 漢字"
    if completed._bundle_state is not None:
        completed._bundle_state.path.unlink()  # Owned fixture: offline receiver must never reopen its locator.
    for path in completed.protected_report_inputs:
        Path(path).unlink(missing_ok=True)
    monkeypatch.setattr("quantfit.safety.verify._make_report", lambda *a, **kw: pytest.fail("reassembled metadata"))
    monkeypatch.setattr("quantfit.safety.verify._load_probes", lambda *a, **kw: pytest.fail("reread corpus"))
    monkeypatch.setattr("quantfit.safety.verify._classify_refusals", lambda *a, **kw: pytest.fail("reran judge"))
    result = recover_inspect_report(str(checkpoint), receipt["checkpoint"]["sha256"], out_path=str(restored))
    assert restored.read_bytes() == original
    assert result["native_exit_code"] == receipt["native_exit_code"]


@pytest.mark.parametrize("fault", ["extra", "schema", "report_hash", "count", "runtime", "binding", "bare", "unscored"])
def test_tampered_closed_checkpoint_refuses_without_output(completed, tmp_path, fault):
    from quantfit.inspect_recovery import InspectRecoveryError, recover_inspect_report

    checkpoint = tmp_path / "checkpoint.json"
    completed.write_report(str(tmp_path / "report.json"), *completed.observed_arms, 64, recovery_out=str(checkpoint))
    value = json.loads(checkpoint.read_bytes())
    if fault == "extra":
        value["private_logs"] = "PRIVATE_SENTINEL"
    elif fault == "schema":
        value["inspect_recovery_schema"] = 1.0
    elif fault == "report_hash":
        value["report"]["sha256"] = "0" * 64
    elif fault == "count":
        value["observation"]["n_probes"] = 40.0
    elif fault == "runtime":
        value["observation"]["judge_runtime_s"] = False
    elif fault == "binding":
        value["binding"]["identity"]["probe_dataset"]["n_probes"] = 39
    elif fault == "bare":
        value = json.loads(value["report_json"])
    else:
        value = {"status": "success", "samples": []}
    raw = json.dumps(value).encode()
    checkpoint.write_bytes(raw)
    out = tmp_path / "refused.json"
    with pytest.raises(InspectRecoveryError):
        recover_inspect_report(str(checkpoint), hashlib.sha256(raw).hexdigest(), out_path=str(out))
    assert not out.exists()


@pytest.mark.parametrize("fault", ["correction", "checkpoint"])
def test_failure_before_checkpoint_commit_never_replaces_prior_report(completed, tmp_path, monkeypatch, fault):
    import quantfit.inspect_recovery as recovery
    from quantfit.safety import report, verify

    out, checkpoint = tmp_path / "report.json", tmp_path / "checkpoint.json"
    out.write_bytes(b"PREVIOUS_REPORT")
    calls = []
    native = verify._write_report

    def assembled(*args, **kwargs):
        calls.append(True)
        return native(*args, **kwargs)

    def failed(*args, **kwargs):
        raise RuntimeError("controlled failure before completed checkpoint publication")

    monkeypatch.setattr(verify, "_write_report", assembled)
    monkeypatch.setattr(
        report.DriftReport if fault == "correction" else recovery,
        "from_json" if fault == "correction" else "_exclusive",
        failed,
    )
    with pytest.raises(RuntimeError):
        completed.write_report(str(out), *completed.observed_arms, 64, recovery_out=str(checkpoint))
    assert calls == [True] and out.read_bytes() == b"PREVIOUS_REPORT" and not checkpoint.exists()
    assert not list(tmp_path.glob(".quantfit-inspect-report-*"))


def test_repeated_checkpoint_refuses_preserving_old_checkpoint_and_receipt(completed, tmp_path):
    from quantfit.inspect_recovery import InspectRecoveryError

    checkpoint = tmp_path / "checkpoint.json"
    completed.write_report(str(tmp_path / "first.json"), *completed.observed_arms, 64, recovery_out=str(checkpoint))
    before, receipt = checkpoint.read_bytes(), completed.recovery_receipt
    with pytest.raises(InspectRecoveryError):
        completed.write_report(
            str(tmp_path / "second.json"), *completed.observed_arms, 64, recovery_out=str(checkpoint)
        )
    assert checkpoint.read_bytes() == before and completed.recovery_receipt == receipt
    assert not (tmp_path / "second.json").exists()


@pytest.mark.parametrize("completed", [("default", 0), ("default", 3), ("default", 4)], indirect=True)
def test_real_cli_recovers_same_completed_report_and_retains_native_exit(completed, tmp_path):
    checkpoint, original, restored = (
        tmp_path / "checkpoint.json",
        tmp_path / "original.json",
        tmp_path / "restored.json",
    )
    completed.write_report(str(original), *completed.observed_arms, 64, recovery_out=str(checkpoint))
    receipt = completed.recovery_receipt
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "quantfit.cli",
            "inspect-recover",
            "--checkpoint",
            str(checkpoint),
            "--sha256",
            receipt["checkpoint"]["sha256"],
            "--out",
            str(restored),
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1"),
    )
    assert result.returncode == receipt["native_exit_code"], result.stdout + result.stderr
    value = json.loads(result.stdout)
    assert value["result"]["report_published"] and value["result"]["checkpoint"] == receipt["checkpoint"]
    assert restored.read_bytes() == original.read_bytes()


def test_cli_final_failure_emits_pin_receipt_and_admits_roles_before_contact(completed, tmp_path, monkeypatch, capsys):
    from quantfit.cli import main

    out, checkpoint = tmp_path / "report.json", tmp_path / "checkpoint.json"
    out.write_bytes(b"PRESERVE_PRIOR_REPORT")
    seen = []

    def captured(*args, **kwargs):
        seen.append(True)
        return completed

    real_replace = os.replace

    def failed(source, target):
        if Path(target) == out:
            raise OSError("controlled final-only failure")
        return real_replace(source, target)

    monkeypatch.setattr("quantfit.inspect_task.qsr_eval", captured)
    monkeypatch.setattr(os, "replace", failed)
    args = [
        "inspect-run",
        "--baseline",
        completed.arms[0],
        "--quant",
        completed.arms[1],
        "--report",
        str(out),
        "--recovery-out",
        str(checkpoint),
        "--json",
    ]
    assert main(args) == 2
    value = json.loads(capsys.readouterr().out)
    assert (
        value["result"]["recovery_receipt"]["checkpoint"]["sha256"]
        == hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    )
    assert value["result"]["report_published"] is False and seen == [True]
    assert out.read_bytes() == b"PRESERVE_PRIOR_REPORT"
    assert main(args) == 2  # Existing checkpoint refuses before another model call.
    assert json.loads(capsys.readouterr().out)["result"] is None and seen == [True]


@pytest.mark.parametrize("role", ["same_sink", "old_checkpoint", "model", "directory", "parent_file", "logs"])
def test_cli_unsafe_sink_roles_refuse_before_qsr_eval(tmp_path, monkeypatch, capsys, role):
    from quantfit.cli import main

    first, second = tmp_path / "base.gguf", tmp_path / "quant.gguf"
    first.write_bytes(b"PRIVATE_SOURCE_ONE")
    second.write_bytes(b"PRIVATE_SOURCE_TWO")
    out, checkpoint = tmp_path / "report.json", tmp_path / "checkpoint.json"
    extra = []
    if role == "same_sink":
        checkpoint = out
    elif role == "old_checkpoint":
        checkpoint.write_bytes(b"OLD_CHECKPOINT")
    elif role == "model":
        checkpoint = first
    elif role == "directory":
        out = tmp_path
    elif role == "parent_file":
        out = first / "report.json"
    else:
        extra = ["--log-dir", str(tmp_path / "private-logs")]
        checkpoint = tmp_path / "private-logs" / "checkpoint.json"
        checkpoint.parent.mkdir()
    monkeypatch.setattr(
        "quantfit.inspect_task.qsr_eval", lambda *a, **kw: pytest.fail("unsafe paths reached model work")
    )
    assert (
        main(
            [
                "inspect-run",
                "--baseline",
                f"quantfit_gguf/{first}",
                "--quant",
                f"quantfit_gguf/{second}",
                "--report",
                str(out),
                "--recovery-out",
                str(checkpoint),
                *extra,
                "--json",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["result"] is None
    assert first.read_bytes() == b"PRIVATE_SOURCE_ONE" and second.read_bytes() == b"PRIVATE_SOURCE_TWO"


def test_checkpoint_never_projects_capture_log_or_adds_dataclass_fields(completed, tmp_path):
    from dataclasses import fields, replace

    class CaptureTrap:
        def __deepcopy__(self, memo):
            raise AssertionError("copied capture-class log")

    run = replace(completed, log=CaptureTrap())
    assert not any("recovery" in field.name for field in fields(run))
    checkpoint = tmp_path / "checkpoint.json"
    run.write_report(str(tmp_path / "report.json"), *run.observed_arms, 64, recovery_out=str(checkpoint))
    saved = json.loads(checkpoint.read_bytes())
    assert set(saved) == {"inspect_recovery_schema", "report_json", "report", "binding", "observation", "scope"}
    assert "protected_report_inputs" not in checkpoint.read_text(encoding="utf-8")
    assert str(tmp_path / "server") not in checkpoint.read_text(encoding="utf-8")
    external = run.recovery_receipt
    external["checkpoint"]["sha256"] = "0" * 64
    assert run.recovery_receipt["checkpoint"]["sha256"] != "0" * 64


@pytest.mark.parametrize("limit", ["MAX_REPORT_BYTES", "MAX_CHECKPOINT_BYTES"])
def test_profile_bounds_refuse_checkpoint_before_publication(completed, tmp_path, monkeypatch, limit):
    import quantfit.inspect_recovery as recovery

    out, checkpoint = tmp_path / "report.json", tmp_path / "checkpoint.json"
    out.write_bytes(b"PRIOR_REPORT")
    monkeypatch.setattr(recovery, limit, 1)
    with pytest.raises(recovery.InspectRecoveryError):
        completed.write_report(str(out), *completed.observed_arms, 64, recovery_out=str(checkpoint))
    assert out.read_bytes() == b"PRIOR_REPORT" and not checkpoint.exists()


@pytest.mark.parametrize("role", ["checkpoint", "existing", "parent_file", "hardlinked_input", "wrong_pin", "bad_pin"])
def test_offline_receive_pin_and_exclusive_roles(completed, tmp_path, monkeypatch, role):
    import quantfit.inspect_recovery as recovery

    checkpoint = tmp_path / "checkpoint.json"
    completed.write_report(str(tmp_path / "report.json"), *completed.observed_arms, 64, recovery_out=str(checkpoint))
    raw, pin, out = (
        checkpoint.read_bytes(),
        completed.recovery_receipt["checkpoint"]["sha256"],
        tmp_path / "restored.json",
    )
    if role == "checkpoint":
        out = checkpoint
    elif role == "existing":
        out.write_bytes(b"PRIOR_OUTPUT")
    elif role == "parent_file":
        out = checkpoint / "report.json"
    elif role == "hardlinked_input":
        os.link(checkpoint, tmp_path / "hardlink.json")
    elif role == "wrong_pin":
        pin = "0" * 64
        monkeypatch.setattr(recovery, "_receive", lambda *a: pytest.fail("parsed unpinned checkpoint"))
    else:
        pin = "0" * 63
        monkeypatch.setattr(recovery, "hold", lambda *a: pytest.fail("read with malformed expected pin"))
    with pytest.raises(recovery.InspectRecoveryError):
        recovery.recover_inspect_report(str(checkpoint), pin, out_path=str(out))
    assert checkpoint.read_bytes() == raw
    if role == "existing":
        assert out.read_bytes() == b"PRIOR_OUTPUT"


@pytest.mark.parametrize("fault", ["identity", "decode", "runtime"])
def test_copied_declarations_require_exact_identity_not_statistical_tolerance(completed, tmp_path, fault):
    from quantfit.bundle import _report
    from quantfit.inspect_recovery import InspectRecoveryError, recover_inspect_report
    from quantfit.safety.calibration_binding import identity_fingerprint, measurement_identity

    checkpoint = tmp_path / "checkpoint.json"
    completed.write_report(str(tmp_path / "report.json"), *completed.observed_arms, 64, recovery_out=str(checkpoint))
    value = json.loads(checkpoint.read_bytes())
    if fault == "identity":
        value["binding"]["identity"]["decode"]["temperature"] = 1e-13
    elif fault == "runtime":
        value["observation"]["baseline_runtime_s"] += 1e-13
    else:
        report = json.loads(value["report_json"])
        report["decode"]["temperature"] = 1e-13
        raw_report = json.dumps(report, ensure_ascii=False).encode("utf-8")
        identity = measurement_identity(_report(raw_report))
        value.update(
            report_json=raw_report.decode("utf-8"),
            report={"sha256": hashlib.sha256(raw_report).hexdigest(), "size_bytes": len(raw_report)},
            binding={"identity": identity, "fingerprint": identity_fingerprint(identity)},
        )
    raw = json.dumps(value).encode("utf-8")
    checkpoint.write_bytes(raw)
    with pytest.raises(InspectRecoveryError):
        recover_inspect_report(
            str(checkpoint), hashlib.sha256(raw).hexdigest(), out_path=str(tmp_path / "refused.json")
        )


@pytest.mark.parametrize("mode", ["checkpoint", "recover"])
def test_unattested_stage_retains_explicit_state_and_closes_descriptor(completed, tmp_path, monkeypatch, mode):
    import quantfit.inspect_recovery as recovery

    original, checkpoint, out = tmp_path / "original.json", tmp_path / "checkpoint.json", tmp_path / "restored.json"
    if mode == "recover":
        completed.write_report(str(original), *completed.observed_arms, 64, recovery_out=str(checkpoint))
    real_temp, real_fstat = recovery.tempfile.mkstemp, os.fstat
    acquired = []

    def temporary(*args, **kwargs):
        fd, path = real_temp(*args, **kwargs)
        if kwargs.get("prefix") == ".quantfit-recovery-":
            acquired.append((fd, Path(path)))
        return fd, path

    def failed(fd):
        if acquired and fd == acquired[-1][0]:
            raise OSError("controlled stage identity failure")
        return real_fstat(fd)

    monkeypatch.setattr(recovery.tempfile, "mkstemp", temporary)
    monkeypatch.setattr(os, "fstat", failed)
    try:
        with pytest.raises(recovery.InspectRecoveryError, match="^recovery_stage_preserved$"):
            if mode == "recover":
                recovery.recover_inspect_report(
                    str(checkpoint), hashlib.sha256(checkpoint.read_bytes()).hexdigest(), out_path=str(out)
                )
            else:
                completed.write_report(str(original), *completed.observed_arms, 64, recovery_out=str(checkpoint))
        assert len(acquired) == 1 and acquired[0][1].is_file()
        with pytest.raises(OSError):
            real_fstat(acquired[0][0])
    finally:
        if acquired:
            try:
                os.close(acquired[0][0])
            except OSError:
                pass


def test_changed_assembled_temp_after_checkpoint_never_publishes_unbound_bytes(completed, tmp_path, monkeypatch):
    import quantfit.inspect_recovery as recovery

    out, checkpoint = tmp_path / "report.json", tmp_path / "checkpoint.json"
    out.write_bytes(b"PRIOR_REPORT")
    native = recovery._checkpoint_report

    def changed(raw, path):
        value = native(raw, path)
        temporary = list(tmp_path.glob(".quantfit-inspect-report-*"))
        assert len(temporary) == 1
        temporary[0].write_bytes(b"UNVALIDATED_TEMP_MUTATION")
        return value

    monkeypatch.setattr(recovery, "_checkpoint_report", changed)
    with pytest.raises(recovery.InspectPublicationError) as caught:
        completed.write_report(str(out), *completed.observed_arms, 64, recovery_out=str(checkpoint))
    assert out.read_bytes() == b"PRIOR_REPORT"
    assert caught.value.receipt["checkpoint"]["sha256"] == hashlib.sha256(checkpoint.read_bytes()).hexdigest()


def test_fresh_cli_offline_recovery_traps_network_model_judge_and_reassembly(completed, tmp_path):
    checkpoint, original, restored = (
        tmp_path / "checkpoint.json",
        tmp_path / "original.json",
        tmp_path / "restored.json",
    )
    completed.write_report(str(original), *completed.observed_arms, 64, recovery_out=str(checkpoint))
    receipt = completed.recovery_receipt
    args = [
        "inspect-recover",
        "--checkpoint",
        str(checkpoint),
        "--sha256",
        receipt["checkpoint"]["sha256"],
        "--out",
        str(restored),
        "--json",
    ]
    code = """
import runpy, socket, sys
def forbidden(*args, **kwargs):
    raise AssertionError('offline recovery attempted model/network/judge/reassembly')
socket.create_connection = forbidden
socket.socket.connect = forbidden
import quantfit.inspect_task as task
import quantfit.safety.verify as verify
task.qsr_eval = forbidden
verify._make_report = verify._write_report = verify._load_probes = verify._classify_refusals = forbidden
sys.argv = ['quantfit', *sys.argv[1:]]
runpy.run_module('quantfit.cli', run_name='__main__')
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", code, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1"),
    )
    assert result.returncode == receipt["native_exit_code"], result.stdout + result.stderr
    assert json.loads(result.stdout)["result"]["report"] == receipt["report"]
    assert restored.read_bytes() == original.read_bytes()


def test_final_replace_and_temp_cleanup_failure_still_returns_saved_pin(completed, tmp_path, monkeypatch):
    import quantfit.inspect_recovery as recovery

    out, checkpoint = tmp_path / "report.json", tmp_path / "checkpoint.json"
    out.write_bytes(b"PRIOR_REPORT")
    real_replace, real_unlink = os.replace, Path.unlink

    def failed_replace(source, target):
        if Path(target) == out:
            raise OSError("controlled final replace failure")
        return real_replace(source, target)

    def failed_cleanup(path, *args, **kwargs):
        if path.name.startswith(".quantfit-inspect-report-"):
            raise OSError("controlled retained temp after final error")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "replace", failed_replace)
    monkeypatch.setattr(Path, "unlink", failed_cleanup)
    with pytest.raises(recovery.InspectPublicationError) as caught:
        completed.write_report(str(out), *completed.observed_arms, 64, recovery_out=str(checkpoint))
    assert caught.value.receipt["checkpoint"]["sha256"] == hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    assert caught.value.receipt["report_published"] is False
    assert caught.value.receipt["temporary_cleanup"] == "preserved"
    assert out.read_bytes() == b"PRIOR_REPORT" and len(list(tmp_path.glob(".quantfit-inspect-report-*"))) == 1


@pytest.mark.parametrize("local_source", [False, True])
def test_opted_known_model_symlink_roles_preserve_execution_ref_and_alias_protection(
    tmp_path, monkeypatch, capsys, local_source
):
    from quantfit.cli import main
    from quantfit.inspect_recovery import InspectRecoveryError, admit_recovery_paths

    model, alias, quant = tmp_path / "base.gguf", tmp_path / "alias.gguf", tmp_path / "quant.gguf"
    model.write_bytes(b"controlled role fixture only; not model inference")
    quant.write_bytes(b"controlled second role")
    try:
        alias.symlink_to(model)
    except OSError:
        pytest.skip("Symlink privilege unavailable; hosted Linux exercises valid native source refs")
    report, checkpoint = tmp_path / "report.json", tmp_path / "checkpoint.json"
    admit_recovery_paths(str(report), str(checkpoint), (str(alias),))
    with pytest.raises(InspectRecoveryError):
        admit_recovery_paths(str(model), str(checkpoint), (str(alias),))
    extra = []
    if local_source:
        from quantfit.probe_bundle import prepare_probe_bundle

        rows, bundle = tmp_path / "private-rows.json", tmp_path / "private-bundle.json"
        rows.write_text(
            json.dumps([{"prompt": "controlled role-only row", "zone": "clear_safe", "expected": "safe"}]),
            encoding="utf-8",
        )
        prepared = prepare_probe_bundle(str(rows), out_path=str(bundle))
        extra = ["--probe-bundle", str(bundle), "--probe-sha256", prepared["sha256"]]
    seen = []

    def reached(baseline, quantized, **kwargs):
        seen.append((baseline, quantized))
        raise RuntimeError("controlled after valid role admission")

    monkeypatch.setattr("quantfit.inspect_task.qsr_eval", reached)
    assert (
        main(
            [
                "inspect-run",
                "--baseline",
                f"quantfit_gguf/{alias}",
                "--quant",
                f"quantfit_gguf/{quant}",
                "--report",
                str(report),
                "--recovery-out",
                str(checkpoint),
                *extra,
                "--json",
            ]
        )
        == 2
    )
    assert seen == [(f"quantfit_gguf/{alias}", f"quantfit_gguf/{quant}")]
    assert "after valid role" in json.loads(capsys.readouterr().out)["error"]["message"]
    assert not report.exists() and not checkpoint.exists()
