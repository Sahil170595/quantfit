"""Whole pinned-corpus policy controls; SDK/generation seams are controlled."""

import json

import pytest
from test_probe_corpus import rows, software_arms

from quantfit import gate
from quantfit.safety import verify as v
from quantfit.safety.report import DriftReport

pytest_plugins = ["test_probe_corpus"]


def alternative(sdk):
    source = v.ProbeCorpus("controlled/alternative", "d" * 40, "validation")
    sdk["hash"] = source.revision
    sdk["rows"] = rows(6)
    return source


def test_native_alternative_positive_retains_full_rows_and_explicit_expected(sdk, monkeypatch, tmp_path):
    source = alternative(sdk)
    calls = software_arms(monkeypatch)
    path = tmp_path / "native.json"
    drift = v.verify_safety("controlled/base", "controlled/quant", probe_corpus=source, report_path=str(path))
    report = DriftReport.from_json(str(path))
    assert report.probe_dataset == {"id": source.id, "revision": source.revision, "split": source.split, "n_probes": 6}
    assert drift.to_dict()["refusal_robustness"]["expected_unsafe_n"] == 3
    assert drift.to_dict()["over_refusal"]["expected_safe_n"] == 3
    assert sdk["rows"][0]["zone"] == "clear_safe" and sdk["rows"][0]["expected"] == "unsafe"
    assert len(sdk["loads"]) == sdk["iterations"] == 1
    assert calls == [[r["prompt"] for r in rows(6)]] * 2


def test_saved_custom_policy_uses_native_census_and_is_offline(sdk, monkeypatch, tmp_path):
    source = alternative(sdk)
    software_arms(monkeypatch)
    path = tmp_path / "native.json"
    v.verify_safety("controlled/base", "controlled/quant", probe_corpus=source, report_path=str(path))

    def forbidden(*args, **kwargs):
        raise AssertionError("saved replay must not reload the source or execute a model")

    monkeypatch.setattr(v, "_prepare_probes", forbidden)
    monkeypatch.setattr(v, "_generate_completions", forbidden)
    result = gate.evaluate_report(str(path), threshold=0.30, probe_corpus=source)
    assert result["schema_version"] == 3 and result["decision_schema_version"] == 1
    assert result["exit_code"] == 5  # native n=3 cannot resolve this effect, unlike fixed12
    assert result["probe_corpus"]["n_probes"] == 6
    assert result["probe_corpus"]["expected_unsafe_n"] == 3
    assert result["probe_corpus"]["population_basis"] == "saved_report_native_counts"


def test_live_custom_preflight_resolves_population_before_any_model(sdk, monkeypatch):
    source = alternative(sdk)

    def forbidden(*args, **kwargs):
        raise AssertionError("unresolvable native census must refuse before model/judge execution")

    monkeypatch.setattr(v, "_generate_completions", forbidden)
    monkeypatch.setattr(v, "_classify_refusals", forbidden)
    result = gate.run_gate("controlled/base", "controlled/quant", threshold=0.30, probe_corpus=source)
    assert result["schema_version"] == 3 and result["decision_schema_version"] == 1
    assert result["exit_code"] == 5
    assert result["probe_corpus"]["population_basis"] == "resolved_native_population"
    assert result["probe_corpus"]["expected_safe_n"] == 3
    assert len(sdk["loads"]) == sdk["iterations"] == 1 and sdk["yielded"] == 6


@pytest.mark.parametrize(
    "options, expected",
    [
        ({}, "population_reached"),
        ({"capture_path": "private.capture.jsonl"}, "execution_recipe_mismatch"),
        ({"baseline_cache_dir": "private-cache"}, "execution_recipe_mismatch"),
        ({"max_new_tokens": 63}, "execution_recipe_mismatch"),
    ],
)
def test_existing_reference_preflight_retains_capture_cache_and_decode_guards(monkeypatch, options, expected):
    def reached(*args, **kwargs):
        raise RuntimeError("population_reached")

    monkeypatch.setattr(v, "_prepare_probes", reached)
    with pytest.raises(RuntimeError, match=expected):
        v.verify_safety("baseline.gguf", "quant.gguf", _execution_guard=lambda *a: None, **options)


def native_runtime(monkeypatch):
    from quantfit.safety import report as report_module
    from quantfit.safety.report import ArmRun

    calls = []

    def generate(model, prompts, max_tokens, token):
        calls.append((model, list(prompts)))
        return ["refused" if i % 2 == 0 else "answered" for i in range(len(prompts))], ArmRun(
            model,
            ("a" if "base" in model else "b") * 40,
            "torch.float32",
            1.0,
            {"name": "transformers", "version": "synthetic-not-used", "device": "cpu"},
            None,
        )

    monkeypatch.setattr(v, "_generate_completions", generate)
    monkeypatch.setattr(v, "_classify_refusals", lambda values, token: ([x == "refused" for x in values], 0.25))
    monkeypatch.setattr(
        report_module,
        "environment_fingerprint",
        lambda: {
            "python": "synthetic-not-used",
            "torch": "synthetic-not-used",
            "transformers": "synthetic-not-used",
            "cuda": None,
            "device": "cpu",
        },
    )
    return calls


@pytest.mark.parametrize("selected", [False, True])
def test_native_corpus_gate_observed_receiving_and_junit(sdk, monkeypatch, tmp_path, selected):
    from quantfit.bundle import create_bundle, verify_bundle
    from quantfit.junit import gate_to_junit

    source = alternative(sdk)
    sdk["rows"] = rows(30)
    calls = native_runtime(monkeypatch)
    report, artifact = tmp_path / "report.json", tmp_path / "gate.json"
    options = (
        {"axis_thresholds": {"refusal-robustness": 0.30, "over-refusal": 0.30}} if selected else {"threshold": 0.30}
    )
    result = gate.run_gate(
        "controlled/base1",
        "controlled/quant1",
        probe_corpus=source,
        report_path=str(report),
        out_path=str(artifact),
        **options,
    )
    assert result["exit_code"] == 0 and result["decision_schema_version"] == (2 if selected else 1)
    assert result["probe_corpus"]["expected_unsafe_n"] == 15
    assert len(calls) == 2 and all(len(prompts) == 30 for _, prompts in calls)
    assert sdk["iterations"] == 1
    archive = tmp_path / "bundle"
    create_bundle(str(report), str(archive), gate_path=str(artifact))
    assert verify_bundle(str(archive))
    xml = gate_to_junit(result, baseline="controlled/base1", quant="controlled/quant1")
    assert "probe_corpus=" in xml and source.revision in xml


def manifest(path, *, control="pass"):
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "controlled source",
                "sensitivity_control": {"status": control},
                "targets": [
                    {
                        "name": "first",
                        "stratum": "compressed-tensors",
                        "baseline": "controlled/base1",
                        "quant": "controlled/quant1",
                    },
                    {
                        "name": "last",
                        "stratum": "compressed-tensors",
                        "baseline": "controlled/base2",
                        "quant": "controlled/quant2",
                    },
                ],
            }
        )
    )


def test_screen_shares_one_native_population_and_complete_resume_is_offline(sdk, monkeypatch, tmp_path):
    from quantfit.saved_screen import summarize_screen
    from quantfit.screen import run_screen

    source = alternative(sdk)
    calls = native_runtime(monkeypatch)
    config, out = tmp_path / "manifest.json", tmp_path / "reports"
    manifest(config)
    result = run_screen(str(config), str(out), probe_corpus=source)
    assert result["schema_version"] == 2 and result["probe_corpus"]["n_probes"] == 6
    assert result["sensitivity_control"]["status"] == "pass" and result["control_evidence_verified"] is False
    assert all(row["refusal_robustness"]["conditionality"] is not None for row in result["by_stratum"].values())
    assert [model for model, _ in calls] == [
        "controlled/base1",
        "controlled/quant1",
        "controlled/base2",
        "controlled/quant2",
    ]
    assert len(sdk["loads"]) == sdk["iterations"] == 1
    for _, prompts in calls:
        assert prompts == [r["prompt"] for r in rows(6)]

    def forbidden(*a, **k):
        raise AssertionError("saved and complete resume must be offline")

    monkeypatch.setattr(v, "_prepare_probes", forbidden)
    monkeypatch.setattr(v, "verify_safety", forbidden)
    saved = summarize_screen(str(config), str(out), probe_corpus=source)
    assert saved["saved_screen_summary_schema_version"] == 2
    assert saved["probe_corpus"]["population_basis"] == "saved_report_native_counts"
    resumed = run_screen(str(config), str(out), probe_corpus=source, resume=True)
    assert resumed["probe_corpus"] == saved["probe_corpus"]
    assert [r["action"] for r in resumed["resume_receipt"]["targets"]] == ["skipped", "skipped"]


def test_saved_all_missing_source_is_unknown_not_zero(sdk, tmp_path):
    from quantfit.saved_screen import summarize_screen

    source = alternative(sdk)
    config, out = tmp_path / "manifest.json", tmp_path / "reports"
    manifest(config)
    out.mkdir()
    result = summarize_screen(str(config), str(out), probe_corpus=source)
    assert result["probe_corpus"]["population_basis"] == "unavailable_no_reports"
    assert result["probe_corpus"]["n_probes"] is None and result["probe_corpus"]["zone_counts"] is None
    assert result["coverage"]["n_missing"] == 2 and result["exit_code"] == 4


@pytest.mark.parametrize("alternate_census", [False, True])
def test_screen_compares_native_report_to_resolved_census_before_summary(sdk, monkeypatch, tmp_path, alternate_census):
    from quantfit.probe_population import _PreparedPopulation
    from quantfit.screen import ScreenError, run_screen

    source = alternative(sdk)
    native_runtime(monkeypatch)
    original = v.verify_safety

    def producer(*args, **kwargs):
        if alternate_census:
            held = kwargs["_prepared_population"]
            # Genuine native verifier/writer, deliberately supplied a different
            # valid same-source population by this controlled producer mutation.
            kwargs["_prepared_population"] = _PreparedPopulation(held.source, held.probes[:4])
        return original(*args, **kwargs)

    monkeypatch.setattr(v, "verify_safety", producer)
    config, out = tmp_path / "manifest.json", tmp_path / "reports"
    manifest(config)
    if alternate_census:
        with pytest.raises(ScreenError):
            run_screen(str(config), str(out), probe_corpus=source)
        assert DriftReport.from_json(str(out / "first.json")).probe_dataset["n_probes"] == 4
        assert not (out / "screen-summary.json").exists()
    else:
        result = run_screen(str(config), str(out), probe_corpus=source)
        assert result["probe_corpus"]["n_probes"] == 6
        assert DriftReport.from_json(str(out / "first.json")).probe_dataset["n_probes"] == 6
    assert sdk["yielded"] == 6 and sdk["iterations"] == 1
