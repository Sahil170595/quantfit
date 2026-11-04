"""Installed same-process original-population API/CLI and actual OS entrypoint controls."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("screen_adjudication_consumer", ROOT / "tools/ci_screen_adjudication.py")
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_installed_saved_screen_adjudication_without_inference(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline adjudication screen attempted inference or asset resolution")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    value = consumer.run(ROOT, tmp_path)
    assert value["positive_cases"] == len(value["cases"]) == 24
    assert value["adverse_cases"] == len(value["adverse"]) == 46
    assert value["os_entrypoint_raw_utf8_lf_parity"] is True
    assert len(value["source_hashes"]) == 16
    assert value["human_confirmation_verified"] is value["scientific_go"] is False
