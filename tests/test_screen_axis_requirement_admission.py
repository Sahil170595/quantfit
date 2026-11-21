"""Axis-map option admission precedes every held input and output operation."""

import contextlib
import io
import json
from collections.abc import Mapping
from unittest.mock import Mock

import pytest
from test_screen_axis_requirement import selected
from test_screen_requirement import AXES, inputs

from quantfit.cli import main
from quantfit.saved_screen import SavedScreenError, summarize_screen


@pytest.mark.parametrize(
    "value",
    [True, False, None, 0, -1, 100.01, float("nan"), float("inf"), float("-inf"), 10**1000, "40", []],
)
def test_invalid_numeric_axis_ceiling_is_categorical_before_any_io(monkeypatch, tmp_path, value):
    hold = Mock(side_effect=AssertionError("source held before invalid axis ceiling"))
    monkeypatch.setattr("quantfit.saved_screen._hold_screen_inputs", hold)
    with pytest.raises(SavedScreenError, match="invalid_conditional_resolution_requirement"):
        summarize_screen(
            "PRIVATE",
            "PRIVATE",
            calibrations_dir="PRIVATE",
            required_conditional_resolution_by_axis_pp={AXES[0]: value},
            out_path=str(tmp_path / "out.json"),
            junit_path=str(tmp_path / "out.xml"),
        )
    hold.assert_not_called()
    assert not list(tmp_path.iterdir())


class DuplicateMapping(Mapping):
    def __iter__(self):
        return iter((AXES[0], AXES[0]))

    def __len__(self):
        return 2

    def __getitem__(self, key):
        return 40


class HugeMapping(DuplicateMapping):
    def __len__(self):
        return 10**1000


@pytest.mark.parametrize(
    "mapping",
    [
        {},
        [],
        [(AXES[0], 40)],
        {"dangerous": 40},
        {True: 40},
        {AXES[0]: 40, AXES[1]: 40, "other": 40},
        DuplicateMapping(),
        HugeMapping(),
    ],
)
def test_invalid_map_shape_is_bounded_before_hold(monkeypatch, mapping):
    hold = Mock(side_effect=AssertionError("source held before map admission"))
    monkeypatch.setattr("quantfit.saved_screen._hold_screen_inputs", hold)
    with pytest.raises(SavedScreenError, match="invalid_conditional_resolution_requirement"):
        summarize_screen(
            "PRIVATE", "PRIVATE", calibrations_dir="PRIVATE", required_conditional_resolution_by_axis_pp=mapping
        )
    hold.assert_not_called()


@pytest.mark.parametrize("mode", ["no-calibration", "scalar", "control"])
def test_axis_requirement_combination_refusals_precede_source_io(monkeypatch, mode):
    hold = Mock(side_effect=AssertionError("source held before option combination admission"))
    monkeypatch.setattr("quantfit.saved_screen._hold_screen_inputs", hold)
    options = {"required_conditional_resolution_by_axis_pp": {AXES[0]: 40}}
    if mode == "scalar":
        options.update(calibrations_dir="PRIVATE", required_conditional_resolution_pp=40)
    elif mode == "control":
        options.update(control_report="PRIVATE", control_capture="PRIVATE", control_adjudication="PRIVATE")
    with pytest.raises(SavedScreenError):
        summarize_screen("PRIVATE", "PRIVATE", **options)
    hold.assert_not_called()


@pytest.mark.parametrize("mode", ["single", "variants"])
def test_direct_native_calibration_entries_also_admit_map_before_io(monkeypatch, mode):
    hold = Mock(side_effect=AssertionError("native source held before map admission"))
    monkeypatch.setattr("quantfit.saved_screen._hold_screen_inputs", hold)
    if mode == "single":
        from quantfit.screen_resolution import summarize_screen_with_resolution as invoke

        options = {"calibrations_dir": "PRIVATE"}
    else:
        from quantfit.calibration_choices import summarize_screen_with_variants as invoke

        options = {"calibration_variants": {"declared": None}}
    with pytest.raises(SavedScreenError, match="invalid_conditional_resolution_requirement"):
        invoke("PRIVATE", "PRIVATE", required_conditional_resolution_by_axis_pp={AXES[0]: 10**1000}, **options)
    hold.assert_not_called()


def test_original_mapping_is_read_once_and_copied_before_native_hold(tmp_path, monkeypatch):
    from quantfit import saved_screen

    class Original(Mapping):
        def __init__(self):
            self.values = {AXES[1]: 40, AXES[0]: 40}
            self.reads, self.iterations = [], 0

        def __iter__(self):
            self.iterations += 1
            return iter(self.values)

        def __len__(self):
            return len(self.values)

        def __getitem__(self, key):
            self.reads.append(key)
            return self.values[key]

    paths = inputs(tmp_path)
    original = Original()
    native_hold = saved_screen._hold_screen_inputs

    def hold(*args, **kwargs):
        original.values = {AXES[0]: 1, AXES[1]: 1}
        return native_hold(*args, **kwargs)

    monkeypatch.setattr(saved_screen, "_hold_screen_inputs", hold)
    result = selected(paths, original)
    requirement = result["conditional_resolution_requirement"]
    assert original.iterations == 1 and original.reads == [AXES[1], AXES[0]]
    assert requirement["selected_axes"] == list(AXES)
    assert requirement["required_conditional_resolution_by_axis_pp"] == {AXES[0]: 40.0, AXES[1]: 40.0}
    assert result["exit_code"] == 0


@pytest.mark.parametrize(
    "options",
    [
        [f"{AXES[0]}=40", f"{AXES[0]}=50"],
        [f"{AXES[0]}=40", f"{AXES[1]}=50", f"{AXES[1]}=60"],
        ["PRIVATE=40"],
        [f"{AXES[0]}="],
        [f"{AXES[0]}=nan"],
        [f"{AXES[0]}=inf"],
        [f"{AXES[0]}=True"],
        [f"{AXES[0]}=0"],
        [f"{AXES[0]}=101"],
        [f"{AXES[0]}=" + "9" * 10000],
        ["PRIVATE"],
        ["=40"],
    ],
)
def test_invalid_repeated_cli_options_are_closed_two_before_io(monkeypatch, tmp_path, options):
    hold = Mock(side_effect=AssertionError("CLI source IO before option refusal"))
    monkeypatch.setattr("quantfit.saved_screen._hold_screen_inputs", hold)
    args = [
        "screen-summary",
        "--targets",
        "PRIVATE",
        "--reports-dir",
        "PRIVATE",
        "--calibrations-dir",
        "PRIVATE",
        "--json",
        "--out",
        str(tmp_path / "out.json"),
    ]
    for value in options:
        args += ["--require-axis-conditional-resolution", value]
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(args)
    document = json.loads(stdout.getvalue())
    assert code == document["exit_code"] == 2 and document["result"] is None
    assert len(stdout.getvalue()) < 1000 and "PRIVATE" not in stdout.getvalue() + stderr.getvalue()
    assert not list(tmp_path.iterdir())
    hold.assert_not_called()


def test_cli_scalar_map_conflict_is_categorical_before_any_io(monkeypatch):
    hold = Mock(side_effect=AssertionError("CLI source IO before scalar-map refusal"))
    monkeypatch.setattr("quantfit.saved_screen._hold_screen_inputs", hold)
    args = [
        "screen-summary",
        "--targets",
        "PRIVATE",
        "--reports-dir",
        "PRIVATE",
        "--calibrations-dir",
        "PRIVATE",
        "--require-axis-conditional-resolution",
        f"{AXES[0]}=40",
        "--require-conditional-resolution",
        "40",
        "--json",
    ]
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(args)
    assert code == json.loads(stdout.getvalue())["exit_code"] == 2
    hold.assert_not_called()
