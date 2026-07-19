"""DriftReport schema v2 — round-trip + validation (hermetic, no model load)."""

import json

import pytest

from quantfit.safety.report import SCHEMA_VERSION, ArmRun, DriftReport, ReportError

_TF_ENGINE = {"name": "transformers", "version": "5.10.1", "device": "cpu"}
_LCPP_ENGINE = {"name": "llama.cpp", "binary_sha256": "b" * 64, "source": "pinned", "threads": 8, "device": "cpu"}


def _arm(**overrides):
    fields = dict(
        model="m",
        revision="r1",
        resolved_dtype="torch.float16",
        runtime_s=1.0,
        engine=_TF_ENGINE,
        artifact_sha256=None,
    )
    fields.update(overrides)
    return ArmRun(**fields)


def _report(**overrides):
    fields = dict(
        schema_version=SCHEMA_VERSION,
        quantfit_version="0.4.1",
        created_utc="2026-07-11T00:00:00+00:00",
        judge={"id": "j", "revision": "abc123", "input_contract": "completion-only"},
        probe_dataset={"id": "d", "revision": "def456", "split": "train", "n_probes": 40},
        decode={"max_new_tokens": 64, "do_sample": False, "chat_template": "model-default"},
        env={"python": "3.13.0", "torch": "2.9.0", "transformers": "5.10.1", "cuda": None, "device": "cpu"},
        baseline=_arm(),
        quantized=_arm(model="q", revision=None, runtime_s=2.0),
        judge_runtime_s=0.5,
        drift={"n_probes": 40, "verdict": "NO REGRESSION DETECTED"},
    )
    fields.update(overrides)
    return DriftReport(**fields)


def test_round_trip(tmp_path):
    report = _report()
    p = report.to_json(str(tmp_path / "r.json"))
    assert DriftReport.from_json(str(p)) == report


@pytest.mark.parametrize("wrong", [99, 1])  # 1 = the real-world case: a 0.4.0 report read by this quantfit
def test_wrong_schema_version_refused(tmp_path, wrong):
    p = _report().to_json(str(tmp_path / "r.json"))
    payload = json.loads(p.read_text(encoding="utf-8"))
    payload["schema_version"] = wrong
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
        _arm(resolved_dtype="auto")


def test_engine_must_be_named_object():
    # engine provenance is load-bearing (the same-binary mandate is audited from
    # it); a stringly or nameless engine is refused at construction.
    with pytest.raises(ReportError, match="engine"):
        _arm(engine="llama.cpp")
    with pytest.raises(ReportError, match="engine"):
        _arm(engine={"threads": 8})


def test_gguf_arm_round_trips(tmp_path):
    report = _report(
        baseline=_arm(
            model="hf:org/repo/m-f16.gguf", resolved_dtype="F16", engine=_LCPP_ENGINE, artifact_sha256="a" * 64
        ),
        quantized=_arm(
            model="hf:org/repo/m-q4.gguf", resolved_dtype="Q4_K_M", engine=_LCPP_ENGINE, artifact_sha256="c" * 64
        ),
    )
    p = report.to_json(str(tmp_path / "r.json"))
    parsed = DriftReport.from_json(str(p))
    assert parsed == report
    # the same-binary mandate is auditable from the report alone:
    assert parsed.baseline.engine["binary_sha256"] == parsed.quantized.engine["binary_sha256"]


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("judge", "tampered"),  # object replaced by a string
        ("drift", []),  # object replaced by a list
        ("created_utc", 123),  # string replaced by a number
        ("judge_runtime_s", "fast"),  # number replaced by a string
        ("baseline", "tampered"),  # arm replaced by a string
    ],
)
def test_nested_type_confusion_refused(tmp_path, field, bad):
    # Key names alone are not validation: a tampered report whose values have the
    # wrong types must be refused on parse, not crash downstream audit tooling.
    p = _report().to_json(str(tmp_path / "r.json"))
    payload = json.loads(p.read_text(encoding="utf-8"))
    payload[field] = bad
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReportError):
        DriftReport.from_json(str(p))


def test_armrun_field_type_confusion_refused(tmp_path):
    p = _report().to_json(str(tmp_path / "r.json"))
    payload = json.loads(p.read_text(encoding="utf-8"))
    payload["baseline"]["runtime_s"] = "fast"
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReportError, match="runtime_s"):
        DriftReport.from_json(str(p))


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
    pytest.importorskip("transformers", reason="fingerprint records the transformers version too")
    from quantfit.safety.report import environment_fingerprint

    env = environment_fingerprint()
    assert set(env) == {"python", "torch", "transformers", "cuda", "device"}
    assert env["device"]  # never empty: a GPU name or the literal "cpu"


def test_write_report_assembles_valid_schema_v2(tmp_path, monkeypatch):
    # The report-building path must be provable without a GPU run: fake arms +
    # a static env fingerprint, real tabulation, then a full round-trip parse.
    import quantfit.safety.report as report_mod
    from quantfit.safety.verify import JUDGE_REVISION, PROBE_DATASET_REVISION, Probe, _tabulate, _write_report

    monkeypatch.setattr(
        report_mod,
        "environment_fingerprint",
        lambda: {"python": "3.13.0", "torch": "x", "transformers": "y", "cuda": None, "device": "cpu"},
    )
    probes = [Probe("u", "clear_unsafe", "unsafe"), Probe("s", "clear_safe", "safe")]
    drift = _tabulate(probes, [True, False], [True, True])  # one over-refusal flip
    baseline = _arm(model="base", resolved_dtype="torch.bfloat16", runtime_s=1.5)
    quantized = _arm(model="quant", revision=None, resolved_dtype="torch.bfloat16", runtime_s=0.8)

    out = tmp_path / "report.json"
    _write_report(str(out), drift, baseline, quantized, judge_runtime_s=0.2, max_new_tokens=64)

    parsed = DriftReport.from_json(str(out))
    assert parsed.judge["revision"] == JUDGE_REVISION
    assert parsed.probe_dataset["revision"] == PROBE_DATASET_REVISION
    assert parsed.probe_dataset["n_probes"] == parsed.drift["n_probes"] == 2  # one fact, one value
    assert parsed.baseline.resolved_dtype == "torch.bfloat16"
    assert parsed.baseline.engine["name"] == "transformers"
    assert parsed.drift["over_refusal"]["overrefusal_regressions"] == 1
    assert parsed.drift["refusal_robustness"]["baseline_refused"] == 1
    assert "uncalibrated" in parsed.judge["card_xstest_accuracy_label"]
