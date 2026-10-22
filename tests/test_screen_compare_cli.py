"""Descriptive screen comparisons preserve native exit and publication semantics."""

import json
import sys
from types import SimpleNamespace

import pytest

from quantfit.cli import main


@pytest.mark.parametrize("code", [0, 3, 4])
@pytest.mark.parametrize("outputs", [False, True])
def test_screen_compare_cli_delegates_protected_outputs_and_native_verdict(monkeypatch, capsys, code, outputs):
    called = []
    result = {"kind": "quantfit.screen-comparison", "exit_code": code, "scope": "Declared observations only."}

    def compare(reference, candidate, *, out_path=None, junit_path=None):
        called.append((reference, candidate, out_path, junit_path))
        return result

    monkeypatch.setitem(sys.modules, "quantfit.screen_compare", SimpleNamespace(compare_screen_bundles=compare))
    args = ["screen-compare", "--reference-bundle", "ref", "--candidate-bundle", "cand"]
    if outputs:
        args += ["--out", "receiving.json", "--junit", "receiving.xml"]
    assert main([*args, "--json"]) == code
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert document["command"] == "screen-compare" and document["exit_code"] == code
    assert document["result"] == result and captured.err == ""
    assert called == [("ref", "cand", "receiving.json" if outputs else None, "receiving.xml" if outputs else None)]
