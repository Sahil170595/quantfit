"""DriftReport schema v1 — round-trip + validation (hermetic, no model load)."""

import json

import pytest

from quantfit.safety.report import SCHEMA_VERSION, ArmRun, DriftReport, ReportError


def _report(**overrides):
    fields = dict(
        schema_version=SCHEMA_VERSION,
        quantfit_version="0.4.0",
        created_utc="2026-07-11T00:00:00+00:00",
        judge={"id": "j", "revision": "abc123", "input_contract": "completion-only"},
        probe_dataset={"id": "d", "revision": "def456", "split": "train", "n_probes": 40},
        decode={"max_new_tokens": 64, "do_sample": False, "chat_template": "model-default"},
        env={"python": "3.13.0", "torch": "2.9.0", "transformers": "5.10.1", "cuda": None, "device": "cpu"},
        baseline=ArmRun(model="m", revision="r1", resolved_dtype="torch.float16", runtime_s=1.0),
        quantized=ArmRun(model="q", revision=None, resolved_dtype="torch.float16", runtime_s=2.0),
        judge_runtime_s=0.5,
        drift={"n_probes": 40, "verdict": "NO REGRESSION DETECTED"},
    )
    fields.update(overrides)
    return DriftReport(**fields)


def test_round_trip(tmp_path):
    report = _report()
    p = report.to_json(str(tmp_path / "r.json"))
    assert DriftReport.from_json(str(p)) == report


def test_wrong_schema_version_refused(tmp_path):
    p = _report().to_json(str(tmp_path / "r.json"))
    payload = json.loads(p.read_text(encoding="utf-8"))
    payload["schema_version"] = 99
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReportError, match="schema_version"):
        DriftReport.from_json(str(p))


def test_missing_field_refused(tmp_path):
    p = _report().to_json(str(tmp_path / "r.json"))
    payload = json.loads(p.read_text(encoding="utf-8"))
    del payload["judge"]
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReportError, match="does not match schema"):
        DriftReport.from_json(str(p))


def test_unreadable_report_refused(tmp_path):
    bad = tmp_path / "nope.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ReportError, match="unreadable"):
        DriftReport.from_json(str(bad))


def test_auto_dtype_refused():
    # "auto" is an input, not a provenance fact — the schema rejects it outright.
    with pytest.raises(ReportError, match="auto"):
        ArmRun(model="m", revision=None, resolved_dtype="auto", runtime_s=1.0)


def test_drift_to_dict_carries_stats():
    from quantfit.safety.verify import Probe, _tabulate

    probes = [Probe("u", "clear_unsafe", "unsafe"), Probe("s", "clear_safe", "safe")]
    d = _tabulate(probes, [True, False], [True, False]).to_dict()
    assert d["verdict"].startswith("NO REGRESSION DETECTED")
    assert not d["regression_detected"] and d["unmeasurable_axes"] == []
    assert d["refusal_robustness"]["at_risk"] == 1
    lo, hi = d["refusal_robustness"]["flip_rate_wilson95"]
    assert 0.0 <= lo <= hi <= 1.0
    assert d["over_refusal"]["mde_at_80pct_power"] == pytest.approx(0.8)  # 1 - 0.2^(1/1)


def test_environment_fingerprint_is_resolved():
    pytest.importorskip("torch", reason="fingerprint resolves the live torch env")
    from quantfit.safety.report import environment_fingerprint

    env = environment_fingerprint()
    assert set(env) == {"python", "torch", "transformers", "cuda", "device"}
    assert env["device"]  # never empty: a GPU name or the literal "cpu"
