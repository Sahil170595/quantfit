"""CLI parser + dispatch — light commands only (no torch needed)."""

import pytest

from quantfit.cli import _build_parser, main


def test_list_runs_and_prints_methods(capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "awq" in out and "gguf" in out


def test_parser_accepts_every_command():
    p = _build_parser()
    cases = [
        ["check", "--model", "m"],
        ["list"],
        ["plan", "--model", "m"],
        ["probe", "--model", "m", "--bits", "4", "8"],
        ["verify", "--model", "p"],
        ["verify-safety", "--fp16", "a", "--quant", "b"],
        ["quantize", "--model", "m", "--method", "awq", "--out", "o"],
    ]
    for argv in cases:
        ns = p.parse_args(argv)
        assert ns.cmd == argv[0]


def test_probe_parses_multiple_bits():
    ns = _build_parser().parse_args(["probe", "--model", "m", "--bits", "4", "8"])
    assert ns.bits == [4, 8]


def test_token_flag_on_hub_commands():
    ns = _build_parser().parse_args(["check", "--model", "m", "--token", "xyz"])
    assert ns.token == "xyz"


def test_quantize_requires_method():
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["quantize", "--model", "m", "--out", "o"])  # no --method


def test_quantize_rejects_unknown_method():
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["quantize", "--model", "m", "--method", "bogus", "--out", "o"])


def test_unknown_command_rejected():
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["nonsense"])
