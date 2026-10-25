"""Actual installed-origin capture-backed review and separate native consumers."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("retained_review_consumer", ROOT / "tools/ci_retained_review.py")
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_actual_installed_capture_backed_retained_review_cli_and_api(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("retained review attempted inference or asset resolution")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    result = consumer.run(ROOT, tmp_path)
    assert set(result["interfaces"]) == {"cli", "api"}
    for record in result["interfaces"].values():
        assert record["preparation"]["n_selected"] == 12
        assert record["application"]["n_reviewed"] == 12
        assert record["native_counts"]["n_labeled"] == 18
        assert record["native_counts"]["n_unusable"] == 4
        assert record["separate_truthful_extract_and_schema3"]
        assert record["original_retained_inputs_unchanged"] and record["original_synthetic_sheets_unavailable"]
