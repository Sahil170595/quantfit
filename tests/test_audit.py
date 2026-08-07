"""Tests for the docs=code parity auditor.

Every check is exercised twice against a fixture repository built in `tmp_path` — once
on documents that agree with the code (must be silent) and once on documents that do not
(must fire, with the doc, the line and the real value in the finding). A check that only
ever ran against the real repo would be untestable in the failing direction, which is the
direction that matters.

One test runs the auditor over the REAL repository and asserts only that it does not
crash. It deliberately does not assert cleanliness: this repo's whole point is that its
drift is discovered, not assumed absent, and a test that pinned "zero findings" would
have to be edited every time the auditor found something — which is how a check gets
turned off.

Hermetic: no network, no model loads, no torch. The parser under test is a real
`argparse` parser built in the test (so the walker is exercised, not stubbed) and the
constant claims point at `quantfit.audit`'s own module attributes.
"""

from __future__ import annotations

import argparse
import textwrap

import pytest

from quantfit import audit as A

# ---------------------------------------------------------------------------------
# fixture repository
# ---------------------------------------------------------------------------------

_FIXTURE_CLI = '''
"""fixture cli"""


def _dispatch(args):
    if args.cmd == "check":
        return 0
    if args.cmd == "screen":
        return 3
    return 1
'''


def _repo(tmp_path, **files):
    """A minimal repo root: `quantfit/cli.py` plus whatever documents a test needs."""
    root = tmp_path / "repo"
    (root / "quantfit").mkdir(parents=True)
    (root / "quantfit" / "cli.py").write_text(files.pop("cli", _FIXTURE_CLI), encoding="utf-8")
    for name, body in files.items():
        path = root / name.replace("__", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return root


def _fake_parser():
    """A real argparse parser with the shapes the walker has to handle."""
    parser = argparse.ArgumentParser(prog="quantfit")
    sub = parser.add_subparsers(dest="cmd", required=True)
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--token", default=None)

    check = sub.add_parser(
        "check", parents=[shared], help="fits? (exit 0 = fits, 3 = won't fit, 2 = operational error)"
    )
    check.add_argument("--model", required=True)

    screen = sub.add_parser("screen", help="screen (exit 0 = no regression, 3 = regression, 2 = operational error)")
    screen.add_argument("--targets", required=True)
    screen.add_argument("--legacy", "--old", dest="legacy", default=None)

    emit = sub.add_parser("emit", help="emit")
    emit.add_argument("what", choices=("model-card",))

    calibrate = sub.add_parser("calibrate", help="calibrate")
    csub = calibrate.add_subparsers(dest="calibrate_cmd", required=True)
    sheet = csub.add_parser("sheet", help="sheet")
    sheet.add_argument("--capture", required=True)
    return parser


@pytest.fixture
def surface(monkeypatch):
    monkeypatch.setattr("quantfit.cli._build_parser", _fake_parser)
    return A._parser_surface()


def _kinds(findings):
    return [f.kind for f in findings]


# ---------------------------------------------------------------------------------
# root resolution
# ---------------------------------------------------------------------------------


def test_root_must_look_like_the_repo(tmp_path):
    with pytest.raises(A.AuditError, match="does not look like the quantfit repo"):
        A.audit(tmp_path)


def test_missing_root_is_operational(tmp_path):
    with pytest.raises(A.AuditError, match="not a directory"):
        A.audit(tmp_path / "nope")


def test_empty_corpus_refuses_rather_than_reporting_clean(tmp_path):
    root = _repo(tmp_path)
    with pytest.raises(A.AuditError, match="no documents matched"):
        A._load_docs(root, ("docs/*.md",))


# ---------------------------------------------------------------------------------
# check 1 — command parity
# ---------------------------------------------------------------------------------


def test_parser_surface_walks_subcommands_positionals_and_aliases(surface):
    assert set(surface) == {"check", "screen", "emit", "calibrate", "calibrate sheet"}
    assert surface["check"]["options"] == {"--model": "--model", "--token": "--token"}
    assert surface["screen"]["aliases"] == frozenset({"--old"})
    assert surface["emit"]["positionals"] == {"what": ("model-card",)}
    assert "--capture" in surface["calibrate sheet"]["options"]


def test_command_parity_clean(tmp_path, surface, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "README.md": """
                Run `quantfit check --model X --token T`, `quantfit emit model-card`
                and `quantfit screen --targets t.json --legacy --old`.
                Also `quantfit calibrate sheet --capture c.jsonl`.
                """
        },
    )
    monkeypatch.setattr(A, "COMMAND_DOC_GLOBS", ("README.md",))
    monkeypatch.setattr(A, "_parser_surface", _fake_parser and (lambda: surface))
    findings, coverage = A._check_commands(root)
    assert findings == []
    assert coverage["invocations_parsed"] == 4
    assert "calibrate" in coverage["commands_documented"]  # credited via `calibrate sheet`


def test_command_parity_flags_unknown_command_flag_and_positional(tmp_path, surface, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "README.md": """
                `quantfit check --model X --token T --nope`
                `quantfit frobnicate --model X`
                `quantfit emit model-cards`
                `quantfit screen --targets t.json --legacy --old`
                `quantfit calibrate sheet --capture c.jsonl`
                """
        },
    )
    monkeypatch.setattr(A, "COMMAND_DOC_GLOBS", ("README.md",))
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, _ = A._check_commands(root)
    kinds = _kinds(findings)
    assert kinds.count("unknown_flag") == 1
    assert kinds.count("unknown_command") == 1
    assert kinds.count("unknown_positional") == 1
    flag = next(f for f in findings if f.kind == "unknown_flag")
    assert flag.doc == "README.md" and flag.line == 1
    assert "--nope" in flag.claim and "--model" in flag.actual
    assert all(f.severity == A.SEVERITY_ERROR for f in findings)


def test_command_parity_flags_undocumented_surface(tmp_path, surface, monkeypatch):
    root = _repo(tmp_path, **{"README.md": "`quantfit check --model X --token T`\n"})
    monkeypatch.setattr(A, "COMMAND_DOC_GLOBS", ("README.md",))
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, _ = A._check_commands(root)
    undocumented = {f.claim for f in findings if f.kind == "undocumented_command"}
    assert any("quantfit screen" in claim for claim in undocumented)
    assert any("quantfit calibrate sheet" in claim for claim in undocumented)
    aliases = [f for f in findings if f.kind == "undocumented_flag_alias"]
    assert [f.severity for f in aliases] == [A.SEVERITY_WARNING]  # `--old` is a shim, not a promise
    assert all(f.severity == A.SEVERITY_ERROR for f in findings if f.kind == "undocumented_flag")


def test_command_parity_ignores_prose_help_and_other_tools(tmp_path, surface, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "README.md": """
                `quantfit` quantizes models, and pip installs it.

                ```bash
                ruff check quantfit tests
                quantfit check --model X --token T   # a comment about --nonexistent
                quantfit check --help
                ```

                ```python
                from quantfit import audit
                ```
                `quantfit emit model-card` `quantfit screen --targets t --legacy --old`
                `quantfit calibrate sheet --capture c`
                """
        },
    )
    monkeypatch.setattr(A, "COMMAND_DOC_GLOBS", ("README.md",))
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, _ = A._check_commands(root)
    assert findings == [], _kinds(findings)


def test_command_parity_joins_continuation_lines(tmp_path, surface, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "README.md": """
                ```bash
                quantfit screen \\
                  --targets t.json \\
                  --nope
                ```
                """
        },
    )
    monkeypatch.setattr(A, "COMMAND_DOC_GLOBS", ("README.md",))
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, _ = A._check_commands(root)
    unknown = [f for f in findings if f.kind == "unknown_flag"]
    assert len(unknown) == 1 and "--nope" in unknown[0].claim


# ---------------------------------------------------------------------------------
# check 2 — citation resolution
# ---------------------------------------------------------------------------------

_CITED_MODULE = """
CONSTANT = 1


class Thing:
    def method(self):
        return CONSTANT


def helper():
    return Thing()
"""


def test_citation_symbols_resolve(tmp_path, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "quantfit__mod.py": _CITED_MODULE,
            "spec__s.md": """
                See `quantfit/mod.py:CONSTANT`, `quantfit/mod.py:Thing`,
                `quantfit/mod.py:Thing.method`, `mod.py:helper` and `spec/s.md:CONSTANT`.
                """,
        },
    )
    monkeypatch.setattr(A, "CITATION_DOC_GLOBS", ("spec/*.md",))
    findings, coverage = A._check_citations(root)
    assert findings == [], [f.as_dict() for f in findings]
    assert coverage["symbol_citations"] == 5


def test_citation_unresolved_symbol_is_an_error(tmp_path, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "quantfit__mod.py": _CITED_MODULE,
            "spec__s.md": "Cites `quantfit/mod.py:GONE` and `quantfit/missing.py:CONSTANT`.\n",
        },
    )
    monkeypatch.setattr(A, "CITATION_DOC_GLOBS", ("spec/*.md",))
    findings, _ = A._check_citations(root)
    assert _kinds(findings) == ["unresolved_symbol", "missing_file"]
    assert all(f.severity == A.SEVERITY_ERROR for f in findings)
    assert findings[0].doc == "spec/s.md" and findings[0].line == 1
    assert "GONE is not defined in quantfit/mod.py" in findings[0].actual


def test_citation_line_out_of_range_is_only_a_warning(tmp_path, monkeypatch):
    root = _repo(
        tmp_path,
        **{"quantfit__mod.py": _CITED_MODULE, "spec__s.md": "See `quantfit/mod.py:900` and `quantfit/mod.py:2`.\n"},
    )
    monkeypatch.setattr(A, "CITATION_DOC_GLOBS", ("spec/*.md",))
    findings, coverage = A._check_citations(root)
    assert _kinds(findings) == ["line_out_of_range"]
    assert findings[0].severity == A.SEVERITY_WARNING
    assert coverage["line_citations"] == 2


def test_citation_stale_quote_names_the_current_line(tmp_path, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "quantfit__mod.py": _CITED_MODULE,
            "spec__s.md": "The rule is `def helper():` (`quantfit/mod.py:2`) and it holds.\n",
        },
    )
    monkeypatch.setattr(A, "CITATION_DOC_GLOBS", ("spec/*.md",))
    findings, coverage = A._check_citations(root)
    assert _kinds(findings) == ["stale_line_citation"]
    assert findings[0].severity == A.SEVERITY_WARNING
    assert findings[0].actual == "quoted text is at quantfit/mod.py:9"
    assert coverage["quoted_line_citations"] == 1


def test_citation_quote_that_matches_is_silent(tmp_path, monkeypatch):
    root = _repo(
        tmp_path,
        **{"quantfit__mod.py": _CITED_MODULE, "spec__s.md": "The rule is `def helper():` (`quantfit/mod.py:10`).\n"},
    )
    monkeypatch.setattr(A, "CITATION_DOC_GLOBS", ("spec/*.md",))
    findings, _ = A._check_citations(root)
    assert findings == []


def test_citation_quote_across_a_string_literal_seam_is_not_stale(tmp_path, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "quantfit__mod.py": """
                def boom():
                    raise RuntimeError(
                        f"refusing to extract an unverified "
                        f"binary. Build it yourself."
                    )
                """,
            "spec__s.md": 'It says "refusing to extract an unverified binary." (`quantfit/mod.py:3-4`).\n',
        },
    )
    monkeypatch.setattr(A, "CITATION_DOC_GLOBS", ("spec/*.md",))
    findings, _ = A._check_citations(root)
    assert findings == [], [f.as_dict() for f in findings]


def test_citation_neighbouring_quote_of_another_clause_is_not_read_as_this_one(tmp_path, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "quantfit__mod.py": _CITED_MODULE,
            # The quote belongs to the previous sentence; the citation is not parenthetical.
            "spec__s.md": 'Its docstring says *"nothing exists here"*. `quantfit/mod.py:2` states the same.\n',
        },
    )
    monkeypatch.setattr(A, "CITATION_DOC_GLOBS", ("spec/*.md",))
    findings, _ = A._check_citations(root)
    assert findings == []


def test_citation_ambiguous_basename_resolves_against_either_file(tmp_path, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "quantfit__mod.py": _CITED_MODULE,  # 11 lines
            "quantfit__safety__mod.py": "SHORT = 1\n",  # 1 line
            "spec__s.md": "See `mod.py:10` and `mod.py:SHORT`.\n",
        },
    )
    monkeypatch.setattr(A, "CITATION_DOC_GLOBS", ("spec/*.md",))
    findings, _ = A._check_citations(root)
    assert findings == [], [f.as_dict() for f in findings]


def test_citation_unparseable_python_is_reported_as_such(tmp_path, monkeypatch):
    root = _repo(tmp_path, **{"quantfit__bad.py": "def (\n", "spec__s.md": "See `quantfit/bad.py:thing`.\n"})
    monkeypatch.setattr(A, "CITATION_DOC_GLOBS", ("spec/*.md",))
    findings, _ = A._check_citations(root)
    assert _kinds(findings) == ["unreadable_file"]


# ---------------------------------------------------------------------------------
# check 3 — exit-code parity
# ---------------------------------------------------------------------------------


def _exit_repo(tmp_path, table):
    return _repo(
        tmp_path,
        cli=_FIXTURE_CLI,
        **{"docs__x.md": table},
    )


def test_exit_codes_clean(tmp_path, surface, monkeypatch):
    root = _exit_repo(
        tmp_path,
        """
        | exit | meaning |
        |---|---|
        | **0** | no regression observed |
        | **3** | a regression was detected |
        | **4** | an axis was unmeasurable |
        | **5** | unresolvable: threshold finer than the resolution |
        | **2** | operational error |

        Exit 0 pass, 3 fail, 4 nothing was measured, 5 unresolvable, 2 operational.
        """,
    )
    monkeypatch.setattr(A, "EXIT_CODE_DOC_GLOBS", ("docs/*.md",))
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, coverage = A._check_exit_codes(root)
    assert findings == [], [f.as_dict() for f in findings]
    assert coverage["doc_claims_classified"] == 10
    assert coverage["canonical_codes"]["unresolvable"] == 5


def test_exit_code_mismatch_in_a_table_is_flagged(tmp_path, surface, monkeypatch):
    root = _exit_repo(
        tmp_path,
        """
        | exit | meaning |
        |---|---|
        | **1** | a regression was detected |
        """,
    )
    monkeypatch.setattr(A, "EXIT_CODE_DOC_GLOBS", ("docs/*.md",))
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, _ = A._check_exit_codes(root)
    assert _kinds(findings) == ["exit_code_mismatch"]
    assert findings[0].doc == "docs/x.md"
    assert findings[0].actual == "code says fail is 3"


def test_exit_code_prose_about_a_code_is_not_read_as_a_definition(tmp_path, surface, monkeypatch):
    root = _exit_repo(
        tmp_path,
        """
        Exit 4 exists precisely so that outcome cannot reach you as a pass.
        Runs only on exit 0 — the action fails the job on 2/3/4/5.
        """,
    )
    monkeypatch.setattr(A, "EXIT_CODE_DOC_GLOBS", ("docs/*.md",))
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, coverage = A._check_exit_codes(root)
    assert findings == [], [f.as_dict() for f in findings]
    assert coverage["doc_claims_classified"] == 0


def test_exit_code_help_text_is_audited_against_dispatch(tmp_path, surface, monkeypatch):
    # The fixture `_dispatch` returns 3 for `screen`, whose help advertises 0/3/2 — clean.
    # `check`'s help advertises 0/3/2 and its branch returns 0 — also clean.
    root = _exit_repo(tmp_path, "| exit | meaning |\n|---|---|\n| **0** | no regression observed |\n")
    monkeypatch.setattr(A, "EXIT_CODE_DOC_GLOBS", ("docs/*.md",))
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, coverage = A._check_exit_codes(root)
    assert findings == []
    assert coverage["dispatch_branches"] == {"check": [0], "screen": [3]}
    assert coverage["cli_help_claims_classified"] == 6


def test_exit_code_dispatch_return_outside_the_help_is_flagged(tmp_path, surface, monkeypatch):
    root = _exit_repo(tmp_path, "| exit | meaning |\n|---|---|\n| **0** | no regression observed |\n")
    (root / "quantfit" / "cli.py").write_text(
        'def _dispatch(args):\n    if args.cmd == "check":\n        return 4\n    return 1\n', encoding="utf-8"
    )
    monkeypatch.setattr(A, "EXIT_CODE_DOC_GLOBS", ("docs/*.md",))
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, _ = A._check_exit_codes(root)
    assert _kinds(findings) == ["undocumented_dispatch_return"]
    assert "_dispatch can return 4" in findings[0].actual


def test_exit_code_constants_agree_across_modules(tmp_path, surface, monkeypatch):
    """The cross-module leg reads the real gate/reproduce constants (import-light)."""
    root = _exit_repo(tmp_path, "no claims here\n")
    monkeypatch.setattr(A, "EXIT_CODE_DOC_GLOBS", ("docs/*.md",))
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, coverage = A._check_exit_codes(root)
    assert [f for f in findings if f.kind == "constant_disagreement"] == []
    assert coverage["canonical_codes"] == {"pass": 0, "operational": 2, "fail": 3, "unmeasurable": 4, "unresolvable": 5}


def test_exit_code_constant_disagreement_is_flagged(tmp_path, surface, monkeypatch):
    root = _exit_repo(tmp_path, "no claims here\n")
    monkeypatch.setattr(A, "EXIT_CODE_DOC_GLOBS", ("docs/*.md",))
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    monkeypatch.setattr("quantfit.reproduce.EXIT_BREACH", 9)
    findings, _ = A._check_exit_codes(root)
    assert "constant_disagreement" in _kinds(findings)


def test_dispatch_returns_reads_ternary_verdicts(tmp_path):
    """`return 0 if cap.fits else 3` is a two-code branch, not a branch with no codes."""
    root = _repo(
        tmp_path,
        cli='def _dispatch(args):\n    if args.cmd == "check":\n        return 0 if x else 3\n    return 1\n',
    )
    assert A._dispatch_returns(root) == {"check": {0, 3}}


def test_dispatch_returns_refuses_an_unparseable_cli(tmp_path):
    root = _repo(tmp_path, cli="def _dispatch(\n")
    with pytest.raises(A.AuditError, match="cannot parse"):
        A._dispatch_returns(root)


# ---------------------------------------------------------------------------------
# check 4 — constant parity
# ---------------------------------------------------------------------------------

_CLAIMS = (
    A.ConstantClaim(
        id="schema",
        target="quantfit.audit:AUDIT_SCHEMA_VERSION",
        value_re=r"\d+",
        names=("AUDIT_SCHEMA_VERSION",),
        patterns=(r"audit schema v(\d+)",),
    ),
    A.ConstantClaim(
        id="drift_code",
        target="quantfit.audit:EXIT_DRIFT",
        value_re=r"\d+",
        names=("EXIT_DRIFT",),
    ),
    A.ConstantClaim(
        id="checks",
        target="quantfit.audit:CHECKS",
        value_re=r"[a-z_]+",
        names=("CHECKS",),
        style="members",
    ),
)


def test_constant_parity_clean(tmp_path, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "docs__c.md": """
                | constant | value |
                |---|---|
                | `AUDIT_SCHEMA_VERSION` | `1` |
                | `EXIT_DRIFT` | `3` |
                | `CHECKS` | `command_parity` |

                `AUDIT_SCHEMA_VERSION = 1`, and this is audit schema v1.
                """
        },
    )
    monkeypatch.setattr(A, "CONSTANT_DOC_GLOBS", ("docs/*.md",))
    monkeypatch.setattr(A, "CONSTANT_CLAIMS", _CLAIMS)
    findings, coverage = A._check_constants(root)
    assert findings == [], [f.as_dict() for f in findings]
    assert coverage["schema"]["asserted_ok"] == 3  # two table/prose forms plus the pattern
    assert coverage["checks"]["asserted_ok"] == 1


def test_constant_mismatch_names_doc_line_and_shipped_value(tmp_path, monkeypatch):
    root = _repo(tmp_path, **{"docs__c.md": "intro\n\n`AUDIT_SCHEMA_VERSION` = `7` and `EXIT_DRIFT` is 4.\n"})
    monkeypatch.setattr(A, "CONSTANT_DOC_GLOBS", ("docs/*.md",))
    monkeypatch.setattr(A, "CONSTANT_CLAIMS", _CLAIMS)
    findings, coverage = A._check_constants(root)
    assert _kinds(findings) == ["constant_mismatch", "constant_mismatch"]
    assert {f.line for f in findings} == {3}
    assert findings[0].claim == "schema = 7"
    assert findings[0].actual == "quantfit.audit:AUDIT_SCHEMA_VERSION = 1"
    assert coverage["drift_code"]["asserted_mismatch"] == 1


def test_constant_named_without_a_value_is_not_a_claim(tmp_path, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "docs__c.md": """
                This document cites `AUDIT_SCHEMA_VERSION` rather than copying its value,
                and 7 other things. `EXIT_DRIFT` in `quantfit/audit.py` is 3.
                """
        },
    )
    monkeypatch.setattr(A, "CONSTANT_DOC_GLOBS", ("docs/*.md",))
    monkeypatch.setattr(A, "CONSTANT_CLAIMS", _CLAIMS)
    findings, coverage = A._check_constants(root)
    assert findings == [], [f.as_dict() for f in findings]
    assert coverage["schema"]["named_without_value"] == 1
    assert coverage["drift_code"]["named_without_value"] == 1


def test_constant_rate_and_word_renderings_are_accepted():
    assert "30" in A._renderings(0.30, "auto")  # 30pp
    assert "0.3" in A._renderings(0.30, "auto")
    assert A._renderings(0.30, "exact") == frozenset({"0.3"})
    assert "three" in A._renderings(3, "auto")
    assert A._renderings({"smoke": 1, "full": 2}, "members") == frozenset({"smoke", "full"})


def test_constant_claim_target_must_resolve():
    with pytest.raises(A.AuditError, match="does not resolve"):
        A._load_attribute("quantfit.audit:NO_SUCH_CONSTANT")


# ---------------------------------------------------------------------------------
# check 5 — schema-field parity
# ---------------------------------------------------------------------------------

_EMITTER = """
def build(alpha, *, t0_reference=None):
    out = {"schema_version": 1, "verdict": "PASS", "resolution": {"printed_mde": 0.1, "stage": "pre_run"}}
    out["headline"] = "x"
    return out
"""


def _schema_claims():
    return (A.SchemaClaim(id="record", modules=("quantfit/emit.py",), docs=("docs/f.md",), sections=("Fields",)),)


def test_schema_fields_clean(tmp_path, surface, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "quantfit__emit.py": _EMITTER,
            "docs__f.md": """
                ## Fields

                `schema_version`, `resolution.printed_mde`, `resolution.stage`,
                `t0_reference` and `headline`.
                """,
        },
    )
    monkeypatch.setattr(A, "SCHEMA_CLAIMS", _schema_claims())
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, coverage = A._check_schema_fields(root)
    assert findings == [], [f.as_dict() for f in findings]
    # `headline` is not counted: a single word with no underscore or dot is indistinguishable
    # from prose, so the token filter never offers it to the check.
    assert coverage["record"]["tokens_checked"] == 4


def test_schema_unknown_field_is_flagged_with_the_closest_real_one(tmp_path, surface, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "quantfit__emit.py": _EMITTER,
            "docs__f.md": """
                ## Fields

                `schema_versions` and `resolution.printed_mdes`.
                """,
        },
    )
    monkeypatch.setattr(A, "SCHEMA_CLAIMS", _schema_claims())
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, _ = A._check_schema_fields(root)
    assert _kinds(findings) == ["unknown_field", "unknown_field"]
    assert "closest emitted: schema_version" in findings[0].actual
    assert findings[0].severity == A.SEVERITY_ERROR


def test_schema_scan_is_scoped_to_the_named_sections(tmp_path, surface, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "quantfit__emit.py": _EMITTER,
            "docs__f.md": """
                ## Other

                `not_a_field_at_all` lives here and must be ignored.

                ## Fields

                `schema_version`.
                """,
        },
    )
    monkeypatch.setattr(A, "SCHEMA_CLAIMS", _schema_claims())
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, coverage = A._check_schema_fields(root)
    assert findings == []
    assert coverage["record"]["tokens_checked"] == 1


def test_schema_code_references_are_not_read_as_fields(tmp_path, surface, monkeypatch):
    root = _repo(
        tmp_path,
        **{
            "quantfit__emit.py": _EMITTER,
            "docs__f.md": """
                ## Fields

                Shaped like `report.py`, `safety/verify.py`, `torch.version.cuda` and
                `gguf_arm.generate_completions` — none of which is a field.
                """,
        },
    )
    monkeypatch.setattr(A, "SCHEMA_CLAIMS", _schema_claims())
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    findings, coverage = A._check_schema_fields(root)
    assert findings == []
    assert coverage["record"]["tokens_checked"] == 0


def test_schema_claim_pointing_at_a_missing_module_is_operational(tmp_path, surface, monkeypatch):
    root = _repo(tmp_path, **{"docs__f.md": "## Fields\n\n`x_y`\n"})
    monkeypatch.setattr(A, "SCHEMA_CLAIMS", _schema_claims())
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)
    with pytest.raises(A.AuditError, match="missing module"):
        A._check_schema_fields(root)


# ---------------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------------


def _full_repo(tmp_path, readme):
    return _repo(
        tmp_path,
        **{
            "README.md": readme,
            "quantfit__emit.py": _EMITTER,
            "docs__f.md": "## Fields\n\n`schema_version`\n",
            "docs__x.md": "| exit | meaning |\n|---|---|\n| **0** | no regression observed |\n",
            "spec__s.md": "`AUDIT_SCHEMA_VERSION` = `1`\n",
        },
    )


@pytest.fixture
def scoped(monkeypatch, surface):
    monkeypatch.setattr(A, "COMMAND_DOC_GLOBS", ("README.md",))
    monkeypatch.setattr(A, "CITATION_DOC_GLOBS", ("spec/*.md",))
    monkeypatch.setattr(A, "EXIT_CODE_DOC_GLOBS", ("docs/x.md",))
    monkeypatch.setattr(A, "CONSTANT_DOC_GLOBS", ("spec/*.md",))
    monkeypatch.setattr(A, "CONSTANT_CLAIMS", _CLAIMS[:1])
    monkeypatch.setattr(A, "SCHEMA_CLAIMS", _schema_claims())
    monkeypatch.setattr(A, "_parser_surface", lambda: surface)


def test_audit_is_clean_and_exits_zero_when_everything_agrees(tmp_path, scoped):
    root = _full_repo(
        tmp_path,
        """
        `quantfit check --model X --token T` `quantfit emit model-card`
        `quantfit screen --targets t --legacy --old` `quantfit calibrate sheet --capture c`
        """,
    )
    result = A.audit(root)
    assert result["ok"] is True
    assert result["exit_code"] == A.EXIT_CLEAN
    assert result["counts"] == {"findings": 0, "errors": 0, "warnings": 0}
    assert set(result["checks"]) == set(A.CHECKS)
    assert result["schema_version"] == A.AUDIT_SCHEMA_VERSION


def test_audit_reports_drift_and_exits_three(tmp_path, scoped):
    root = _full_repo(tmp_path, "`quantfit frobnicate --model X`\n")
    result = A.audit(root)
    assert result["ok"] is False
    assert result["exit_code"] == A.EXIT_DRIFT
    assert result["counts"]["errors"] >= 1
    kinds = {f["kind"] for f in result["checks"]["command_parity"]["findings"]}
    assert "unknown_command" in kinds
    counts = result["counts"]
    assert A.summarize(result).endswith(f"{counts['errors']} error(s), {counts['warnings']} warning(s)")


def test_warnings_alone_do_not_fail_the_audit(tmp_path, scoped):
    root = _full_repo(
        tmp_path,
        """
        `quantfit check --model X --token T` `quantfit emit model-card`
        `quantfit screen --targets t --legacy --old` `quantfit calibrate sheet --capture c`
        """,
    )
    (root / "spec" / "s.md").write_text("`AUDIT_SCHEMA_VERSION` = `1`\nSee `quantfit/emit.py:900`.\n", encoding="utf-8")
    result = A.audit(root)
    assert result["counts"]["warnings"] == 1
    assert result["counts"]["errors"] == 0
    assert result["ok"] is True and result["exit_code"] == A.EXIT_CLEAN


def test_summarize_renders_every_check(tmp_path, scoped):
    root = _full_repo(tmp_path, "`quantfit frobnicate`\n")
    text = A.summarize(A.audit(root), limit=1)
    for name in A.CHECKS:
        assert name in text


# ---------------------------------------------------------------------------------
# the real repository
# ---------------------------------------------------------------------------------


def test_audit_runs_over_the_real_repo_without_crashing():
    """Not "the repo is clean" — "the auditor survives the repo and reports structure".

    Pinning cleanliness here would make every real finding a test failure, and the
    cheapest way to make that test pass is to weaken the check that found it.
    """
    result = A.audit()
    assert set(result["checks"]) == set(A.CHECKS)
    assert result["exit_code"] in (A.EXIT_CLEAN, A.EXIT_DRIFT)
    for name in A.CHECKS:
        block = result["checks"][name]
        assert block["n_findings"] == block["n_errors"] + block["n_warnings"]
        for finding in block["findings"]:
            assert finding["check"] == name
            assert finding["severity"] in (A.SEVERITY_ERROR, A.SEVERITY_WARNING)
            assert finding["claim"] and finding["actual"]
    assert isinstance(A.summarize(result), str)


def test_the_real_audit_actually_inspects_things():
    """An auditor that read nothing would report clean; these are the numbers that show it did not."""
    result = A.audit()
    coverage = {name: result["checks"][name]["coverage"] for name in A.CHECKS}
    assert len(coverage["command_parity"]["docs_scanned"]) >= 5
    assert coverage["command_parity"]["invocations_parsed"] >= 10
    assert coverage["citation_resolution"]["symbol_citations"] >= 20
    assert coverage["citation_resolution"]["line_citations"] >= 20
    assert coverage["exit_code_parity"]["doc_claims_classified"] >= 5
    assert sum(c["asserted_ok"] for c in coverage["constant_parity"].values()) >= 20
    assert sum(c["tokens_checked"] for c in coverage["schema_field_parity"].values()) >= 20
