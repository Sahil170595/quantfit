"""Resume admits a complete held native population before execution or mutation."""

import hashlib
import json
import os
from pathlib import Path

import pytest
from test_saved_screen import corpus

from quantfit.safety.verify import DECODE_CHAT_TEMPLATE_POLICY
from quantfit.screen import CONDITIONALITY_LABEL, RESOLUTION_LABEL, ScreenError, run_screen


def native_corpus(tmp_path, entries, **kwargs):
    manifest, reports = corpus(tmp_path, entries, **kwargs)
    # Explicit producer policy, rather than relying on a historical prototype.
    for path in reports.glob("*.json"):
        payload = json.loads(path.read_bytes())
        payload["decode"]["chat_template"] = DECODE_CHAT_TEMPLATE_POLICY
        path.write_text(json.dumps(payload, indent=3) + "\n", encoding="utf-8")
    return manifest, reports


def snapshot(root):
    return {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}


def trap(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        pytest.fail("resume contacted the model")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    return calls


@pytest.mark.parametrize(
    "mutation",
    ["truncated", "private", "duplicate_json", "target", "judge", "population", "decode", "cap", "arithmetic"],
)
def test_last_invalid_present_refuses_before_first_missing_contact_or_mutation(tmp_path, monkeypatch, mutation):
    manifest, reports = native_corpus(
        tmp_path, [("missing", "gguf", 0, 0, None), ("last", "gguf", 0, 0, None)], missing=("missing",)
    )
    path = reports / "last.json"
    payload = json.loads(path.read_bytes())
    if mutation == "truncated":
        path.write_bytes(b'{"PRIVATE provider text"')
    elif mutation == "duplicate_json":
        path.write_bytes(b'{"schema_version":2,"schema_version":2}')
    else:
        if mutation == "private":
            payload["completions"] = ["PRIVATE provider text"]
        elif mutation == "target":
            payload["quantized"]["model"] = "PRIVATE foreign target"
        elif mutation == "judge":
            payload["judge"]["revision"] = "a" * 40
        elif mutation == "population":
            payload["probe_dataset"]["n_probes"] += 1
        elif mutation == "decode":
            payload["decode"]["chat_template"] = "raw prompt always"
        elif mutation == "cap":
            payload["decode"]["max_new_tokens"] = 65
        elif mutation == "arithmetic":
            payload["drift"]["regression_detected"] = True
        path.write_text(json.dumps(payload), encoding="utf-8")
    (reports / "screen-summary.json").write_bytes(b'{"old_summary": true}')
    original = snapshot(reports)
    capture = tmp_path / "new-captures"
    calls = trap(monkeypatch)
    with pytest.raises(ScreenError) as error:
        run_screen(str(manifest), str(reports), resume=True, capture_dir=str(capture))
    assert "PRIVATE" not in str(error.value)
    assert not calls and snapshot(reports) == original and not capture.exists()


@pytest.mark.parametrize("cap", [True, False, 0, -1, 1.5, "64", None])
def test_invalid_requested_cap_refuses_before_output_creation(tmp_path, monkeypatch, cap):
    manifest, reports = native_corpus(tmp_path, [("g0", "gguf", 0, 0, None)], missing=("g0",))
    reports.rmdir()
    trap(monkeypatch)
    with pytest.raises(ScreenError):
        run_screen(str(manifest), str(reports), resume=True, max_new_tokens=cap)
    assert not reports.exists()


def test_skips_flagged_and_unmeasured_with_original_receipts_and_unverified_control(tmp_path, monkeypatch):
    manifest, reports = native_corpus(tmp_path, [("flag", "gguf", 1, 0, "over"), ("zero", "gguf", 0, 0, "danger")])
    original = snapshot(reports)
    (reports / "screen-summary.json").write_text(
        json.dumps({"rows": [{"status": "no_regression", "human_verified": True}], "control": "pass"}),
        encoding="utf-8",
    )
    trap(monkeypatch)
    result = run_screen(str(manifest), str(reports), resume=True)
    assert [row["status"] for row in result["rows"]] == ["regression", "unmeasurable"]
    assert all(row["human_verified"] is None for row in result["rows"])
    axes = result["by_stratum"]["gguf"]
    assert axes["refusal_robustness"]["n_measured"] == 1
    assert axes["refusal_robustness"]["n_regressed"] == 1
    for axis in ("refusal_robustness", "over_refusal"):
        assert axes[axis]["conditionality"] == CONDITIONALITY_LABEL
        assert axes[axis]["resolution_caveat"] == RESOLUTION_LABEL
    receipt = result["resume_receipt"]
    assert receipt["kind"] == "quantfit.screen-resume" and receipt["schema_version"] == 1
    assert receipt["n_skipped"] == 2 and receipt["n_executed"] == 0
    assert receipt["control_evidence_verified"] is False
    assert receipt["manifest"] == {
        "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "size_bytes": manifest.stat().st_size,
    }
    for row in receipt["targets"]:
        raw = original[row["member"]]
        assert row["action"] == "skipped" and row["sha256"] == hashlib.sha256(raw).hexdigest()
        assert row["size_bytes"] == len(raw) and (reports / row["member"]).read_bytes() == raw


@pytest.mark.parametrize("kind", ["unknown", "directory", "summary_alias", "capture_alias", "manifest_alias"])
def test_closed_inventory_and_output_aliases_refuse_before_contact(tmp_path, monkeypatch, kind):
    manifest, reports = native_corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    capture = None
    if kind == "unknown":
        (reports / "foreign.capture.jsonl").write_bytes(b"PRIVATE")
    elif kind == "directory":
        (reports / "g0.json").unlink()
        (reports / "g0.json").mkdir()
    elif kind == "summary_alias":
        os.link(reports / "g0.json", reports / "screen-summary.json")
    elif kind == "capture_alias":
        capture = tmp_path / "captures"
        capture.mkdir()
        os.link(manifest, capture / "g0.capture.jsonl")
    else:
        # Existing output summary may not alias the held manifest.
        os.link(manifest, reports / "screen-summary.json")
    original = snapshot(reports)
    trap(monkeypatch)
    with pytest.raises(ScreenError):
        run_screen(str(manifest), str(reports), resume=True, capture_dir=str(capture) if capture else None)
    assert snapshot(reports) == original


def test_missing_only_executes_and_uses_fresh_native_bytes_not_returned_drift(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    _, native = native_corpus(source, [("g0", "gguf", 1, 0, None), ("g1", "gguf", 0, 0, None)])
    fresh = (native / "g0.json").read_bytes()
    manifest, reports = native_corpus(
        tmp_path, [("g0", "gguf", 1, 0, None), ("g1", "gguf", 0, 0, None)], missing=("g0",)
    )
    skipped = (reports / "g1.json").read_bytes()
    calls = []

    def execute(base, quant, **kwargs):
        from test_screen import _clean

        calls.append(quant)
        Path(kwargs["report_path"]).write_bytes(fresh)
        return _clean()  # Deliberate disagreement: only the original native artifact is evidence.

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", execute)
    result = run_screen(str(manifest), str(reports), resume=True)
    assert len(calls) == 1 and calls[0].endswith("g0-quant.gguf")
    assert [row["status"] for row in result["rows"]] == ["regression", "no_regression"]
    assert (reports / "g0.json").read_bytes() == fresh and (reports / "g1.json").read_bytes() == skipped
    receipt = result["resume_receipt"]
    assert receipt["initial_missing"] == ["g0"] and receipt["n_executed"] == 1 and receipt["n_skipped"] == 1
    assert receipt["targets"][0]["sha256"] == hashlib.sha256(fresh).hexdigest()


@pytest.mark.parametrize("written", [None, b'{"drift":{}}'])
def test_success_without_valid_native_file_refuses_without_fabrication(tmp_path, monkeypatch, written):
    manifest, reports = native_corpus(tmp_path, [("g0", "gguf", 0, 0, None)], missing=("g0",))
    (reports / "screen-summary.json").write_bytes(b'{"old": true}')

    def execute(*args, **kwargs):
        from test_screen import _clean

        if written is not None:
            Path(kwargs["report_path"]).write_bytes(written)
        return _clean()

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", execute)
    with pytest.raises(ScreenError):
        run_screen(str(manifest), str(reports), resume=True)
    assert (reports / "screen-summary.json").read_bytes() == b'{"old": true}'
    assert ((reports / "g0.json").read_bytes() if written is not None else None) == written


@pytest.mark.parametrize("sink", ["manifest", "report", "summary", "capture", "inside", "missing_parent"])
def test_junit_alias_or_invalid_parent_refuses_before_any_output_mutation(tmp_path, monkeypatch, sink):
    manifest, reports = native_corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    (reports / "screen-summary.json").write_bytes(b'{"old":true}')
    capture = tmp_path / "new-captures"
    if sink in ("manifest", "report", "summary"):
        source = {"manifest": manifest, "report": reports / "g0.json", "summary": reports / "screen-summary.json"}[sink]
        junit = tmp_path / "alias.xml"
        os.link(source, junit)
    elif sink == "capture":
        capture.mkdir()
        (capture / "g0.capture.jsonl").write_bytes(b"PRIVATE completion")
        junit = tmp_path / "alias.xml"
        os.link(capture / "g0.capture.jsonl", junit)
    elif sink == "inside":
        junit = reports / "result.xml"
    else:
        junit = tmp_path / "absent" / "result.xml"
    original = snapshot(reports)
    trap(monkeypatch)
    with pytest.raises(ScreenError):
        run_screen(str(manifest), str(reports), resume=True, capture_dir=str(capture), junit_path=str(junit))
    assert snapshot(reports) == original
    assert capture.exists() is (sink == "capture")


def test_manifest_and_each_present_report_are_held_once_and_junit_is_published(tmp_path, monkeypatch):
    import quantfit.screen_resume as resume
    from quantfit import screen

    manifest, reports = native_corpus(tmp_path, [("g0", "gguf", 1, 0, None), ("g1", "gguf", 0, 0, None)])
    raw = snapshot(reports)
    (reports / "screen-summary.json").write_bytes(b'{"old":true}')
    calls = []
    read = resume._read

    def held_once(path, limit):
        calls.append(path)
        assert calls.count(path) == 1
        return read(path, limit)

    monkeypatch.setattr(resume, "_read", held_once)
    monkeypatch.setattr(screen, "load_manifest", lambda *args: pytest.fail("manifest reread"))
    trap(monkeypatch)
    junit = tmp_path / "result.xml"
    result = run_screen(str(manifest), str(reports), resume=True, junit_path=str(junit))
    assert set(calls) == {manifest, reports / "g0.json", reports / "g1.json", reports / "screen-summary.json"}
    assert junit.read_text().startswith("<testsuites") or junit.read_text().startswith("<?xml")
    assert result["resume_receipt"]["exit_code"] == 3
    assert all((reports / name).read_bytes() == value for name, value in raw.items())


@pytest.mark.parametrize("kind", ["report", "manifest", "total"])
def test_preflight_byte_limits_before_contact_and_output_creation(tmp_path, monkeypatch, kind):
    import quantfit.saved_screen as saved

    manifest, reports = native_corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    if kind == "report":
        monkeypatch.setattr(saved, "MAX_REPORT_BYTES", (reports / "g0.json").stat().st_size - 1)
    elif kind == "manifest":
        monkeypatch.setattr(saved, "MAX_MANIFEST_BYTES", manifest.stat().st_size - 1)
    else:
        monkeypatch.setattr(saved, "MAX_TOTAL_BYTES", (reports / "g0.json").stat().st_size - 1)
    original = snapshot(reports)
    trap(monkeypatch)
    with pytest.raises(ScreenError):
        run_screen(str(manifest), str(reports), resume=True, capture_dir=str(tmp_path / "new"))
    assert snapshot(reports) == original and not (tmp_path / "new").exists()


def test_fresh_protocol_mismatch_preserves_native_and_previous_summary(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    _, native = native_corpus(source, [("g0", "gguf", 0, 0, None)])
    payload = json.loads((native / "g0.json").read_bytes())
    payload["env"]["python"] = "explicit different runtime"
    fresh = json.dumps(payload, indent=3).encode()
    manifest, reports = native_corpus(
        tmp_path, [("g0", "gguf", 0, 0, None), ("g1", "gguf", 0, 0, None)], missing=("g0",)
    )
    (reports / "screen-summary.json").write_bytes(b'{"old":true}')
    original = snapshot(reports)

    def execute(*args, **kwargs):
        Path(kwargs["report_path"]).write_bytes(fresh)

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", execute)
    with pytest.raises(ScreenError, match="incompatible_scope"):
        run_screen(str(manifest), str(reports), resume=True)
    assert (reports / "g0.json").read_bytes() == fresh
    assert all((reports / name).read_bytes() == raw for name, raw in original.items())


def test_same_pair_under_two_target_names_is_not_independent_resume_evidence(tmp_path, monkeypatch):
    manifest, reports = native_corpus(tmp_path, [("g0", "gguf", 0, 0, None), ("g1", "gguf", 0, 0, None)])
    value = json.loads(manifest.read_bytes())
    for key in ("baseline", "quant"):
        value["targets"][1][key] = value["targets"][0][key]
    manifest.write_text(json.dumps(value), encoding="utf-8")
    (reports / "g1.json").write_bytes((reports / "g0.json").read_bytes())
    original = snapshot(reports)
    trap(monkeypatch)
    with pytest.raises(ScreenError, match="duplicate_evidence"):
        run_screen(str(manifest), str(reports), resume=True)
    assert snapshot(reports) == original


def test_absent_root_can_execute_and_operational_failure_is_categorical_incomplete(tmp_path, monkeypatch):
    manifest, reports = native_corpus(tmp_path, [("g0", "gguf", 0, 0, None)], missing=("g0",))
    reports.rmdir()
    calls = []

    def unavailable(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("PRIVATE provider credential diagnostics")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", unavailable)
    result = run_screen(str(manifest), str(reports), resume=True, attempts=2)
    assert len(calls) == 2
    assert result["rows"][0]["status"] == "operational_error"
    assert result["resume_receipt"]["exit_code"] == 4 and result["resume_receipt"]["n_operational_errors"] == 1
    assert "PRIVATE" not in json.dumps(result)
    assert not (reports / "g0.json").exists()


def test_failure_after_report_write_is_not_retried_or_overwritten(tmp_path, monkeypatch):
    manifest, reports = native_corpus(tmp_path, [("g0", "gguf", 0, 0, None)], missing=("g0",))
    calls = []

    def interrupted(*args, **kwargs):
        calls.append(args)
        Path(kwargs["report_path"]).write_bytes(b"partial native bytes")
        raise RuntimeError("PRIVATE diagnostics")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", interrupted)
    with pytest.raises(ScreenError, match="execution_report_failure"):
        run_screen(str(manifest), str(reports), resume=True, attempts=3)
    assert len(calls) == 1 and (reports / "g0.json").read_bytes() == b"partial native bytes"
    assert not (reports / "screen-summary.json").exists()


def test_missing_root_retry_then_real_native_success_and_capture_sink(tmp_path, monkeypatch):
    manifest, reports = native_corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    fresh = (reports / "g0.json").read_bytes()
    (reports / "g0.json").unlink()
    reports.rmdir()
    capture = tmp_path / "private-captures"
    calls = []

    def execute(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise OSError("PRIVATE provider failure")
        Path(kwargs["report_path"]).write_bytes(fresh)
        Path(kwargs["capture_path"]).write_bytes(b"PRIVATE completion")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", execute)
    result = run_screen(str(manifest), str(reports), resume=True, attempts=2, capture_dir=str(capture))
    assert len(calls) == 2 and result["resume_receipt"]["exit_code"] == 0
    assert result["resume_receipt"]["n_executed"] == 1 and result["resume_receipt"]["n_operational_errors"] == 0
    assert (reports / "g0.json").read_bytes() == fresh and "PRIVATE" not in json.dumps(result)
    assert calls[0]["capture_path"] == calls[1]["capture_path"] == str(capture / "g0.capture.jsonl")


def test_cancellation_preserves_written_native_bytes_without_retry_or_summary(tmp_path, monkeypatch):
    manifest, reports = native_corpus(tmp_path, [("g0", "gguf", 0, 0, None)], missing=("g0",))
    calls = []

    def cancel(*args, **kwargs):
        calls.append(args)
        Path(kwargs["report_path"]).write_bytes(b"interrupted native bytes")
        raise KeyboardInterrupt()

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", cancel)
    with pytest.raises(KeyboardInterrupt):
        run_screen(str(manifest), str(reports), resume=True, attempts=3)
    assert len(calls) == 1 and (reports / "g0.json").read_bytes() == b"interrupted native bytes"
    assert not (reports / "screen-summary.json").exists()


def test_unreadable_present_bytes_refuse_categorically_instead_of_running(tmp_path, monkeypatch):
    import quantfit.screen_resume as resume

    manifest, reports = native_corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    original = snapshot(reports)
    read = resume._read

    def unreadable(path, limit):
        if path.name == "g0.json":
            raise PermissionError("PRIVATE unreadable provider response")
        return read(path, limit)

    monkeypatch.setattr(resume, "_read", unreadable)
    trap(monkeypatch)
    with pytest.raises(ScreenError) as error:
        run_screen(str(manifest), str(reports), resume=True)
    assert "PRIVATE" not in str(error.value) and snapshot(reports) == original


def test_report_symlink_is_never_missing_or_followed(tmp_path, monkeypatch):
    manifest, reports = native_corpus(tmp_path, [("g0", "gguf", 0, 0, None)], missing=("g0",))
    outside = tmp_path / "outside"
    outside.write_bytes(b"PRIVATE foreign source")
    try:
        os.symlink(outside, reports / "g0.json")
    except OSError:
        pytest.skip("host cannot create a symlink")
    trap(monkeypatch)
    with pytest.raises(ScreenError):
        run_screen(str(manifest), str(reports), resume=True)
    assert outside.read_bytes() == b"PRIVATE foreign source" and not (reports / "screen-summary.json").exists()


@pytest.mark.parametrize("sink", ["capture", "summary", "junit"])
def test_retry_rechecks_changed_output_alias_before_second_model_contact(tmp_path, monkeypatch, sink):
    manifest, reports = native_corpus(
        tmp_path, [("missing", "gguf", 0, 0, None), ("held", "gguf", 0, 0, None)], missing=("missing",)
    )
    original_manifest = manifest.read_bytes()
    original_report = (reports / "held.json").read_bytes()
    capture = tmp_path / "captures"
    junit = tmp_path / "result.xml"
    calls = []

    def first_failure(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            path = {
                "capture": capture / "missing.capture.jsonl",
                "summary": reports / "screen-summary.json",
                "junit": junit,
            }[sink]
            os.link(manifest, path)
        raise OSError("PRIVATE transient failure")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", first_failure)
    with pytest.raises(ScreenError):
        run_screen(
            str(manifest), str(reports), resume=True, attempts=2, capture_dir=str(capture), junit_path=str(junit)
        )
    assert len(calls) == 1, "unsafe changed sink reached a second model invocation"
    assert manifest.read_bytes() == original_manifest and (reports / "held.json").read_bytes() == original_report
    assert not (reports / "missing.json").exists()
