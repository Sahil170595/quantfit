"""Actual CLI/native analyses and retained producer inside the installed-origin guard."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("requirement_consumer", ROOT / "tools/ci_screen_requirement.py")
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_actual_installed_requirement_default_positive_adverse_and_schema3(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("receiving requirement attempted inference or assets")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    result = consumer.run(ROOT, tmp_path)
    assert {name: case["exit_code"] for name, case in result["cases"].items()} == {
        "qualified": 0,
        "coarse": 5,
        "saturated": 5,
        "missing": 4,
        "native_flagged": 3,
        "mixed_flags": 3,
        "mixed_incomplete": 4,
        "retained_schema3": 5,
    }
    assert result["retained_calibration_schema"] == 3 and result["original_sheet_unavailable_for_retained"]
    assert result["additional_native_inference_calls"] == 0 and not result["scientific_go"]
    assert {name: case["exit_code"] for name, case in result["axis_cases"].items()} == {
        "one_axis": 0,
        "unequal_axes": 0,
        "coarse": 5,
        "saturated": 5,
        "unselected_native_flag": 3,
        "unselected_native_incomplete": 4,
        "late_missing": 4,
        "retained_schema3": 5,
    }
    assert len(result["axis_cases"]["late_missing"]["requirement"]["rows"]) == 3


def test_actual_retained_schema3_requirement_composes_with_verified_control(tmp_path, monkeypatch):
    from test_screen_control_evidence import case, options

    from quantfit.junit import screen_to_junit
    from quantfit.saved_screen import summarize_screen

    def forbidden(*args, **kwargs):
        raise AssertionError("composed retained receiving attempted inference or assets")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    fixture_root = tmp_path / "native"
    fixture_root.mkdir()
    accepted = consumer.run(ROOT, fixture_root)
    assert accepted["retained_calibration_schema"] == 3 and accepted["original_sheet_unavailable_for_retained"]
    controls = case(tmp_path / "control")
    source = fixture_root / "schema3"
    manifest = json.loads((source / "targets.json").read_bytes())
    manifest["sensitivity_control"] = {"status": "pass", "report": str(controls[2]), "human_verifier": "declared"}
    native = consumer._module(ROOT, "ci_screen_resolution.py")
    paths = native.stage(
        tmp_path / "combined",
        json.dumps(manifest).encode(),
        {"clean": (source / "reports/clean.json").read_bytes()},
        {"clean": (source / "calibrations/clean.json").read_bytes()},
    )
    calibration = summarize_screen(
        str(paths[0]), str(paths[1]), calibrations_dir=str(paths[2]), required_conditional_resolution_pp=100
    )
    combined = summarize_screen(
        str(paths[0]),
        str(paths[1]),
        calibrations_dir=str(paths[2]),
        required_conditional_resolution_pp=100,
        **options(controls),
    )
    assert combined["exit_code"] == calibration["exit_code"] == 5
    assert combined["control_evidence"]["status"] == "conflicting"
    assert combined["conditional_resolution_requirement"] == calibration["conditional_resolution_requirement"]
    assert screen_to_junit(combined) == screen_to_junit(calibration)
