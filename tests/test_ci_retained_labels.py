"""Installed-origin acceptance uses actual native producer, retained CLI and resolution."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("retained_consumer", ROOT / "tools/ci_retained_labels.py")
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_actual_retained_cli_native_resolution_without_original_sheet(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline retained workflow attempted inference or asset access")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    result = consumer.run(ROOT, tmp_path)
    assert result["n_rows"] == 80 and result["n_pairs"] == 40
    assert result["legacy_statistics_equal"] and result["original_sheet_unavailable"]
    assert result["scientific_go"] is result["human_labels_authenticated"] is False
