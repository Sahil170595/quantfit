"""Installed-origin review producer/application and unchanged native calibration consumer."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("review_consumer", ROOT / "tools/ci_label_review.py")
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_actual_installed_review_prepare_apply_and_native_ingest(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("review workflow attempted inference or asset resolution")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    result = consumer.run(ROOT, tmp_path)
    assert result["preparation"]["n_selected"] == 12
    assert result["application"]["n_changed_vs_a"] == 10
    assert result["partial_review_native_ingest_exit_code"] == 2
    assert result["complete_reviewed_native_ingest_exit_code"] == 0
    assert result["native_ingest_counts"]["calibration_schema"] == 2
    assert result["native_ingest_counts"]["baseline"]["n"] == result["native_ingest_counts"]["quantized"]["n"] == 7
    assert result["originals_unchanged"] and result["synthetic_operator_labels"]
