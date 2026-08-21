"""`tools/quickstart_check.py` — the README quickstart gate, tested hermetically.

Two halves, and the second one is the one that would catch a real regression:

  1. **Unit tests on fixture READMEs** (`tmp_path`) — extraction, classification and
     validation, with the CLI surface injected as canned `--help` text. No subprocess,
     no network, no torch.
  2. **Tests against the REAL `README.md` and the REAL shipped parser** — every command
     the README advertises must exist in `quantfit/cli.py`'s parser, and nothing heavy
     may ever be classified runnable. The parser is introspected in-process via
     `format_help()`, which is byte-identical to what the installed CLI prints, so this
     is the same drift catch the CI script performs without paying for 15 subprocesses.

Nothing here executes a category-(b/c/d/e) command, and nothing here executes the real
CLI at all: `run_clean_venv` is exercised with a recording fake runner.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_TOOL_PATH = _ROOT / "tools" / "quickstart_check.py"


def _load_tool():
    """Import the tool by path: it is a script in tools/, not an installed module."""
    spec = importlib.util.spec_from_file_location("quantfit_quickstart_check", _TOOL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


qs = _load_tool()


# --------------------------------------------------------------------------------
# Fixture help text: what argparse actually prints, including both alias renderings
# --------------------------------------------------------------------------------

ROOT_HELP = """\
usage: quantfit [-h] {check,list,gate,emit,calibrate} ...

Quantize an LLM.

positional arguments:
  {check,list,gate,emit,calibrate}
    check               will this model fit your GPU?
    list                list supported methods
    gate                pre-release gate
    emit                render an artifact
    calibrate           judge calibration

options:
  -h, --help            show this help message and exit
"""

CHECK_HELP = """\
usage: quantfit check [-h] [--token TOKEN] --model MODEL

options:
  -h, --help     show this help message and exit
  --token TOKEN  HF token
  --model MODEL  HF model id
"""

LIST_HELP = """\
usage: quantfit list [-h]

options:
  -h, --help  show this help message and exit
"""

# `--baseline, --fp16 BASELINE` is the 3.13+ alias rendering; the help PROSE mentions
# `--deleted-flag`, which must NOT be read as a flag (see the prose test below).
GATE_HELP = """\
usage: quantfit gate [-h] --baseline BASELINE --quant QUANT
                     (--threshold PP | --tier {smoke,full}) [--eps-upper RATE]

options:
  -h, --help            show this help message and exit
  --baseline, --fp16 BASELINE
                        the unquantized baseline arm (replaces --deleted-flag,
                        which no longer exists)
  --quant QUANT         the quantized artifact to gate
  --threshold PP        declared threshold in PERCENTAGE POINTS
  --tier {smoke,full}   a named tier instead of a raw threshold
  --eps-upper RATE      per-arm upper bound on judge error
"""

EMIT_HELP = """\
usage: quantfit emit [-h] --report PATH {model-card}

positional arguments:
  {model-card}   what to emit

options:
  -h, --help     show this help message and exit
  --report PATH  a schema-v2 drift report
"""

CALIBRATE_HELP = """\
usage: quantfit calibrate [-h] {sheet,ingest} ...

positional arguments:
  {sheet,ingest}
    sheet       capture -> blinded sheet
    ingest      filled sheet -> report

options:
  -h, --help  show this help message and exit
"""

CALIBRATE_SHEET_HELP = """\
usage: quantfit calibrate sheet [-h] --capture PATH --sheet PATH --key PATH

options:
  -h, --help      show this help message and exit
  --capture PATH  a *.capture.jsonl
  --sheet PATH    blinded sheet to write
  --key PATH      unblinding key to write
"""

CALIBRATE_INGEST_HELP = """\
usage: quantfit calibrate ingest [-h] --sheet PATH --key PATH --out PATH

options:
  -h, --help    show this help message and exit
  --sheet PATH  the filled labeling sheet
  --key PATH    the key written next to it
  --out PATH    calibration report JSON to write
"""

_FAKE_HELP = {
    (): ROOT_HELP,
    ("check",): CHECK_HELP,
    ("list",): LIST_HELP,
    ("gate",): GATE_HELP,
    ("emit",): EMIT_HELP,
    # `emit`'s positional is a plain choices= argument: argparse reprints emit's help.
    ("emit", "model-card"): EMIT_HELP,
    ("calibrate",): CALIBRATE_HELP,
    ("calibrate", "sheet"): CALIBRATE_SHEET_HELP,
    ("calibrate", "ingest"): CALIBRATE_INGEST_HELP,
}


def fake_runner(calls: list[tuple[str, ...]] | None = None):
    """A Runner over canned help text. Records every invocation it is given."""

    def run(argv, _timeout):
        argv = tuple(argv)
        if calls is not None:
            calls.append(argv)
        if argv and argv[-1] == "--help":
            help_text = _FAKE_HELP.get(argv[:-1])
            return (0, help_text, "") if help_text else (2, "", f"no such command: {argv}")
        return 0, "ok\n", ""

    return run


@pytest.fixture
def surface():
    return qs.discover_surface(fake_runner())


def readme(tmp_path: Path, body: str) -> str:
    (tmp_path / "README.md").write_text(body, encoding="utf-8")
    return (tmp_path / "README.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------------


def test_only_bash_fences_are_commands(tmp_path):
    # A bare ``` block is sample OUTPUT. Treating it as commands is how a checker
    # starts "failing" on a verdict string the README is quoting.
    text = readme(
        tmp_path,
        "# t\n\n```bash\nquantfit list\n```\n\n```\nsafety drift over 40 probes - REGRESSION\n```\n",
    )
    commands = qs.extract_commands(text)
    assert [c.text for c in commands] == ["quantfit list"]


def test_backslash_continuations_are_joined(tmp_path):
    text = readme(tmp_path, "```bash\nquantfit gate \\\n  --baseline a \\\n  --quant b\n```\n")
    (command,) = qs.extract_commands(text)
    assert command.argv == ("quantfit", "gate", "--baseline", "a", "--quant", "b")
    assert command.line == 2  # the line the command STARTS on


def test_trailing_comments_and_prompts_are_stripped(tmp_path):
    text = readme(tmp_path, "```bash\n$ quantfit list   # what methods exist?\n```\n")
    (command,) = qs.extract_commands(text)
    assert command.argv == ("quantfit", "list")
    assert command.normalized == "quantfit list"


def test_comment_lines_are_not_commands(tmp_path):
    # Regression guard: treating `#` as a shell prompt turned every comment into a
    # command, and `# quantfit teleport` would then be reported as README drift.
    text = readme(tmp_path, "```bash\n# quantfit teleport --model x\nquantfit list\n```\n")
    assert [c.argv for c in qs.extract_commands(text)] == [("quantfit", "list")]


def test_inline_spans_are_extracted_and_may_wrap(tmp_path):
    text = readme(tmp_path, "prose about `quantfit\nlist` and more.\n")
    (command,) = qs.extract_commands(text)
    assert command.argv == ("quantfit", "list")
    assert command.source == qs.SOURCE_INLINE
    assert command.line == 1


def test_inline_extraction_ignores_fenced_bodies(tmp_path):
    text = readme(tmp_path, "```bash\nquantfit list\n```\n\nprose `quantfit check --model m`\n")
    sources = {c.source: c.text for c in qs.extract_commands(text)}
    assert sources == {qs.SOURCE_FENCED: "quantfit list", qs.SOURCE_INLINE: "quantfit check --model m"}


def test_inline_can_be_disabled(tmp_path):
    text = readme(tmp_path, "prose `quantfit list`\n")
    assert qs.extract_commands(text, include_inline=False) == []


def test_non_command_backticks_are_ignored(tmp_path):
    # `quantfit[awq]` is an extra, not a command; `quantfit.safety` is a module.
    text = readme(tmp_path, "install `quantfit[awq]`; import `quantfit.safety`\n")
    assert qs.extract_commands(text) == []


# --------------------------------------------------------------------------------
# Fence pairing — the failure that halves the audited surface while exiting 0
# --------------------------------------------------------------------------------


def test_an_odd_fence_marker_count_is_refused(tmp_path):
    """ONE stray ``` flips every later open/close. Silently auditing half a README is
    strictly worse than refusing to start, so this is exit 2, not a quiet pass."""
    text = readme(tmp_path, "```bash\nquantfit list\n```\n\n```\nstray, never closed\n")
    with pytest.raises(qs.QuickstartCheckError, match="odd number"):
        qs.extract_commands(text)


def test_a_desynced_closer_with_an_info_string_is_refused(tmp_path):
    """Even marker count, still desynced: a 'closer' carrying an info string is the
    alternation telling you an earlier marker was stray. Real closers never do."""
    text = readme(tmp_path, "```bash\nquantfit list\n```bash\nquantfit check --model m\n```\n```\n")
    assert len(qs._FENCE_RE.findall(text)) == 4, "fixture must be EVEN, or the odd-count check fires first"
    with pytest.raises(qs.QuickstartCheckError, match="CLOSING position"):
        qs.extract_commands(text)


def test_a_stray_fence_would_otherwise_have_halved_the_surface(tmp_path):
    """The regression this guards, spelled out: without the refusal, two of the three
    advertised commands below vanish from the audit and the gate still exits 0."""
    body = "```bash\nquantfit list\n```\n\n```\noutput\n\n```bash\nquantfit check --model m\n```\n"
    with pytest.raises(qs.QuickstartCheckError):
        qs.extract_commands(body)
    # Balanced, the same README yields both commands: the refusal is about pairing only.
    fixed = body.replace("```\noutput\n\n", "```\noutput\n```\n\n")
    assert [c.text for c in qs.extract_commands(fixed)] == ["quantfit list", "quantfit check --model m"]


def test_a_tilde_fence_is_refused_rather_than_silently_unread(tmp_path):
    """`~~~` blocks are invisible to _FENCE_RE. Half-support is the bug; refusal is not."""
    text = readme(tmp_path, "```bash\nquantfit list\n```\n\n~~~bash\nquantfit check --model m\n~~~\n")
    with pytest.raises(qs.QuickstartCheckError, match="~~~"):
        qs.extract_commands(text)


def _main_against_fake_cli(monkeypatch, tmp_path: Path, body: str, *extra: str) -> int:
    """Run `main` end to end with the canned CLI surface: no subprocess, no wheel."""
    (tmp_path / "README.md").write_text(body, encoding="utf-8")
    monkeypatch.setattr(qs, "subprocess_runner", lambda _prefix: fake_runner())
    return qs.main(["--readme", str(tmp_path / "README.md"), "--no-run", *extra])


def test_the_fence_refusal_is_operational_not_drift(monkeypatch, tmp_path):
    """Exit 2, not 1: an unpairable README is a reader that cannot read, not a verdict."""
    assert _main_against_fake_cli(monkeypatch, tmp_path, "```bash\nquantfit list\n") == qs.EXIT_OPERATIONAL


# --------------------------------------------------------------------------------
# Unparseable commands are findings, never silent drops
# --------------------------------------------------------------------------------


def test_an_unparseable_fenced_command_is_reported_not_dropped(tmp_path):
    text = readme(tmp_path, '```bash\nquantfit check --model "unclosed\nquantfit list\n```\n')
    unparsed: list = []
    commands = qs.extract_commands(text, unparsed=unparsed)
    assert [c.text for c in commands] == ["quantfit list"]
    (dropped,) = unparsed
    assert dropped.raw == 'quantfit check --model "unclosed'
    assert dropped.line == 2 and dropped.source == qs.SOURCE_FENCED
    (finding,) = qs.unparsed_findings(unparsed)
    assert finding.kind == "unparseable-command"
    assert finding.severity == qs.SEVERITY_ERROR
    assert finding.line == 2
    assert finding.command == 'quantfit check --model "unclosed'  # the RAW line, for fixing


def test_an_unparseable_inline_command_is_reported(tmp_path):
    text = readme(tmp_path, 'prose about `quantfit check --model "oops`\n')
    unparsed: list = []
    assert qs.extract_commands(text, unparsed=unparsed) == []
    assert [(u.line, u.source) for u in unparsed] == [(1, qs.SOURCE_INLINE)]


def test_an_unparseable_command_fails_the_gate(monkeypatch, tmp_path):
    """A quoting typo must be LOUDER than no command at all, not quieter."""
    body = '```bash\nquantfit list\nquantfit check --model "unclosed\n```\n'
    assert _main_against_fake_cli(monkeypatch, tmp_path, body) == qs.EXIT_DRIFT
    # ...and the same README without the typo passes, so the FAIL is the typo's doing.
    assert _main_against_fake_cli(monkeypatch, tmp_path, body.replace('"unclosed', "m")) == qs.EXIT_OK


def test_extract_commands_still_works_without_the_unparsed_channel(tmp_path):
    """Callers that pass no list keep the old signature; only `main` opts in."""
    text = readme(tmp_path, '```bash\nquantfit check --model "unclosed\nquantfit list\n```\n')
    assert [c.text for c in qs.extract_commands(text)] == ["quantfit list"]


# --------------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------------


def _classify(text: str) -> qs.Classification:
    command = qs.Command(text=text, argv=tuple(text.split()), source=qs.SOURCE_FENCED, line=1, block=1)
    return qs.classify(command)


def test_list_and_plan_are_clean_venv():
    for text in ("quantfit list", "quantfit plan --model Qwen/Qwen2.5-7B-Instruct"):
        item = _classify(text)
        assert item.category == qs.CAT_CLEAN_VENV, text
        assert item.runnable and item.requirements == ()


def test_check_needs_the_network_only():
    item = _classify("quantfit check --model Qwen/Qwen2.5-7B-Instruct")
    assert item.category == qs.CAT_NETWORK
    assert item.requirements == (qs.REQ_NETWORK,)
    assert not item.runnable


def test_quantize_and_probe_need_a_gpu():
    for text in ("quantfit quantize --model m --method awq --out ./out", "quantfit probe --model m --bits 4 8"):
        item = _classify(text)
        assert item.category == qs.CAT_GPU, text
        assert qs.REQ_GPU in item.requirements and qs.REQ_DOWNLOAD in item.requirements


def test_gguf_pair_drops_the_gpu_requirement_but_not_the_download():
    item = _classify(
        "quantfit verify-safety --baseline hf:org/repo/model-f16.gguf --quant hf:org/repo/model-Q4_K_M.gguf"
    )
    assert item.category == qs.CAT_DOWNLOAD
    assert qs.REQ_GPU not in item.requirements
    assert qs.REQ_DOWNLOAD in item.requirements
    assert any("llama.cpp" in reason for reason in item.reasons)


def test_transformers_pair_keeps_the_gpu_requirement():
    item = _classify("quantfit verify-safety --baseline Qwen/Qwen2.5-1.5B-Instruct --quant ./out")
    assert item.category == qs.CAT_GPU


def test_artifact_consumers_are_not_runnable():
    for text in (
        "quantfit emit model-card --report drift.json",
        "quantfit screen --targets t.json --out d",
        # `reproduce` reads two reports; `audit` reads a source checkout (--root defaults
        # to the tree containing quantfit, which in a clean venv is site-packages).
        "quantfit reproduce --reference ref.json --candidate t4.json",
        "quantfit audit",
    ):
        item = _classify(text)
        assert item.category == qs.CAT_NOT_RUNNABLE, text
        assert qs.REQ_ARTIFACT in item.requirements, text


def test_every_shipped_subcommand_has_a_classification_rule():
    """A quantfit subcommand with no entry lands in REQ_UNCLASSIFIED, whose reason reads
    "no classification rule covers this program or subcommand" — true, but it is a hole in
    the classifier reported as a fact about the README. `reproduce` and `audit` sat in it.

    Read from the shipped parser, so wiring a new subcommand into the CLI without deciding
    what it needs fails here rather than being silently filed as not-runnable.
    """
    from quantfit.cli import _build_parser

    shipped = set(_subparser_map(_build_parser()))
    assert shipped, "the shipped parser exposes no subcommands; this reader is stale"
    missing = sorted(shipped - set(qs.SUBCOMMAND_REQUIREMENTS))
    assert not missing, (
        f"{missing} are shipped subcommands with no entry in SUBCOMMAND_REQUIREMENTS, so they are classified "
        "'unclassified' rather than by what they actually need. Add an entry with a cited reason."
    )


def test_placeholder_commands_are_never_runnable():
    item = _classify("quantfit plan --model <id>")
    assert item.category == qs.CAT_NOT_RUNNABLE
    assert qs.REQ_PLACEHOLDER in item.requirements


def test_pip_install_is_network():
    item = _classify("pip install quantfit")
    assert item.category == qs.CAT_NETWORK and not item.runnable


def test_unknown_program_and_unknown_subcommand_are_never_runnable():
    for text in ("wget https://example.invalid/x", "quantfit teleport --model m"):
        item = _classify(text)
        assert item.category == qs.CAT_NOT_RUNNABLE, text
        assert qs.REQ_UNCLASSIFIED in item.requirements


# --------------------------------------------------------------------------------
# Help parsing + surface discovery
# --------------------------------------------------------------------------------


def test_parse_help_reads_flags_aliases_choices_and_positionals():
    flags, value_flags, flag_choices, positional = qs.parse_help(GATE_HELP)
    assert {"--baseline", "--fp16", "--quant", "--threshold", "--tier", "--eps-upper"} <= flags
    assert "--fp16" in value_flags  # the alias shares the metavar in the 3.13 rendering
    assert flag_choices["--tier"] == ("smoke", "full")
    assert positional == ()
    assert qs.parse_help(EMIT_HELP)[3] == ("model-card",)


def test_parse_help_reads_the_pre_313_alias_rendering():
    flags, value_flags, _choices, _pos = qs.parse_help(
        "usage: quantfit gate [-h]\n\noptions:\n  --baseline BASELINE, --fp16 BASELINE\n                        the arm\n"
    )
    assert flags == {"--baseline", "--fp16"} and value_flags == {"--baseline", "--fp16"}


def test_parse_help_ignores_flags_named_only_in_help_prose():
    # The whole drift catch rests on this: `--deleted-flag` appears in GATE_HELP's
    # wrapped prose. If prose counted, a flag deleted from the CLI but still described
    # in another flag's help would keep validating forever.
    flags, _values, _choices, _pos = qs.parse_help(GATE_HELP)
    assert "--deleted-flag" not in flags


def test_usage_prog_reads_the_command_path():
    assert qs.usage_prog(CALIBRATE_SHEET_HELP) == ("quantfit", "calibrate", "sheet")
    assert qs.usage_prog(EMIT_HELP) == ("quantfit", "emit")


def test_discover_surface_walks_real_subparsers_only():
    calls: list[tuple[str, ...]] = []
    surface = qs.discover_surface(fake_runner(calls))
    assert set(surface.positional_choices) == {"check", "list", "gate", "emit", "calibrate"}
    # `calibrate` is a real subparser: its children are nodes with their own flags.
    assert set(surface.children["calibrate"].children) == {"sheet", "ingest"}
    assert "--capture" in surface.children["calibrate"].children["sheet"].flags
    # `emit model-card` is a choices= positional: probed once, never made a child.
    assert surface.children["emit"].children == {}
    assert ("emit", "model-card", "--help") in calls


def test_discover_surface_refuses_unparseable_help():
    def broken(_argv, _timeout):
        return 0, "usage: quantfit\n\nno options section here\n", ""

    with pytest.raises(qs.QuickstartCheckError, match="no parseable option entries"):
        qs.discover_surface(broken)


def test_discover_surface_refuses_a_failing_help():
    def failing(_argv, _timeout):
        return 1, "", "boom"

    with pytest.raises(qs.QuickstartCheckError, match="cannot read the CLI surface"):
        qs.discover_surface(failing)


# --------------------------------------------------------------------------------
# Validation — the drift catch
# --------------------------------------------------------------------------------


def _validate(text: str, surface) -> list[qs.Finding]:
    command = qs.Command(text=text, argv=tuple(text.split()), source=qs.SOURCE_FENCED, line=7, block=1)
    return qs.validate_command(command, surface)


def test_valid_commands_produce_no_findings(surface):
    for text in (
        "quantfit list",
        "quantfit check --model Qwen/Qwen2.5-7B-Instruct",
        "quantfit gate --baseline a --quant b --tier smoke",
        "quantfit gate --fp16 a --quant b --threshold 30",
        "quantfit emit model-card --report drift.json",
        "quantfit calibrate sheet --capture c.jsonl --sheet s.csv --key k.json",
        "quantfit --help",
    ):
        assert _validate(text, surface) == [], text


def test_a_removed_subcommand_is_a_finding(surface):
    (finding,) = _validate("quantfit teleport --model m", surface)
    assert finding.kind == "unknown-subcommand"
    assert finding.severity == qs.SEVERITY_ERROR
    assert finding.line == 7


def test_a_removed_flag_is_a_finding(surface):
    (finding,) = _validate("quantfit check --model m --offload", surface)
    assert finding.kind == "unknown-flag" and "--offload" in finding.detail


def test_a_removed_flag_choice_is_a_finding(surface):
    (finding,) = _validate("quantfit gate --baseline a --quant b --tier turbo", surface)
    assert finding.kind == "unknown-choice" and "turbo" in finding.detail


def test_a_removed_positional_choice_is_a_finding(surface):
    (finding,) = _validate("quantfit emit modelcard --report r.json", surface)
    assert finding.kind == "unknown-positional"


def test_a_removed_sub_subcommand_flag_is_a_finding(surface):
    (finding,) = _validate("quantfit calibrate sheet --capture c.jsonl --labels s.csv", surface)
    assert finding.kind == "unknown-flag" and "calibrate sheet" in finding.detail


def test_flag_values_are_not_mistaken_for_subcommands(surface):
    # `--model list` must not be read as the `list` subcommand.
    assert _validate("quantfit check --model list", surface) == []


def test_inline_equals_form_is_validated(surface):
    assert _validate("quantfit gate --tier=smoke --baseline a --quant b", surface) == []
    (finding,) = _validate("quantfit gate --tier=turbo --baseline a --quant b", surface)
    assert finding.kind == "unknown-choice"


def test_non_quantfit_commands_are_not_validated(surface):
    assert _validate("pip install quantfit", surface) == []


def test_undocumented_subcommands_are_reported(surface):
    commands = [qs.Command(text="quantfit list", argv=("quantfit", "list"), source="fenced", line=1, block=1)]
    assert qs.undocumented_subcommands(commands, surface) == ("calibrate", "check", "emit", "gate")


# --------------------------------------------------------------------------------
# Execution: only category (a), and only ever through the injected runner
# --------------------------------------------------------------------------------


def test_run_clean_venv_runs_only_category_a(tmp_path):
    text = readme(
        tmp_path,
        "```bash\npip install quantfit\nquantfit list\nquantfit quantize --model m --method awq --out o\n"
        "quantfit plan --model m\n```\n",
    )
    classifications = [qs.classify(c) for c in qs.extract_commands(text)]
    calls: list[tuple[str, ...]] = []
    results = qs.run_clean_venv(classifications, fake_runner(calls))
    assert [r.command for r in results] == ["quantfit list", "quantfit plan --model m"]
    assert all(r.ok for r in results)
    # Nothing heavy was even offered to the runner.
    assert calls == [("list",), ("plan", "--model", "m")]


def test_a_failing_clean_venv_command_is_a_failure(tmp_path):
    text = readme(tmp_path, "```bash\nquantfit list\n```\n")
    classifications = [qs.classify(c) for c in qs.extract_commands(text)]

    def failing(_argv, _timeout):
        return 3, "", "exploded"

    (result,) = qs.run_clean_venv(classifications, failing)
    assert not result.ok and result.returncode == 3
    verdict, exit_code, _why = qs.decide(classifications, [], [result])
    assert (verdict, exit_code) == ("FAIL", qs.EXIT_DRIFT)


def test_decide_fails_on_findings_and_on_a_short_runnable_set():
    finding = qs.Finding(kind="unknown-flag", severity=qs.SEVERITY_ERROR, command="c", line=1, detail="d")
    assert qs.decide([], [finding], [])[:2] == ("FAIL", qs.EXIT_DRIFT)
    assert qs.decide([], [], [])[:2] == ("PASS", qs.EXIT_OK)
    assert qs.decide([], [], [], require_runnable=1)[:2] == ("FAIL", qs.EXIT_DRIFT)


def test_decide_enforces_a_floor_on_the_audited_surface(tmp_path):
    """The count floor: a collapse in extraction must fail the build, not shrink quietly."""
    text = readme(tmp_path, "```bash\nquantfit list\nquantfit plan --model m\n```\n")
    classifications = [qs.classify(c) for c in qs.extract_commands(text)]
    assert qs.decide(classifications, [], [], min_commands=2)[:2] == ("PASS", qs.EXIT_OK)
    verdict, exit_code, why = qs.decide(classifications, [], [], min_commands=3)
    assert (verdict, exit_code) == ("FAIL", qs.EXIT_DRIFT)
    assert why["n_commands"] == 2 and why["short_of_min_commands"]


def test_min_commands_is_wired_through_main(monkeypatch, tmp_path):
    body = "```bash\nquantfit list\n```\n"
    assert _main_against_fake_cli(monkeypatch, tmp_path, body, "--min-commands", "1") == qs.EXIT_OK
    assert _main_against_fake_cli(monkeypatch, tmp_path, body, "--min-commands", "2") == qs.EXIT_DRIFT


def test_the_validator_gaps_are_documented_decisions_not_oversights():
    """Two things `validate_command` does not check, pinned so they stay deliberate.

    Required args and extra positionals both pass. That is a decision — the README names
    commands in prose by bare name (`quantfit gate`, `quantfit audit`), and rejecting those
    would fail the build on correct English — and the module docstring has to keep saying
    so. If either gap is ever closed, this test is what forces the docstring to follow.
    """
    surface = qs.discover_surface(fake_runner())
    assert _validate("quantfit gate", surface) == []  # required --baseline/--quant missing
    assert _validate("quantfit list extra-junk", surface) == []  # positional the CLI rejects
    doc = qs.__doc__ or ""
    assert "Required arguments are not checked" in doc
    assert "Extra or malformed positionals are not checked" in doc
    assert "Only ``` fences are read" in doc


def test_missing_readme_is_operational_not_drift(tmp_path):
    assert qs.main(["--readme", str(tmp_path / "nope.md"), "--no-run"]) == qs.EXIT_OPERATIONAL


def test_the_sandbox_removes_the_network_and_the_gpu():
    # The (a) run is only evidence if the capabilities are actually gone. "-1" and not
    # "" for CUDA_VISIBLE_DEVICES: measured on torch 2.11+cu128/Windows, "" leaves
    # torch.cuda.is_available() True with device_count() 0.
    assert qs.SANDBOX_ENV["HF_HUB_OFFLINE"] == "1"
    assert qs.SANDBOX_ENV["TRANSFORMERS_OFFLINE"] == "1"
    assert qs.SANDBOX_ENV["HF_DATASETS_OFFLINE"] == "1"
    assert qs.SANDBOX_ENV["CUDA_VISIBLE_DEVICES"] == "-1"


def test_the_docstring_does_not_claim_the_gpu_mask_fails_loudly():
    """The sandbox's two halves are not equally strong, and the docstring must say so.

    `HF_HUB_OFFLINE=1` makes a misclassified network command RAISE. `CUDA_VISIBLE_DEVICES=-1`
    does not: `torch.cuda.is_available()` simply returns False and code that branches on it
    takes its CPU path and exits 0. `quantfit plan` is exactly that shape — it reroutes to
    route() rule 1 and PASSes — so a docstring claiming a misclassified GPU command "fails
    loudly here" would be describing a guarantee this tool does not provide.
    """
    doc = qs.__doc__ or ""
    assert "silently REROUTED, not failed" in doc
    assert "quantfit plan" in doc, "the one device-consulting category-(a) command must be named"
    assert "fails loudly here" not in doc


def test_the_tool_is_stdlib_only_and_never_imports_quantfit():
    # It audits the INSTALLED wheel through a process boundary. An `import quantfit`
    # here would silently test the source tree instead, and a third-party dependency
    # would make the checker uninstallable in the clean venv it is checking.
    tree = ast.parse(_TOOL_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert "quantfit" not in imported
    assert imported <= set(sys.stdlib_module_names), f"non-stdlib imports: {imported - set(sys.stdlib_module_names)}"


# --------------------------------------------------------------------------------
# The real README against the real shipped parser
# --------------------------------------------------------------------------------


def _subparser_map(parser) -> dict:
    """argparse exposes no public accessor for subparsers; duck-type the action."""
    for action in parser._actions:  # the only way in, and this is a test
        if not action.option_strings and isinstance(getattr(action, "choices", None), dict):
            return action.choices
    return {}


def real_parser_runner():
    """A Runner backed by the SHIPPED parser's `format_help()` — no subprocess.

    `format_help()` is exactly the text `quantfit <path> --help` prints, so validating
    against it is the same check the CI script performs against the installed wheel.
    """
    from quantfit.cli import _build_parser  # torch-free import (see tests/test_cli.py)

    root = _build_parser()

    def run(argv, _timeout=0):
        node = root
        for token in argv:
            if token in ("-h", "--help"):
                break
            children = _subparser_map(node)
            if token in children:  # a plain choices= positional just falls through,
                node = children[token]  # exactly as argparse does for `emit model-card`
        return 0, node.format_help(), ""

    return run


@pytest.fixture(scope="module")
def real_surface():
    return qs.discover_surface(real_parser_runner())


@pytest.fixture(scope="module")
def real_commands():
    return qs.extract_commands((_ROOT / "README.md").read_text(encoding="utf-8"))


#: The floor on the audited surface. The README advertised 21 commands when this was
#: written; 15 is a deliberately slack floor that still fails on the collapse mode that
#: matters — a fence desync roughly halves the count. Raise it, never lower it silently.
MIN_README_COMMANDS = 15


def test_the_real_readme_parses(real_commands):
    assert real_commands, "no commands extracted from README.md - the extractor went blind"
    assert all(command.argv for command in real_commands)
    assert any(command.source == qs.SOURCE_FENCED for command in real_commands)
    assert any(command.source == qs.SOURCE_INLINE for command in real_commands)


def test_the_real_readme_has_no_unparseable_command():
    """The gate would exit 1 on these; catching them here names the line in a unit run."""
    unparsed: list = []
    qs.extract_commands((_ROOT / "README.md").read_text(encoding="utf-8"), unparsed=unparsed)
    assert not unparsed, [f"L{u.line}: {u.raw!r} ({u.error})" for u in unparsed]


def test_the_real_readme_surface_has_not_collapsed(real_commands):
    """A floor, so a silent halving of the audited surface fails the unit suite too.

    `_iter_fences` now refuses a marker desync outright, which is the mechanism this
    guards against; the count floor is the belt to that braces, and it fails for any other
    way extraction could quietly shrink.
    """
    assert len(real_commands) >= MIN_README_COMMANDS, (
        f"README.md now yields {len(real_commands)} commands, below the recorded floor of "
        f"{MIN_README_COMMANDS}. Either the README genuinely shrank (lower the floor on purpose, in the same "
        "commit) or extraction collapsed."
    )


def test_the_real_readme_fence_markers_pair(real_commands):
    """The desync precondition, asserted against the file the gate actually reads."""
    text = (_ROOT / "README.md").read_text(encoding="utf-8")
    markers = qs._FENCE_RE.findall(text)
    assert len(markers) % 2 == 0, f"README.md has {len(markers)} ``` markers; one is unpaired"
    assert not qs._TILDE_FENCE_RE.search(text), "README.md gained a ~~~ fence, which this extractor cannot read"


def test_every_readme_command_exists_in_the_shipped_cli(real_commands, real_surface):
    """ROADMAP 0.10's docs=code parity, as an assertion.

    If this fails, either the README advertises something the CLI no longer defines
    (fix the README) or a flag was renamed without updating it (fix one of them). It
    is never correct to relax this test.
    """
    findings = [f for command in real_commands for f in qs.validate_command(command, real_surface)]
    assert findings == [], "\n".join(f"L{f.line} {f.kind}: {f.detail} | {f.command}" for f in findings)


def test_every_category_a_command_is_a_real_cli_command(real_commands, real_surface):
    """The gate clause's own precondition: what we RUN must be what the CLI defines."""
    runnable = [c for c in (qs.classify(command) for command in real_commands) if c.runnable]
    assert runnable, "the README advertises no clean-venv-runnable command; the 1.0 quickstart gate would be vacuous"
    for item in runnable:
        subcommand = qs.subcommand_of(item.command.argv)
        assert item.command.is_quantfit
        if subcommand:
            assert subcommand in real_surface.positional_choices, subcommand
        else:
            # A top-level flag form — `quantfit --version` — is a real command with no
            # subcommand at all. `subcommand_of` returns "" for it, which is not and should
            # not be a positional choice; the guarantee is carried by validate_command
            # below, which resolves the flag against the top-level parser.
            assert [tok for tok in item.command.argv[1:] if tok.startswith("-")], item.command.argv
        assert qs.validate_command(item.command, real_surface) == []


def test_no_heavy_readme_command_is_ever_runnable(real_commands):
    """The other half of the same guarantee: CI must never download or quantize here.

    This check keys on the SUBCOMMAND NAME rather than on the classifier's output, and
    that coarseness is the point: it is an independent second opinion, so a classifier
    that wrongly marks something runnable is caught by something that does not share its
    logic.

    `verify-safety --demo` is the one carve-out, added 2026-08-21. It is exempt because
    it genuinely is not heavy - bundled fixtures, no model, no network, no weights - and
    verified as such by running it under HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
    CUDA_VISIBLE_DEVICES=-1, where it exits 0 in under a second. The exemption is written
    as an explicit flag test rather than by consulting the classifier, so this stays an
    independent opinion about everything else.
    """
    heavy = {"quantize", "probe", "verify", "verify-safety", "gate", "screen", "check"}
    for item in (qs.classify(command) for command in real_commands):
        if "--demo" in item.command.argv:
            continue
        if qs.subcommand_of(item.command.argv) in heavy:
            assert not item.runnable, item.command.text


def test_the_readme_quickstart_block_is_still_the_quickstart(real_commands):
    """The first bash block is the install + tour; if it stops being that, say so."""
    first_block = [c for c in real_commands if c.block == 1]
    assert first_block, "README.md's first fenced bash block is gone"
    assert first_block[0].argv[:2] == ("pip", "install")
    assert {qs.subcommand_of(c.argv) for c in first_block if c.is_quantfit}


def test_verify_safety_demo_is_clean_venv_not_gpu():
    """Requirements are a property of the invocation, not of the subcommand name.

    `verify-safety --demo` runs the real tabulation over bundled fixtures: no model, no
    network, no weights. It was filed under c:gpu on the strength of its subcommand's
    name, which meant the README's second command was the one command in that opening
    the quickstart gate declined to run.
    """
    item = _classify("quantfit verify-safety --demo")
    assert item.category == qs.CAT_CLEAN_VENV
    assert item.requirements == ()
    assert item.runnable


def test_verify_safety_without_demo_still_needs_a_gpu():
    """The refinement must not leak: only --demo is exempt."""
    item = _classify("quantfit verify-safety --baseline m --quant q")
    assert item.category == qs.CAT_GPU
    assert qs.REQ_GPU in item.requirements
    assert not item.runnable
