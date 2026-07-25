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
        ["screen", "--targets", "t.json", "--out", "d"],
        ["emit", "model-card", "--report", "r.json"],
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


def _screen_summary(status, n_measured=1, n_regressed=0):
    axis = {
        "n_measured": n_measured,
        "n_regressed": n_regressed,
        "n_regressed_human_verified": 0,
        "prevalence_bound_wilson95": [0.0, 1.0],
        "conditionality": None,
    }
    return {
        "rows": [{"status": status}],
        "by_stratum": {
            "gguf": {
                "n_targets": 1,
                "n_completed": 1,
                "n_operational_errors": 0,
                "refusal_robustness": dict(axis),
                "over_refusal": dict(axis),
            }
        },
    }


def test_screen_exit_codes_mirror_the_verify_safety_contract(monkeypatch):
    # 0 = clean, 3 = a regression row, 4 = unmeasured axis or row, 2 = ScreenError.
    import quantfit.screen as sc

    cases = [
        (_screen_summary("no_regression"), 0),
        (_screen_summary("regression", n_regressed=1), 3),
        (_screen_summary("unmeasurable"), 4),
        (_screen_summary("no_regression", n_measured=0), 4),  # axis nothing was measured on
    ]
    for summary, expected in cases:
        monkeypatch.setattr(sc, "run_screen", lambda *a, _s=summary, **k: _s)
        assert main(["screen", "--targets", "t.json", "--out", "d"]) == expected

    def _operational(*a, **k):
        raise sc.ScreenError("target manifest t.json has schema_version None")

    monkeypatch.setattr(sc, "run_screen", _operational)
    assert main(["screen", "--targets", "t.json", "--out", "d"]) == 2


def test_emit_model_card_prints_the_fragment(monkeypatch, capsys):
    import quantfit.modelcard as mc

    monkeypatch.setattr(mc, "model_card_fragment", lambda path: "## fragment\n")
    assert main(["emit", "model-card", "--report", "r.json"]) == 0
    assert capsys.readouterr().out == "## fragment\n"


def test_emit_refuses_wrong_schema_report_with_exit_2(monkeypatch):
    # §5.7's wrong-schema leg of the exit-2 contract, exercised through the CLI.
    import quantfit.modelcard as mc
    from quantfit.safety.report import ReportError

    def _refuse(path):
        raise ReportError(f"report {path} has schema_version 1; this quantfit reads 2")

    monkeypatch.setattr(mc, "model_card_fragment", _refuse)
    assert main(["emit", "model-card", "--report", "old.json"]) == 2
