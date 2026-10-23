"""Actual CLI/native analyses and retained producer inside the installed-origin guard."""

import importlib.util
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
