"""CLI parser + dispatch — light commands only (no torch needed)."""

import argparse
import ast
import inspect
import json
from pathlib import Path

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
        ["verify-safety", "--baseline", "a", "--quant", "b", "--capture", "c.capture.jsonl"],
        ["screen", "--targets", "t.json", "--out", "d"],
        ["emit", "model-card", "--report", "r.json"],
        ["calibrate", "sheet", "--capture", "c.capture.jsonl", "--sheet", "s.labels.csv", "--key", "k.labelkey.json"],
        ["calibrate", "ingest", "--sheet", "s.labels.csv", "--key", "k.labelkey.json", "--out", "cal.json"],
        ["gate", "--baseline", "a", "--quant", "b", "--tier", "smoke"],
        ["gate", "--baseline", "a", "--quant", "b", "--threshold", "30"],
        ["reproduce", "--reference", "a.json", "--candidate", "b.json"],
        ["audit"],
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


def _subparsers() -> dict:
    """{command name: its parser}, read off the built parser rather than restated here."""
    for action in _build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    raise AssertionError("the CLI has no subparsers any more")


def _dispatch_branches() -> dict[str, ast.If]:
    """{command name: the `if args.cmd == "<name>":` node in _dispatch}."""
    tree = ast.parse(Path(inspect.getfile(_build_parser)).read_text(encoding="utf-8"))
    dispatch = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_dispatch")
    branches = {}
    for node in ast.walk(dispatch):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        left, comparators = node.test.left, node.test.comparators
        if (
            isinstance(left, ast.Attribute)
            and left.attr == "cmd"
            and isinstance(left.value, ast.Name)
            and left.value.id == "args"
            and len(comparators) == 1
            and isinstance(comparators[0], ast.Constant)
        ):
            branches[comparators[0].value] = node
    return branches


def test_every_command_that_accepts_token_actually_reads_it():
    """An accepted-but-unread flag is a lie the parser tells: `--help` advertises gated-model
    support, `--token hf_...` is accepted without complaint, and the credential is dropped.

    `plan` shipped exactly that — it carried `parents=[tok]` while its dispatch branch never
    touched `args.token` (nothing in its chain reaches the Hub: detect_target(),
    Engine.feasible() and route() are all local). The flag was removed rather than wired.
    This test generalizes the fix: accepting a token and using one must be the same set.
    """
    accepting = {
        name for name, parser in _subparsers().items() if any("--token" in a.option_strings for a in parser._actions)
    }
    branches = _dispatch_branches()
    assert accepting <= set(branches), (
        f"commands with --token but no dispatch branch: {sorted(accepting - set(branches))}"
    )

    reading = {
        name
        for name, node in branches.items()
        if any(
            isinstance(sub, ast.Attribute)
            and sub.attr == "token"
            and isinstance(sub.value, ast.Name)
            and sub.value.id == "args"
            for sub in ast.walk(node)
        )
    }
    inert = sorted(accepting - reading)
    undeclared = sorted(reading - accepting)
    assert not inert, (
        f"these commands accept --token and never read it: {inert}. Either pass it down to the "
        "call that reaches the Hub, or drop the flag — an inert credential flag is worse than a "
        "missing one, because it looks like it worked."
    )
    assert not undeclared, f"these commands read args.token without declaring --token: {undeclared}"


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


def test_verify_safety_passes_capture_through(monkeypatch):
    import quantfit.safety.verify as sv
    from quantfit.safety.verify import Probe

    seen = {}

    def fake(baseline, quant, token=None, max_new_tokens=64, report_path=None, capture_path=None):
        seen["capture_path"] = capture_path
        probes = [Probe("u", "clear_unsafe", "unsafe"), Probe("s", "clear_safe", "safe")]
        return _drift([True, False], [True, False], probes)

    monkeypatch.setattr(sv, "verify_safety", fake)
    assert main(["verify-safety", "--baseline", "a", "--quant", "b", "--capture", "x.capture.jsonl"]) == 0
    assert seen["capture_path"] == "x.capture.jsonl"


def test_gate_threshold_is_percentage_points_at_the_cli_boundary(monkeypatch, capsys):
    # The operator declares 30pp; run_gate takes a RATE. A silent 100x here would
    # gate every quant at 3000pp (i.e. never fail), so the unit split is tested.
    import quantfit.gate as g

    seen = {}

    def fake(baseline, quant, **kwargs):
        seen.update(kwargs)
        seen["baseline"] = baseline
        return {"headline": "PASS (fake)", "exit_code": 0}

    monkeypatch.setattr(g, "run_gate", fake)
    assert main(["gate", "--baseline", "a", "--quant", "b", "--threshold", "30"]) == 0
    assert seen["threshold"] == pytest.approx(0.30)
    assert seen["tier"] is None
    assert "PASS (fake)" in capsys.readouterr().out

    seen.clear()
    assert main(["gate", "--baseline", "a", "--quant", "b", "--tier", "smoke"]) == 0
    assert seen["threshold"] is None and seen["tier"] == "smoke"


def test_gate_exit_codes_are_relayed_verbatim(monkeypatch):
    # The gate owns its verdict; the CLI must not reinterpret it — especially 4
    # ("nothing measured") and 5 ("threshold unresolvable"), which are not passes.
    import quantfit.gate as g

    for code in (0, 3, 4, 5):
        monkeypatch.setattr(g, "run_gate", lambda *a, _c=code, **k: {"headline": "h", "exit_code": _c})
        assert main(["gate", "--baseline", "a", "--quant", "b", "--tier", "smoke"]) == code

    def _operational(*a, **k):
        raise g.GateError("threshold must be a flip RATE in (0, 1]")

    monkeypatch.setattr(g, "run_gate", _operational)
    assert main(["gate", "--baseline", "a", "--quant", "b", "--tier", "smoke"]) == 2


def test_reproduce_relays_outcome_exit_codes_and_builds_t0_from_replicates(monkeypatch, capsys):
    # The CLI turns replicate FILES into a T0 result at the boundary; compare() takes
    # the result. Every outcome's code is relayed verbatim — 3 and 4 are not passes.
    import quantfit.reproduce as rp

    seen = {}

    def fake_t0(paths):
        seen.setdefault("t0_calls", []).append(list(paths))
        return {"pass": True, "n_replicates": len(paths), "meets_protocol_replicate_count": len(paths) >= 3}

    monkeypatch.setattr(rp, "within_hardware_identical", fake_t0)
    for code in (0, 3, 4):
        monkeypatch.setattr(rp, "compare", lambda *a, _c=code, **k: {"headline": "h", "exit_code": _c})
        assert main(["reproduce", "--reference", "a.json", "--candidate", "b.json"]) == code

    def _capture(reference, candidate, out, *, t0_reference=None, t0_candidate=None):
        seen["t0_reference"] = t0_reference
        seen["t0_candidate"] = t0_candidate
        return {"headline": "h", "exit_code": 0}

    monkeypatch.setattr(rp, "compare", _capture)
    assert main(["reproduce", "--reference", "a.json", "--candidate", "b.json"]) == 0
    assert seen["t0_reference"] is None and seen["t0_candidate"] is None  # absent, not fabricated

    assert (
        main(["reproduce", "--reference", "a.json", "--candidate", "b.json", "--t0-reference", "r1", "r2", "r3"]) == 0
    )
    assert seen["t0_reference"]["meets_protocol_replicate_count"] is True
    assert seen["t0_candidate"] is None
    assert seen["t0_calls"][-1] == ["r1", "r2", "r3"]

    def _operational(*a, **k):
        raise rp.ReproduceError("unreadable report a.json")

    monkeypatch.setattr(rp, "compare", _operational)
    assert main(["reproduce", "--reference", "a.json", "--candidate", "b.json"]) == 2


def test_audit_relays_its_exit_code_and_can_write_json(monkeypatch, tmp_path, capsys):
    import quantfit.audit as au

    result = {"exit_code": 3, "ok": False, "counts": {"findings": 1, "errors": 1, "warnings": 0}}
    monkeypatch.setattr(au, "audit", lambda root=None: result)
    monkeypatch.setattr(au, "summarize", lambda r, limit=0: "drift: 1 error(s)")

    out = tmp_path / "findings.json"
    assert main(["audit", "--json", str(out)]) == 3  # drift fails a build, it does not warn
    assert "drift: 1 error(s)" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))["counts"]["errors"] == 1

    monkeypatch.setattr(au, "audit", lambda root=None: {**result, "exit_code": 0, "ok": True})
    assert main(["audit"]) == 0


def test_calibrate_subcommands_dispatch_and_refuse_operationally(monkeypatch, capsys):
    from pathlib import Path

    import quantfit.safety.calibrate as cal

    monkeypatch.setattr(cal, "build_labeling_sheet", lambda c, s, k: (Path(s), Path(k)))
    assert main(["calibrate", "sheet", "--capture", "c", "--sheet", "s.labels.csv", "--key", "k.labelkey.json"]) == 0
    out = capsys.readouterr().out
    assert "blinded sheet" in out and "labeler never sees" in out

    report = {
        "baseline": {"n": 4, "judge_errors": 1, "epsilon": 0.25},
        "quantized": {"n": 0, "judge_errors": 0, "epsilon": None},
    }
    monkeypatch.setattr(cal, "ingest_labels", lambda s, k, o: report)
    assert main(["calibrate", "ingest", "--sheet", "s", "--key", "k", "--out", "o.json"]) == 0
    out = capsys.readouterr().out
    assert "epsilon=0.2500" in out and "epsilon=unmeasured" in out

    def _refuse(*a, **k):
        raise cal.CalibrationError("row 3 (id rdeadbeef) is unlabeled")

    monkeypatch.setattr(cal, "ingest_labels", _refuse)
    assert main(["calibrate", "ingest", "--sheet", "s", "--key", "k", "--out", "o.json"]) == 2
