"""Portable installed/source entry for the complete controlled corpus consumer."""

import importlib.util
from pathlib import Path


def test_current_corpus_consumer_uses_native_receivers_and_actual_cli(tmp_path):
    path = Path(__file__).resolve().parents[1] / "tools/ci_corpus_gate.py"
    spec = importlib.util.spec_from_file_location("ci_corpus_gate", path)
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    result = consumer.run(tmp_path / "work")
    assert result["live_native_gate_codes"] == [0, 3, 4]
    assert result["complete_resume_offline"] and result["late_invalid_preserves_output"]
