"""Installed-origin complete paired CLI workflow and native consumer refusal."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("paired_consumer", ROOT / "tools/ci_calibration_paired.py")
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_installed_native_paired_consumer_preserves_common_population_and_refuses_gate_replacement(
    tmp_path, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("paired diagnostic attempted inference or asset resolution")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    result = consumer.run(ROOT, tmp_path)
    assert result["n_pairs"] == 24 and result["n_rows"] == 48
    assert result["paired"]["coverage"]["n_pairs_both_usable"] == 21
    assert result["full_retained_statistics_equal"] and result["original_sheet_unavailable_for_retained"]
    assert result["native_bound_loader_refused_diagnostic"]
    assert result["native_gate_refused_diagnostic_exit_code"] == 2 and result["scientific_go"] is False
