"""Explicit receiving requirements use native conditional analysis, never new statistics."""

import json
from pathlib import Path
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest
from test_calibration_binding import calibration_fixture
from test_saved_screen import corpus

from quantfit.bundle import _report
from quantfit.junit import screen_to_junit
from quantfit.resolution import analyze_resolution_bytes
from quantfit.safety.verify import SafetyDrift
from quantfit.saved_screen import SavedScreenError, summarize_screen

AXES = ("refusal-robustness", "over-refusal")


def inputs(tmp_path, *, n=120, entries=None, unsafe=None):
    entries = entries or [("g0", "gguf", 0, 0, None)]
    manifest, reports = corpus(tmp_path, entries)
    calibrations = tmp_path / "calibrations"
    calibrations.mkdir()
    for name, _, danger, over, unmeasured in entries:
        path = reports / f"{name}.json"
        report = json.loads(path.read_bytes())
        size = n // 2 if unsafe is None else unsafe
        safe = n - size
        base_unsafe = 0 if unmeasured == "danger" else size
        base_safe = safe if unmeasured == "over" else 0
        report["probe_dataset"]["n_probes"] = n
        report["drift"] = SafetyDrift(
            n,
            size,
            base_unsafe,
            base_unsafe - danger,
            danger,
            safe,
            base_safe,
            base_safe + over,
            over,
            {
                "clear_unsafe": {"n": size, "baseline_refused": base_unsafe, "quant_refused": base_unsafe - danger},
                "clear_safe": {"n": safe, "baseline_refused": base_safe, "quant_refused": base_safe + over},
            },
        ).to_dict()
        raw = (json.dumps(report, sort_keys=True) + "\n").encode("utf-8")
        path.write_bytes(raw)
        calibration = calibration_fixture(_report(raw))
        (calibrations / f"{name}.json").write_text(json.dumps(calibration), encoding="utf-8")
    return manifest, reports, calibrations


def summarize(paths, ceiling=None, **kwargs):
    manifest, reports, calibrations = paths
    return summarize_screen(
        str(manifest),
        str(reports),
        calibrations_dir=str(calibrations),
        required_conditional_resolution_pp=ceiling,
        **kwargs,
    )


def test_default_is_exact_native_annotation_and_junit_without_requirement(tmp_path):
    paths = inputs(tmp_path)
    manifest, reports, calibrations = paths
    native = summarize_screen(str(manifest), str(reports), calibrations_dir=str(calibrations))
    result = summarize(paths)
    result["created_utc"] = native["created_utc"]
    for row, original in zip(
        result["conditional_resolution"]["rows"], native["conditional_resolution"]["rows"], strict=True
    ):
        row["analysis"]["created_utc"] = original["analysis"]["created_utc"]
    assert result == native and "conditional_resolution_requirement" not in result
    assert screen_to_junit(result) == screen_to_junit(native)


def test_native_zero_missing_calibration_default_zero_required_four_and_junit_failure(tmp_path):
    paths = inputs(tmp_path)
    (paths[2] / "g0.json").unlink()
    assert summarize(paths)["exit_code"] == 0
    result = summarize(paths, 40)
    requirement = result["conditional_resolution_requirement"]
    assert result["exit_code"] == requirement["qualification_exit_code"] == 4
    assert requirement["native_exit_code"] == 0 and result["outcome"] == "conditional_no_detection"
    assert requirement["manifest_sha256"] == result["manifest"]["sha256"]
    assert [row["name"] for row in requirement["rows"]] == ["g0"]
    for axis in AXES:
        assert requirement["rows"][0]["axes"][axis]["reasons"] == ["calibration_missing"]
    xml = ET.fromstring(screen_to_junit(result))
    assert len(xml.findall(".//testcase")) == 4 and len(xml.findall(".//testcase/failure")) == 3


def test_native_positive_both_axes_qualify_and_preserve_original_cases(tmp_path):
    paths = inputs(tmp_path)
    native = summarize(paths)
    result = summarize(paths, 40)
    requirement = result["conditional_resolution_requirement"]
    assert result["exit_code"] == requirement["native_exit_code"] == 0 and requirement["requirement_met"]
    for axis in AXES:
        checked = requirement["rows"][0]["axes"][axis]
        observed = result["conditional_resolution"]["rows"][0]["analysis"]["axes"][axis]
        assert observed["detectable_at_target_power"] is True and checked["requirement_met"]
        assert checked["effective_mde_pp"] == observed["resolution"]["effective_mde"] * 100 <= 40
    original = ET.fromstring(screen_to_junit(native)).findall(".//testcase")
    xml = ET.fromstring(screen_to_junit(result))
    assert len(original) == 1
    assert [ET.tostring(case) for case in xml.findall(".//testcase")[: len(original)]] == [
        ET.tostring(case) for case in original
    ]
    assert len(xml.findall(".//testcase")) == 4 and not xml.findall(".//testcase/failure")


def test_actual_saturated_one_is_not_detectable_even_at_hundred_pp(tmp_path):
    paths = inputs(tmp_path, n=40)
    result = summarize(paths, 100)
    assert result["exit_code"] == 5 and result["outcome"] == "conditional_no_detection"
    requirement = result["conditional_resolution_requirement"]
    assert requirement["native_exit_code"] == 0 and not requirement["requirement_met"]
    for axis in AXES:
        observed = result["conditional_resolution"]["rows"][0]["analysis"]["axes"][axis]
        assert observed["resolution"]["effective_mde"] == 1.0
        assert observed["detectable_at_target_power"] is False
        assert requirement["rows"][0]["axes"][axis]["reasons"] == ["target_power_unattainable"]


def test_inclusive_pp_boundary_and_single_coarse_axis(tmp_path):
    paths = inputs(tmp_path, unsafe=40)
    row = summarize(paths)["conditional_resolution"]["rows"][0]
    ceilings = {axis: row["analysis"]["axes"][axis]["resolution"]["effective_mde"] * 100 for axis in AXES}
    assert ceilings[AXES[0]] > ceilings[AXES[1]]
    assert summarize(paths, max(ceilings.values()))["exit_code"] == 0
    result = summarize(paths, sum(ceilings.values()) / 2)
    axes = result["conditional_resolution_requirement"]["rows"][0]["axes"]
    assert result["exit_code"] == 5 and axes[AXES[0]]["reasons"] == ["resolution_exceeds_requirement"]
    assert axes[AXES[1]]["requirement_met"]


@pytest.mark.parametrize("native,expected", [("flagged", 3), ("unmeasured", 4)])
def test_native_priority_keeps_simultaneous_missing_and_coarse_reasons(tmp_path, native, expected):
    entries = [
        ("g0", "gguf", 1 if native == "flagged" else 0, 0, "danger" if native == "unmeasured" else None),
        ("g1", "gguf", 0, 0, None),
        ("g2", "gguf", 0, 0, None),
    ]
    paths = inputs(tmp_path, entries=entries)
    (paths[2] / "g1.json").unlink()
    result = summarize(paths, 1)
    requirement = result["conditional_resolution_requirement"]
    assert result["exit_code"] == requirement["native_exit_code"] == expected
    assert [row["name"] for row in requirement["rows"]] == ["g0", "g1", "g2"]
    assert requirement["rows"][1]["axes"][AXES[0]]["reasons"] == ["calibration_missing"]
    assert "resolution_exceeds_requirement" in requirement["rows"][2]["axes"][AXES[1]]["reasons"]
    assert not requirement["requirement_met"]


@pytest.mark.parametrize("ceiling", [True, False, 0, -1, 100.01, float("nan"), float("inf"), 10**1000, "30"])
def test_invalid_requirement_refuses_before_any_hold_or_output(tmp_path, monkeypatch, ceiling):
    hold = Mock(side_effect=AssertionError("input held before invalid requirement"))
    monkeypatch.setattr("quantfit.saved_screen._hold_screen_inputs", hold)
    with pytest.raises(SavedScreenError):
        summarize_screen(
            "PRIVATE",
            "PRIVATE",
            calibrations_dir="PRIVATE",
            required_conditional_resolution_pp=ceiling,
            out_path=str(tmp_path / "out.json"),
            junit_path=str(tmp_path / "out.xml"),
        )
    hold.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_requirement_requires_calibration_directory_before_hold(monkeypatch):
    hold = Mock(side_effect=AssertionError("input held before directory requirement"))
    monkeypatch.setattr("quantfit.saved_screen._hold_screen_inputs", hold)
    with pytest.raises(SavedScreenError):
        summarize_screen("PRIVATE", "PRIVATE", required_conditional_resolution_pp=30)
    hold.assert_not_called()


def test_native_flags_still_fail_with_all_requirement_axes_met(tmp_path):
    paths = inputs(tmp_path, entries=[("g0", "gguf", 1, 0, None)])
    result = summarize(paths, 40)
    requirement = result["conditional_resolution_requirement"]
    assert result["exit_code"] == 3 and requirement["rows"][0]["requirement_met"]
    assert requirement["reasons"] == ["native_flags_detected"]
    assert len(ET.fromstring(screen_to_junit(result)).findall(".//testcase/failure")) == 2


def test_required_orphan_calibration_retains_missing_report_and_native_skip(tmp_path, monkeypatch):
    paths = inputs(tmp_path)
    (paths[1] / "g0.json").unlink()
    analysis = Mock(side_effect=AssertionError("orphan calibration was analyzed"))
    monkeypatch.setattr("quantfit.resolution.analyze_resolution_bytes", analysis)
    result = summarize(paths, 40)
    checked = result["conditional_resolution_requirement"]
    assert result["exit_code"] == checked["native_exit_code"] == 4
    assert checked["rows"][0]["name"] == "g0"
    assert checked["rows"][0]["calibration_sha256"] and checked["rows"][0]["native_report_sha256"] is None
    for axis in AXES:
        assert checked["rows"][0]["axes"][axis]["reasons"] == ["report_missing"]
    analysis.assert_not_called()
    cases = ET.fromstring(screen_to_junit(result)).findall(".//testcase")
    assert len(cases) == 4 and cases[0].find("skipped") is not None
    assert sum(case.find("failure") is not None for case in cases) == 3


def test_native_zero_later_unattainable_target_prevents_first_target_pass(tmp_path):
    paths = inputs(tmp_path, entries=[("g0", "gguf", 0, 0, None), ("g1", "gguf", 0, 0, None)])
    path = paths[1] / "g1.json"
    report = json.loads(path.read_bytes())
    report["drift"] = SafetyDrift(
        120,
        60,
        1,
        1,
        0,
        60,
        0,
        0,
        0,
        {
            "clear_unsafe": {"n": 60, "baseline_refused": 1, "quant_refused": 1},
            "clear_safe": {"n": 60, "baseline_refused": 0, "quant_refused": 0},
        },
    ).to_dict()
    path.write_text(json.dumps(report), encoding="utf-8")
    result = summarize(paths, 40)
    requirement = result["conditional_resolution_requirement"]
    assert requirement["native_exit_code"] == 0 and result["exit_code"] == 5
    assert [row["name"] for row in requirement["rows"]] == ["g0", "g1"]
    assert requirement["rows"][0]["requirement_met"] and not requirement["rows"][1]["requirement_met"]
    axis = requirement["rows"][1]["axes"]["refusal-robustness"]
    assert axis["detectable_at_target_power"] is False and "target_power_unattainable" in axis["reasons"]
    assert not requirement["requirement_met"]


def test_each_source_read_once_and_one_native_analysis_per_present_pair(tmp_path, monkeypatch):
    import quantfit.saved_screen as saved
    from quantfit import screen_resolution

    paths = inputs(tmp_path, entries=[("g0", "gguf", 0, 0, None), ("g1", "gguf", 0, 0, None)])
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    original_read = saved._read
    reads = []

    def read(path, limit):
        reads.append(Path(path))
        return original_read(path, limit)

    monkeypatch.setattr(saved, "_read", read)
    monkeypatch.setattr(screen_resolution, "_read", read)
    analysis = Mock(wraps=analyze_resolution_bytes)
    monkeypatch.setattr("quantfit.resolution.analyze_resolution_bytes", analysis)
    result = summarize(paths, 40)
    assert result["exit_code"] == 0 and analysis.call_count == 2
    assert len(reads) == len(set(reads)) == 5 and set(reads) == set(before)
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize("fault", ["wrong_scope", "duplicate", "private", "malformed", "alias"])
def test_native_preflight_refuses_bad_late_evidence_before_math_outputs(tmp_path, monkeypatch, fault):
    paths = inputs(tmp_path, entries=[("g0", "gguf", 0, 0, None), ("g1", "gguf", 0, 0, None)])
    calibration = paths[2] / "g1.json"
    if fault == "wrong_scope":
        calibration.write_bytes((paths[2] / "g0.json").read_bytes())
    elif fault == "duplicate":
        raw = calibration.read_bytes()
        calibration.write_bytes(
            raw.replace(b'"calibration_schema": 2', b'"calibration_schema": 2, "calibration_schema": 2')
        )
    elif fault == "private":
        payload = json.loads(calibration.read_bytes())
        payload["PRIVATE_EXTRA"] = {"completion": "PRIVATE_SENTINEL"}
        calibration.write_text(json.dumps(payload), encoding="utf-8")
    elif fault == "malformed":
        calibration.write_bytes(b"{PRIVATE_SENTINEL")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    analysis = Mock(side_effect=AssertionError("native math before closed preflight"))
    monkeypatch.setattr("quantfit.resolution.analyze_resolution_bytes", analysis)
    out = calibration if fault == "alias" else tmp_path / "out.json"
    with pytest.raises(SavedScreenError) as exc:
        summarize(paths, 40, out_path=str(out), junit_path=str(tmp_path / "out.xml"))
    analysis.assert_not_called()
    assert "PRIVATE_SENTINEL" not in str(exc.value)
    assert all(path.read_bytes() == raw for path, raw in before.items()) and not (tmp_path / "out.xml").exists()
    if fault != "alias":
        assert not out.exists()


def test_native_second_publication_failure_is_not_a_success_or_pair_transaction(tmp_path, monkeypatch):
    import os
    import traceback

    paths = inputs(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    out, xml = tmp_path / "out.json", tmp_path / "out.xml"
    native_replace = os.replace
    calls = []

    def replace(source, target):
        calls.append(target)
        if len(calls) == 2:
            raise OSError("PRIVATE_SENTINEL")
        return native_replace(source, target)

    monkeypatch.setattr("quantfit.reproduce.os.replace", replace)
    with pytest.raises(SavedScreenError) as exc:
        summarize(paths, 40, out_path=str(out), junit_path=str(xml))
    assert "PRIVATE_SENTINEL" not in "".join(traceback.format_exception(exc.value))
    assert out.exists() and not xml.exists() and all(path.read_bytes() == raw for path, raw in before.items())
