"""Conditional presentation of synthetic aggregates; no human calibration is claimed."""

import hashlib
import json
from pathlib import Path

import pytest
from test_resolution import resolution_fixture

from quantfit.cli import main
from quantfit.modelcard import model_card_fragment
from quantfit.resolution import analyze_resolution


def card_fixture(tmp_path, **kwargs):
    report, calibration = resolution_fixture(tmp_path, **kwargs)
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["judge"]["card_xstest_accuracy_label"] = "SYNTHETIC fixture; no judge ran"
    report.write_text(json.dumps(payload), encoding="utf-8")
    return report, calibration


def test_conditional_card_preserves_original_measurement_and_exact_input_hashes(tmp_path):
    report, calibration = card_fixture(tmp_path)
    original = {path: path.read_bytes() for path in (report, Path(calibration))}
    plain = model_card_fragment(str(report))
    md = model_card_fragment(str(report), calibration_report=calibration)
    analysis = analyze_resolution(str(report), calibration)
    # No reclassification: the original table, verdict and provenance stay intact.
    assert plain.split("\n---\n")[0] in md
    assert "perfect-judge FLOOR" in md
    assert "### Conditional resolution from bound calibration" in md
    assert "human labels: **unverified**" in md
    assert "assumptions: **unverified**" in md
    assert "no safety verdict, research GO or sensitivity-control result" in md
    assert "A1" in md and "A2" in md and "A3" in md
    assert "sentinel: no effect size reaches target power" in md
    for path, data in original.items():
        assert hashlib.sha256(data).hexdigest() in md
        assert path.read_bytes() == data
    assert analysis["binding_fingerprint"] in md
    for axis in analysis["axes"].values():
        assert f"{axis['resolution']['effective_mde'] * 100:.1f}pp" in md
    assert f"{analysis['eps_baseline_upper']:.6f}" in md
    assert f"{analysis['eps_quant_upper']:.6f}" in md
    assert model_card_fragment(str(report), calibration_report=calibration) == md


def test_unmeasurable_axis_remains_no_answer_in_conditional_card(tmp_path):
    report, calibration = card_fixture(tmp_path, unmeasurable=True)
    md = model_card_fragment(str(report), calibration_report=calibration)
    assert "| refusal-robustness | 0 | unmeasurable; no answer |" in md
    assert "**Not measured: refusal-robustness.**" in md


@pytest.mark.parametrize("mutation", ["revision", "counts", "calibration", "duplicate", "verdict", "ci", "floor"])
def test_invalid_binding_or_aggregate_emits_no_fragment(tmp_path, capsys, mutation):
    report, calibration = card_fixture(tmp_path)
    payload = json.loads(report.read_text(encoding="utf-8"))
    if mutation == "revision":
        payload["quantized"]["revision"] = "c" * 40
    elif mutation == "counts":
        payload["drift"]["refusal_robustness"]["at_risk"] = 9
    elif mutation == "calibration":
        bound = json.loads(Path(calibration).read_text(encoding="utf-8"))
        bound["baseline"]["mde_epsilon_upper"] = 0.001
        Path(calibration).write_text(json.dumps(bound), encoding="utf-8")
    elif mutation == "verdict":
        payload["drift"]["verdict"] = "HUMAN CONFIRMED SAFE (forged)"
    elif mutation == "ci":
        payload["drift"]["over_refusal"]["flip_rate_wilson95"] = [False, 0.001]
    elif mutation == "floor":
        payload["drift"]["refusal_robustness"]["mde_at_80pct_power"] = 0.001
    report.write_text(json.dumps(payload), encoding="utf-8")
    if mutation == "duplicate":
        report.write_text('{"schema_version":2,"schema_version":2}', encoding="utf-8")
    assert main(["emit", "model-card", "--report", str(report), "--calibration-report", calibration, "--json"]) == 2
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["result"] is None


def test_emit_cli_exposes_calibrated_card_without_rewriting_inputs(tmp_path, capsys):
    report, calibration = card_fixture(tmp_path)
    assert main(["emit", "model-card", "--report", str(report), "--calibration-report", calibration, "--json"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["result"]["fragment"] == model_card_fragment(str(report), calibration_report=calibration)


def test_card_uses_same_validated_buffer_if_path_changes_after_analysis(tmp_path, monkeypatch):
    from quantfit import resolution

    report, calibration = card_fixture(tmp_path)
    original = report.read_bytes()
    expected = model_card_fragment(str(report), calibration_report=calibration)
    analyze = resolution.analyze_resolution_inputs

    def substitute(*args):
        loaded, artifact = analyze(*args)
        report.write_text('{"different": "unvalidated bytes"}', encoding="utf-8")
        return loaded, artifact

    monkeypatch.setattr(resolution, "analyze_resolution_inputs", substitute)
    assert model_card_fragment(str(report), calibration_report=calibration) == expected
    assert hashlib.sha256(original).hexdigest() in expected
