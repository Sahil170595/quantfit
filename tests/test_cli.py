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


def test_verify_safety_accepts_baseline_and_legacy_fp16_alias():
    ns = _build_parser().parse_args(["verify-safety", "--baseline", "a", "--quant", "b"])
    assert ns.baseline == "a"
    legacy = _build_parser().parse_args(["verify-safety", "--fp16", "a", "--quant", "b"])
    assert legacy.baseline == "a"  # 0.1-0.3 invocations keep working


def _drift(baseline_flags, quant_flags, probes):
    from quantfit.safety.verify import _tabulate

    return _tabulate(probes, baseline_flags, quant_flags)


def test_verify_safety_exit_codes_are_the_ci_contract(monkeypatch):
    # 0 = measured + no regression, 3 = regression, 4 = axis unmeasurable.
    import quantfit.safety.verify as sv
    from quantfit.safety.verify import Probe

    probes = [Probe("u", "clear_unsafe", "unsafe"), Probe("s", "clear_safe", "safe")]
    cases = [
        (_drift([True, False], [True, False], probes), 0),  # clean, both axes measured
        (_drift([True, False], [False, False], probes), 3),  # dangerous flip
        (_drift([False, False], [False, False], probes), 4),  # dangerous axis unmeasurable
        (_drift([False, False], [False, True], probes), 3),  # regression outranks unmeasurable
    ]
    for drift, expected in cases:
        monkeypatch.setattr(sv, "verify_safety", lambda *a, _d=drift, **k: _d)
        assert main(["verify-safety", "--baseline", "a", "--quant", "b"]) == expected


def test_check_exit_codes(monkeypatch):
    # 0 = fits, 3 = won't-fit verdict, 2 = operational error — never conflated.
    import quantfit.fit as fit_mod
    from quantfit.fit import LIMIT_MACHINE, MODE_GPU, MODE_REFUSE, CapacityPlan

    gib = 1024**3

    def cap(mode, limit=""):
        return CapacityPlan("m", 3 * gib, 11 * gib, 32 * gib, 100 * gib, 5 * gib, mode, limit)

    monkeypatch.setattr(fit_mod, "capacity_plan", lambda *a, **k: cap(MODE_GPU))
    assert main(["check", "--model", "m"]) == 0
    monkeypatch.setattr(fit_mod, "capacity_plan", lambda *a, **k: cap(MODE_REFUSE, LIMIT_MACHINE))
    assert main(["check", "--model", "m"]) == 3

    def _operational(*a, **k):
        raise RuntimeError("no weight-file sizes found via Hub metadata")

    monkeypatch.setattr(fit_mod, "capacity_plan", _operational)
    assert main(["check", "--model", "m"]) == 2


def test_verify_exit_code_for_failed_smoke(monkeypatch):
    import quantfit.verify as v

    monkeypatch.setattr(v, "verify", lambda *a, **k: (False, "did not generate"))
    assert main(["verify", "--model", "x"]) == 3
