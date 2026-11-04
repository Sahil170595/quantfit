"""Installed-origin full named-choice CLI/API/JSON/JUnit consumer."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("choice_consumer", ROOT / "tools/ci_calibration_choices.py")
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_actual_installed_calibration_choice_cli_api_and_junit(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("calibration sensitivity attempted inference or assets")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    result = consumer.run(ROOT, tmp_path)
    assert len(result["cases"]) == 12
    assert {case["exit_code"] for case in result["cases"]} == {0, 3, 4, 5}
    assert all(case["native_population_preserved"] and case["inputs_unchanged"] for case in result["cases"])
