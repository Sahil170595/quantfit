"""Whole-population supplied-choice sensitivity, never pooled labels or best-rater selection."""

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from test_screen_requirement import inputs

from quantfit.junit import screen_to_junit
from quantfit.saved_screen import SavedScreenError, summarize_screen


def choices(tmp_path, *, entries=None, weak=False):
    manifest, reports, first = inputs(tmp_path, entries=entries)
    second = tmp_path / "other"
    second.mkdir()
    for path in first.iterdir():
        raw = path.read_bytes()
        if weak:
            from quantfit.safety.calibrate import _arm_block

            data = json.loads(raw)
            for arm in ("baseline", "quantized"):
                data[arm] = _arm_block(
                    {
                        "n": 120,
                        "n_unusable": 0,
                        "human_refusals": 60,
                        "human_compliances": 60,
                        "judge_refusal_human_compliance": 30,
                        "judge_compliance_human_refusal": 30,
                    }
                )
            raw = json.dumps(data).encode()
        (second / path.name).write_bytes(raw)
    return manifest, reports, {"first": str(first), "second": str(second)}


def summary(paths, ceiling=None, **kwargs):
    manifest, reports, variants = paths
    return summarize_screen(
        str(manifest), str(reports), calibration_variants=variants, required_conditional_resolution_pp=ceiling, **kwargs
    )


def test_no_requirement_preserves_native_once_and_adds_skipped_variant_cases(tmp_path, monkeypatch):
    import quantfit.saved_screen as saved

    paths = choices(tmp_path)
    native = summarize_screen(str(paths[0]), str(paths[1]))
    calls = []
    old = saved._summarize_held

    def held(*args, **kwargs):
        calls.append(1)
        return old(*args, **kwargs)

    monkeypatch.setattr(saved, "_summarize_held", held)
    result = summary(paths)
    assert calls == [1] and result["exit_code"] == native["exit_code"] == 0
    projection = {
        k: v
        for k, v in result.items()
        if k not in ("calibration_choice_sensitivity", "calibration_choice_requirement", "created_utc")
    }
    assert projection == {k: v for k, v in native.items() if k != "created_utc"}
    block = result["calibration_choice_sensitivity"]
    assert block["variants"] == ["first", "second"] and block["coverage"]["expected"] == 2
    assert len(block["digest_copy_groups"]) == 1
    assert block["envelopes"][0]["axes"]["refusal-robustness"]["attainable"] == 2
    cases = list(ET.fromstring(screen_to_junit(result)).iter("testcase"))
    old_cases = list(ET.fromstring(screen_to_junit(native)).iter("testcase"))
    assert ET.tostring(cases[0]) == ET.tostring(old_cases[0])
    assert len(cases) == 6 and all(c.find("skipped") is not None for c in cases[1:])


def test_explicit_all_choice_requirement_keeps_native_and_unattainable_envelope(tmp_path):
    paths = choices(tmp_path, weak=True)
    result = summary(paths, 40)
    assert result["exit_code"] == 5 and result["outcome"] == "conditional_no_detection"
    req = result["calibration_choice_requirement"]
    assert req["native_exit_code"] == 0
    assert req["rows"][0]["requirement_met"] is True and req["rows"][1]["requirement_met"] is False
    for block in result["calibration_choice_sensitivity"]["envelopes"][0]["axes"].values():
        assert block["expected"] == block["analyzed"] == block["measurable"] == 2
        assert block["attainable"] == 1 and block["incomplete"] is True
        assert block["effective_mde_pp_max"] < 100
    assert "target_power_unattainable" in req["reasons"]


def test_declared_missing_variant_remains_coverage_and_only_explicit_gate_changes_exit(tmp_path):
    paths = choices(tmp_path)
    paths[2]["second"] = None
    descriptive = summary(paths)
    assert descriptive["exit_code"] == 0
    assert descriptive["calibration_choice_sensitivity"]["variants"] == ["first", "second"]
    required = summary(paths, 40)
    assert required["exit_code"] == 4
    assert required["calibration_choice_requirement"]["native_exit_code"] == 0
    assert required["calibration_choice_sensitivity"]["coverage"]["expected"] == 2


@pytest.mark.parametrize("entries,code", [([("g0", "gguf", 1, 0, None)], 3), ([("g0", "gguf", 0, 0, "danger")], 4)])
def test_native_adverse_outcome_wins_over_all_variant_criteria(tmp_path, entries, code):
    result = summary(choices(tmp_path, entries=entries, weak=True), 40)
    assert result["exit_code"] == result["calibration_choice_requirement"]["native_exit_code"] == code


def test_late_bad_variant_refuses_before_any_earlier_resolution_math(tmp_path, monkeypatch):
    paths = choices(tmp_path)
    (Path(paths[2]["second"]) / "g0.json").write_bytes(b'{"PRIVATE invalid"')

    def forbidden(*args, **kwargs):
        raise AssertionError("variant math ran before complete admission")

    monkeypatch.setattr("quantfit.resolution._analysis", forbidden)
    with pytest.raises(SavedScreenError):
        summary(paths, 40, out_path=str(tmp_path / "out.json"))
    assert not (tmp_path / "out.json").exists()


def trap_math(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("conditional math ran before complete variant admission")

    monkeypatch.setattr("quantfit.resolution._analysis", forbidden)


def test_global_inventory_budget_refuses_before_any_calibration_read(tmp_path, monkeypatch):
    import quantfit.calibration_choices as choice
    from quantfit import screen_resolution

    paths = choices(tmp_path)
    sizes = sum((Path(directory) / "g0.json").stat().st_size for directory in paths[2].values())
    monkeypatch.setattr(screen_resolution, "MAX_TOTAL_CALIBRATION_BYTES", sizes - 1)

    def forbidden(*args, **kwargs):
        raise AssertionError("calibration payload read before GLOBAL inventory admission")

    monkeypatch.setattr(choice, "_read", forbidden)
    trap_math(monkeypatch)
    with pytest.raises(SavedScreenError, match="calibration_byte_limit"):
        summary(paths)


def test_actual_read_growth_cannot_exceed_global_remaining_budget(tmp_path, monkeypatch):
    import quantfit.calibration_choices as choice
    from quantfit import screen_resolution

    paths = choices(tmp_path)
    size = sum((Path(directory) / "g0.json").stat().st_size for directory in paths[2].values())
    monkeypatch.setattr(screen_resolution, "MAX_TOTAL_CALIBRATION_BYTES", size)
    old = choice._read
    calls = []

    def grow(path, limit):
        if not calls:
            path.write_bytes(path.read_bytes() + b"\n")
        calls.append(path)
        return old(path, limit)

    monkeypatch.setattr(choice, "_read", grow)
    trap_math(monkeypatch)
    with pytest.raises(SavedScreenError):
        summary(paths)


def test_work_budget_is_one_sum_across_variants_and_does_not_reset(tmp_path, monkeypatch):
    from quantfit import screen_resolution

    paths = choices(tmp_path)
    monkeypatch.setattr(screen_resolution, "MAX_ANALYSIS_WORK_UNITS", 2 * 120**2 - 1)
    trap_math(monkeypatch)
    with pytest.raises(SavedScreenError, match="resolution_work_limit"):
        summary(paths)


def test_same_directory_is_held_once_but_charged_logically_and_copies_visible(tmp_path, monkeypatch):
    import quantfit.calibration_choices as choice

    paths = choices(tmp_path)
    paths[2]["second"] = paths[2]["first"]
    old = choice._read
    calls = []

    def read(path, limit):
        calls.append(path)
        return old(path, limit)

    monkeypatch.setattr(choice, "_read", read)
    result = summary(paths, 40)
    assert len(calls) == 1 and result["exit_code"] == 0
    block = result["calibration_choice_sensitivity"]
    assert block["analysis_work_units"] == 2 * 120**2 and len(block["digest_copy_groups"]) == 1


def test_bad_supplied_path_is_refusal_but_explicit_missing_is_coverage(tmp_path, monkeypatch):
    paths = choices(tmp_path)
    paths[2]["second"] = str(tmp_path / "missing-directory")
    trap_math(monkeypatch)
    with pytest.raises(SavedScreenError):
        summary(paths)


@pytest.mark.parametrize("variants", [{}, {"bad:name": None}, {"x": ""}, {"x": 3}, {str(i): None for i in range(9)}])
def test_entire_variant_option_mapping_is_admitted_before_native_io(tmp_path, monkeypatch, variants):
    def forbidden(*args, **kwargs):
        raise AssertionError("native IO happened before variant option validation")

    monkeypatch.setattr("quantfit.saved_screen._hold_screen_inputs", forbidden)
    with pytest.raises(SavedScreenError):
        summarize_screen("missing", "missing", calibration_variants=variants)


@pytest.mark.parametrize("state", ["pending", "wrong_target", "orphan"])
def test_every_provided_calibration_even_without_report_is_prevalidated(tmp_path, monkeypatch, state):
    paths = choices(tmp_path)
    (paths[1] / "g0.json").unlink()
    second = Path(paths[2]["second"]) / "g0.json"
    if state == "orphan":
        second.rename(second.with_name("foreign.json"))
    elif state == "wrong_target":
        from quantfit.safety.calibration_binding import identity_fingerprint

        data = json.loads(second.read_bytes())
        data["binding"]["identity"]["baseline"]["model"] = "foreign"
        data["binding"]["fingerprint"] = identity_fingerprint(data["binding"]["identity"])
        second.write_text(json.dumps(data), encoding="utf-8")
    trap_math(monkeypatch)
    if state != "pending":
        with pytest.raises(SavedScreenError):
            summary(paths)
    else:
        result = summary(paths, 40)
        assert result["exit_code"] == 4
        assert all(
            row["status"] == "pending_report_missing" and row["analysis"] is None
            for row in result["calibration_choice_sensitivity"]["rows"]
        )


@pytest.mark.parametrize("sink", ["second_input", "second_root", "native_input", "same_outputs"])
def test_every_variant_and_native_source_protects_both_outputs_before_math(tmp_path, monkeypatch, sink):
    paths = choices(tmp_path)
    second = Path(paths[2]["second"])
    target = {
        "second_input": second / "g0.json",
        "second_root": second / "new.json",
        "native_input": paths[1] / "g0.json",
        "same_outputs": tmp_path / "same",
    }[sink]
    trap_math(monkeypatch)
    with pytest.raises(SavedScreenError):
        summary(paths, 40, out_path=str(target), junit_path=str(target) if sink == "same_outputs" else None)


def test_missing_calibration_and_unmet_criterion_keep_simultaneous_reasons(tmp_path):
    paths = choices(tmp_path, weak=True)
    (Path(paths[2]["first"]) / "g0.json").unlink()
    result = summary(paths, 40)
    assert result["exit_code"] == 4
    reasons = result["calibration_choice_requirement"]["reasons"]
    assert "calibration_missing" in reasons and "target_power_unattainable" in reasons


def test_each_variant_uses_frozen_native_zero_after_an_earlier_unmet_choice(tmp_path):
    paths = choices(tmp_path, weak=True)
    variants = paths[2]
    paths = (*paths[:2], {"weak": variants["second"], "strong": variants["first"]})
    result = summary(paths, 40)
    rows = result["calibration_choice_requirement"]["rows"]
    assert [row["variant"] for row in rows] == ["weak", "strong"]
    assert [row["requirement_met"] for row in rows] == [False, True]
    assert result["calibration_choice_requirement"]["native_exit_code"] == 0 and result["exit_code"] == 5


def test_output_budget_also_applies_to_api_return_without_files(tmp_path, monkeypatch):
    import quantfit.calibration_choices as choice

    paths = choices(tmp_path)
    monkeypatch.setattr(choice, "MAX_OUTPUT_BYTES", 1)
    with pytest.raises(SavedScreenError, match="variant_output_byte_limit"):
        summary(paths)


def test_all_unattainable_envelopes_are_null_and_no_ceiling_is_not_a_gate(tmp_path):
    paths = choices(tmp_path, weak=True)
    paths[2]["first"] = paths[2]["second"]
    result = summary(paths)
    assert result["exit_code"] == 0
    for target in result["calibration_choice_sensitivity"]["envelopes"]:
        for axis in target["axes"].values():
            assert (
                axis["attainable"] == 0
                and axis["effective_mde_pp_min"] is None
                and axis["effective_mde_pp_max"] is None
            )
    assert all(
        case.find("skipped") is not None for case in list(ET.fromstring(screen_to_junit(result)).iter("testcase"))[1:]
    )


@pytest.mark.parametrize("options", [["duplicate=-", "duplicate=-"], ["missing_equals"], ["empty="], ["bad:name=-"]])
def test_invalid_cli_variant_options_refuse_before_native_io(tmp_path, monkeypatch, capsys, options):
    from quantfit.cli import main

    def forbidden(*args, **kwargs):
        raise AssertionError("bad CLI mapping reached native IO")

    monkeypatch.setattr("quantfit.saved_screen._hold_screen_inputs", forbidden)
    args = ["screen-summary", "--targets", "missing", "--reports-dir", "missing", "--json"]
    for option in options:
        args += ["--calibration-variant", option]
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["error"]["message"] == "invalid_calibration_variants"


def test_cli_and_api_modes_are_mutually_exclusive_before_io(tmp_path, monkeypatch):
    from quantfit.cli import main

    def forbidden(*args, **kwargs):
        raise AssertionError("mixed modes reached IO")

    monkeypatch.setattr("quantfit.saved_screen._hold_screen_inputs", forbidden)
    with pytest.raises(SavedScreenError):
        summarize_screen("missing", "missing", calibrations_dir="single", calibration_variants={"variant": None})
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "screen-summary",
                "--targets",
                "missing",
                "--reports-dir",
                "missing",
                "--calibrations-dir",
                "single",
                "--calibration-variant",
                "variant=-",
            ]
        )
    assert exc.value.code == 2


def test_inventory_addition_before_publication_refuses_without_reanalysis(tmp_path, monkeypatch):
    import quantfit.calibration_choices as choice

    paths = choices(tmp_path)
    member = Path(paths[2]["second"]) / "g0.json"
    held_bytes = member.read_bytes()
    member.unlink()
    native = choice._publish_reproduction_outputs

    def raced(plan, buffers, *, recheck):
        member.write_bytes(held_bytes)
        return native(plan, buffers, recheck=recheck)

    monkeypatch.setattr(choice, "_publish_reproduction_outputs", raced)
    out = tmp_path / "out.json"
    with pytest.raises(SavedScreenError):
        summary(paths, out_path=str(out))
    assert not out.exists()
