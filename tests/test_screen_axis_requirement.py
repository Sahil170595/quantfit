"""Selected-axis receiving ceilings reuse every original native conditional analysis."""

import contextlib
import io
import json
from pathlib import Path
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest
from test_calibration_choices import choices
from test_screen_requirement import AXES, inputs, summarize

from quantfit.cli import main
from quantfit.junit import screen_to_junit
from quantfit.saved_screen import summarize_screen


def selected(paths, ceilings, **kwargs):
    manifest, reports, calibrations = paths
    mode = (
        {"calibration_variants": calibrations}
        if isinstance(calibrations, dict)
        else {"calibrations_dir": str(calibrations)}
    )
    return summarize_screen(
        str(manifest), str(reports), required_conditional_resolution_by_axis_pp=ceilings, **mode, **kwargs
    )


def native_ceilings(paths):
    row = summarize(paths)["conditional_resolution"]["rows"][0]
    return {name: row["analysis"]["axes"][name]["resolution"]["effective_mde"] * 100 for name in AXES}


def test_unequal_exact_axis_ceilings_preserve_native_analyses_and_junit_prefix(tmp_path):
    paths = inputs(tmp_path, unsafe=40)
    ceilings = native_ceilings(paths)
    assert ceilings[AXES[0]] > ceilings[AXES[1]]
    native = summarize(paths)
    result = selected(paths, dict(reversed(list(ceilings.items()))))
    requirement = result["conditional_resolution_requirement"]
    assert result["exit_code"] == requirement["native_exit_code"] == 0
    assert requirement["screen_resolution_requirement_schema_version"] == 2
    assert requirement["selected_axes"] == list(AXES)
    assert list(requirement["required_conditional_resolution_by_axis_pp"]) == list(AXES)
    assert requirement["required_conditional_resolution_by_axis_pp"] == ceilings
    assert "required_conditional_resolution_pp" not in requirement
    assert all(check["requirement_met"] for check in requirement["rows"][0]["axes"].values())
    original = list(ET.fromstring(screen_to_junit(native)).iter("testcase"))
    current = list(ET.fromstring(screen_to_junit(result)).iter("testcase"))
    assert [ET.tostring(case) for case in current[: len(original)]] == [ET.tostring(case) for case in original]
    assert len(current) == len(original) + len(AXES) + 1


def test_one_selected_axis_can_pass_when_the_legacy_scalar_rejects_other_axis(tmp_path):
    paths = inputs(tmp_path, unsafe=40)
    ceilings = native_ceilings(paths)
    middle = sum(ceilings.values()) / 2
    assert summarize(paths, middle)["exit_code"] == 5
    result = selected(paths, {AXES[1]: middle})
    requirement = result["conditional_resolution_requirement"]
    assert result["exit_code"] == 0 and requirement["requirement_met"]
    assert requirement["selected_axes"] == [AXES[1]]
    assert list(requirement["rows"][0]["axes"]) == [AXES[1]]
    assert len(list(ET.fromstring(screen_to_junit(result)).iter("testcase"))) == 3


def test_late_target_in_late_variant_is_not_hidden_by_earlier_selected_passes(tmp_path):
    paths = choices(tmp_path, entries=[(f"g{i}", "gguf", 0, 0, None) for i in range(3)])
    (Path(paths[2]["second"]) / "g2.json").unlink()
    result = selected(paths, {AXES[1]: 40})
    requirement = result["calibration_choice_requirement"]
    assert requirement["calibration_choice_requirement_schema_version"] == 2
    assert result["exit_code"] == 4 and requirement["native_exit_code"] == 0
    assert [(row["name"], row["variant"]) for row in requirement["rows"]] == [
        (f"g{i}", variant) for i in range(3) for variant in ("first", "second")
    ]
    assert requirement["rows"][-1]["axes"][AXES[1]]["reasons"] == ["calibration_missing"]
    assert all(row["requirement_met"] for row in requirement["rows"][:-1])
    assert all(list(row["axes"]) == [AXES[1]] for row in requirement["rows"])
    assert result["calibration_choice_sensitivity"]["coverage"]["expected"] == 6


def test_repeated_cli_axis_requirements_emit_selected_json_and_saved_junit(tmp_path):
    paths = inputs(tmp_path)
    out, xml = tmp_path / "receiving.json", tmp_path / "receiving.xml"
    args = [
        "screen-summary",
        "--targets",
        str(paths[0]),
        "--reports-dir",
        str(paths[1]),
        "--calibrations-dir",
        str(paths[2]),
        "--require-axis-conditional-resolution",
        f"{AXES[1]}=40",
        "--require-axis-conditional-resolution",
        f"{AXES[0]}=50",
        "--out",
        str(out),
        "--junit",
        str(xml),
        "--json",
    ]
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(args)
    document = json.loads(stdout.getvalue())
    assert code == document["exit_code"] == 0 and not stderr.getvalue()
    result = document["result"]
    assert result == json.loads(out.read_bytes())
    assert result["conditional_resolution_requirement"]["selected_axes"] == list(AXES)
    assert xml.read_text(encoding="utf-8") == screen_to_junit(result)


@pytest.mark.parametrize("variants", [False, True])
@pytest.mark.parametrize("native,code", [("flagged", 3), ("unmeasured", 4)])
def test_unselected_axis_native_adverse_verdict_keeps_priority(tmp_path, variants, native, code):
    entries = [("g0", "gguf", int(native == "flagged"), 0, "danger" if native == "unmeasured" else None)]
    paths = choices(tmp_path, entries=entries) if variants else inputs(tmp_path, entries=entries)
    result = selected(paths, {AXES[1]: 40})
    requirement = result["calibration_choice_requirement" if variants else "conditional_resolution_requirement"]
    assert result["exit_code"] == requirement["native_exit_code"] == code
    assert all(row["axes"][AXES[1]]["requirement_met"] for row in requirement["rows"])
    assert requirement["reasons"] == ["native_flags_detected" if code == 3 else "native_evidence_incomplete"]


def test_missing_calibration_four_precedes_an_earlier_selected_unmet_five(tmp_path):
    paths = choices(tmp_path, entries=[(f"g{i}", "gguf", 0, 0, None) for i in range(3)])
    (Path(paths[2]["second"]) / "g2.json").unlink()
    result = selected(paths, {AXES[1]: 1})
    requirement = result["calibration_choice_requirement"]
    assert result["exit_code"] == 4 and requirement["native_exit_code"] == 0
    assert "resolution_exceeds_requirement" in requirement["rows"][0]["axes"][AXES[1]]["reasons"]
    assert requirement["rows"][-1]["axes"][AXES[1]]["reasons"] == ["calibration_missing"]
    assert len(requirement["rows"]) == 6


def test_actual_default_power_sentinel_one_never_qualifies_at_hundred_pp(tmp_path):
    result = selected(inputs(tmp_path, n=40), {AXES[0]: 100})
    observed = result["conditional_resolution"]["rows"][0]["analysis"]["axes"][AXES[0]]
    checked = result["conditional_resolution_requirement"]["rows"][0]["axes"][AXES[0]]
    assert observed["resolution"]["effective_mde"] == 1.0 and observed["measurable"]
    assert observed["detectable_at_target_power"] is False
    assert result["exit_code"] == 5 and checked["reasons"] == ["target_power_unattainable"]


def test_genuine_native_attainable_one_boundary_is_not_rejected_as_a_sentinel():
    from quantfit.safety.mde import mde_block, power_at
    from quantfit.screen_requirement import _check_axis

    target = power_at(1.0, 1, 0.01)
    block = mde_block(1, 0.005, 0.005, "synthetic declared directional upper bounds", power=target)
    observed = {
        "measurable": True,
        "detectable_at_target_power": power_at(1.0, 1, block["false_flip_rate_bound"]) >= block["power"],
        "resolution": block,
    }
    assert block["effective_mde"] == 1.0 and observed["detectable_at_target_power"] is True
    assert _check_axis(observed, True, True, 100)["requirement_met"]
    assert _check_axis(observed, True, True, 99)["reasons"] == ["resolution_exceeds_requirement"]


@pytest.mark.parametrize("variants", [False, True])
def test_all_original_sources_read_once_and_native_analysis_not_replayed(tmp_path, monkeypatch, variants):
    from quantfit import calibration_choices, resolution, saved_screen, screen_resolution

    entries = [(f"g{i}", "gguf", 0, 0, None) for i in range(2)]
    paths = choices(tmp_path, entries=entries) if variants else inputs(tmp_path, entries=entries)
    if variants:
        paths[2]["second"] = paths[2]["first"]
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    native_read = saved_screen._read
    reads = []

    def read(path, limit):
        reads.append(Path(path))
        return native_read(path, limit)

    for module in (saved_screen, screen_resolution, calibration_choices):
        monkeypatch.setattr(module, "_read", read)
    analysis = Mock(wraps=resolution._analysis)
    monkeypatch.setattr(resolution, "_analysis", analysis)
    result = selected(paths, {AXES[1]: 40})
    assert result["exit_code"] == 0 and len(reads) == len(set(reads)) == 5
    assert analysis.call_count == (4 if variants else 2)
    if variants:
        assert result["calibration_choice_sensitivity"]["analysis_work_units"] == 4 * 120**2
        assert len(result["calibration_choice_requirement"]["rows"]) == 4
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize("role", ["manifest", "report", "calibration", "same-output"])
@pytest.mark.parametrize("sink", ["out", "junit"])
def test_selected_outputs_retain_native_alias_guards_before_analysis(tmp_path, monkeypatch, role, sink):
    from quantfit.saved_screen import SavedScreenError

    paths = inputs(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    target = {
        "manifest": paths[0],
        "report": paths[1] / "g0.json",
        "calibration": paths[2] / "g0.json",
        "same-output": tmp_path / "both",
    }[role]
    options = {sink + "_path": str(target)}
    if role == "same-output":
        options = {"out_path": str(target), "junit_path": str(target)}
    analysis = Mock(side_effect=AssertionError("analysis before destination admission"))
    monkeypatch.setattr("quantfit.resolution._analysis", analysis)
    with pytest.raises(SavedScreenError):
        selected(paths, {AXES[0]: 40}, **options)
    analysis.assert_not_called()
    assert all(path.read_bytes() == raw for path, raw in before.items())


def test_selected_human_requirement_is_explicit_and_preserves_native_headline(tmp_path):
    paths = inputs(tmp_path)
    args = [
        "screen-summary",
        "--targets",
        str(paths[0]),
        "--reports-dir",
        str(paths[1]),
        "--calibrations-dir",
        str(paths[2]),
        "--require-axis-conditional-resolution",
        f"{AXES[1]}=30",
    ]
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(args)
    text = stdout.getvalue()
    assert code == 5 and not stderr.getvalue()
    assert text.index("over-refusal=30 pp — UNMET") < text.index("conditional_no_detection")
    assert "Qualification exit 5; native exit 0" in text


@pytest.mark.parametrize("variants", [False, True])
def test_late_missing_native_report_retains_original_selected_rows_and_native_skip(tmp_path, variants):
    entries = [(f"g{i}", "gguf", 0, 0, None) for i in range(3)]
    paths = choices(tmp_path, entries=entries) if variants else inputs(tmp_path, entries=entries)
    (paths[1] / "g2.json").unlink()
    result = selected(paths, {AXES[1]: 40})
    requirement = result["calibration_choice_requirement" if variants else "conditional_resolution_requirement"]
    assert result["exit_code"] == requirement["native_exit_code"] == 4
    assert len(requirement["rows"]) == (6 if variants else 3)
    late = [row for row in requirement["rows"] if row["name"] == "g2"]
    assert all(row["axes"][AXES[1]]["reasons"] == ["report_missing"] for row in late)
    cases = list(ET.fromstring(screen_to_junit(result)).iter("testcase"))
    assert cases[2].find("skipped") is not None


@pytest.mark.parametrize("fault", ["private", "wrong-scope", "alias"])
def test_late_variant_private_scope_and_alias_refusal_precedes_all_analysis(tmp_path, monkeypatch, fault):
    from quantfit.saved_screen import SavedScreenError

    paths = choices(tmp_path, entries=[(f"g{i}", "gguf", 0, 0, None) for i in range(2)])
    late = Path(paths[2]["second"]) / "g1.json"
    if fault == "private":
        payload = json.loads(late.read_bytes())
        payload["PRIVATE"] = {"completion": "PRIVATE_CANARY"}
        late.write_text(json.dumps(payload), encoding="utf-8")
    elif fault == "wrong-scope":
        late.write_bytes((Path(paths[2]["first"]) / "g0.json").read_bytes())
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    out = late if fault == "alias" else tmp_path / "out.json"
    analysis = Mock(side_effect=AssertionError("analysis ran before late variant admission"))
    monkeypatch.setattr("quantfit.resolution._analysis", analysis)
    with pytest.raises(SavedScreenError) as caught:
        selected(paths, {AXES[0]: 40}, out_path=str(out), junit_path=str(tmp_path / "out.xml"))
    assert "PRIVATE_CANARY" not in str(caught.value)
    analysis.assert_not_called()
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert not (tmp_path / "out.xml").exists()


def test_named_choice_human_map_requirement_is_explicit(tmp_path):
    paths = choices(tmp_path)
    args = [
        "screen-summary",
        "--targets",
        str(paths[0]),
        "--reports-dir",
        str(paths[1]),
        "--require-axis-conditional-resolution",
        f"{AXES[1]}=30",
    ]
    for name, path in paths[2].items():
        args += ["--calibration-variant", f"{name}={path}"]
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(args)
    text = stdout.getvalue()
    assert code == 5 and not stderr.getvalue()
    assert "over-refusal=30 pp — UNMET" in text and "g0 first over-refusal" in text
    assert "g0 second over-refusal" in text and "Qualification exit 5; native exit 0" in text
