"""Installed-origin complete annotation workflow with explicit fixture labels."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("chunk_consumer", ROOT / "tools/ci_annotation_chunks.py")
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_installed_cli_api_chunks_collect_and_native_ingest(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("annotation workflow attempted inference or asset resolution")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    result = consumer.run(ROOT, tmp_path)
    assert result["preparation"]["n_rows"] == result["collection"]["n_rows"] == 18
    assert result["native_counts"]["calibration_schema"] == 2 and result["retained_calibration_schema"] == 3
    assert result["native_counts"]["n_unusable"] == 4
    assert result["missing_part_exit_code"] == 2
    assert result["api_all_unusable"] == {"n_rows": 18, "n_unusable": 18, "native_ingest_refused": True}
    assert result["originals_unchanged"] and not result["scientific_go"]
