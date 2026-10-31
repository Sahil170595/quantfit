"""Same-process installed public API/CLI/native cards with fresh capture receiving."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "adjudication_verification_consumer", ROOT / "tools/ci_adjudication_verification.py"
)
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_actual_installed_capture_verification_and_cards_without_inference(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("verification attempted inference or asset resolution")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    result = consumer.run(ROOT, tmp_path)
    assert result["positive_cases"] == len(result["cases"]) == 10
    assert result["adverse_cases"] == len(result["adverse"]) == 20
    assert result["auxiliary_cases"] == len(result["auxiliary"]) == 4
    assert result["capture_backed_cards"] == 20 and len(result["source_hashes"]) == 17
    assert all(
        case["queue_preparation_removed_before_receiving"] and case["originals_unchanged"] for case in result["cases"]
    )
    assert result["human_confirmation_verified"] is result["scientific_go"] is False
