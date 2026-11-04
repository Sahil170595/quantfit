"""Actual installed-origin capture/full/retained diagnostic consumer, no inference."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("strata_consumer", ROOT / "tools/ci_calibration_strata.py")
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_actual_installed_strata_consumes_native_capture_and_retained_labels(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("diagnostics attempted inference or assets")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    result = consumer.run(ROOT, tmp_path)
    assert result["n_rows"] == 16 and result["full_retained_statistics_equal"]
    assert result["native_bound_loader_refused_diagnostic"]
    assert result["scientific_go"] is False
