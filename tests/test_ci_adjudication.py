"""Installed-origin complete adjudication producer and real stdout/string card consumers."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("adjudication_consumer", ROOT / "tools/ci_adjudication.py")
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_actual_installed_adjudication_cli_api_and_both_native_cards(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("adjudication attempted inference or asset resolution")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    result = consumer.run(ROOT, tmp_path)
    assert len(result["cases"]) == 8
    assert all(
        row["originals_unchanged_through_production"] and row["synthetic_capture_removed_before_receiving"]
        for row in result["cases"]
    )
    assert all(not row["proof_limits"]["human_confirmation_verified"] for row in result["cases"])
