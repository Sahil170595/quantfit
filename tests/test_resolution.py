"""Offline aggregate fixtures; no human calibration or safety finding is asserted."""

import hashlib
import json
from dataclasses import replace

import pytest
from test_calibration_binding import calibration_fixture, report_fixture, write_calibration

from quantfit.cli import main
from quantfit.safety.verify import SafetyDrift


def resolution_fixture(tmp_path, *, unmeasurable=False):
    report = report_fixture()
    drift = SafetyDrift(
        n=40,
        unsafe_n=12,
        unsafe_baseline_refused=0 if unmeasurable else 10,
        unsafe_quant_refused=3 if unmeasurable else 9,
        harmful_compliance_regressions=0 if unmeasurable else 1,
        safe_n=28,
        safe_baseline_refused=4,
        safe_quant_refused=6,
        overrefusal_regressions=2,
        by_zone={
            "clear_unsafe": {
                "n": 12,
                "baseline_refused": 0 if unmeasurable else 10,
                "quant_refused": 3 if unmeasurable else 9,
            },
            "clear_safe": {"n": 12, "baseline_refused": 2, "quant_refused": 3},
            "borderline": {"n": 16, "baseline_refused": 2, "quant_refused": 3},
        },
    )
    report = replace(report, drift=drift.to_dict())
    report_path = tmp_path / "drift.json"
    report.to_json(str(report_path))
    calibration_path = write_calibration(tmp_path, calibration_fixture(report))
    return report_path, calibration_path


def test_cli_writes_separate_analysis_and_preserves_input_bytes(tmp_path, capsys):
    report, calibration = resolution_fixture(tmp_path)
    original = {p: p.read_bytes() for p in (report, tmp_path / "calibration.json")}
    out = tmp_path / "resolution.json"
    assert (
        main(["resolution", "--report", str(report), "--calibration-report", calibration, "--out", str(out), "--json"])
        == 0
    )
    envelope = json.loads(capsys.readouterr().out)
    result = envelope["result"]
    assert result == json.loads(out.read_text(encoding="utf-8"))
    assert result["resolution_schema"] == 1
    assert result["inputs"]["report_sha256"] == hashlib.sha256(original[report]).hexdigest()
    assert result["inputs"]["calibration_sha256"] == hashlib.sha256(original[tmp_path / "calibration.json"]).hexdigest()
    assert result["eps_baseline_upper"] < result["eps_quant_upper"]
    assert result["axes"]["refusal-robustness"]["flagged_flips"] == 1
    assert result["axes"]["refusal-robustness"]["n_at_risk"] == 10
    assert result["axes"]["over-refusal"]["n_at_risk"] == 24
    assert result["human_confirmation_verified"] is False
    assert "verdict" not in result
    for path, data in original.items():
        assert path.read_bytes() == data


def test_realized_power_matches_independent_scipy_binomial_tail(tmp_path):
    scipy = pytest.importorskip("scipy.stats")
    from quantfit.resolution import analyze_resolution

    report, calibration = resolution_fixture(tmp_path)
    result = analyze_resolution(str(report), calibration)
    for axis in result["axes"].values():
        block = axis["resolution"]
        n, q, alpha = block["n_at_risk"], block["false_flip_rate_bound"], block["alpha"]
        expected_k = next((k for k in range(1, n + 1) if scipy.binom.sf(k - 1, n, q) <= alpha), n + 1)
        assert block["detection_threshold_flips"] == expected_k
        for row in block["power_at_pre_registered"]:
            assert row["power"] == pytest.approx(scipy.binom.sf(expected_k - 1, n, row["effect"] * (1 - q)), abs=1e-9)
        assert "independent" in block["correlated_error_note"]


def test_zero_at_risk_is_explicitly_unmeasurable_not_a_safety_pass(tmp_path):
    from quantfit.resolution import analyze_resolution

    report, calibration = resolution_fixture(tmp_path, unmeasurable=True)
    axis = analyze_resolution(str(report), calibration)["axes"]["refusal-robustness"]
    assert axis["measurable"] is False
    assert axis["detectable_at_target_power"] is False
    assert axis["resolution"]["n_at_risk"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["drift"].update(n_probes=39),
        lambda p: p["drift"]["refusal_robustness"].update(at_risk=9),
        lambda p: p["drift"]["over_refusal"].update(overrefusal_regressions=25),
        lambda p: p["drift"]["refusal_robustness"].update(quant_refused=True),
        lambda p: p["drift"]["refusal_robustness"].update(harmful_compliance_regressions=0),
        lambda p: p["drift"].update(regression_detected=False),
        lambda p: p["drift"].update(unmeasurable_axes=["over-refusal"]),
        lambda p: p["baseline"].update(revision="c" * 40),
        lambda p: p["drift"]["by_zone"]["clear_unsafe"].update(n=999999),
        lambda p: p["drift"]["by_zone"]["clear_safe"].update(quant_refused=27),
        lambda p: p["drift"]["by_zone"]["clear_safe"].update(n=True),
    ],
)
def test_inconsistent_counts_or_changed_scope_refused_before_output(tmp_path, mutation, capsys):
    report, calibration = resolution_fixture(tmp_path)
    payload = json.loads(report.read_text(encoding="utf-8"))
    mutation(payload)
    report.write_text(json.dumps(payload), encoding="utf-8")
    original = report.read_bytes()
    out = tmp_path / "resolution.json"
    assert (
        main(["resolution", "--report", str(report), "--calibration-report", calibration, "--out", str(out), "--json"])
        == 2
    )
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["result"] is None
    assert not out.exists()
    assert report.read_bytes() == original


@pytest.mark.parametrize(
    "content", ['{"schema_version":2,"schema_version":2}', '{"value":NaN}', '{"value":1e999}', "[]"]
)
def test_strict_json_rejects_duplicate_nonfinite_and_nonobject(tmp_path, content):
    from quantfit.resolution import ResolutionError, analyze_resolution

    report, calibration = resolution_fixture(tmp_path)
    report.write_text(content, encoding="utf-8")
    with pytest.raises(ResolutionError):
        analyze_resolution(str(report), calibration)


def test_output_must_not_overwrite_either_input(tmp_path):
    from quantfit.resolution import ResolutionError, analyze_resolution

    report, calibration = resolution_fixture(tmp_path)
    for out in (str(report), calibration):
        with pytest.raises(ResolutionError, match="input"):
            analyze_resolution(str(report), calibration, out)


def test_oversized_report_is_bounded(tmp_path):
    from quantfit.resolution import MAX_REPORT_BYTES, ResolutionError, analyze_resolution

    report, calibration = resolution_fixture(tmp_path)
    report.write_bytes(b" " * (MAX_REPORT_BYTES + 1))
    with pytest.raises(ResolutionError, match="limit"):
        analyze_resolution(str(report), calibration)


def test_hardlinked_output_cannot_modify_input(tmp_path):
    import os

    from quantfit.resolution import ResolutionError, analyze_resolution

    report, calibration = resolution_fixture(tmp_path)
    out = tmp_path / "hardlink.json"
    os.link(report, out)
    original = report.read_bytes()
    with pytest.raises(ResolutionError, match="input"):
        analyze_resolution(str(report), calibration, str(out))
    assert report.read_bytes() == original


def test_failed_atomic_output_preserves_existing_file_and_removes_temporary(tmp_path, monkeypatch):
    from quantfit.resolution import ResolutionError, analyze_resolution

    report, calibration = resolution_fixture(tmp_path)
    out = tmp_path / "resolution.json"
    out.write_bytes(b"existing artifact")
    original_names = set(tmp_path.iterdir())

    def fail(*args):
        raise OSError("fixture replace failure")

    monkeypatch.setattr("quantfit.resolution.os.replace", fail)
    with pytest.raises(ResolutionError, match="cannot write"):
        analyze_resolution(str(report), calibration, str(out))
    assert out.read_bytes() == b"existing artifact"
    assert set(tmp_path.iterdir()) == original_names
