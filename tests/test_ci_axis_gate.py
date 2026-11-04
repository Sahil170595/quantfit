"""Current native producer/strict receiving/actual OS CLI in every installed profile."""

import importlib.metadata
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("axis_gate_consumer", ROOT / "tools/ci_axis_gate.py")
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_actual_axis_gate_saved_live_cli_strict_receiving_and_junit(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("aggregate axis policy attempted real inference/assets")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    result = consumer.run(ROOT, tmp_path)
    assert {name: row["exit_code"] for name, row in result["cases"].items()} == {
        "no_detection": 0,
        "operator_not_detected": 0,
        "over_detected": 3,
        "unselected_dangerous": 0,
        "zero_risk": 4,
        "both_selected": 3,
        "policy_preflight": 5,
    }
    assert result["live_controlled_OSCLI"] == {"0": 0, "3": 3, "4": 4}
    assert result["late_invalid_preserved"] and result["forged_overall_refused"]
    assert result["additional_real_inference_calls"] == 0


@pytest.mark.parametrize("unavailable", ["torch", "transformers"])
def test_native_fixture_without_unused_backend_distribution_metadata(monkeypatch, unavailable):
    original = importlib.metadata.version
    lookups = []

    def version(name):
        lookups.append(name)
        if name == unavailable:
            raise importlib.metadata.PackageNotFoundError(name)
        return original(name)

    monkeypatch.setattr(importlib.metadata, "version", version)
    report = consumer.native_report(safe_flips=1)
    assert report.drift["n_probes"] == 40
    assert report.drift["over_refusal"]["overrefusal_regressions"] == 1
    assert report.baseline.engine["version"] == "synthetic-not-used"
    assert report.env["torch"] == report.env["transformers"] == "synthetic-not-used"
    assert unavailable not in lookups
