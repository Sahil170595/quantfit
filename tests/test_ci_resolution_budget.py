"""Actual installed CLI/API finite planning remains separate from original analysis."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("budget_consumer", ROOT / "tools/ci_resolution_budget.py")
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_actual_installed_resolution_budget_cli_and_api(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("planning attempted inference or asset download")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    result = consumer.run(ROOT, tmp_path)
    assert set(result["interfaces"]) == {"cli", "api"}
    assert result["actual_inputs_unchanged"] and result["no_feasible_grid_analysis_completed"]
    for record in result["interfaces"].values():
        assert record["actual_analysis_preserved"] and record["exit_code"] == 0
        assert record["curve_point_count"] == record["planning"]["grid"]["n_points"] == 129
