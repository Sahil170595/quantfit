"""The reconciliation leaf emits aggregate results and categorical errors only."""

import json
import sys
from types import SimpleNamespace

import pytest

from quantfit.cli import main


@pytest.mark.parametrize("json_mode", [False, True])
def test_reconciliation_cli_dispatches_private_inputs_and_emits_aggregate_result(monkeypatch, capsys, json_mode):
    calls = []
    result = {
        "kind": "quantfit.label-reconciliation",
        "n_pairs": 4,
        "arms": {
            "baseline": {"n_rows": 4, "n_usable_agreement": 2, "n_usable_disagreement": 1},
            "quantized": {"n_rows": 4, "n_usable_agreement": 1, "n_usable_disagreement": 2},
        },
        "rater_identity_verified": False,
        "independence_verified": False,
        "consensus_calibration": False,
    }

    def reconcile(a, b, key, *, out_path=None):
        calls.append((a, b, key, out_path))
        return result

    monkeypatch.setitem(sys.modules, "quantfit.safety.reconcile", SimpleNamespace(reconcile_labels=reconcile))
    args = [
        "calibrate", "reconcile", "--sheet-a", "private-a.csv", "--sheet-b", "private-b.csv",
        "--key", "private-key.json", "--out", "aggregate.json",
    ]  # fmt: skip
    assert main([*args, *(["--json"] if json_mode else [])]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert calls == [("private-a.csv", "private-b.csv", "private-key.json", "aggregate.json")]
    assert all(value not in captured.out for value in ("private-a.csv", "private-b.csv", "private-key.json"))
    if json_mode:
        document = json.loads(captured.out)
        assert document["command"] == "calibrate reconcile" and document["exit_code"] == 0
        assert document["result"] == result
    else:
        assert "baseline" in captured.out and "quantized" in captured.out
        assert "unverified" in captured.out.lower() and "aggregate.json" in captured.out


def test_reconciliation_cli_categorical_error_does_not_reflect_private_paths(monkeypatch, capsys):
    def reconcile(*args, **kwargs):
        raise RuntimeError("invalid_label_reconciliation")

    monkeypatch.setitem(sys.modules, "quantfit.safety.reconcile", SimpleNamespace(reconcile_labels=reconcile))
    args = [
        "calibrate", "reconcile", "--sheet-a", "PRIVATE-A.csv", "--sheet-b", "PRIVATE-B.csv",
        "--key", "PRIVATE-KEY.json", "--out", "aggregate.json", "--json",
    ]  # fmt: skip
    assert main(args) == 2
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    # Operational errors retain the existing parent-command JSON envelope.
    assert document["command"] == "calibrate" and document["exit_code"] == 2
    assert "invalid_label_reconciliation" in captured.out + captured.err
    assert "PRIVATE" not in captured.out + captured.err
