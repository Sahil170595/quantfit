"""Actual CLI strict-resume consumers, also run under the installed-origin guard."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ci_screen_resume_consumer", ROOT / "tools/ci_screen_resume.py")
assert SPEC is not None and SPEC.loader is not None
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)
PROTOTYPE = ROOT / "validation/2026-08-21-screen-complete/reports/gguf-gemma3-270m-lmstudio.json"


@pytest.fixture(autouse=True)
def no_resolution_or_download(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline resume consumer attempted asset resolution or download")

    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)


@pytest.fixture
def fixture():
    return consumer.synthetic_fixture(PROTOTYPE)


def test_fixture_is_strict_native_aggregate_and_count_oracle_is_independent(tmp_path, fixture):
    from quantfit.saved_screen import summarize_screen

    manifest_data, reports = fixture
    manifest, out = consumer.write_fixture(tmp_path / "native", manifest_data, reports)
    native = summarize_screen(str(manifest), str(out))
    assert native["exit_code"] == 3 and native["coverage"]["n_present"] == 3
    expected = consumer.native_counts([json.loads(raw) for raw in reports.values()])
    assert expected == {
        "exit_code": 3,
        "n_targets": 3,
        "axes": {
            "refusal_robustness": {"n_measured": 2, "n_regressed": 1, "n_regressed_human_verified": 0},
            "over_refusal": {"n_measured": 2, "n_regressed": 0, "n_regressed_human_verified": 0},
        },
    }


def test_actual_cli_all_present_exact_one_json_no_generation_and_negative_junit(tmp_path, fixture):
    manifest_data, reports = fixture
    manifest, out = consumer.write_fixture(tmp_path / "native", manifest_data, reports)
    original_manifest = manifest.read_bytes()
    # A producer summary's favourable claims are deliberately ignored.
    (out / "screen-summary.json").write_text('{"rows": [], "scientific_go": true}', encoding="utf-8")
    xml = tmp_path / "screen.xml"
    with patch(
        "quantfit.safety.verify.verify_safety", side_effect=AssertionError("unexpected model call")
    ) as execution:
        document, _ = consumer.invoke(manifest, out, junit=xml)
    execution.assert_not_called()
    assert manifest.read_bytes() == original_manifest
    projection = consumer.check(document, manifest, out, reports)
    assert projection["n_skipped"] == 3 and projection["n_executed"] == 0
    assert consumer.check_junit(xml, reports) == {"tests": 3, "failures": 1, "skipped": 1, "errors": 0}


def test_missing_only_executes_once_and_original_bytes_remain_bound(tmp_path, fixture):
    from quantfit.safety.report import DriftReport
    from quantfit.safety.verify import SafetyDrift

    manifest_data, reports = fixture
    manifest, out = consumer.write_fixture(tmp_path / "native", manifest_data, reports, missing=("clean",))
    expected_target = manifest_data["targets"][0]
    fresh_raw = reports["clean"]
    staged = tmp_path / "fresh.json"
    staged.write_bytes(fresh_raw)
    parsed = DriftReport.from_json(str(staged))
    drift = parsed.drift

    def execute(baseline, quant, *, max_new_tokens, report_path, **kwargs):
        assert baseline == expected_target["baseline"] and quant == expected_target["quant"]
        assert max_new_tokens == 64 and Path(report_path) == out / "clean.json"
        Path(report_path).write_bytes(fresh_raw)
        d, o = drift["refusal_robustness"], drift["over_refusal"]
        return SafetyDrift(
            40,
            12,
            d["baseline_refused"],
            d["quant_refused"],
            d["harmful_compliance_regressions"],
            28,
            o["baseline_refused"],
            o["quant_refused"],
            o["overrefusal_regressions"],
            drift["by_zone"],
        )

    with patch("quantfit.safety.verify.verify_safety", side_effect=execute) as execution:
        document, _ = consumer.invoke(manifest, out)
    assert execution.call_count == 1
    assert consumer.check(document, manifest, out, reports, executed=("clean",))["n_skipped"] == 2


@pytest.mark.parametrize("mutation", ["corrupt", "tokens", "template", "reference", "private", "extra"])
def test_invalid_last_report_refuses_before_earlier_missing_can_execute(tmp_path, fixture, mutation):
    manifest_data, reports = fixture
    manifest, out = consumer.write_fixture(tmp_path / "native", manifest_data, reports, missing=("clean",))
    path = out / "unmeasured.json"
    value = json.loads(path.read_bytes())
    if mutation == "corrupt":
        raw = b'{"schema_version":2,"PRIVATE_SENTINEL_DO_NOT_REFLECT":'
    else:
        if mutation == "tokens":
            value["decode"]["max_new_tokens"] = 63
        elif mutation == "template":
            value["decode"]["chat_template"] = "raw prompt always"
        elif mutation == "reference":
            value["baseline"]["model"] = "hf:synthetic/wrong/wrong.gguf"
        elif mutation == "private":
            value["PRIVATE_SENTINEL_DO_NOT_REFLECT"] = "not retained"
        elif mutation == "extra":
            (out / "undeclared.json").write_bytes(b"{}")
        raw = (json.dumps(value) + "\n").encode()
    path.write_bytes(raw)
    originals = {p: p.read_bytes() for p in (manifest, *out.iterdir())}
    with patch(
        "quantfit.safety.verify.verify_safety", side_effect=AssertionError("executed before preflight")
    ) as execution:
        document, stderr = consumer.invoke(manifest, out)
    execution.assert_not_called()
    assert document["exit_code"] == 2 and document["result"] is None
    assert "PRIVATE_SENTINEL_DO_NOT_REFLECT" not in json.dumps(document) + stderr
    assert not (out / "clean.json").exists()
    assert all(p.read_bytes() == raw for p, raw in originals.items())


@pytest.mark.parametrize("alias", ["manifest", "report", "summary"])
def test_junit_output_alias_refuses_without_any_input_mutation(tmp_path, fixture, alias):
    manifest_data, reports = fixture
    manifest, out = consumer.write_fixture(tmp_path / "native", manifest_data, reports)
    summary = out / "screen-summary.json"
    summary.write_bytes(b'{"producer_claim":"ignored"}\n')
    originals = {p: p.read_bytes() for p in (manifest, *out.iterdir())}
    destination = {"manifest": manifest, "report": out / "clean.json", "summary": summary}[alias]
    with patch(
        "quantfit.safety.verify.verify_safety", side_effect=AssertionError("unexpected native call")
    ) as execution:
        document, _ = consumer.invoke(manifest, out, junit=destination)
    execution.assert_not_called()
    assert document["exit_code"] == 2
    assert all(p.read_bytes() == raw for p, raw in originals.items())


def test_report_budget_refuses_before_model_contact(tmp_path, fixture):
    manifest_data, reports = fixture
    manifest, out = consumer.write_fixture(tmp_path / "native", manifest_data, reports, missing=("clean",))
    raw = b" " * (8 * 1024 * 1024 + 1)
    (out / "unmeasured.json").write_bytes(raw)
    with patch(
        "quantfit.safety.verify.verify_safety", side_effect=AssertionError("unexpected native call")
    ) as execution:
        document, _ = consumer.invoke(manifest, out)
    execution.assert_not_called()
    assert document["exit_code"] == 2 and (out / "unmeasured.json").read_bytes() == raw


@pytest.mark.parametrize("name,code,flagged", [("clean", 0, 0), ("flagged", 3, 1), ("unmeasured", 4, 0)])
def test_cpu_adapter_reuses_original_native_and_derives_actual_negative_flags(tmp_path, fixture, name, code, flagged):
    _, reports = fixture
    source = tmp_path / "original.json"
    source.write_bytes(reports[name])
    result = consumer.accept_cpu(source, tmp_path / "cpu-resume")
    assert result["additional_native_calls"] == 0 and result["exit_code"] == code
    assert result["n_targets"] == result["n_skipped"] == 1 and result["n_executed"] == 0
    assert result["axes"]["refusal_robustness"]["n_regressed"] == flagged
    assert source.read_bytes() == reports[name]


def test_installed_and_existing_cpu_seams_are_single_offline_calls():
    installed = (ROOT / "tools/ci_installed.py").read_text(encoding="utf-8")
    assert installed.count('"test_ci_screen_resume.py"') == 1
    cpu = (ROOT / "tools/ci_cpu_acceptance.py").read_text(encoding="utf-8")
    assert cpu.count("screen_resume_accept_cpu(") == 1
    assert 'Path(result["runs"][0]["report"]["path"])' in cpu
    assert '"strict_screen_resume": screen_resume' in cpu
