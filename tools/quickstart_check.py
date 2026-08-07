#!/usr/bin/env python3
"""README-only quickstart check — ROADMAP 1.0's gate clause as a script, not a promise.

ROADMAP 1.0's gate reads, in part: *"scripted README-only quickstart passes in a clean
venv."* A human reading the README and typing its commands is not a gate — it is a
memory of a gate. This script is the gate: it reads `README.md`, extracts **every**
shell command it advertises, classifies each one by what it actually needs, runs the
ones a clean venv can run, and refuses to be quiet about the ones it did not run.

--------------------------------------------------------------------------------
## The two jobs, and why the second one is the point

**1. Execution.** Category (a) commands — no network, no GPU, no pre-existing
artifact — are executed against the installed CLI and reported PASS/FAIL. This is the
literal gate clause.

**2. Drift detection, which is the job that actually catches things.** Every extracted
`quantfit` command is validated against the CLI's own `--help` surface: the subcommand
must exist, every flag must exist on that subcommand, and every value passed to a
choice-flag (`--tier smoke`, `--method awq`) must be one of the choices the CLI
declares. A README that advertises a command, flag or choice the shipped CLI no longer
defines makes this script **exit 1**. That is the docs=code skew ROADMAP 1.0's audit
exists to catch, and category (a) being small does not weaken it: the validation runs
over commands from every category, because the *existence* of a command costs nothing
to check and needs no GPU.

The CLI surface is read by running `quantfit --help` and `quantfit <sub> --help`
(recursively, for sub-subcommands like `calibrate sheet`) as **subprocesses** against
the installed console script. This module deliberately never imports `quantfit`: the
thing under test is the wheel a reader of the README installed, entry point included,
and an in-process import would test the source tree instead.

--------------------------------------------------------------------------------
## The categories — five, not four, and the fifth is an honesty tax

  a  `clean-venv`     no network, no GPU, no downloaded weights, no input artifact.
                      RUN.
  b  `network`        needs the Hub or PyPI, but no weights on disk (metadata only,
                      or a package install). NOT RUN.
  c  `gpu`            loads or quantizes weights through torch/llm-compressor. NOT RUN.
  d  `long-download`  materializes multi-GB weights (GGUF pairs run on CPU, so they
                      are not (c) — but nobody runs them in a unit gate). NOT RUN.
  e  `not-runnable`   cannot be run verbatim at all: it contains a `<placeholder>`, or
                      it consumes an artifact (a drift report, a capture, a target
                      manifest) that a clean venv does not have. NOT RUN.

A command's `requirements` set is the honest record; `category` is only the strongest
blocker in that set, ranked e > c > d > b > a. Read `requirements` if you care.

Categories (b), (c), (d) and (e) are **never executed** — not sampled, not "tried
anyway". Each is reported as UNRUN with the specific reason it was not run, so the
output is a list of what this gate does *not* cover. That list is the deliverable.

--------------------------------------------------------------------------------
## What makes the (a) run trustworthy

Category (a) commands are executed with the network and the GPU **removed from the
environment**, not merely assumed absent:

    HF_HUB_OFFLINE=1  TRANSFORMERS_OFFLINE=1  HF_DATASETS_OFFLINE=1
    HF_HUB_DISABLE_TELEMETRY=1  CUDA_VISIBLE_DEVICES=-1

So a misclassification cannot pass silently: a command classified (a) that in fact
reaches for the Hub or a CUDA device fails loudly here instead of succeeding on a
developer box and failing on a reader's. The same environment is used for the `--help`
introspection calls.

--------------------------------------------------------------------------------
## Exit codes

  0  every extracted command validated against the CLI, and every category-(a)
     command ran and exited 0.
  1  drift or failure: an unknown subcommand/flag/choice in the README, or a
     category-(a) command that failed.
  2  operational: no README, no runnable `quantfit` binary, unparseable `--help`.

Exit 0 means *the README's commands exist and its clean-venv subset works*. It does
not mean the README is correct — a command can exist, run, and still document a lie.
Nothing here validates output text, and nothing here runs on hardware.

--------------------------------------------------------------------------------
## CI usage

After installing the built wheel into a clean venv (see `.github/workflows/ci.yml`
`install-smoke` and `.github/workflows/canary.yml` `quickstart-install`):

    $BIN/python tools/quickstart_check.py --quantfit-bin $BIN/quantfit \\
        --json quickstart-check.json

`--quantfit-bin` is shlex-split, so `--quantfit-bin "python -m quantfit.cli"` also
works for a source checkout with no console script on PATH.

Stdlib only, by design: it must run inside the reader's venv without adding a
dependency to it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess  # running the installed CLI through its process boundary is the point
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------------
# Requirements and categories
# --------------------------------------------------------------------------------

REQ_NETWORK = "network"
REQ_DOWNLOAD = "download"
REQ_GPU = "gpu"
REQ_ARTIFACT = "artifact"
REQ_PLACEHOLDER = "placeholder"
REQ_UNCLASSIFIED = "unclassified"

CAT_CLEAN_VENV = "a:clean-venv"
CAT_NETWORK = "b:network"
CAT_GPU = "c:gpu"
CAT_DOWNLOAD = "d:long-download"
CAT_NOT_RUNNABLE = "e:not-runnable"

# Strongest blocker first: the category is the first requirement present here.
_CATEGORY_RANK: tuple[tuple[str, str], ...] = (
    (REQ_UNCLASSIFIED, CAT_NOT_RUNNABLE),
    (REQ_PLACEHOLDER, CAT_NOT_RUNNABLE),
    (REQ_ARTIFACT, CAT_NOT_RUNNABLE),
    (REQ_GPU, CAT_GPU),
    (REQ_DOWNLOAD, CAT_DOWNLOAD),
    (REQ_NETWORK, CAT_NETWORK),
)

RUNNABLE_CATEGORY = CAT_CLEAN_VENV

# Per-subcommand requirements. Keyed by the FIRST subcommand only; refinements that
# depend on the arguments live in `_refine`. Every entry cites why it is what it is,
# because this table is the classifier's entire claim to being auditable.
SUBCOMMAND_REQUIREMENTS: Mapping[str, tuple[str, ...]] = {
    # `catalog()` is a local constant table (quantfit/registry.py).
    "list": (),
    # `route()` never touches the Hub — it routes on the model id as a STRING plus the
    # local target (quantfit/policy/route.py); on a CPU-only host rule 1 fires and
    # returns GGUF Q4_K_M, so this is the one README command a clean venv can run.
    "plan": (),
    # `capacity_plan` -> `estimate_fp16_bytes` reads HF metadata; no weights.
    "check": (REQ_NETWORK,),
    # Forward passes on real weights.
    "probe": (REQ_NETWORK, REQ_DOWNLOAD, REQ_GPU),
    "quantize": (REQ_NETWORK, REQ_DOWNLOAD, REQ_GPU),
    # Smoke-loads a LOCAL artifact through transformers (GGUF: magic bytes only).
    "verify": (REQ_ARTIFACT, REQ_GPU),
    # Two arms + the judge. Refined to CPU for all-GGUF pairs (CHANGELOG 0.4.1).
    "verify-safety": (REQ_NETWORK, REQ_DOWNLOAD, REQ_GPU),
    "gate": (REQ_NETWORK, REQ_DOWNLOAD, REQ_GPU),
    # Plus a target manifest that a clean venv does not have.
    "screen": (REQ_ARTIFACT, REQ_NETWORK, REQ_DOWNLOAD, REQ_GPU),
    # Pure local rendering — but of a drift report that must already exist.
    "emit": (REQ_ARTIFACT,),
    # Pure local — but of a capture / labeling sheet that must already exist.
    "calibrate": (REQ_ARTIFACT,),
}

# Non-quantfit programs the README is allowed to advertise.
PROGRAM_REQUIREMENTS: Mapping[str, tuple[str, ...]] = {
    "pip": (REQ_NETWORK,),
    "pip3": (REQ_NETWORK,),
    "python": (REQ_UNCLASSIFIED,),
    "docker": (REQ_NETWORK, REQ_DOWNLOAD),
}

QUANTFIT = "quantfit"

# Args that name a model / artifact arm, used by the refinements below.
_ARM_FLAGS = ("--baseline", "--fp16", "--quant", "--model")

_REASONS: Mapping[str, str] = {
    REQ_NETWORK: "reaches the network (Hub metadata or a package index)",
    REQ_DOWNLOAD: "materializes multi-GB weights",
    REQ_GPU: "loads weights through torch / llm-compressor",
    REQ_ARTIFACT: "consumes an artifact a clean venv does not have",
    REQ_PLACEHOLDER: "contains a <placeholder> and cannot be run verbatim",
    REQ_UNCLASSIFIED: "no classification rule covers this program",
}

# The offline+no-GPU environment category (a) runs are executed under. Removing the
# capability is the point: a misclassified command must FAIL here, not succeed.
SANDBOX_ENV: Mapping[str, str] = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    # "-1", NOT the empty string. Measured on torch 2.11.0+cu128 / Windows:
    # CUDA_VISIBLE_DEVICES="" leaves `torch.cuda.is_available()` True while
    # `device_count()` is 0, so the empty value tests a torch quirk instead of
    # simulating a GPU-less host. "-1" gives is_available() False, count 0.
    "CUDA_VISIBLE_DEVICES": "-1",
    "NO_COLOR": "1",
    "PYTHONIOENCODING": "utf-8",
}

DEFAULT_TIMEOUT_S = 180
MAX_SURFACE_DEPTH = 3

BASH_INFO_STRINGS = frozenset({"bash", "sh", "shell", "console", "shell-session", "sh-session"})

SOURCE_FENCED = "fenced"
SOURCE_INLINE = "inline"

SEVERITY_ERROR = "error"
SEVERITY_NOTE = "note"

JSON_SCHEMA = "quantfit-quickstart-check/1"

EXIT_OK, EXIT_DRIFT, EXIT_OPERATIONAL = 0, 1, 2


class QuickstartCheckError(RuntimeError):
    """Operational failure of the checker itself (exit 2) — never a README verdict."""


# --------------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Command:
    """One advertised shell command, normalized to a single line."""

    text: str
    argv: tuple[str, ...]
    source: str  # SOURCE_FENCED | SOURCE_INLINE
    line: int  # 1-based line in the README where the command starts
    block: int | None  # fenced-block index (1-based), None for inline spans

    @property
    def program(self) -> str:
        return self.argv[0] if self.argv else ""

    @property
    def normalized(self) -> str:
        """The command as it will actually be executed: comments and padding gone."""
        return shlex.join(self.argv)

    @property
    def is_quantfit(self) -> bool:
        return self.program == QUANTFIT


_FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)```(?P<info>[^\n]*)$", re.MULTILINE)
# Shell prompts only. `#` is deliberately NOT a prompt here: stripping it would turn
# every comment line in a fenced block into a command.
_PROMPT_RE = re.compile(r"^\s*(?:\$|>)\s+")


@dataclass(frozen=True)
class _Fence:
    index: int
    fence_start: int
    body_start: int
    body_end: int
    fence_end: int
    info: str
    first_body_line: int


def _iter_fences(text: str) -> list[_Fence]:
    """Fenced blocks, paired by alternation (open, close, open, close, ...)."""
    fences = list(_FENCE_RE.finditer(text))
    blocks: list[_Fence] = []
    index = 0
    i = 0
    while i < len(fences) - 1:
        opener, closer = fences[i], fences[i + 1]
        index += 1
        blocks.append(
            _Fence(
                index=index,
                fence_start=opener.start(),
                body_start=min(opener.end() + 1, len(text)),
                body_end=closer.start(),
                fence_end=closer.end(),
                info=opener.group("info").strip(),
                first_body_line=text[: opener.end()].count("\n") + 2,
            )
        )
        i += 2
    return blocks


def _blank_out_fenced(text: str) -> str:
    """Replace fenced blocks (markers included) with spaces, preserving byte offsets.

    Offsets are preserved so inline-span line numbers stay honest; a length-changing
    substitution would report the wrong README line and make a finding unfixable.
    """
    out = list(text)
    for fence in _iter_fences(text):
        for i in range(fence.fence_start, fence.fence_end):
            if out[i] != "\n":
                out[i] = " "
    return "".join(out)


def _split_command(raw: str) -> tuple[str, ...]:
    """shlex a single logical command line; `()` when it is empty or unparseable."""
    try:
        return tuple(shlex.split(raw, comments=True))
    except ValueError:
        return ()


def extract_fenced_commands(text: str) -> list[Command]:
    """Every command in every ```bash-family fenced block, `\\`-continuations joined."""
    commands: list[Command] = []
    for fence in _iter_fences(text):
        words = fence.info.split()
        if not words or words[0].lower() not in BASH_INFO_STRINGS:
            continue  # a bare ``` block is sample OUTPUT, not commands
        index = fence.index
        body = text[fence.body_start : fence.body_end]
        pending: list[str] = []
        pending_line = 0
        for offset, raw_line in enumerate(body.splitlines()):
            line_no = fence.first_body_line + offset
            stripped = _PROMPT_RE.sub("", raw_line).strip()
            if not pending and not stripped:
                continue
            if not pending:
                pending_line = line_no
            if stripped.endswith("\\"):
                pending.append(stripped[:-1].strip())
                continue
            pending.append(stripped)
            joined = " ".join(part for part in pending if part).strip()
            pending = []
            if not joined or joined.startswith("#"):
                continue
            argv = _split_command(joined)
            if argv:
                commands.append(Command(text=joined, argv=argv, source=SOURCE_FENCED, line=pending_line, block=index))
        if pending:  # a trailing `\` at the end of a block: keep it, do not drop it
            joined = " ".join(part for part in pending if part).strip()
            argv = _split_command(joined)
            if argv:
                commands.append(Command(text=joined, argv=argv, source=SOURCE_FENCED, line=pending_line, block=index))
    return commands


def extract_inline_commands(text: str, program: str = QUANTFIT) -> list[Command]:
    """`quantfit ...` spans in backticked prose, outside fenced blocks.

    The README advertises `screen` and `emit` only in prose, so an extractor that read
    fenced blocks alone would leave two shipped commands unaudited. Spans may wrap
    across a line; whitespace is collapsed.
    """
    masked = _blank_out_fenced(text)
    commands: list[Command] = []
    for match in re.finditer(r"`([^`]+)`", masked):
        span = " ".join(match.group(1).split())
        if not span.startswith(program + " "):
            continue
        argv = _split_command(span)
        if not argv:
            continue
        commands.append(
            Command(text=span, argv=argv, source=SOURCE_INLINE, line=text[: match.start()].count("\n") + 1, block=None)
        )
    return commands


def extract_commands(text: str, *, include_inline: bool = True) -> list[Command]:
    """Every advertised command, fenced first, then inline, in README order."""
    commands = extract_fenced_commands(text)
    if include_inline:
        commands += extract_inline_commands(text)
    return sorted(commands, key=lambda c: (c.line, c.source != SOURCE_FENCED))


# --------------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Classification:
    command: Command
    category: str
    requirements: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def runnable(self) -> bool:
        return self.category == RUNNABLE_CATEGORY


def subcommand_of(argv: Sequence[str]) -> str:
    """The first non-flag token after the program name, or '' if there is none."""
    return next((tok for tok in argv[1:] if not tok.startswith("-")), "")


def _has_placeholder(argv: Sequence[str]) -> bool:
    return any("<" in tok and ">" in tok for tok in argv)


def _gguf_ref(token: str) -> bool:
    return token.lower().endswith(".gguf")


def _arm_values(argv: Sequence[str]) -> list[str]:
    values: list[str] = []
    for i, tok in enumerate(argv):
        if tok in _ARM_FLAGS and i + 1 < len(argv):
            values.append(argv[i + 1])
        elif "=" in tok and tok.split("=", 1)[0] in _ARM_FLAGS:
            values.append(tok.split("=", 1)[1])
    return values


def _refine(subcommand: str, argv: Sequence[str], reqs: set[str]) -> list[str]:
    """Argument-dependent adjustments. Returns extra human-readable reasons."""
    extra: list[str] = []
    if subcommand in ("verify-safety", "gate"):
        arms = _arm_values(argv)
        if arms and all(_gguf_ref(a) for a in arms):
            # Both arms GGUF => one pinned llama.cpp binary on CPU (CHANGELOG 0.4.1,
            # README "GGUF pairs"). No GPU is needed; the multi-GB download remains.
            reqs.discard(REQ_GPU)
            extra.append("both arms are GGUF: runs on CPU under one pinned llama.cpp binary, so no GPU")
    if subcommand == "verify-safety" and any(_gguf_ref(a) for a in _arm_values(argv)):
        reqs.add(REQ_DOWNLOAD)
    return extra


def classify(command: Command) -> Classification:
    """Map a command onto its requirement set and the strongest blocker."""
    reqs: set[str] = set()
    reasons: list[str] = []

    if _has_placeholder(command.argv):
        reqs.add(REQ_PLACEHOLDER)

    if command.is_quantfit:
        subcommand = subcommand_of(command.argv)
        if not subcommand:
            # Bare `quantfit` or `quantfit --help`: parser-only, no dispatch.
            reasons.append("no subcommand: argparse only")
        elif subcommand in SUBCOMMAND_REQUIREMENTS:
            reqs.update(SUBCOMMAND_REQUIREMENTS[subcommand])
            reasons.extend(_refine(subcommand, command.argv, reqs))
        else:
            # Unknown subcommand: the surface validation reports it as drift; the
            # classifier refuses to guess, and refuses to call it runnable.
            reqs.add(REQ_UNCLASSIFIED)
    else:
        reqs.update(PROGRAM_REQUIREMENTS.get(command.program, (REQ_UNCLASSIFIED,)))

    category = next((cat for req, cat in _CATEGORY_RANK if req in reqs), CAT_CLEAN_VENV)
    reasons = [_REASONS[r] for r in sorted(reqs)] + reasons
    if not reqs:
        reasons.append("no network, no GPU, no input artifact")
    return Classification(command=command, category=category, requirements=tuple(sorted(reqs)), reasons=tuple(reasons))


# --------------------------------------------------------------------------------
# The CLI surface, read from `--help`
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandNode:
    """One node of the installed CLI's argparse surface."""

    path: tuple[str, ...]
    flags: frozenset[str]
    value_flags: frozenset[str]
    flag_choices: Mapping[str, tuple[str, ...]]
    positional_choices: tuple[str, ...]
    children: Mapping[str, CommandNode] = field(default_factory=dict)


_OPTION_LINE_RE = re.compile(r"^ {1,4}(-{1,2}[A-Za-z0-9])")
_BRACE_RE = re.compile(r"\{([^{}]*)\}")


def _section(help_text: str, header: str) -> list[str]:
    """Indented body lines of an argparse section, e.g. 'options:'."""
    lines = help_text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip().lower() == header)
    except StopIteration:
        return []
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith(" "):
            break
        body.append(line)
    return body


def parse_help(help_text: str) -> tuple[frozenset[str], frozenset[str], dict[str, tuple[str, ...]], tuple[str, ...]]:
    """(flags, value_flags, flag_choices, positional_choices) from one `--help` dump.

    Only the `options:` entry lines are read — never the wrapped help prose, which
    mentions other flags by name. Reading prose would make a DELETED flag still look
    present, which is precisely the drift this checker exists to catch.
    """
    flags: set[str] = set()
    value_flags: set[str] = set()
    flag_choices: dict[str, tuple[str, ...]] = {}

    for header in ("options:", "optional arguments:"):
        for line in _section(help_text, header):
            if not _OPTION_LINE_RE.match(line):
                continue
            chunk = re.split(r"\s{2,}", line.strip())[0].strip()
            parts = [p.strip() for p in chunk.split(",") if p.strip()]
            names = [p.split()[0] for p in parts if p.split() and p.split()[0].startswith("-")]
            if not names:
                continue
            takes_value = any(len(p.split()) > 1 for p in parts)
            choice_match = _BRACE_RE.search(chunk)
            choices = tuple(c.strip() for c in choice_match.group(1).split(",")) if choice_match else ()
            for name in names:
                flags.add(name)
                if takes_value:
                    value_flags.add(name)
                if choices:
                    flag_choices[name] = choices

    positional: tuple[str, ...] = ()
    for line in _section(help_text, "positional arguments:"):
        match = _BRACE_RE.search(line)
        if match:
            positional = tuple(c.strip() for c in match.group(1).split(",") if c.strip())
            break

    return frozenset(flags), frozenset(value_flags), flag_choices, positional


# A runner returns (returncode, stdout, stderr); returncode None means "did not run".
Runner = Callable[[Sequence[str], int], tuple[int | None, str, str]]


_USAGE_RE = re.compile(r"^usage:\s+(.*)$", re.MULTILINE)


def usage_prog(help_text: str) -> tuple[str, ...]:
    """The command words argparse prints after `usage:`, e.g. ('quantfit', 'gate')."""
    match = _USAGE_RE.search(help_text)
    if not match:
        return ()
    words: list[str] = []
    for token in match.group(1).split():
        if token.startswith(("[", "{", "-", "(")):
            break
        words.append(token)
    return tuple(words)


def discover_surface(runner: Runner, *, timeout: int = DEFAULT_TIMEOUT_S) -> CommandNode:
    """Walk `--help` recursively and build the installed CLI's surface.

    A positional's choices are not necessarily subcommands: `quantfit emit` takes a
    plain `choices=("model-card",)` argument, so `quantfit emit model-card --help`
    prints *emit's* help. Recursing on that would loop until the depth cap and invent
    a node the CLI does not have. The `usage:` prog line distinguishes the two — a
    real subparser reprints its own path — so only real subparsers become children.
    """

    def fetch(path: tuple[str, ...]) -> str:
        code, stdout, stderr = runner([*path, "--help"], timeout)
        if code != 0:
            raise QuickstartCheckError(
                f"`{' '.join((QUANTFIT, *path))} --help` exited {code}; cannot read the CLI surface.\n"
                f"{(stderr or stdout).strip()[:400]}"
            )
        return stdout

    def build(path: tuple[str, ...], depth: int, help_text: str) -> CommandNode:
        flags, value_flags, flag_choices, positional = parse_help(help_text)
        if not flags:
            raise QuickstartCheckError(
                f"`{' '.join((QUANTFIT, *path))} --help` produced no parseable option entries; "
                "the help format changed and this checker would silently pass everything."
            )
        children: dict[str, CommandNode] = {}
        if depth < MAX_SURFACE_DEPTH:
            for choice in positional:
                child_path = (*path, choice)
                child_help = fetch(child_path)
                if usage_prog(child_help)[-len(child_path) :] != child_path:
                    continue  # a `choices=` positional, not a subparser
                children[choice] = build(child_path, depth + 1, child_help)
        return CommandNode(
            path=path,
            flags=flags,
            value_flags=value_flags,
            flag_choices=flag_choices,
            positional_choices=positional,
            children=children,
        )

    return build((), 0, fetch(()))


# --------------------------------------------------------------------------------
# Validation — the drift catch
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    kind: str
    severity: str
    command: str
    line: int
    detail: str


def validate_command(command: Command, surface: CommandNode) -> list[Finding]:
    """Every subcommand, flag and choice the README uses must exist in the CLI."""
    if not command.is_quantfit:
        return []

    findings: list[Finding] = []
    node = surface
    index = 1
    while index < len(command.argv):
        token = command.argv[index]
        index += 1
        if token.startswith("-") and token != "-":
            name, _, inline_value = token.partition("=")
            if name in ("-h", "--help"):
                continue
            if name not in node.flags:
                where = " ".join(node.path) or "(top level)"
                findings.append(
                    Finding(
                        kind="unknown-flag",
                        severity=SEVERITY_ERROR,
                        command=command.text,
                        line=command.line,
                        detail=f"`{name}` is not a flag of `quantfit {where}`",
                    )
                )
                continue
            value = inline_value
            if not value and name in node.value_flags and index < len(command.argv):
                value = command.argv[index]
                index += 1
            choices = node.flag_choices.get(name, ())
            if choices and value and value not in choices and "<" not in value:
                findings.append(
                    Finding(
                        kind="unknown-choice",
                        severity=SEVERITY_ERROR,
                        command=command.text,
                        line=command.line,
                        detail=f"`{name} {value}` is not one of {list(choices)}",
                    )
                )
            continue

        if node.children and token in node.children:
            node = node.children[token]
            continue
        if node.positional_choices and token not in node.positional_choices:
            where = " ".join(node.path)
            scope = f"`quantfit {where}`" if where else "the top-level parser"
            findings.append(
                Finding(
                    kind="unknown-subcommand" if not node.path else "unknown-positional",
                    severity=SEVERITY_ERROR,
                    command=command.text,
                    line=command.line,
                    detail=f"`{token}` is not one of {list(node.positional_choices)} on {scope}",
                )
            )
            break
        # A bare value (a model id, a path, a repeated --bits value): nothing to check.
    return findings


def undocumented_subcommands(commands: Sequence[Command], surface: CommandNode) -> tuple[str, ...]:
    """CLI subcommands the README never mentions — reverse drift, reported as a note.

    A note and not an error on purpose: a README is allowed to be a quickstart rather
    than a manual. It is listed because ROADMAP 1.0's docs=code parity audit needs the
    list, not because an omission fails a build.
    """
    advertised = {subcommand_of(command.argv) for command in commands if command.is_quantfit}
    return tuple(sorted(set(surface.positional_choices) - advertised))


# --------------------------------------------------------------------------------
# Execution of category (a)
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class RunResult:
    command: str  # the argv actually executed, not the README line (comments stripped)
    line: int
    ok: bool
    returncode: int | None
    seconds: float
    stdout_tail: str
    stderr_tail: str


def _tail(text: str, limit: int = 600) -> str:
    text = text.strip()
    return text if len(text) <= limit else "..." + text[-limit:]


def run_clean_venv(
    classifications: Sequence[Classification], runner: Runner, *, timeout: int = DEFAULT_TIMEOUT_S
) -> list[RunResult]:
    """Execute exactly the category-(a) commands. Nothing else is ever executed."""
    results: list[RunResult] = []
    for item in classifications:
        # Only quantfit commands are ever executed: the runner IS the installed CLI.
        # A non-quantfit command cannot reach category (a) with the shipped tables.
        if not item.runnable or not item.command.is_quantfit:
            continue
        argv = list(item.command.argv[1:])
        started = time.monotonic()
        code, stdout, stderr = runner(argv, timeout)
        results.append(
            RunResult(
                command=shlex.join(item.command.argv),
                line=item.command.line,
                ok=code == 0,
                returncode=code,
                seconds=round(time.monotonic() - started, 2),
                stdout_tail=_tail(stdout),
                stderr_tail=_tail(stderr),
            )
        )
    return results


def subprocess_runner(prefix: Sequence[str]) -> Runner:
    """A Runner that invokes the installed CLI with the network and GPU removed."""

    def run(argv: Sequence[str], timeout: int) -> tuple[int | None, str, str]:
        env = {**os.environ, **SANDBOX_ENV}
        try:
            # argv is shlex-split from the README and passed as a list: never a shell string.
            proc = subprocess.run(
                [*prefix, *argv],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            raise QuickstartCheckError(
                f"cannot run `{' '.join(prefix)}`: {exc}. Install the wheel first, or pass "
                "--quantfit-bin (it is shlex-split, so 'python -m quantfit.cli' works)."
            ) from exc
        except subprocess.TimeoutExpired:
            return None, "", f"timed out after {timeout}s"
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    return run


# --------------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------------


def build_report(
    readme: Path,
    prefix: Sequence[str],
    classifications: Sequence[Classification],
    findings: Sequence[Finding],
    runs: Sequence[RunResult],
    undocumented: Sequence[str],
    *,
    ran: bool,
) -> dict:
    by_category: dict[str, int] = {}
    for item in classifications:
        by_category[item.category] = by_category.get(item.category, 0) + 1
    return {
        "schema": JSON_SCHEMA,
        "readme": str(readme),
        "quantfit_bin": list(prefix),
        "sandbox_env": dict(SANDBOX_ENV),
        "n_commands": len(classifications),
        "by_category": dict(sorted(by_category.items())),
        "commands": [
            {
                "text": c.command.text,  # verbatim from the README, comments included
                "argv": list(c.command.argv),  # what would actually be executed
                "line": c.command.line,
                "source": c.command.source,
                "block": c.command.block,
                "category": c.category,
                "requirements": list(c.requirements),
                "reasons": list(c.reasons),
                "run": c.runnable and ran,
            }
            for c in classifications
        ],
        "runs": [
            {
                "command": r.command,
                "line": r.line,
                "ok": r.ok,
                "returncode": r.returncode,
                "seconds": r.seconds,
                "stdout_tail": r.stdout_tail,
                "stderr_tail": r.stderr_tail,
            }
            for r in runs
        ],
        "findings": [
            {"kind": f.kind, "severity": f.severity, "command": f.command, "line": f.line, "detail": f.detail}
            for f in findings
        ],
        "undocumented_subcommands": list(undocumented),
        "executed": ran,
    }


def _print_report(report: dict, runs: Sequence[RunResult], classifications: Sequence[Classification]) -> None:
    """ASCII only: this runs on a Windows console the CLI itself has to reconfigure."""
    print(f"readme:      {report['readme']}")
    print(f"quantfit:    {' '.join(report['quantfit_bin'])}")
    print(f"commands:    {report['n_commands']} extracted  {report['by_category']}")
    print()
    print("category (a) - runnable in a clean venv (no network, no GPU, no artifact):")
    runnable = [c for c in classifications if c.runnable]
    if not runnable:
        print("  (none) - the README advertises no command a clean venv can run.")
    for result in runs:
        status = "PASS" if result.ok else "FAIL"
        print(f"  [{status}] L{result.line} {result.command}  (exit {result.returncode}, {result.seconds}s)")
        if not result.ok:
            for label, tail in (("stdout", result.stdout_tail), ("stderr", result.stderr_tail)):
                if tail:
                    print(f"         {label}: {tail}")
    if runnable and not runs:
        print("  (not executed: --no-run)")
    print()
    print("NOT RUN - every other advertised command, with the reason it was not run:")
    for item in classifications:
        if item.runnable:
            continue
        print(f"  [UNRUN] L{item.command.line} {item.command.normalized}")
        print(f"          {item.category}: {'; '.join(item.reasons)}")
    print()
    if report["undocumented_subcommands"]:
        print(f"note: CLI subcommands the README never shows: {', '.join(report['undocumented_subcommands'])}")
    findings = report["findings"]
    if findings:
        print("FINDINGS (docs=code drift):")
        for finding in findings:
            print(f"  [{finding['severity']}] L{finding['line']} {finding['kind']}: {finding['detail']}")
            print(f"          in: {finding['command']}")
    else:
        print("findings: none - every advertised subcommand, flag and choice exists in the installed CLI.")


# --------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------


def _default_readme() -> Path:
    return Path(__file__).resolve().parent.parent / "README.md"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quickstart_check.py",
        description="Extract, classify and run README.md's advertised commands (ROADMAP 1.0 gate clause).",
        epilog="exit 0 = clean, 1 = README/CLI drift or a failed clean-venv command, 2 = operational.",
    )
    parser.add_argument("--readme", type=Path, default=None, help="README to audit (default: the repo's)")
    parser.add_argument(
        "--quantfit-bin",
        default=QUANTFIT,
        help="how to invoke the installed CLI; shlex-split (default: quantfit)",
    )
    parser.add_argument("--json", type=Path, default=None, metavar="PATH", help="write the machine-readable report")
    parser.add_argument("--no-run", action="store_true", help="validate only; execute nothing (still needs the CLI)")
    parser.add_argument("--no-inline", action="store_true", help="fenced blocks only; skip backticked prose commands")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="per-command timeout in seconds")
    parser.add_argument(
        "--require-runnable",
        type=int,
        default=0,
        metavar="N",
        help="fail unless at least N category-(a) commands were found (default 0: report the gap, do not fail)",
    )
    return parser


def decide(
    classifications: Sequence[Classification],
    findings: Sequence[Finding],
    runs: Sequence[RunResult],
    *,
    require_runnable: int = 0,
) -> tuple[str, int, dict]:
    """(verdict, exit_code, why) — the whole pass/fail rule, in one testable place.

    Three independent ways to fail, and none of them is "the README looks wrong":
    an advertised command that does not exist, a clean-venv command that did not
    run clean, and (opt-in) a quickstart with fewer runnable commands than the
    caller demanded. Notes never fail a build.
    """
    n_runnable = sum(1 for item in classifications if item.runnable)
    why = {
        "n_runnable": n_runnable,
        "n_errors": sum(1 for f in findings if f.severity == SEVERITY_ERROR),
        "n_failed_runs": sum(1 for r in runs if not r.ok),
        "short_of_required_runnable": n_runnable < require_runnable,
        "require_runnable": require_runnable,
    }
    failed = bool(why["n_errors"] or why["n_failed_runs"] or why["short_of_required_runnable"])
    return ("FAIL", EXIT_DRIFT, why) if failed else ("PASS", EXIT_OK, why)


def _force_utf8_stdio() -> None:
    """Same guard quantfit/cli.py uses: a cp1252 console must not kill the report."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def main(argv: Sequence[str] | None = None) -> int:
    _force_utf8_stdio()
    args = build_arg_parser().parse_args(argv)
    readme = (args.readme or _default_readme()).resolve()
    prefix = shlex.split(args.quantfit_bin)
    if not prefix:
        print("error: --quantfit-bin is empty", file=sys.stderr)
        return EXIT_OPERATIONAL

    try:
        text = readme.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read {readme}: {exc}", file=sys.stderr)
        return EXIT_OPERATIONAL

    commands = extract_commands(text, include_inline=not args.no_inline)
    classifications = [classify(command) for command in commands]

    runner = subprocess_runner(prefix)
    try:
        surface = discover_surface(runner, timeout=args.timeout)
        findings: list[Finding] = []
        for command in commands:
            findings.extend(validate_command(command, surface))
        undocumented = undocumented_subcommands(commands, surface)
        runs = [] if args.no_run else run_clean_venv(classifications, runner, timeout=args.timeout)
    except QuickstartCheckError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_OPERATIONAL

    report = build_report(readme, prefix, classifications, findings, runs, undocumented, ran=not args.no_run)
    _print_report(report, runs, classifications)

    verdict, exit_code, why = decide(classifications, findings, runs, require_runnable=args.require_runnable)
    n_runnable = why["n_runnable"]
    report["verdict"] = verdict
    report["exit_code"] = exit_code
    report["why"] = why

    if args.json:
        try:
            if args.json.parent != Path():
                args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write {args.json}: {exc}", file=sys.stderr)
            return EXIT_OPERATIONAL
        print(f"\nreport -> {args.json}")

    print()
    if why["short_of_required_runnable"]:
        print(
            f"FAIL: --require-runnable {args.require_runnable} but only {n_runnable} category-(a) command(s) "
            "are advertised."
        )
    if why["n_errors"]:
        print(f"FAIL: {why['n_errors']} README command(s) name something the installed CLI does not define.")
    if why["n_failed_runs"]:
        print(f"FAIL: {why['n_failed_runs']} category-(a) command(s) failed in a clean venv.")
    if verdict == "PASS":
        print(
            f"PASS: {len(commands)} advertised command(s) all exist in the installed CLI; "
            f"{len(runs)} clean-venv command(s) ran and passed."
        )
        print(
            "      This gate covers existence + the clean-venv subset ONLY. "
            f"{len(commands) - n_runnable} command(s) were NOT run - see the UNRUN list."
        )
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
