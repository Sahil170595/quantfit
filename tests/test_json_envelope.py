"""`--json` as a contract, not a convenience.

The gap this closes: not one of ten commands emitted machine-readable output, so the
verdict, the Wilson bounds, the MDE and the provenance — the entire product of this tool —
reached a caller only as a file written to a path, and only from two commands. Exit codes
carried the verdict faithfully and could not carry the numbers.

The contract, and what each test here pins:

1. **Every leaf command accepts `--json`.** Walked off the real parser, so a fourteenth
   command cannot quietly miss it — the failure mode a hand-written flag list has.
2. **stdout carries exactly one JSON document and nothing else.** A caller that has to
   strip lines before parsing does not have a contract. This is the one that would have
   caught the sibling planner's defect, where a warning printed to stdout broke the parse
   at exit 0.
3. **The envelope agrees with the process exit code.** Two sources of truth that can
   disagree are worse than one, so this is asserted per command rather than assumed.
4. **Failures are JSON too.** A caller that asked for JSON gets it on the error path, which
   is the path it most needs to parse.
5. **Prose mode is untouched.** The human rendering is the default and must not shift.

These run the real CLI in a subprocess rather than calling `main()`: the contract is about
what lands on the *streams*, and an in-process call cannot see a stray `print` from a
library, which is exactly the leak being guarded against.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from quantfit import __version__
from quantfit.cli import CLI_JSON_SCHEMA_VERSION, _build_parser

_ROOT = Path(__file__).resolve().parent.parent

# CUDA masked: these must be decided by the CLI, not by whether the test box has a GPU.
_ENV = dict(os.environ, PYTHONIOENCODING="utf-8", CUDA_VISIBLE_DEVICES="-1")

# Stub packages that raise on import, prepended to the child's path. CI's `test` job
# installs neither torch nor transformers (CONTRIBUTING §2, the hermetic-test rule), so a
# case whose command imports a backend passes on a dev box and fails on all five matrix
# jobs — which is exactly what `plan` and `verify` did the first time this file was
# written. Blocking them here reproduces CI's environment on any machine, so the mistake
# cannot come back silently.
_BLOCKED = ("torch", "transformers", "datasets", "llmcompressor")


def _blocked_backend_path(tmp: Path) -> str:
    for name in _BLOCKED:
        (tmp / f"{name}.py").write_text(
            f"raise ImportError({name!r} + ' is deliberately blocked: this command must run "
            "without a backend, the way CI's test job runs it')\n",
            encoding="utf-8",
        )
    return str(tmp)


def _run(*argv: str, block_backends: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(_ENV)
    if block_backends is not None:
        stub = _blocked_backend_path(block_backends)
        env["PYTHONPATH"] = stub + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "quantfit.cli", *argv],
        capture_output=True,
        cwd=str(_ROOT),
        env=env,
        check=False,
        timeout=300,
    )


def _leaf_commands() -> list[tuple[str, ...]]:
    """Every runnable command path, read off the real parser."""

    def walk(parser: argparse.ArgumentParser, path: tuple[str, ...]) -> list[tuple[str, ...]]:
        subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            return [path]
        return [leaf for a in subs for name, child in a.choices.items() for leaf in walk(child, (*path, name))]

    return walk(_build_parser(), ())


def _parser_for(path: tuple[str, ...]) -> argparse.ArgumentParser:
    parser = _build_parser()
    for name in path:
        action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        parser = action.choices[name]
    return parser


# --------------------------------------------------------------------------------
# 1. The flag reaches every leaf
# --------------------------------------------------------------------------------


def test_every_leaf_command_accepts_json():
    missing = [
        " ".join(path)
        for path in _leaf_commands()
        if "--json" not in {opt for a in _parser_for(path)._actions for opt in a.option_strings}
    ]
    assert not missing, (
        f"these commands do not accept --json: {missing}. The flag is attached by walking the "
        "parser (`_add_json_flag`) precisely so a new command cannot miss it — if one did, that "
        "walk was bypassed."
    )


def test_the_leaf_set_is_what_we_think_it_is():
    """A floor, so the walk above cannot pass by finding nothing."""
    leaves = {" ".join(p) for p in _leaf_commands()}
    expected = {
        "check", "list", "plan", "probe", "verify", "verify-safety", "screen", "emit",
        "calibrate sheet", "calibrate ingest", "gate", "reproduce", "audit", "quantize",
    }  # fmt: skip
    assert leaves == expected, f"leaf command set changed: {sorted(leaves ^ expected)}"


def test_json_is_not_a_flag_on_the_parent_of_a_subcommand():
    """`calibrate` deliberately does NOT take --json; its leaves do.

    argparse lets a subparser's default overwrite a parent's value for the same dest, so
    `quantfit calibrate --json sheet` would parse and then silently reset json to False —
    a flag that is accepted and ignored, which is the exact defect `plan --token` was.
    """
    calibrate = _parser_for(("calibrate",))
    assert "--json" not in {opt for a in calibrate._actions for opt in a.option_strings}


# --------------------------------------------------------------------------------
# 2-4. The stream contract, per command, on paths reachable without a GPU
# --------------------------------------------------------------------------------

# (label, argv, expected exit code).
#
# Every case must run with NO torch and NO transformers installed. CI's `test` job
# deliberately installs neither (CONTRIBUTING §2, "the hermetic-test rule"), and these
# spawn the real CLI, so a case whose command imports a backend passes on a dev box and
# fails on all five matrix jobs. `plan` (imports torch via detect_target) and `verify`
# (imports transformers) were in this list and did exactly that.
#
# Heavy commands are covered on their ERROR path where that path is reachable without a
# backend — which is also the path a caller most needs to be able to parse.
_CASES = [
    ("list", ["list"], 0),
    ("audit", ["audit"], None),  # 0 or 3 depending on the tree; both are verdicts
    ("verify-safety-demo", ["verify-safety", "--demo"], 0),
    ("verify-safety-missing-arms", ["verify-safety"], 2),
    ("emit-missing", ["emit", "model-card", "--report", "no-such-report-xyz.json"], 2),
    ("reproduce-missing", ["reproduce", "--reference", "no-a.json", "--candidate", "no-b.json"], 2),
]


@pytest.mark.parametrize(("label", "argv", "expected"), _CASES, ids=[c[0] for c in _CASES])
def test_json_stdout_is_exactly_one_document(label, argv, expected, tmp_path):
    # Backends blocked: every case here must hold in CI's dependency-free test job.
    result = _run(*argv, "--json", block_backends=tmp_path)
    stdout = result.stdout.decode("utf-8", "replace")

    document = json.loads(stdout)  # the assertion: raises if anything else is on stdout

    assert document["schema_version"] == CLI_JSON_SCHEMA_VERSION
    assert document["tool"] == {"name": "quantfit", "version": __version__}
    assert document["command"] == argv[0]
    assert document["exit_code"] == result.returncode, (
        f"the envelope says exit_code={document['exit_code']} but the process returned "
        f"{result.returncode}; two sources of truth that disagree are worse than one"
    )
    if expected is not None:
        assert result.returncode == expected


@pytest.mark.parametrize(("label", "argv", "expected"), _CASES, ids=[c[0] for c in _CASES])
def test_prose_mode_is_unchanged_and_is_not_json(label, argv, expected):
    """The human rendering stays the default. `--json` adds a mode; it does not replace one."""
    result = _run(*argv)
    stdout = result.stdout.decode("utf-8", "replace")
    if expected is not None:
        assert result.returncode == expected
    if stdout.strip():
        with pytest.raises(json.JSONDecodeError):
            json.loads(stdout)


def test_an_operational_failure_is_still_json(tmp_path):
    """The path a caller most needs to parse is the one that failed."""
    result = _run("emit", "model-card", "--report", "no-such-report-xyz.json", "--json", block_backends=tmp_path)
    document = json.loads(result.stdout.decode("utf-8", "replace"))
    assert document["exit_code"] == 2
    assert result.returncode == 2
    assert document["result"] is None
    assert document["error"]["message"], "an error block with no message helps nobody"
    assert document["error"]["kind"], "the exception class is what a caller branches on"


def test_a_verdict_failure_is_not_reported_as_an_error(monkeypatch, capsys):
    """Exit 3 is an answer, not a failure. It must not carry an `error` block.

    In-process with a monkeypatched `verify_safety`, because the only commands that return
    3 need a backend to reach that state — and the subprocess cases above are deliberately
    run with backends blocked. The distinction under test is in the envelope, not in the
    measurement, so a stubbed drift exercises it exactly.
    """
    import quantfit.safety.verify as sv
    from quantfit.cli import main

    drift = sv._tabulate(
        [sv.Probe("p", "clear_unsafe", sv.EXPECTED_UNSAFE)],
        [True],
        [False],  # baseline refused, quant complied: a dangerous flip
    )
    monkeypatch.setattr(sv, "verify_safety", lambda *a, **k: drift)

    code = main(["verify-safety", "--baseline", "a", "--quant", "b", "--json"])
    document = json.loads(capsys.readouterr().out)

    assert code == 3
    assert document["exit_code"] == 3
    assert "error" not in document, "a verdict is not an operational failure"
    assert document["result"]["regression_detected"] is True


def test_notices_do_not_leak_onto_stdout_under_json(tmp_path):
    """`audit --json-out PATH` prints 'audit findings -> PATH' in prose mode.

    Under --json that notice must not reach stdout — a single stray line is the whole
    defect this file exists to prevent, and it is how the sibling planner's --json broke.
    """
    out = tmp_path / "findings.json"
    result = _run("audit", "--json", "--json-out", str(out))
    document = json.loads(result.stdout.decode("utf-8", "replace"))
    assert document["result"]["findings_path"] == str(out), "the path belongs in the payload"
    assert out.exists(), "--json-out must still write the file"
    assert json.loads(out.read_text(encoding="utf-8")), "and it must still be valid JSON"


def test_json_output_is_stable_across_runs():
    """Two runs of a deterministic command must produce byte-identical documents.

    A payload that reorders keys or embeds a timestamp cannot be diffed, and diffing two
    runs is the main thing a machine-readable verdict is for.
    """
    first = _run("list", "--json").stdout
    second = _run("list", "--json").stdout
    assert first == second


def test_the_payload_carries_more_than_the_exit_code_already_did():
    """The point of the envelope: numbers the exit code cannot carry."""
    document = json.loads(_run("list", "--json").stdout.decode("utf-8", "replace"))
    methods = document["result"]["methods"]
    assert methods and all("default_scheme" in m and "backend" in m for m in methods)
    assert document["result"]["schemes"], "the scheme list is half of what `list` is for"
