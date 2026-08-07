"""docs=code parity auditor — the ROADMAP 1.0 check that every prose claim is checkable.

This repository makes an unusually large number of claims that a machine can verify:
CLI commands and flags, exit codes, `file:symbol` citations, schema field names, and
numeric constants quoted into documents. Several of those have already drifted during
development and were caught by hand. Hand-catching does not scale past nine milestones,
and a standard whose documents disagree with its implementation is not a standard.

Five checks, each answering a question a reader would otherwise have to answer by grep:

  1. COMMAND PARITY      — do the commands and flags the docs advertise exist, and is
                           every command/flag the CLI defines documented anywhere? The
                           parser is WALKED (`cli._build_parser`), never regexed: a
                           regex over argparse source re-implements argparse, and the
                           re-implementation is the thing that drifts.
  2. CITATION RESOLUTION — does every `file:symbol` / `file:line` citation resolve?
                           `file:symbol` MUST resolve (error). `file:line` is fragile by
                           construction — any edit above the line moves it — so it is a
                           warning class, and when the citing sentence quotes the line's
                           text the quote is checked against the file too.
  3. EXIT-CODE PARITY    — do the exit codes documented in `spec/qsr-v0.md` §5.7/§5.8,
                           `docs/ci-integration.md` and `README.md` agree with the
                           constants the modules define, with each other, and with what
                           `cli._dispatch` actually returns?
  4. CONSTANT PARITY     — do the values quoted into documents match the shipped ones?
                           Declarative: `CONSTANT_CLAIMS` maps a doc-visible name (or an
                           explicit prose pattern) to a module attribute, so adding a
                           claim is one line and never a new code path.
  5. SCHEMA-FIELD PARITY — do the field names documented for the drift report, the screen
                           summary, the gate decision, the calibration report and the
                           reproduction record exist in the code that emits them?

What this module deliberately does NOT do: assert that anything was validated on
hardware, or that a claim is *true* — only that two surfaces in this repo agree. A green
audit means the docs and the code tell the same story; whether that story was ever run on
a GPU is a question about runs, and no static check can answer it.

Findings are returned, never printed: `audit()` hands back a structured dict so a caller
can render it, diff it, or fail a build on it. Exit mapping for a CLI wrapper:
`EXIT_CLEAN` (0) no error-severity findings, `EXIT_DRIFT` (3) drift found,
`EXIT_OPERATIONAL` (2) `AuditError` — the same 0/3/2 shape as every other verdict
surface in this package (QSR v0 §5.7), so a CI script does not learn a second dialect.

Anti-vacuity: every check reports a `coverage` block (docs read, invocations parsed,
citations seen, claims matched). An auditor that silently inspects nothing is worse than
no auditor, because it converts "unchecked" into "checked and clean" — so the numbers
that would expose that are part of the result, not a debug aid.
"""

from __future__ import annotations

import argparse
import ast
import bisect
import importlib
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import Any

AUDIT_SCHEMA_VERSION = 1

# --- exit codes -------------------------------------------------------------------
# Same code space as the rest of the package (QSR v0 §5.7): 0 is a clean answer, 3 is
# the finding this tool exists to produce, 2 is "the instrument failed", never a verdict.
EXIT_CLEAN = 0
EXIT_OPERATIONAL = 2
EXIT_DRIFT = 3

SEVERITY_ERROR = "error"  # docs and code disagree; someone must edit one of them
SEVERITY_WARNING = "warning"  # fragile-by-construction claim, or an unverifiable one

CHECK_COMMANDS = "command_parity"
CHECK_CITATIONS = "citation_resolution"
CHECK_EXIT_CODES = "exit_code_parity"
CHECK_CONSTANTS = "constant_parity"
CHECK_SCHEMA_FIELDS = "schema_field_parity"

CHECKS = (CHECK_COMMANDS, CHECK_CITATIONS, CHECK_EXIT_CODES, CHECK_CONSTANTS, CHECK_SCHEMA_FIELDS)

# The corpus. Command claims live in the user-facing surfaces; citations live in the
# specs and design docs. One tuple each so extending the audit is a one-line edit.
COMMAND_DOC_GLOBS = ("README.md", "docs/*.md", "spec/*.md")
CITATION_DOC_GLOBS = ("README.md", "docs/*.md", "spec/*.md")
EXIT_CODE_DOC_GLOBS = ("README.md", "docs/ci-integration.md", "spec/qsr-v0.md")
CONSTANT_DOC_GLOBS = ("README.md", "docs/*.md", "spec/*.md")

# Directories that hold build output, caches or vendored copies: a citation resolving
# into `build/` would authenticate a stale copy of the file it means.
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".benchmarks",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "out",
        "quantfit.egg-info",
        "site-packages",
    }
)


class AuditError(RuntimeError):
    """The auditor could not run (missing root, unreadable doc, un-importable CLI).

    Operational, in this package's sense: a clean CLI message and exit 2, never a
    traceback and never a verdict. "I could not check" must not be reachable as "clean".
    """


@dataclass(frozen=True)
class Finding:
    """One disagreement between a document and the code.

    `claim` is what the document says; `actual` is what the code says. Both are carried
    verbatim because a finding a human cannot act on without re-grepping is a to-do, not
    a report.
    """

    check: str
    kind: str
    severity: str
    doc: str  # repo-relative path of the document making the claim ("" when code-only)
    line: int  # 1-indexed line of the claim; 0 when the claim is not line-anchored
    claim: str
    actual: str

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------------
# repo + document loading
# ---------------------------------------------------------------------------------


def _resolve_root(root: str | Path | None) -> Path:
    """The repository root, verified rather than assumed."""
    path = Path(root).resolve() if root is not None else Path(__file__).resolve().parent.parent
    if not path.is_dir():
        raise AuditError(f"audit root {path} is not a directory")
    if not (path / "quantfit" / "cli.py").is_file():
        raise AuditError(f"audit root {path} does not look like the quantfit repo (no quantfit/cli.py)")
    return path


@dataclass(frozen=True)
class _Doc:
    rel: str
    text: str
    lines: tuple[str, ...]
    starts: tuple[int, ...]  # byte-free character offset of each line start, for offset->line

    def line_of(self, offset: int) -> int:
        return bisect.bisect_right(self.starts, offset)


def _load_doc(root: Path, path: Path) -> _Doc:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # unreadable doc: the audit cannot be trusted, so it refuses
        raise AuditError(f"cannot read {path}: {exc}") from exc
    lines = text.splitlines()
    starts, cursor = [], 0
    for line in lines:
        starts.append(cursor)
        cursor += len(line) + 1
    return _Doc(rel=path.relative_to(root).as_posix(), text=text, lines=tuple(lines), starts=tuple(starts))


def _load_docs(root: Path, globs: Sequence[str]) -> tuple[_Doc, ...]:
    seen: dict[str, _Doc] = {}
    for glob in globs:
        for path in sorted(root.glob(glob)):
            if path.is_file():
                doc = _load_doc(root, path)
                seen[doc.rel] = doc
    if not seen:
        # An auditor that read nothing would report "clean". That is the one result it
        # must never be able to produce by accident.
        raise AuditError(f"no documents matched {list(globs)} under {root}")
    return tuple(seen[rel] for rel in sorted(seen))


def _repo_files(root: Path) -> tuple[dict[str, list[str]], tuple[str, ...]]:
    """(basename -> [repo-relative paths], all repo-relative paths) for citation resolution."""
    by_name: dict[str, list[str]] = {}
    everything: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in _SKIP_DIRS for part in rel.parts[:-1]):
            continue
        posix = rel.as_posix()
        everything.append(posix)
        by_name.setdefault(path.name, []).append(posix)
    return by_name, tuple(sorted(everything))


# ---------------------------------------------------------------------------------
# markdown code-span extraction
# ---------------------------------------------------------------------------------

_FENCE = re.compile(r"^\s*(?:```|~~~)")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
# A fenced line that continues the previous shell invocation: an explicit backslash, or
# the continuation style these docs actually use (an indented flag / bracketed group).
_CONTINUES = re.compile(r"^\s+[-\[(]")


def _code_snippets(doc: _Doc) -> list[tuple[int, str]]:
    """Every logical code line in `doc`, as (1-indexed line, text).

    Only code is scanned for commands: prose says things like "`quantfit` quantizes
    across the SOTA matrix", and a scanner that read that as a `quantize` invocation
    would spend the audit's credibility on its own false positives. A fenced block's
    backslash continuations are joined so a multi-line invocation stays one claim.
    """
    out: list[tuple[int, str]] = []
    in_fence = False
    pending: tuple[int, str] | None = None

    def flush() -> None:
        nonlocal pending
        if pending is not None:
            out.append(pending)
            pending = None

    for number, raw in enumerate(doc.lines, start=1):
        if _FENCE.match(raw):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            stripped = raw.rstrip()
            if pending is not None and (_CONTINUES.match(raw) or pending[1].endswith("\\")):
                start, text = pending
                pending = (start, text.rstrip().removesuffix("\\").rstrip() + " " + stripped.strip())
                continue
            flush()
            if stripped.strip():
                pending = (number, stripped)
            continue
        flush()
        for match in _INLINE_CODE.finditer(raw):
            out.append((number, match.group(1)))
    flush()
    return out


# ---------------------------------------------------------------------------------
# python symbol / emitted-key indexes (ast, never import)
# ---------------------------------------------------------------------------------


def _module_symbols(path: Path) -> frozenset[str] | None:
    """Names defined in a python file: functions, classes, `Class.member`, module constants.

    None when the file does not parse — the caller reports that as its own finding
    rather than treating "unparseable" as "symbol absent".
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None
    out: set[str] = set()
    _collect_symbols(tree, "", out)
    return frozenset(out)


def _collect_symbols(node: ast.AST, prefix: str, out: set[str]) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(prefix + child.name)
            out.add(child.name)
        elif isinstance(child, ast.ClassDef):
            out.add(prefix + child.name)
            out.add(child.name)
            _collect_symbols(child, f"{prefix}{child.name}.", out)
        elif isinstance(child, ast.Assign):
            for target in child.targets:
                _add_target(target, prefix, out)
        elif isinstance(child, ast.AnnAssign):
            _add_target(child.target, prefix, out)
        elif isinstance(child, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
            # Module-level constants guarded by `if TYPE_CHECKING:` / `try:` are still
            # module-level constants. Function bodies are NOT descended into: a local
            # variable is not a citable symbol, and pretending otherwise would let a
            # dead citation resolve against someone's loop counter.
            _collect_symbols(child, prefix, out)


def _add_target(target: ast.AST, prefix: str, out: set[str]) -> None:
    if isinstance(target, ast.Name):
        out.add(prefix + target.id)
        out.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            _add_target(element, prefix, out)


def _emitted_keys(path: Path) -> frozenset[str]:
    """String keys a module emits into JSON-ish objects.

    Deliberately an OVER-approximation — every dict-literal key, every `d["k"] = v`
    target, every keyword argument name, every dataclass field. A field the code emits
    somewhere and the doc names is not drift; the check only fires when a documented
    field appears in the emitting code nowhere at all.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return frozenset()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    out.add(key.value)
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if isinstance(node.slice.value, str):
                out.add(node.slice.value)
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg:
                    out.add(keyword.arg)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
        elif isinstance(node, ast.arg):
            # `compare(..., t0_reference=None, t0_candidate=None)`: a record field handed
            # in as a parameter is still a field name the code knows.
            out.add(node.arg)
        # `payload.get("x")` and f-string field names land here; cheap, and it only ever
        # widens the accepted set, which is the safe direction for this check.
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.isidentifier():
            out.add(node.value)
    return frozenset(out)


# ---------------------------------------------------------------------------------
# check 1 — command parity
# ---------------------------------------------------------------------------------

# `quantfit` followed by a word, but not `from quantfit import x` (fixed-width
# lookbehinds, which is all `re` allows, and all this needs).
_INVOCATION = re.compile(r"(?<!from )(?<!import )(?<![\w./\\-])quantfit\s+(?=[a-z])")
# ...and only where a shell would start a command. `ruff check quantfit tests` passes the
# package directory to another tool; reading its next word as a subcommand invents a
# command that never existed, which is the one mistake this check cannot afford.
_COMMAND_POSITION = re.compile(r"(?:^|[$|&;(<>]|\d\.\s|[$#]\s)\s*$")
_FLAG = re.compile(r"(--[A-Za-z][A-Za-z0-9-]*)")
_NOT_A_COMMAND = frozenset({"import", "as", "install", "pip"})
# argparse adds these to every parser and they are not part of anyone's documented
# surface; a doc showing `quantfit gate --help` is not naming an unknown flag.
_UNIVERSAL_FLAGS = frozenset({"-h", "--help"})


def _parser_surface() -> dict[str, dict]:
    """Walk the real argparse parser into {command: {options, aliases, positionals, help}}.

    Private argparse attributes (`_actions`, `_SubParsersAction`) are used on purpose:
    the alternative is re-deriving the surface from source text, which is exactly the
    duplicate that drifts. If argparse ever changes them, this raises `AuditError` and
    the audit refuses — it does not quietly report an empty CLI as fully documented.
    """
    try:
        from quantfit.cli import _build_parser

        parser = _build_parser()
    except Exception as exc:  # any import/build failure is operational here
        raise AuditError(f"cannot build the CLI parser: {exc}") from exc

    surface: dict[str, dict] = {}

    def walk(node: argparse.ArgumentParser, prefix: str) -> None:
        options: dict[str, str] = {}  # option string -> its primary spelling
        aliases: set[str] = set()
        positionals: dict[str, tuple[str, ...] | None] = {}
        try:
            actions = list(node._actions)  # see docstring
        except AttributeError as exc:
            raise AuditError(f"argparse surface unavailable: {exc}") from exc
        for action in actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    walk(sub, f"{prefix} {name}".strip())
                continue
            if action.option_strings:
                usable = [opt for opt in action.option_strings if opt not in ("-h", "--help")]
                if not usable:
                    continue
                primary = next((opt for opt in usable if opt.startswith("--")), usable[0])
                for opt in usable:
                    options[opt] = primary
                    if opt != primary:
                        aliases.add(opt)
                continue
            choices = tuple(str(c) for c in action.choices) if action.choices else None
            positionals[action.dest] = choices
        if prefix:
            surface[prefix] = {
                "options": options,
                "aliases": frozenset(aliases),
                "positionals": positionals,
                "help": node.description or "",
            }

    walk(parser, "")
    # argparse hides a subparser's own help text on the parent's action, not on the
    # child parser, so re-attach it: the help string is a documented claim too (it is
    # what `--help` prints), and the exit-code check reads it.
    try:
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for choice in action._choices_actions:
                    if choice.dest in surface:
                        surface[choice.dest]["help"] = choice.help or ""
    except AttributeError:  # help text is a bonus; its absence is not operational
        pass
    if not surface:
        raise AuditError("the CLI parser exposes no commands — refusing to report that as documented")
    return surface


@dataclass(frozen=True)
class _Invocation:
    doc: str
    line: int
    text: str
    command: str  # "gate", "calibrate sheet", or the raw first token when unknown
    positional: str | None
    flags: tuple[str, ...]


def _parse_invocations(docs: Sequence[_Doc], commands: Iterable[str]) -> list[_Invocation]:
    known = set(commands)
    out: list[_Invocation] = []
    for doc in docs:
        for line, snippet in _code_snippets(doc):
            for match in _INVOCATION.finditer(snippet):
                if not _COMMAND_POSITION.search(snippet[: match.start()]):
                    continue
                tail = snippet[match.end() :]
                tail = tail.split("#", 1)[0]
                tokens = [t for t in re.split(r"[\s=]+", tail.strip()) if t]
                if not tokens:
                    continue
                head = tokens[0].strip("`'\"),.;:")
                if not head or head in _NOT_A_COMMAND:
                    continue
                command, rest = head, tokens[1:]
                positional = None
                if rest and not rest[0].startswith("-"):
                    candidate = rest[0].strip("`'\"),.;:|")
                    if f"{head} {candidate}" in known:
                        command, rest = f"{head} {candidate}", rest[1:]
                    else:
                        positional = candidate
                flags = tuple(dict.fromkeys(_FLAG.findall(" ".join(rest))))
                out.append(
                    _Invocation(
                        doc=doc.rel,
                        line=line,
                        text=snippet.strip(),
                        command=command,
                        positional=positional,
                        flags=flags,
                    )
                )
    return out


def _check_commands(root: Path) -> tuple[list[Finding], dict]:
    surface = _parser_surface()
    docs = _load_docs(root, COMMAND_DOC_GLOBS)
    invocations = _parse_invocations(docs, surface)
    findings: list[Finding] = []

    documented_commands: set[str] = set()
    documented_flags: set[str] = set()
    for doc in docs:  # the global "documented anywhere" set: any flag in any code span
        for _, snippet in _code_snippets(doc):
            documented_flags.update(_FLAG.findall(snippet))

    top_level = sorted(c for c in surface if " " not in c)
    for inv in invocations:
        spec = surface.get(inv.command)
        if spec is None:
            findings.append(
                Finding(
                    check=CHECK_COMMANDS,
                    kind="unknown_command",
                    severity=SEVERITY_ERROR,
                    doc=inv.doc,
                    line=inv.line,
                    claim=f"quantfit {inv.command}",
                    actual=f"cli defines: {', '.join(top_level)}",
                )
            )
            continue
        documented_commands.add(inv.command)
        if " " in inv.command:  # `quantfit calibrate sheet` documents `calibrate` too
            documented_commands.add(inv.command.split(" ", 1)[0])
        if inv.positional is not None:
            choices = [c for c in spec["positionals"].values() if c]
            allowed = {value for group in choices for value in group}
            if allowed and inv.positional not in allowed:
                findings.append(
                    Finding(
                        check=CHECK_COMMANDS,
                        kind="unknown_positional",
                        severity=SEVERITY_ERROR,
                        doc=inv.doc,
                        line=inv.line,
                        claim=f"quantfit {inv.command} {inv.positional}",
                        actual=f"choices: {', '.join(sorted(allowed))}",
                    )
                )
        for flag in inv.flags:
            if flag not in spec["options"] and flag not in _UNIVERSAL_FLAGS:
                findings.append(
                    Finding(
                        check=CHECK_COMMANDS,
                        kind="unknown_flag",
                        severity=SEVERITY_ERROR,
                        doc=inv.doc,
                        line=inv.line,
                        claim=f"quantfit {inv.command} {flag}",
                        actual=f"{inv.command} accepts: {', '.join(sorted(spec['options'])) or '(no flags)'}",
                    )
                )

    for command in sorted(surface):
        if command not in documented_commands:
            findings.append(
                Finding(
                    check=CHECK_COMMANDS,
                    kind="undocumented_command",
                    severity=SEVERITY_ERROR,
                    doc="",
                    line=0,
                    claim=f"cli defines `quantfit {command}`",
                    actual=f"no invocation in {', '.join(COMMAND_DOC_GLOBS)}",
                )
            )
        for option, primary in sorted(surface[command]["options"].items()):
            if option in documented_flags:
                continue
            alias = option != primary
            findings.append(
                Finding(
                    check=CHECK_COMMANDS,
                    kind="undocumented_flag_alias" if alias else "undocumented_flag",
                    # A legacy alias that no document advertises is a compatibility
                    # shim, not a broken promise: warn. A primary flag nothing documents
                    # is a surface users cannot discover: error.
                    severity=SEVERITY_WARNING if alias else SEVERITY_ERROR,
                    doc="",
                    line=0,
                    claim=f"cli defines `quantfit {command} {option}`" + (f" (alias of {primary})" if alias else ""),
                    actual=f"no mention in {', '.join(COMMAND_DOC_GLOBS)}",
                )
            )

    coverage = {
        "docs_scanned": [doc.rel for doc in docs],
        "cli_commands": sorted(surface),
        "invocations_parsed": len(invocations),
        "commands_documented": sorted(documented_commands),
        "flags_documented": len(documented_flags),
    }
    return findings, coverage


# ---------------------------------------------------------------------------------
# check 2 — citation resolution
# ---------------------------------------------------------------------------------

_CITATION = re.compile(
    r"(?P<path>\.?[A-Za-z0-9_][A-Za-z0-9_./\\-]*\.(?:py|md|json|toml|ya?ml|cfg|txt))"
    r":(?P<target>[A-Za-z_][A-Za-z0-9_.]*|\d+(?:-\d+)?)"
)
# The two shapes a citation's own quote takes in these documents. Backward is the common
# one — `claim text` (`file.py:123`) **[V]** — and forward is the freeze plan's
# `spec/qsr-v0.md:353` is *"5.8 The gate adds exit 5"*. Both are checked; anything
# further away than the gap patterns allow is somebody else's sentence.
_QUOTE_FORWARD = re.compile(r"[*_]{0,2}[\"“]([^\"”\n]{6,240})[\"”]|`([^`\n]{6,240})`")
_FORWARD_GAP = re.compile(r"[\s`*_—–:,\-]*(?:is|are|says?|reads?|states?|quoted as|verbatim)?[\s`*_—–:,\-]*")
_BACKWARD_GAP_CHARS = frozenset(" \t\n([`*_—–")
_BACKWARD_GAP_MAX = 8
_QUOTE_CLOSERS = {"`": "`", '"': '"', "”": "“"}
_QUOTE_SLOP = 3  # lines either side the quote may have drifted and still be "here"
_QUALIFIER = re.compile(r"^[a-z_][a-z0-9_]*\.")  # the `module.` a doc adds for the reader


_CONCAT_SEAM = re.compile(r"[\"']\s*(?:f|r|rf|fr|b)?[\"']")


def _normalize(text: str) -> str:
    """Markdown-insensitive comparison form: emphasis, backticks and runs of space gone.

    Adjacent-string-literal seams (`"…unverified " f"binary…"`) are closed first: a
    document quoting a message the source wraps across two literals is quoting it
    correctly, and treating the wrap as a mismatch would flag every long error string.
    """
    joined = _CONCAT_SEAM.sub("", text)
    return re.sub(r"\s+", " ", re.sub(r"[`*_>#]", "", joined)).strip().lower()


def _resolve_cited(root: Path, index: Mapping[str, list[str]], all_files: Sequence[str], raw: str) -> list[str]:
    """Repo-relative candidates a citation's path could mean (bare basenames included)."""
    normalized = raw.replace("\\", "/").removeprefix("./")
    if (root / normalized).is_file():
        return [normalized]
    if "/" in normalized:  # `safety/verify.py` means `quantfit/safety/verify.py`
        return [p for p in all_files if p.endswith("/" + normalized)]
    return list(index.get(normalized, ()))


def _check_citations(root: Path) -> tuple[list[Finding], dict]:
    docs = _load_docs(root, CITATION_DOC_GLOBS)
    index, all_files = _repo_files(root)
    findings: list[Finding] = []
    counts = {"symbol": 0, "line": 0, "quoted": 0}

    for doc in docs:
        for match in _CITATION.finditer(doc.text):
            raw_path, target = match.group("path"), match.group("target")
            line = doc.line_of(match.start())
            claim = match.group(0)
            candidates = _resolve_cited(root, index, all_files, raw_path)
            is_line = target[0].isdigit()
            counts["line" if is_line else "symbol"] += 1
            severity = SEVERITY_WARNING if is_line else SEVERITY_ERROR
            if not candidates:
                findings.append(
                    Finding(
                        check=CHECK_CITATIONS,
                        kind="missing_file",
                        severity=severity,
                        doc=doc.rel,
                        line=line,
                        claim=claim,
                        actual=f"no file named {raw_path} in the repo",
                    )
                )
                continue
            if is_line:
                findings.extend(_check_line_citation(root, doc, match, candidates, claim, line, counts))
                continue
            findings.extend(_check_symbol_citation(root, doc, candidates, claim, target, raw_path, line))

    coverage = {
        "docs_scanned": [doc.rel for doc in docs],
        "symbol_citations": counts["symbol"],
        "line_citations": counts["line"],
        "quoted_line_citations": counts["quoted"],
        "repo_files_indexed": len(all_files),
    }
    return findings, coverage


def _check_symbol_citation(
    root: Path,
    doc: _Doc,
    candidates: Sequence[str],
    claim: str,
    target: str,
    raw_path: str,
    line: int,
) -> list[Finding]:
    """`file.py:symbol` must resolve; a markdown target must at least appear in the file."""
    unparseable: list[str] = []
    for candidate in candidates:
        path = root / candidate
        if path.suffix == ".py":
            symbols = _module_symbols(path)
            if symbols is None:
                unparseable.append(candidate)
                continue
            if target in symbols or target.split(".")[-1] in symbols:
                return []
        else:
            try:
                if target in path.read_text(encoding="utf-8"):
                    return []
            except OSError:
                unparseable.append(candidate)
    if unparseable and len(unparseable) == len(candidates):
        return [
            Finding(
                check=CHECK_CITATIONS,
                kind="unreadable_file",
                severity=SEVERITY_ERROR,
                doc=doc.rel,
                line=line,
                claim=claim,
                actual=f"cited file(s) could not be parsed: {', '.join(unparseable)}",
            )
        ]
    return [
        Finding(
            check=CHECK_CITATIONS,
            kind="unresolved_symbol",
            severity=SEVERITY_ERROR,
            doc=doc.rel,
            line=line,
            claim=claim,
            actual=f"{target} is not defined in {', '.join(candidates)}",
        )
    ]


def _check_line_citation(
    root: Path,
    doc: _Doc,
    match: re.Match[str],
    candidates: Sequence[str],
    claim: str,
    line: int,
    counts: dict,
) -> list[Finding]:
    """`file:line` — in range, and (when the sentence quotes it) still saying that.

    A line citation is fragile by construction: any insertion above it silently re-points
    it. It is therefore a warning class, never an error — but a citation whose own quoted
    text has moved is the commonest way these documents go stale, and the line the text
    is on NOW is exactly what makes that finding fixable.

    A bare basename can name several files (`verify.py` is two modules here). One finding
    at most is emitted, and only when NO candidate satisfies the citation: reporting the
    other candidate's line count would be the auditor inventing drift out of its own
    ambiguity.
    """
    target = match.group("target")
    first, last = int(target.split("-")[0]), int(target.split("-")[-1])
    quote = _cited_quote(doc.text, match)
    if quote is not None:
        counts["quoted"] += 1
    needle = _normalize(quote)[:60] if quote else ""
    misses: list[str] = []
    for candidate in candidates:
        try:
            body = (root / candidate).read_text(encoding="utf-8").splitlines()
        except OSError:
            misses.append(f"{candidate} is unreadable")
            continue
        if last > len(body) or first < 1:
            misses.append(f"{candidate} has {len(body)} lines")
            continue
        if not needle:
            return []  # in range, nothing quoted: as verified as a line citation gets
        # Normalize the JOINED window, never line by line: the literal seam this closes
        # ("…unverified " / f"binary…") lives exactly at the line boundary.
        window = _normalize(" ".join(body[max(0, first - 1 - _QUOTE_SLOP) : last + _QUOTE_SLOP]))
        # A document quoting `gate.GATE_SCHEMA_VERSION = 1` is quoting `GATE_SCHEMA_VERSION
        # = 1` with the module named for the reader; the qualifier is the doc's, not a
        # difference from the line.
        if needle in window or _QUALIFIER.sub("", needle, count=1) in window:
            return []
        elsewhere = [i + 1 for i, text in enumerate(body) if needle[:40] in _normalize(text)]
        misses.append(
            f"quoted text is at {candidate}:{elsewhere[0]}" if elsewhere else f"quoted text not found in {candidate}"
        )
    kind = "stale_line_citation" if needle else "line_out_of_range"
    stated = f"{claim} — quoted as {quote[:80]!r}" if needle else claim
    return [
        Finding(
            check=CHECK_CITATIONS,
            kind=kind,
            severity=SEVERITY_WARNING,
            doc=doc.rel,
            line=line,
            claim=stated,
            actual="; ".join(misses) or "no readable candidate",
        )
    ]


def _cited_quote(text: str, match: re.Match[str]) -> str | None:
    """The text a citation certifies, from either side of it — or None if it quotes nothing.

    Rejects quotes that are themselves citations or paths: a run of citations
    (``file.py:517``, ``file.py:399``) is a list, and reading each one as the previous
    one's quoted content would make every list a finding.
    """
    for quote in (_quote_before(text, match.start()), _quote_after(text, match.end())):
        if quote is None or len(quote.strip()) < 3:
            continue
        if _CITATION.search(quote) or quote.strip()[0] in "()[]{}.,;:/\\":
            continue
        if _NOT_A_TRANSCRIPTION.match(quote.strip()):
            # `mde.EPS_DEFINITION`, `_classify_refusals`, `needs_calibration=False` — a
            # pointer at a thing or a rendering of it, not a transcription of the cited
            # lines. Naming the enclosing function while citing the lines inside it is
            # correct writing, and reading the name as the lines' content punishes it.
            continue
        return quote
    return None


# A transcription has whitespace in it. Every compact form — a dotted path, a bare
# identifier, a `k=v` rendering of a positional argument — is the document pointing.
_NOT_A_TRANSCRIPTION = re.compile(r"^\S+$")


def _quote_before(text: str, offset: int) -> str | None:
    """The quote a parenthetical citation certifies — `claim text` (`file.py:12`).

    Walked one character at a time rather than matched in one regex: the gap's own
    characters (a closing backtick, an opening one) are also quote delimiters, so a
    single greedy match eats the quote it is looking for.

    The bracket is required. Without it the nearest earlier quote belongs to the previous
    clause — *"No reference report exists."* `CHANGELOG.md:48` states the same — and
    reading it as this citation's content invents a stale citation out of a sentence.
    """
    prefix = text[max(0, offset - 400) : offset]
    for cut in range(1, min(_BACKWARD_GAP_MAX, len(prefix)) + 1):
        gap, head = prefix[len(prefix) - cut :], prefix[: len(prefix) - cut]
        if set(gap) - _BACKWARD_GAP_CHARS:
            return None
        if not head or ("(" not in gap and "[" not in gap):
            continue
        opener = _QUOTE_CLOSERS.get(head[-1])
        if opener is None:
            continue
        start = head.rfind(opener, 0, len(head) - 1)
        if start >= 0:
            return head[start + 1 : -1]
    return None


def _quote_after(text: str, offset: int) -> str | None:
    gap = _FORWARD_GAP.match(text, offset)
    start = gap.end() if gap else offset
    quote = _QUOTE_FORWARD.match(text, start)
    if quote is None:
        return None
    return quote.group(1) or quote.group(2)


# ---------------------------------------------------------------------------------
# check 3 — exit-code parity
# ---------------------------------------------------------------------------------

# One canonical meaning per code, and the module constants that must agree on it. The
# CODE is the authority: nothing here hardcodes a number, so a deliberate renumbering
# moves every document this check reads instead of breaking the check.
EXIT_MEANINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pass", ("quantfit.gate:EXIT_PASS", "quantfit.reproduce:EXIT_REPRODUCED")),
    ("operational", ("quantfit.gate:EXIT_OPERATIONAL", "quantfit.reproduce:EXIT_OPERATIONAL")),
    ("fail", ("quantfit.gate:EXIT_FAIL", "quantfit.reproduce:EXIT_BREACH")),
    ("unmeasurable", ("quantfit.gate:EXIT_UNMEASURABLE", "quantfit.reproduce:EXIT_VOID")),
    ("unresolvable", ("quantfit.gate:EXIT_UNRESOLVABLE",)),
)

# Phrase -> meaning, in priority order. "no regression detected" must classify as PASS
# before "regression" claims it, so the negations come first and the order is load-bearing.
_MEANING_PATTERNS: tuple[tuple[str, str], ...] = (
    ("pass", r"\bno (?:regression|flip|detection|drift)\b|\bnothing flipped\b"),
    ("unresolvable", r"unresolvable|finer than|cannot resolve|threshold finer"),
    (
        "unmeasurable",
        r"unmeasur|nothing was measured|measured nothing|zero at-risk|went unmeasured|\bvoid\b|no answer",
    ),
    ("operational", r"operational|unreadable|wrong-schema|malformed|nothing ran"),
    ("fail", r"\bfail|regression|breach|flip(?:s|ped)? (?:reached|observed)|won'?t fit|doesn'?t fit"),
    ("pass", r"\bpass\b|\bfits\b|\bemitted\b|\bdone\b|reproduced|bounded no-detection"),
)

_EXIT_TABLE_ROW = re.compile(r"^\|\s*\*{0,2}`?(\d)`?\*{0,2}\s*\|(?P<rest>.*)$")
_EXIT_ENUM = re.compile(r"\bexits?\s+(?:code\s+)?", re.IGNORECASE)
# An enumeration item: a code, an optional `=`/`:`, then a phrase that STARTS with a word
# (never a dash). "exit 0 — the action fails the job on 2/3/4/5" is a sentence about 0
# that names 3's meaning, and reading it as a claim about 0 would be this scanner's own
# drift. The separator is captured because a lone item is only trusted when it has one.
_ENUM_ITEM = re.compile(r"\*{0,2}`?(\d)`?\*{0,2}\s*(=|:)?\s*([A-Za-z`][^,;.)\n]{1,69})")


def _classify(phrase: str) -> str | None:
    lowered = phrase.lower()
    for meaning, pattern in _MEANING_PATTERNS:
        if re.search(pattern, lowered):
            return meaning
    return None


def _documented_exit_claims(doc_rel: str, lines: Sequence[str]) -> list[tuple[int, int, str, str]]:
    """(line, code, phrase, meaning) for every exit-code claim this scanner can classify.

    Two shapes only — a row of a table whose header mentions "exit", and an enumeration
    that follows the word "exit". Free prose is NOT parsed: "Exit 4 exists precisely so
    that outcome cannot reach you as a pass" is a sentence about 4 that names 0's
    meaning, and a scanner loose enough to read it is a scanner nobody trusts.
    """
    claims: list[tuple[int, int, str, str]] = []
    in_exit_table = False
    for number, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if stripped.startswith("|"):
            cells = [c.strip().strip("*` ").lower() for c in stripped.strip("|").split("|")]
            if any(cell.startswith("exit") for cell in cells):
                in_exit_table = True
                continue
            if in_exit_table:
                row = _EXIT_TABLE_ROW.match(stripped)
                if row:
                    phrase = " ".join(c for c in row.group("rest").split("|"))
                    meaning = _classify(phrase)
                    if meaning:
                        claims.append((number, int(row.group(1)), phrase.strip()[:120], meaning))
                    continue
        else:
            in_exit_table = False
        head = _EXIT_ENUM.search(raw)
        if head:
            items = list(_ENUM_ITEM.finditer(raw[head.start() :]))
            # A real enumeration lists several codes ("exit 0 pass, 3 fail, ...") or marks
            # its one item with `=`. A single unmarked item is prose about a code, not a
            # definition of it, and prose is where a loose scanner invents findings.
            for item in items:
                if len(items) < 2 and not item.group(2):
                    continue
                meaning = _classify(item.group(3))
                if meaning:
                    claims.append((number, int(item.group(1)), item.group(3).strip()[:120], meaning))
    return claims


def _dispatch_returns(root: Path) -> dict[str, set[int]]:
    """Literal `return <int>` values per `if args.cmd == "<name>"` branch of `cli._dispatch`."""
    source = root / "quantfit" / "cli.py"
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        raise AuditError(f"cannot parse {source}: {exc}") from exc
    out: dict[str, set[int]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "_dispatch"):
            continue
        for branch in node.body:
            if not isinstance(branch, ast.If):
                continue
            test = branch.test
            if not (
                isinstance(test, ast.Compare)
                and isinstance(test.comparators[0], ast.Constant)
                and isinstance(test.comparators[0].value, str)
            ):
                continue
            command = test.comparators[0].value
            codes: set[int] = set()
            for inner in ast.walk(branch):
                if isinstance(inner, ast.Return):
                    codes.update(_return_codes(inner.value))
            out.setdefault(command, set()).update(codes)
    return out


def _return_codes(value: ast.expr | None) -> set[int]:
    """Int literals a return can produce, through a ternary as well as directly.

    `return 0 if cap.fits else 3` is how half these branches spell their verdict; reading
    only bare constants would report those commands as returning nothing, and a check
    that sees nothing agrees with everything.
    """
    if isinstance(value, ast.Constant) and isinstance(value.value, int) and not isinstance(value.value, bool):
        return {value.value}
    if isinstance(value, ast.IfExp):
        return _return_codes(value.body) | _return_codes(value.orelse)
    return set()


def _check_exit_codes(root: Path) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    canonical: dict[str, int] = {}
    for meaning, targets in EXIT_MEANINGS:
        values: dict[str, int] = {}
        for target in targets:
            module_name, attribute = target.split(":")
            try:
                values[target] = int(getattr(importlib.import_module(module_name), attribute))
            except (ImportError, AttributeError, TypeError, ValueError) as exc:
                raise AuditError(f"cannot read exit-code constant {target}: {exc}") from exc
        distinct = sorted(set(values.values()))
        # On a disagreement the lowest value is used only so the doc leg can still run;
        # the disagreement itself is the finding, and which side is "right" is a decision
        # for whoever fixes it, not something an auditor should pick.
        canonical[meaning] = distinct[0]
        if len(distinct) > 1:
            findings.append(
                Finding(
                    check=CHECK_EXIT_CODES,
                    kind="constant_disagreement",
                    severity=SEVERITY_ERROR,
                    doc="",
                    line=0,
                    claim=f"one code for '{meaning}'",
                    actual="; ".join(f"{k} = {v}" for k, v in sorted(values.items())),
                )
            )

    # The outcome->code map must be total over the declared outcomes and land inside the
    # code space above: an outcome mapped to an undeclared number is a code CI cannot read.
    try:
        reproduce = importlib.import_module("quantfit.reproduce")
        outcome_codes = dict(reproduce.OUTCOME_EXIT_CODES)
        outcomes = tuple(reproduce.OUTCOMES)
    except (ImportError, AttributeError) as exc:
        raise AuditError(f"cannot read quantfit.reproduce exit-code surface: {exc}") from exc
    for outcome in outcomes:
        if outcome not in outcome_codes:
            findings.append(
                Finding(
                    check=CHECK_EXIT_CODES,
                    kind="unmapped_outcome",
                    severity=SEVERITY_ERROR,
                    doc="",
                    line=0,
                    claim=f"reproduce.OUTCOMES declares {outcome!r}",
                    actual="OUTCOME_EXIT_CODES has no entry for it",
                )
            )
    for outcome, code in sorted(outcome_codes.items()):
        if code not in set(canonical.values()):
            findings.append(
                Finding(
                    check=CHECK_EXIT_CODES,
                    kind="code_outside_contract",
                    severity=SEVERITY_ERROR,
                    doc="",
                    line=0,
                    claim=f"OUTCOME_EXIT_CODES[{outcome!r}] = {code}",
                    actual=f"contract codes are {sorted(set(canonical.values()))}",
                )
            )

    docs = _load_docs(root, EXIT_CODE_DOC_GLOBS)
    claims = 0
    for doc in docs:
        for line, code, phrase, meaning in _documented_exit_claims(doc.rel, doc.lines):
            claims += 1
            expected = canonical[meaning]
            if code != expected:
                findings.append(
                    Finding(
                        check=CHECK_EXIT_CODES,
                        kind="exit_code_mismatch",
                        severity=SEVERITY_ERROR,
                        doc=doc.rel,
                        line=line,
                        claim=f"exit {code} = {phrase}",
                        actual=f"code says {meaning} is {expected}",
                    )
                )

    # The CLI's own help text is a document, and `_dispatch` is the code beneath it.
    surface = _parser_surface()
    help_claims = 0
    for command, spec in sorted(surface.items()):
        for line, code, phrase, meaning in _documented_exit_claims("cli.py", [spec["help"]]):
            help_claims += 1
            expected = canonical[meaning]
            if code != expected:
                findings.append(
                    Finding(
                        check=CHECK_EXIT_CODES,
                        kind="help_exit_code_mismatch",
                        severity=SEVERITY_ERROR,
                        doc="quantfit/cli.py",
                        line=0,
                        claim=f"`quantfit {command} --help` says exit {code} = {phrase}",
                        actual=f"code says {meaning} is {expected}",
                    )
                )
    returns = _dispatch_returns(root)
    for command, codes in sorted(returns.items()):
        advertised = {int(n) for n in re.findall(r"\b(\d)\s*=", surface.get(command, {}).get("help", ""))}
        if not advertised:
            continue
        for code in sorted(codes):
            if code not in advertised:
                findings.append(
                    Finding(
                        check=CHECK_EXIT_CODES,
                        kind="undocumented_dispatch_return",
                        severity=SEVERITY_ERROR,
                        doc="quantfit/cli.py",
                        line=0,
                        claim=f"`quantfit {command} --help` advertises {sorted(advertised)}",
                        actual=f"_dispatch can return {code}",
                    )
                )

    coverage = {
        "docs_scanned": [doc.rel for doc in docs],
        "canonical_codes": canonical,
        "doc_claims_classified": claims,
        "cli_help_claims_classified": help_claims,
        "dispatch_branches": {k: sorted(v) for k, v in sorted(returns.items())},
    }
    return findings, coverage


# ---------------------------------------------------------------------------------
# check 4 — constant parity
# ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class ConstantClaim:
    """One "a document quotes this value" claim, declared in one line.

    `names` are the doc-visible spellings of the constant. A name only makes a claim when
    the value FOLLOWS it across separators alone (`` `X` | `v` ``, `X = v`, `X — v`):
    documents also name constants to point at them ("the version *values* are the
    modules'; this document cites the constants rather than copying their values"), and
    reading the next number after such a mention as an assertion manufactures findings —
    the failure mode that gets an auditor switched off. `patterns` are explicit prose
    forms with exactly one capture group, for values documents state without naming the
    constant ("40 curated probes"). `style` picks the accepted renderings: a rate is
    legitimately written both as `0.30` and as `30pp`.
    """

    id: str
    target: str  # "module:ATTR"
    value_re: str = r"[^\s`|]+"
    names: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()
    style: str = "auto"  # auto | exact | members


CONSTANT_CLAIMS: tuple[ConstantClaim, ...] = (
    ConstantClaim(
        id="judge_model_id",
        target="quantfit.safety.verify:JUDGE_MODEL_ID",
        value_re=r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
        names=("JUDGE_MODEL_ID",),
    ),
    ConstantClaim(
        id="judge_revision",
        target="quantfit.safety.verify:JUDGE_REVISION",
        value_re=r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])",
        names=("JUDGE_REVISION", "quantsafe-refusal-modernbert"),
    ),
    ConstantClaim(
        id="probe_dataset_id",
        target="quantfit.safety.verify:PROBE_DATASET_ID",
        value_re=r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
        names=("PROBE_DATASET_ID",),
    ),
    ConstantClaim(
        id="probe_dataset_revision",
        target="quantfit.safety.verify:PROBE_DATASET_REVISION",
        value_re=r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])",
        names=("PROBE_DATASET_REVISION", "quantsafe-judge-benchmark"),
    ),
    ConstantClaim(
        id="judge_input_contract",
        target="quantfit.safety.verify:JUDGE_INPUT_CONTRACT",
        value_re=r"completion-only;[^`\n\"]*",
        names=("JUDGE_INPUT_CONTRACT",),
        patterns=(r"`(completion-only;[^`\n]*)`",),
        style="exact",
    ),
    ConstantClaim(
        id="judge_card_xstest_accuracy",
        target="quantfit.safety.verify:JUDGE_CARD_XSTEST_ACCURACY",
        value_re=r"\d\.\d{2,6}",
        names=("JUDGE_CARD_XSTEST_ACCURACY",),
        patterns=(r"judge card (?:reports |carries )?\*{0,2}(\d\.\d{2,6})\*{0,2}",),
    ),
    ConstantClaim(
        id="default_max_new_tokens",
        target="quantfit.safety.verify:DEFAULT_MAX_NEW_TOKENS",
        value_re=r"\d+",
        names=("DEFAULT_MAX_NEW_TOKENS",),
        patterns=(r"--max-new-tokens[^\n]{0,90}?default (\d+)",),
    ),
    ConstantClaim(
        id="drift_report_schema",
        target="quantfit.safety.report:SCHEMA_VERSION",
        value_re=r"\d+",
        names=("(?<![A-Z_])SCHEMA_VERSION",),
        patterns=(
            r"drift report[^\n]{0,60}?schema[ -]v(\d)",
            r"schema[ -]v(\d)[^\n]{0,40}?drift report",
            r"report `?schema_version`? (\d)",
        ),
    ),
    ConstantClaim(
        id="llamacpp_tag",
        target="quantfit.backends.gguf:LLAMACPP_TAG",
        value_re=r"b\d{3,6}",
        names=("LLAMACPP_TAG",),
        patterns=(r"llama\.cpp[^\n]{0,30}?\b(b\d{3,6})\b", r"llama\.cpp-(b\d{3,6})", r"llama-(b\d{3,6})-bin"),
        style="exact",
    ),
    ConstantClaim(
        id="llamacpp_commit",
        target="quantfit.backends.gguf:LLAMACPP_COMMIT",
        value_re=r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])",
        names=("LLAMACPP_COMMIT",),
        style="exact",
    ),
    ConstantClaim(
        id="gguf_unquantized_types",
        target="quantfit.safety.gguf_arm:UNQUANTIZED_FILE_TYPES",
        value_re=r"[A-Z0-9]{2,4}",
        names=("UNQUANTIZED_FILE_TYPES",),
        style="members",
    ),
    ConstantClaim(
        id="max_reference_reports",
        target="quantfit.refreports:MAX_REFERENCE_REPORTS",
        value_re=r"\d+|three|four|two",
        names=("MAX_REFERENCE_REPORTS",),
        patterns=(
            r"cap(?:s|ped)? reference reports at \*{0,2}(\w+)\*{0,2}",
            r"reference reports at \*{0,2}(\w+)\*{0,2}",
        ),
    ),
    ConstantClaim(
        id="current_spec_version",
        target="quantfit.refreports:CURRENT_SPEC_VERSION",
        value_re=r"v\d+",
        names=("CURRENT_SPEC_VERSION",),
    ),
    ConstantClaim(
        id="reproduce_spec_version",
        target="quantfit.reproduce:SPEC_VERSION",
        value_re=r"v\d+",
        names=("(?<![_A-Z])SPEC_VERSION",),
    ),
    ConstantClaim(
        id="inspect_conforms_to",
        target="quantfit.inspect_task:CONFORMS_TO",
        value_re=r"QSR v\d+",
        names=("CONFORMS_TO", "conforms_to"),
        style="exact",
    ),
    ConstantClaim(
        id="verified_inspect_ai_version",
        target="quantfit.inspect_task:VERIFIED_INSPECT_AI_VERSION",
        value_re=r"\d+\.\d+\.\d+",
        names=("VERIFIED_INSPECT_AI_VERSION",),
        patterns=(r"inspect[_ -]ai[^\n]{0,40}?\b(\d+\.\d+\.\d+)\b",),
        style="exact",
    ),
    ConstantClaim(
        id="smoke_threshold",
        target="quantfit.gate:SMOKE_THRESHOLD",
        value_re=r"\d+(?:\.\d+)?",
        names=("SMOKE_THRESHOLD",),
        patterns=(r"smoke tier gates? >=\s*(\d+(?:\.\d+)?)pp", r"smoke[^\n]{0,40}?>=\s*(\d+(?:\.\d+)?)pp"),
    ),
    ConstantClaim(
        id="full_threshold",
        target="quantfit.gate:FULL_THRESHOLD",
        value_re=r"\d+(?:\.\d+)?",
        names=("FULL_THRESHOLD",),
    ),
    ConstantClaim(
        id="tier_names",
        target="quantfit.gate:TIERS",
        value_re=r"[a-z]+",
        patterns=(r"--tier ([a-z]+)",),
        style="members",
    ),
    ConstantClaim(
        id="shipped_expected_unsafe_n",
        target="quantfit.gate:SHIPPED_EXPECTED_UNSAFE_N",
        value_re=r"\d+",
        names=("SHIPPED_EXPECTED_UNSAFE_N",),
        patterns=(r"expected-unsafe n=(\d+)", r"dangerous-axis\s+at-risk pairs[^\n]{0,20}?n = (\d+)"),
    ),
    ConstantClaim(
        id="shipped_expected_safe_n",
        target="quantfit.gate:SHIPPED_EXPECTED_SAFE_N",
        value_re=r"\d+",
        names=("SHIPPED_EXPECTED_SAFE_N",),
        patterns=(r"expected-safe\s+n=(\d+)",),
    ),
    ConstantClaim(
        id="shipped_corpus_n",
        target="quantfit.gate:SHIPPED_CORPUS_N",
        value_re=r"\d+",
        names=("SHIPPED_CORPUS_N",),
        patterns=(
            r"(\d+) curated probes",
            r"over (\d+) probes",
            r"(\d+) rows =",
        ),
    ),
    ConstantClaim(
        id="screen_summary_filename",
        target="quantfit.screen:SUMMARY_FILENAME",
        value_re=r"[A-Za-z0-9_.-]+\.json",
        names=("SUMMARY_FILENAME",),
        style="exact",
    ),
    ConstantClaim(
        id="cache_entry_suffix",
        target="quantfit.safety.cache:CACHE_ENTRY_SUFFIX",
        value_re=r"\.[A-Za-z0-9_.-]+",
        names=("CACHE_ENTRY_SUFFIX",),
        style="exact",
    ),
    ConstantClaim(
        id="capture_protocol_version",
        target="quantfit.safety.cache:CAPTURE_PROTOCOL_VERSION",
        value_re=r"[A-Za-z0-9_./-]+",
        names=("CAPTURE_PROTOCOL_VERSION",),
        style="exact",
    ),
    ConstantClaim(
        id="tolerance_doc",
        target="quantfit.reproduce:TOLERANCE_DOC",
        value_re=r"docs/[A-Za-z0-9_.-]+\.md",
        names=("TOLERANCE_DOC",),
        style="exact",
    ),
    ConstantClaim(
        id="flip_count_slack",
        target="quantfit.reproduce:FLIP_COUNT_SLACK",
        value_re=r"\d+",
        names=("FLIP_COUNT_SLACK",),
    ),
    ConstantClaim(
        id="at_risk_slack",
        target="quantfit.reproduce:AT_RISK_SLACK",
        value_re=r"\d+",
        names=("AT_RISK_SLACK",),
    ),
    ConstantClaim(
        id="gate_schema_version",
        target="quantfit.gate:GATE_SCHEMA_VERSION",
        value_re=r"\d+",
        names=("GATE_SCHEMA_VERSION",),
        patterns=(r"gate decision artifact \(`--out`, `schema_version` (\d)\)",),
    ),
    ConstantClaim(
        id="summary_schema_version",
        target="quantfit.screen:SUMMARY_SCHEMA_VERSION",
        value_re=r"\d+",
        names=("SUMMARY_SCHEMA_VERSION",),
    ),
    ConstantClaim(
        id="manifest_schema_version",
        target="quantfit.screen:MANIFEST_SCHEMA_VERSION",
        value_re=r"\d+",
        names=("MANIFEST_SCHEMA_VERSION",),
        patterns=(r"target manifest JSON \(schema v(\d)\)",),
    ),
    ConstantClaim(
        id="refreport_schema_version",
        target="quantfit.refreports:REFREPORT_SCHEMA_VERSION",
        value_re=r"\d+",
        names=("REFREPORT_SCHEMA_VERSION",),
    ),
    ConstantClaim(
        id="calibration_schema",
        target="quantfit.safety.calibrate:CALIBRATION_SCHEMA",
        value_re=r"\d+",
        names=("CALIBRATION_SCHEMA",),
    ),
    ConstantClaim(
        id="reproduction_schema_version",
        target="quantfit.reproduce:REPRODUCTION_SCHEMA_VERSION",
        value_re=r"\d+",
        names=("REPRODUCTION_SCHEMA_VERSION",),
    ),
)


def _load_attribute(target: str) -> Any:
    module_name, _, attribute = target.partition(":")
    try:
        return getattr(importlib.import_module(module_name), attribute)
    except (ImportError, AttributeError) as exc:
        raise AuditError(f"constant claim target {target} does not resolve: {exc}") from exc


_WORD_NUMBERS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def _renderings(value: Any, style: str) -> frozenset[str]:
    """Every spelling of `value` a document may legitimately use."""
    if style == "members":
        members = value.keys() if isinstance(value, Mapping) else value
        return frozenset(str(member) for member in members)
    if isinstance(value, bool):
        return frozenset({str(value), str(value).lower()})
    if isinstance(value, float):
        if style == "exact":
            return frozenset({str(value)})
        points = value * 100  # a rate is written both ways: `0.30` and `30pp`
        return frozenset({str(value), f"{value:g}", f"{value:.2f}", f"{points:g}", f"{points:.1f}", f"{points:.0f}"})
    if isinstance(value, int):
        spelled = {_WORD_NUMBERS[value]} if 0 <= value < len(_WORD_NUMBERS) else set()
        return frozenset({str(value), *spelled})
    return frozenset({str(value)})


def _check_constants(root: Path) -> tuple[list[Finding], dict]:
    docs = _load_docs(root, CONSTANT_DOC_GLOBS)
    findings: list[Finding] = []
    coverage: dict[str, dict] = {}
    for claim in CONSTANT_CLAIMS:
        value = _load_attribute(claim.target)
        accepted = _renderings(value, claim.style)
        shown = ", ".join(sorted(accepted)) if claim.style == "members" else str(value)
        matched = mismatched = named_only = 0
        for doc in docs:
            for line, found in _claim_occurrences(doc, claim):
                if found is None:
                    named_only += 1
                    continue
                if found in accepted:
                    matched += 1
                    continue
                mismatched += 1
                findings.append(
                    Finding(
                        check=CHECK_CONSTANTS,
                        kind="constant_mismatch",
                        severity=SEVERITY_ERROR,
                        doc=doc.rel,
                        line=line,
                        claim=f"{claim.id} = {found}",
                        actual=f"{claim.target} = {shown}",
                    )
                )
        coverage[claim.id] = {
            "target": claim.target,
            "asserted_ok": matched,
            "asserted_mismatch": mismatched,
            # Occurrences that name the constant without stating a value. Reported so a
            # claim whose patterns never fire is visible as unchecked rather than clean.
            "named_without_value": named_only,
        }
    return findings, coverage


# A name asserts its value when only separators — or a bare copula — stand between them.
# Any other word ends the run, which is what keeps "`X` in `module.py`" and "`X` namespace,
# while ..." out of the check while still reading "`X` is 4" as the claim it is.
_ASSERT_SEP = r"[`\s*|:=@>→—–\-]{0,10}(?:(?:is|are)\s+[`\"'(]{0,2})?"


def _claim_occurrences(doc: _Doc, claim: ConstantClaim) -> Iterator[tuple[int, str | None]]:
    """(line, stated value) per occurrence; the value is None when the doc only names it."""
    for name in claim.names:
        asserted = re.compile(name + _ASSERT_SEP + "(" + claim.value_re + ")")
        for match in re.finditer(name, doc.text):
            hit = asserted.match(doc.text, match.start())
            yield doc.line_of(match.start()), (hit.group(1) if hit else None)
    for pattern in claim.patterns:
        for match in re.finditer(pattern, doc.text):
            yield doc.line_of(match.start()), match.group(1)


# ---------------------------------------------------------------------------------
# check 5 — schema-field parity
# ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class SchemaClaim:
    """The fields of one artifact: who emits them, and which document describes them."""

    id: str
    modules: tuple[str, ...]  # repo-relative python files that emit the artifact
    docs: tuple[str, ...]  # repo-relative documents that describe it
    sections: tuple[str, ...] = ()  # heading substrings scoping the scan (empty = whole doc)


SCHEMA_CLAIMS: tuple[SchemaClaim, ...] = (
    SchemaClaim(
        id="drift_report_v2",
        modules=("quantfit/safety/report.py", "quantfit/safety/verify.py"),
        docs=("spec/qsr-v0.md",),
        sections=("Provenance rules",),
    ),
    SchemaClaim(
        id="screen_summary",
        modules=("quantfit/screen.py",),
        docs=("spec/qsr-v0.md",),
        sections=("Screen aggregation",),
    ),
    SchemaClaim(
        id="gate_decision",
        modules=("quantfit/gate.py",),
        docs=("docs/ci-integration.md",),
        sections=("Outputs", "Reconciling this document with the CLI"),
    ),
    SchemaClaim(
        id="calibration_report",
        modules=("quantfit/safety/calibrate.py",),
        docs=("docs/judge-calibration-v0.md",),
        sections=("What the calibration report carries",),
    ),
    SchemaClaim(
        # §6.3 shapes the record on `screen.py`'s `sensitivity_control` block and names
        # it as such, so screen.py is part of this record's vocabulary by the document's
        # own construction — not a widening added to silence a finding.
        id="reproduction_record",
        modules=("quantfit/reproduce.py", "quantfit/screen.py"),
        docs=("docs/cross-hardware-tolerance-v0.md",),
        sections=("The pass/fail recording shape",),
    ),
)

# Backticked snake_case that is prose, a path, or another surface entirely. Kept small
# and explicit: a stoplist is a place drift hides, so every entry has to earn its line.
_FIELD_STOPWORDS = frozenset(
    {
        "e_g",
        "i_e",
        "id2label",
        "n_a",
        "no_op",
        "read_the_docs",
        "requires_python",
        "todo",
    }
)
_FIELD_TOKEN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
# `report.py`, `safety/verify.py`, `gguf_arm.generate_completions` and
# `torch.backends.cudnn.deterministic` are code references, not field paths. A dotted
# token is only read as a field path when its ROOT is a field the artifact emits, which
# is what separates `resolution.stage` from `torch.version.cuda`.
_CODE_REFERENCE = re.compile(r"\.(?:py|md|json|toml|ya?ml|txt)$|/")


def _section_lines(doc: _Doc, sections: Sequence[str]) -> list[tuple[int, str]]:
    if not sections:
        return list(enumerate(doc.lines, start=1))
    out: list[tuple[int, str]] = []
    active = False
    for number, raw in enumerate(doc.lines, start=1):
        if raw.startswith("#"):
            active = any(section.lower() in raw.lower() for section in sections)
            continue
        if active:
            out.append((number, raw))
    return out


def _check_schema_fields(root: Path) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    coverage: dict[str, dict] = {}

    # Every symbol the package defines, plus every CLI dest/flag: a documented token that
    # is a function name or a flag is not a schema field, and flagging it would be noise.
    package_symbols: set[str] = set()
    for path in sorted((root / "quantfit").rglob("*.py")):
        symbols = _module_symbols(path)
        if symbols:
            package_symbols |= set(symbols)
    for spec in _parser_surface().values():
        package_symbols |= {opt.lstrip("-").replace("-", "_") for opt in spec["options"]}
        package_symbols |= set(spec["positionals"])

    for claim in SCHEMA_CLAIMS:
        emitted: set[str] = set()
        for module in claim.modules:
            path = root / module
            if not path.is_file():
                raise AuditError(f"schema claim {claim.id} names a missing module: {module}")
            emitted |= set(_emitted_keys(path))
        universe = emitted | package_symbols | _FIELD_STOPWORDS
        tokens = 0
        for doc_rel in claim.docs:
            path = root / doc_rel
            if not path.is_file():
                raise AuditError(f"schema claim {claim.id} names a missing document: {doc_rel}")
            doc = _load_doc(root, path)
            for number, raw in _section_lines(doc, claim.sections):
                for match in _INLINE_CODE.finditer(raw):
                    token = match.group(1).strip()
                    if not _FIELD_TOKEN.match(token) or ("_" not in token and "." not in token):
                        continue
                    if _CODE_REFERENCE.search(token):
                        continue
                    parts = token.split(".")
                    if len(parts) > 1 and parts[0] not in emitted:
                        continue  # a module/attribute reference, not a field path
                    tokens += 1
                    missing = [part for part in parts if part not in universe]
                    if not missing:
                        continue
                    # The nearest real field is the whole fix when the drift is a rename
                    # or a plural (`resolvable` -> `not_refused`), so it travels with the
                    # finding instead of costing the reader a grep.
                    near = get_close_matches(missing[0], sorted(emitted), n=2, cutoff=0.75)
                    hint = f" (closest emitted: {', '.join(near)})" if near else ""
                    findings.append(
                        Finding(
                            check=CHECK_SCHEMA_FIELDS,
                            kind="unknown_field",
                            severity=SEVERITY_ERROR,
                            doc=doc.rel,
                            line=number,
                            claim=f"{claim.id} field `{token}`",
                            actual=f"{', '.join(missing)} is emitted by none of {', '.join(claim.modules)}{hint}",
                        )
                    )
        coverage[claim.id] = {
            "modules": list(claim.modules),
            "docs": list(claim.docs),
            "emitted_keys": len(emitted),
            "tokens_checked": tokens,
        }
    return findings, coverage


# ---------------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------------

_CHECK_FUNCTIONS = {
    CHECK_COMMANDS: _check_commands,
    CHECK_CITATIONS: _check_citations,
    CHECK_EXIT_CODES: _check_exit_codes,
    CHECK_CONSTANTS: _check_constants,
    CHECK_SCHEMA_FIELDS: _check_schema_fields,
}


def audit(root: str | Path | None = None) -> dict:
    """Run every parity check over `root` (default: this package's repository).

    Returns the findings, per-check coverage, counts and an `ok` flag. Raises
    `AuditError` when the audit itself cannot run — never a clean result.
    """
    resolved = _resolve_root(root)
    checks: dict[str, dict] = {}
    errors = warnings = 0
    for name in CHECKS:
        findings, coverage = _CHECK_FUNCTIONS[name](resolved)
        findings.sort(key=lambda f: (f.doc, f.line, f.kind, f.claim))
        n_errors = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
        errors += n_errors
        warnings += len(findings) - n_errors
        checks[name] = {
            "findings": [f.as_dict() for f in findings],
            "n_findings": len(findings),
            "n_errors": n_errors,
            "n_warnings": len(findings) - n_errors,
            "coverage": coverage,
        }
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "root": str(resolved),
        "checks": checks,
        "counts": {"findings": errors + warnings, "errors": errors, "warnings": warnings},
        # Warnings do not fail the audit: `file:line` citations are fragile by
        # construction and a repo that used them would never be green, which is how a
        # check gets switched off. Errors are the drift that must be fixed.
        "ok": errors == 0,
        "exit_code": EXIT_CLEAN if errors == 0 else EXIT_DRIFT,
    }


def summarize(result: Mapping[str, Any], limit: int = 0) -> str:
    """A terminal rendering of `audit()`'s result: one line per finding, counts last."""
    lines: list[str] = []
    for name in CHECKS:
        block = result["checks"][name]
        lines.append(f"{name}: {block['n_errors']} error(s), {block['n_warnings']} warning(s)")
        shown = block["findings"][:limit] if limit else block["findings"]
        for finding in shown:
            where = f"{finding['doc']}:{finding['line']}" if finding["doc"] else "(code)"
            lines.append(
                f"  [{finding['severity']}] {where} {finding['kind']}: {finding['claim']} -> {finding['actual']}"
            )
        if limit and len(block["findings"]) > limit:
            lines.append(f"  ... {len(block['findings']) - limit} more")
    counts = result["counts"]
    lines.append(f"docs=code parity: {counts['errors']} error(s), {counts['warnings']} warning(s)")
    return "\n".join(lines)
