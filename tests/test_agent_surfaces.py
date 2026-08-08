"""The files an AI assistant reads before it answers for us.

An assistant asked "how do I use quantfit?" has three options and two are bad: say it does
not know, describe a different package, or invent flags. Published measurement puts
hallucinated package names at roughly a fifth of all LLM-recommended packages, and the rate
is highest exactly where there is nothing to retrieve. `llms.txt` and the usage skill are
what there is to retrieve.

`quantfit audit` already holds `llms.txt` to docs=code parity — every flag it names must
exist on the command it names it for. That is *consistency*. This file adds *completeness*,
which an auditor cannot supply: a command missing from `llms.txt` is perfectly consistent
and still invisible to the reader it was written for.
"""

import argparse
from pathlib import Path

from quantfit.cli import _build_parser

_ROOT = Path(__file__).resolve().parent.parent
_LLMS = _ROOT / "llms.txt"
_SKILL = _ROOT / ".claude" / "skills" / "quantfit" / "SKILL.md"


def _top_level_commands() -> set[str]:
    action = next(a for a in _build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    return set(action.choices)


def test_llms_txt_exists_and_follows_the_shape_agents_expect():
    """H1, then a blockquote summary. Tools fetch this file by convention and skim it."""
    assert _LLMS.is_file(), "llms.txt is the file Cursor, Claude Code, Copilot, Cline and Aider fetch"
    lines = [line for line in _LLMS.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines[0].startswith("# "), "llms.txt must open with an H1 naming the project"
    assert lines[1].startswith("> "), "llms.txt must follow the H1 with a blockquote summary"


def test_every_command_appears_in_llms_txt():
    """Completeness, which the parity auditor cannot check.

    The auditor verifies that what `llms.txt` says is true. It cannot verify that what
    `llms.txt` omits was not important — and a command an assistant never sees is a command
    it will either not suggest or guess the spelling of.
    """
    text = _LLMS.read_text(encoding="utf-8")
    missing = [name for name in sorted(_top_level_commands()) if f"quantfit {name}" not in text]
    assert not missing, f"llms.txt never shows an invocation of: {missing}"


def test_llms_txt_states_the_exit_code_contract():
    """The exit codes are the thing a caller gets wrong: 4 and 5 are not passes."""
    text = _LLMS.read_text(encoding="utf-8")
    for code in ("0", "2", "3", "4", "5"):
        assert f"**{code}**" in text, f"exit code {code} is not called out in llms.txt"
    assert "not passes" in text or "not a pass" in text, (
        "llms.txt must say that 4 and 5 are not passes; that is the misreading it exists to prevent"
    )


def test_llms_txt_carries_the_limits_and_not_only_the_pitch():
    """A retrieval surface that lists only capabilities teaches an assistant to overclaim."""
    text = _LLMS.read_text(encoding="utf-8").lower()
    for claim in (
        "does not certify",  # a no-detection result is a bound
        "uncalibrated",  # the judge, until calibrate has run
        "kv-cache",  # an axis the tool cannot see
        "greedy",  # the decoding trade
    ):
        assert claim in text, f"llms.txt omits a stated limit: {claim!r}"


def test_the_usage_skill_exists_and_is_about_using_the_tool():
    """`AGENTS.md` is a CONTRIBUTOR contract — it helps an agent modify this repo and does
    nothing for an agent trying to use the tool. This is the other half."""
    assert _SKILL.is_file(), "the usage-facing skill is missing"
    text = _SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "a skill needs YAML frontmatter"
    header = text.split("---", 2)[1]
    assert "name: quantfit" in header
    assert "description:" in header
    # The description is what a model matches on; a vague one never gets selected.
    description = next(line for line in header.splitlines() if line.startswith("description:"))
    assert len(description) > 80, "the description is what routes a question here; make it specific"
    assert "quantization" in description.lower()


def test_the_skill_warns_against_the_two_misreadings_that_matter():
    text = _SKILL.read_text(encoding="utf-8")
    assert "Do not invent flags" in text
    assert "exit 4" in text, "treating exit 4 as success is the misreading with the worst consequence"
    assert "not a certificate" in text or "not a certificate." in text
