"""Reference-report registry + CITATION.cff parity (hermetic: no network, no model load, no torch).

What is pinned here, and why each one is load-bearing:

  - **the registry ships EMPTY**, and stays that way while no run exists. A fabricated
    entry would be a claim about a run nobody made, so the emptiness is a test, not an
    accident of authorship;
  - **the cap is enforced on registration**, with ROADMAP risk 5's rationale in the
    message — a bare "too many" would read as an arbitrary limit;
  - **the validity asymmetry**, which is the whole module: bumping the tool version
    must NOT invalidate a published report, and bumping the SPEC version must make it
    stale. Both directions are asserted on entries that differ in exactly one field;
  - **the ambiguity refusals**: duplicate slugs, a second entry claiming the same pair,
    two entries registering the SAME bytes, a non-64-hex sha, an unknown spec version,
    an unknown stratum, an `hf_path` that is not a plain relative repo path, and a spec
    timeline that is not oldest-first;
  - **the spec-version literal is pinned across surfaces**: `refreports` names it,
    `reproduce` and `inspect_task` restate it, and nothing compared them until this test;
  - **`verify_published` on both outcomes**, and that a mismatch is a RETURN VALUE
    rather than an exception — an auditor must be able to print the finding;
  - **CITATION.cff parses, carries CFF 1.2.0's four required keys, and its `version`
    equals the shipped version** — the same class of skew `tests/test_meta.py` exists
    for (0.1.0 shipped with `__init__` trailing pyproject and nothing caught it).

The CFF file is parsed by `_parse_cff` below rather than by PyYAML, and the reason is
narrower than "PyYAML might not be there". PyYAML **is** importable in CI: `huggingface_hub`
declares `pyyaml>=5.1` as a hard (non-extra) requirement and CI installs
`huggingface_hub`, so a `pytest.importorskip("yaml")` would in fact run rather than
silently skip. What PyYAML is not is a **declared** dependency of this project — neither
`pyproject.toml`'s runtime deps nor its `dev` extra names it — so it is present by
transitivity, and a transitive dependency is one an upstream release can drop without a
line changing in this repository. The parity assertions therefore rest on `_parse_cff`,
which always runs and cannot be dropped by somebody else's dependency graph; PyYAML is
used, when importable, to check the hand-rolled reader rather than to replace it. That is
defence in depth, not a claim that PyYAML is missing.
"""

import hashlib
import re
from datetime import date
from pathlib import Path

import pytest

import quantfit
from quantfit.refreports import (
    CURRENT_SPEC_VERSION,
    KNOWN_SPEC_VERSIONS,
    MAX_REFERENCE_REPORTS,
    REGISTRY,
    VERDICT_STALE,
    VERDICT_VALID,
    ReferenceReport,
    RefReportError,
    find,
    hf_url,
    register,
    registry_validity,
    sha256_file,
    validate_registry,
    validity,
    verify_published,
)

try:  # present transitively (huggingface_hub requires pyyaml>=5.1); never declared here
    import yaml as _yaml
except ImportError:  # pragma: no cover — the point of _parse_cff is that this is survivable
    _yaml = None

_ROOT = Path(__file__).resolve().parent.parent
_CITATION = _ROOT / "CITATION.cff"


def _digest(seed: str) -> str:
    """A syntactically valid digest, derived from the fixture's own name.

    It is not the hash of any published artifact — none exists — so it is computed here
    rather than pasted, to keep it obvious that no real reference report is described
    anywhere in this file. Deriving it from the seed also makes every fixture entry's
    digest DISTINCT by default, which matters now that the registry refuses two entries
    carrying one digest: a shared constant would have made that refusal untestable and
    every multi-entry fixture a violation of it.
    """
    return hashlib.sha256(f"reference-report-fixture-{seed}".encode()).hexdigest()


_SHA_A = _digest("a")
_SHA_B = _digest("b")

# The hypothetical spec timeline the spec-bump case is evaluated against. QSR v1 does
# NOT exist: v0 §10.3 records v0 as explicitly not frozen, and v1 needs an eps-calibrated
# MDE (unmeasured) and a calibrated cross-hardware tolerance (no T4 run). Passing the
# timeline in as an argument is how the supersession rule is testable without the
# shipped constant claiming a version that has not been published.
_HYPOTHETICAL_TIMELINE = ("v0", "v1")


def _entry(**overrides) -> ReferenceReport:
    fields = {
        "slug": "ref-a",
        "baseline": "hf:org/repo/model-f16.gguf",
        "quant": "hf:org/repo/model-q4_k_m.gguf",
        "stratum": "gguf",
        "spec_version": "v0",
        "quantfit_version": "0.5.2",
        "report_sha256": None,  # derived from the final slug below unless overridden
        "hf_repo_type": "dataset",
        "hf_repo": "org/quantfit-reference-reports",
        "hf_path": "v0/ref-a.json",
        "hf_revision": None,
    }
    fields.update(overrides)
    if fields["report_sha256"] is None:
        fields["report_sha256"] = _digest(fields["slug"])
    return ReferenceReport(**fields)


# --- the registry ships empty -------------------------------------------------------


def test_registry_ships_empty_because_no_reference_report_exists():
    # Not a stub: the 0.5 screen has not run, the 0.8 free-T4 reproduction has not been
    # attempted (docs/cross-hardware-tolerance-v0.md §6.1) and QSR v1 is not frozen, so
    # every field of every entry would be invented. This assertion is what a future
    # author has to change deliberately, with a run behind it.
    assert REGISTRY == ()
    state = registry_validity()
    assert (state["n_registered"], state["n_stale"]) == (0, 0)
    assert state["max_reference_reports"] == 3
    assert "EMPTY" in state["registry_state"]


def test_max_is_three_and_the_shipped_spec_timeline_does_not_claim_v1():
    assert MAX_REFERENCE_REPORTS == 3
    assert CURRENT_SPEC_VERSION == "v0"
    # QSR v0 §10.3: "v0 is explicitly not frozen: QSR v1 (ROADMAP 0.8) is the frozen
    # citable standard". This assertion is meant to be edited by the change that lands
    # the frozen spec file — never before it, and never as a side effect of something
    # else. Its whole job is to make "v1" impossible to add quietly.
    assert KNOWN_SPEC_VERSIONS == ("v0",)
    # And the timeline is BUILT from the single literal rather than restating it, so the
    # two cannot disagree.
    assert KNOWN_SPEC_VERSIONS == (CURRENT_SPEC_VERSION,)


def test_the_spec_version_literal_agrees_across_every_0_8_surface():
    # Three surfaces landed in this milestone naming one spec version in two spellings:
    # refreports.CURRENT_SPEC_VERSION ("v0"), reproduce.SPEC_VERSION ("v0") and
    # inspect_task.CONFORMS_TO ("QSR v0"). Nothing compared them, which is precisely the
    # drift class tests/test_meta.py exists for — so this is the comparison. Neither
    # sibling module is edited by this test: if one ever disagrees, the fix is a decision
    # about which literal is right, made here, at the point where the disagreement shows.
    from quantfit import inspect_task, reproduce

    assert reproduce.SPEC_VERSION == CURRENT_SPEC_VERSION
    assert inspect_task.CONFORMS_TO == f"QSR {CURRENT_SPEC_VERSION}"
    # reproduce.TOLERANCE_RULE spells the version a third time, inside a citation string
    # ("docs/cross-hardware-tolerance-v0.md v0 §1.3, clauses T1-T5"), so it is asserted on
    # as what it actually is: a substring, not a constant.
    assert f" {CURRENT_SPEC_VERSION} " in reproduce.TOLERANCE_RULE


def test_find_on_an_empty_registry_names_the_state_instead_of_a_bare_miss():
    with pytest.raises(RefReportError, match="no reference report with slug"):
        find("ref-a")


def test_refreport_error_is_a_runtime_error():
    # Stated as the conditional it is: NO CLI subcommand reaches this module today —
    # nothing under quantfit/ imports refreports and cli.py has no reference-report
    # branch. What this pins is that cli.py's existing `except (RuntimeError, OSError)`
    # handler WOULD turn these into a clean exit 2 with no traceback the day one is wired
    # (QSR v0 §5.7), so wiring it is one change rather than two.
    assert issubclass(RefReportError, RuntimeError)


def test_lazy_reexports_if_present_resolve_to_this_module():
    # quantfit/__init__.py may re-export a few of these names lazily (PEP 562). That is
    # the library surface, not a CLI one. Asserted conditionally on purpose: this test
    # must not dictate __init__'s contents (a different file's owner decides those), but
    # if a name IS re-exported it must be THIS object and not a same-named other.
    from quantfit import _LAZY

    for name, expected in (
        ("RefReportError", RefReportError),
        ("find", find),
        ("verify_published", verify_published),
    ):
        if name in _LAZY:
            assert getattr(quantfit, name) is expected


# --- the cap ------------------------------------------------------------------------


def test_cap_refused_on_registration_with_the_roadmap_rationale():
    three = validate_registry([_entry(slug=f"ref-{i}", quant=f"q{i}") for i in range(3)])
    assert len(three) == MAX_REFERENCE_REPORTS

    with pytest.raises(RefReportError) as excinfo:
        register(_entry(slug="ref-4", quant="q4"), into=three)
    message = str(excinfo.value)
    assert "MAX_REFERENCE_REPORTS is 3" in message
    # The message must carry WHY, not just THAT: ROADMAP risk 5 is the regeneration
    # burden, and the cap is what bounds a spec bump's cost.
    assert "risk 5" in message and "regenerat" in message


def test_registering_the_third_is_allowed():
    two = validate_registry([_entry(slug="ref-0", quant="q0"), _entry(slug="ref-1", quant="q1")])
    assert len(register(_entry(slug="ref-2", quant="q2"), into=two)) == 3


# --- ambiguity refusals -------------------------------------------------------------


def test_duplicate_slug_refused():
    with pytest.raises(RefReportError, match="duplicate reference-report slug"):
        validate_registry([_entry(slug="ref-a", quant="q0"), _entry(slug="ref-a", quant="q1")])


def test_two_entries_for_one_pair_at_one_spec_version_refused():
    with pytest.raises(RefReportError, match="both claim the same pair"):
        validate_registry([_entry(slug="ref-a"), _entry(slug="ref-b")])


def test_two_entries_registering_the_same_bytes_refused():
    # Distinct slugs, distinct pairs, ONE digest: two names for one file. This is the
    # paste error the registry exists to remove — and it is not reachable honestly, since
    # even a rerun of one pair produces a different file (created_utc, runtime_s), so
    # equal digests can only mean one artifact registered twice.
    with pytest.raises(RefReportError, match="SAME report_sha256"):
        validate_registry(
            [
                _entry(slug="ref-a", quant="q0", report_sha256=_SHA_A),
                _entry(slug="ref-b", quant="q1", report_sha256=_SHA_A),
            ]
        )


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-hash",
        _SHA_A[:63],  # one hex short
        _SHA_A + "0",  # one hex long
        _SHA_A.upper(),  # a second spelling of one hash is the ambiguity, not a formatting nit
        "",
    ],
)
def test_bad_sha256_refused(bad):
    with pytest.raises(RefReportError, match="report_sha256|non-empty string"):
        _entry(report_sha256=bad)


def test_unknown_spec_version_refused_and_v1_is_named_as_unfrozen():
    with pytest.raises(RefReportError) as excinfo:
        _entry(spec_version="v1")
    message = str(excinfo.value)
    assert "has not published" in message and "not frozen" in message


def test_unknown_stratum_refused():
    with pytest.raises(RefReportError, match="stratum"):
        _entry(stratum="awq")


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("slug", "../evil", "safe citation key"),
        ("slug", "sub/dir", "safe citation key"),
        ("slug", "REF-A", "safe citation key"),  # lowercase, so a slug has one spelling
        ("hf_repo_type", "space", "hf_repo_type"),
        ("hf_repo", "no-slash", "hf_repo"),
        ("hf_path", "v0/ref-a.txt", "ends in .json"),
        # hf_path is handed straight to hf_hub_download and lands on a local filesystem
        # as a cache path, so it gets the discipline `slug` gets, for the same reason.
        ("hf_path", "/v0/ref-a.json", "plain relative repo path"),
        ("hf_path", "../ref-a.json", r"'\.\.' segment"),
        ("hf_path", "v0/../../etc/ref-a.json", r"'\.\.' segment"),
        ("hf_path", "v0/ref a.json", "plain relative repo path"),
        ("hf_path", "v0\\ref-a.json", "plain relative repo path"),
        ("hf_path", "v0//ref-a.json", "plain relative repo path"),
        ("hf_path", " v0/ref-a.json", "plain relative repo path"),
        ("hf_revision", "", "hf_revision"),
        ("baseline", "", "non-empty string"),
        ("quantfit_version", "", "non-empty string"),
    ],
)
def test_malformed_entry_refused(field, value, match):
    with pytest.raises(RefReportError, match=match):
        _entry(**{field: value})


def test_registry_refuses_a_non_entry():
    with pytest.raises(RefReportError, match="not a ReferenceReport"):
        validate_registry([{"slug": "ref-a"}])


def test_hf_url_is_built_from_the_entrys_own_fields():
    dataset = _entry(hf_repo_type="dataset", hf_repo="org/refreports", hf_path="v0/ref-a.json", hf_revision="abc123")
    assert hf_url(dataset) == "https://huggingface.co/datasets/org/refreports/blob/abc123/v0/ref-a.json"
    model = _entry(hf_repo_type="model", hf_repo="org/refreports", hf_path="v0/ref-a.json")
    assert hf_url(model) == "https://huggingface.co/org/refreports/blob/main/v0/ref-a.json"


# --- the validity rule: the asymmetry IS the module ---------------------------------


def test_tool_version_bump_does_not_invalidate():
    # QSR v0 §4.4 / ROADMAP 0.8: dependency and tool bumps must NOT invalidate a
    # published artifact. Two entries differing in exactly one field — the tool version
    # — must both be valid, and the verdict must not mention it as a cause.
    old = validity(_entry(quantfit_version="0.5.2"), "v0")
    new = validity(_entry(quantfit_version="0.9.9"), "v0")
    assert old["verdict"] == new["verdict"] == VERDICT_VALID
    assert (old["regeneration_required"], new["regeneration_required"]) == (False, False)
    assert new["quantfit_version"] == "0.9.9"  # carried as provenance...
    assert new["invalidated_by_tool_or_dependency_bump"] is False  # ...and not as a verdict input
    assert "PROVENANCE" in new["reason"]


def test_spec_version_bump_makes_it_stale():
    entry = _entry(spec_version="v0")
    verdict = validity(entry, "v1", known_spec_versions=_HYPOTHETICAL_TIMELINE)
    assert verdict["verdict"] == VERDICT_STALE
    assert verdict["regeneration_required"] is True
    assert (verdict["spec_version"], verdict["current_spec_version"]) == ("v0", "v1")
    # Stale is not retracted: QSR v0 §10.3 — a bump dates a report, it does not
    # retroactively invalidate it.
    assert verdict["still_citable_at_its_own_spec_version"] is True
    assert "CITABLE" in verdict["reason"]


def test_the_two_bumps_differ_on_identical_entries_otherwise():
    # The pair of assertions that makes the asymmetry a fact rather than a sentence:
    # same entry, same function, one bump each, opposite verdicts.
    entry = _entry(spec_version="v0", quantfit_version="0.5.2")
    tool_bumped = validity(_entry(spec_version="v0", quantfit_version="1.0.0"), "v0")
    spec_bumped = validity(entry, "v1", known_spec_versions=_HYPOTHETICAL_TIMELINE)
    assert (tool_bumped["verdict"], spec_bumped["verdict"]) == (VERDICT_VALID, VERDICT_STALE)


def test_report_bound_to_a_later_spec_than_current_is_a_registry_defect(monkeypatch):
    # Reaching this branch requires an entry bound to a spec version LATER than the one
    # being evaluated against — which the entry constructor refuses outright against the
    # shipped timeline, so the timeline itself is patched for the length of this test.
    # The patch simulates a published v1; it does not assert one exists (v1 is not
    # frozen — QSR v0 §10.3), and it is reverted before the next test. The situation it
    # models is real: an older build reading a registry file that already carries
    # entries from a newer spec.
    from quantfit import refreports

    monkeypatch.setattr(refreports, "KNOWN_SPEC_VERSIONS", _HYPOTHETICAL_TIMELINE)
    with pytest.raises(RefReportError, match="LATER than the current spec"):
        validity(_entry(spec_version="v1"), "v0", known_spec_versions=_HYPOTHETICAL_TIMELINE)


def test_unknown_current_spec_version_refused():
    with pytest.raises(RefReportError, match="not a published spec version"):
        validity(_entry(), "v7")


def test_a_misordered_spec_timeline_is_refused_rather_than_inverting_the_verdict():
    # validity() reads supersession out of index order, and known_spec_versions is a
    # public parameter — so an unvalidated newest-first timeline would not fail, it would
    # INVERT: the entry below is bound to the superseded version and would read VALID.
    # Refused, not sorted: which order the caller meant is not the function's to guess.
    with pytest.raises(RefReportError, match="not strictly OLDEST-FIRST"):
        validity(_entry(spec_version="v0"), "v0", known_spec_versions=("v1", "v0"))
    with pytest.raises(RefReportError, match="not strictly OLDEST-FIRST"):
        validity(_entry(spec_version="v0"), "v0", known_spec_versions=("v0", "v0"))
    with pytest.raises(RefReportError, match="not of the form v<integer>"):
        validity(_entry(spec_version="v0"), "v0", known_spec_versions=("v0", "qsr-1"))
    with pytest.raises(RefReportError, match="non-empty"):
        validity(_entry(spec_version="v0"), "v0", known_spec_versions=())


def test_registry_validity_checks_the_timeline_even_when_the_registry_is_empty():
    # The shipped registry is empty, so validity() never runs and the timeline would
    # otherwise go unread — returning a clean zero-stale summary stamped with an order
    # nobody checked, or with a current version that does not exist.
    with pytest.raises(RefReportError, match="not strictly OLDEST-FIRST"):
        registry_validity("v0", registry=(), known_spec_versions=("v1", "v0"))
    with pytest.raises(RefReportError, match="not a published spec version"):
        registry_validity("v7", registry=())


def test_registry_validity_counts_what_a_spec_bump_would_cost():
    three = validate_registry([_entry(slug=f"ref-{i}", quant=f"q{i}") for i in range(3)])
    at_v0 = registry_validity("v0", registry=three, known_spec_versions=_HYPOTHETICAL_TIMELINE)
    at_v1 = registry_validity("v1", registry=three, known_spec_versions=_HYPOTHETICAL_TIMELINE)
    assert (at_v0["n_registered"], at_v0["n_stale"]) == (3, 0)
    assert (at_v1["n_registered"], at_v1["n_stale"]) == (3, 3)  # the whole budgeted cost of a bump


# --- verify_published ---------------------------------------------------------------


def _report_file(tmp_path, payload=b'{"schema_version": 2}\n'):
    path = tmp_path / "ref-a.json"
    path.write_bytes(payload)
    return path


def test_verify_published_matches_the_registered_hash(tmp_path):
    path = _report_file(tmp_path)
    entry = _entry(report_sha256=sha256_file(str(path)))

    result = verify_published(entry, str(path))

    assert result["matches"] is True
    assert result["actual_sha256"] == result["expected_sha256"] == entry.report_sha256
    # A match authenticates the artifact and nothing more: the uncalibrated-judge label
    # (QSR v0 §2.7) survives verification.
    assert "does not verify the numbers" in result["statement"]
    assert result["hf_url"].startswith("https://huggingface.co/")


def test_verify_published_reports_a_mismatch_as_a_value_not_an_exception(tmp_path):
    path = _report_file(tmp_path)
    entry = _entry(report_sha256=_SHA_B)  # a hash that is not this file's

    result = verify_published(entry, str(path))  # must NOT raise: the finding is the answer

    assert result["matches"] is False
    assert result["actual_sha256"] == sha256_file(str(path)) != _SHA_B
    assert "MISMATCH" in result["statement"] and "Do not cite this file" in result["statement"]
    # The mismatch statement must not invite the wrong repair: a rerun produces a
    # different FILE (timestamps, runtimes) even when the drift block is identical, so
    # reproduction is checked against the tolerance rule, never against this hash.
    assert "tolerance" in result["statement"]


def test_verify_published_on_a_byte_changed_report_mismatches(tmp_path):
    path = _report_file(tmp_path)
    entry = _entry(report_sha256=sha256_file(str(path)))
    path.write_bytes(b'{"schema_version": 2} \n')  # one byte of whitespace

    assert verify_published(entry, str(path))["matches"] is False


def test_verify_published_on_an_unreadable_report_is_operational(tmp_path):
    with pytest.raises(RefReportError, match="unreadable report"):
        verify_published(_entry(), str(tmp_path / "nope.json"))


# --- CITATION.cff --------------------------------------------------------------------

_CFF_KEY = re.compile(r"(?P<key>[A-Za-z0-9_-]+):(?:[ \t]+(?P<value>\S.*))?")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Plain scalars PyYAML's implicit resolvers would turn into something other than a str.
# Refused rather than reimplemented: refusing is loud, and guessing wrong is a parity
# assertion that passes over a file the two parsers read differently.
_YAML_IMPLICIT_WORDS = frozenset({"true", "false", "yes", "no", "on", "off", "null", "none", "~"})
_YAML_RESERVED_FIRST = "[]{}&*!|>%@`"


def _scalar(raw: str, lineno: int):
    """One plain or quoted YAML scalar, resolved the way `yaml.safe_load` resolves it.

    The resolution matters in exactly one place that is not hypothetical: an unquoted
    `date-released: 2026-08-06` is a `datetime.date` to PyYAML and would be a `str` to a
    naive reader, so the two parsers would disagree on the one edit CITATION.cff tells
    the release-cutter to make. This resolves it the same way; CITATION.cff separately
    mandates the quoted form so the file has one spelling, and the date test enforces it.
    """
    text = raw.strip()
    if not text:
        raise ValueError(f"CITATION.cff line {lineno}: empty value; quote it or omit the key")
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        quote, inner = text[0], text[1:-1]
        if quote in inner or "\\" in inner:
            raise ValueError(
                f"CITATION.cff line {lineno}: quoted scalar {text!r} contains an escape or an inner quote, which "
                "this reader does not resolve. Rewrite it without one — the file has never needed one."
            )
        return inner
    if text[0] in _YAML_RESERVED_FIRST or text[0] in "\"'":
        raise ValueError(f"CITATION.cff line {lineno}: unsupported YAML construct — {text!r}")
    if text.startswith("#") or " #" in text:
        raise ValueError(
            f"CITATION.cff line {lineno}: trailing comments are not supported — {text!r}. Put the comment on its "
            "own line; a half-parsed value is worse than a refused one."
        )
    if _ISO_DATE.fullmatch(text):
        try:
            return date.fromisoformat(text)  # what yaml.safe_load returns for an unquoted ISO date
        except ValueError as exc:
            raise ValueError(f"CITATION.cff line {lineno}: {text!r} is not a real date: {exc}") from exc
    if text.lower() in _YAML_IMPLICIT_WORDS:
        raise ValueError(
            f"CITATION.cff line {lineno}: {text!r} is an implicit YAML boolean/null and would not be the string it "
            "looks like. Quote it."
        )
    try:
        float(text)
    except ValueError:
        pass
    else:
        raise ValueError(
            f"CITATION.cff line {lineno}: {text!r} resolves to a number, not a string. Quote it — every value in "
            "this file is a string, and `version: 0.5` silently becoming a float is the reason."
        )
    return text


def _tokenize(text: str) -> list[tuple[int, str, int]]:
    """(indent, content, lineno) for every significant line. Blank and full-line `#` skipped."""
    tokens: list[tuple[int, str, int]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line[indent:]
        if content.startswith("#"):
            continue
        if content.startswith("\t"):
            raise ValueError(f"CITATION.cff line {lineno}: tabs are not valid YAML indentation")
        if content in ("---", "..."):
            raise ValueError(
                f"CITATION.cff line {lineno}: document markers are not supported — CITATION.cff is one implicit "
                "document, and a second one would be a second citation."
            )
        tokens.append((indent, content, lineno))
    return tokens


def _parse_block(tokens: list[tuple[int, str, int]], pos: int, indent: int):
    if tokens[pos][1].startswith("-"):
        return _parse_sequence(tokens, pos, indent)
    return _parse_mapping(tokens, pos, indent)


def _parse_sequence(tokens: list[tuple[int, str, int]], pos: int, indent: int):
    items: list = []
    while pos < len(tokens) and tokens[pos][0] == indent and tokens[pos][1].startswith("-"):
        _, content, lineno = tokens[pos]
        if not content.startswith("- "):
            raise ValueError(f"CITATION.cff line {lineno}: '-' must carry a value on the same line — {content!r}")
        body = content[2:]
        item_indent = indent + 2 + (len(body) - len(body.lstrip(" ")))
        body = body.lstrip(" ")
        if _CFF_KEY.fullmatch(body) is None:  # a scalar item
            items.append(_scalar(body, lineno))
            pos += 1
            if pos < len(tokens) and tokens[pos][0] > indent:
                raise ValueError(f"CITATION.cff line {tokens[pos][2]}: indented block under a scalar sequence item")
            continue
        # A mapping item: rewrite the token as the mapping's first line at its own column,
        # so the item's continuation lines (and any block nested under them) parse by the
        # same rules as any other mapping. This is what lets `references:` carry the
        # nested `authors:` sequence CFF 1.2.0 requires on every entry.
        tokens[pos] = (item_indent, body, lineno)
        value, pos = _parse_mapping(tokens, pos, item_indent)
        items.append(value)
    return items, pos


def _parse_mapping(tokens: list[tuple[int, str, int]], pos: int, indent: int):
    mapping: dict = {}
    while pos < len(tokens) and tokens[pos][0] == indent:
        _, content, lineno = tokens[pos]
        if content.startswith("-"):
            raise ValueError(f"CITATION.cff line {lineno}: sequence item where a mapping key was expected")
        match = _CFF_KEY.fullmatch(content)
        if match is None:
            raise ValueError(f"CITATION.cff line {lineno}: not a 'key: value' or 'key:' — {content!r}")
        key, value = match.group("key"), match.group("value")
        if key in mapping:
            raise ValueError(f"CITATION.cff line {lineno}: duplicate key {key!r}; one key, one answer")
        pos += 1
        if value is not None:
            mapping[key] = _scalar(value, lineno)
            continue
        if pos < len(tokens) and tokens[pos][0] > indent:
            mapping[key], pos = _parse_block(tokens, pos, tokens[pos][0])
        elif pos < len(tokens) and tokens[pos][0] == indent and tokens[pos][1].startswith("- "):
            mapping[key], pos = _parse_sequence(tokens, pos, indent)  # sequence at the key's own column
        else:
            raise ValueError(f"CITATION.cff line {lineno}: key {key!r} has no value and no nested block")
    return mapping, pos


def _parse_cff(text: str) -> dict:
    """Parse the CFF subset this repository's CITATION.cff uses, refusing anything else.

    Deliberately strict, and deliberately NOT flat: block mappings and block sequences
    nest to any depth, because CFF 1.2.0 requires `authors` — itself a sequence of
    mappings — on every entry of `references`, and a reader that could not hold that
    would make the "no unsourced bibliographic claim" test below unfalsifiable: the very
    edit CITATION.cff prescribes would break the parser instead of satisfying the test.

    Supported: block mappings, block sequences (at the key's column or indented), scalar
    and mapping sequence items, and quoted or plain scalars resolved as `yaml.safe_load`
    resolves them. Full-line `#` comments and blank lines are skipped. NOT supported, each
    raising rather than half-parsing: trailing comments, flow collections, anchors,
    aliases, block scalars, multiple documents, tabs, duplicate keys, and any plain scalar
    PyYAML would resolve to a bool, null or number. A parser that silently dropped a
    construct would let the parity assertions below pass over a file they never read.
    """
    tokens = _tokenize(text)
    if not tokens:
        raise ValueError("CITATION.cff is empty")
    if tokens[0][0] != 0:
        raise ValueError(f"CITATION.cff line {tokens[0][2]}: the document must start at column 0")
    if tokens[0][1].startswith("-"):
        raise ValueError("CITATION.cff must be a mapping at the top level, not a sequence")
    doc, pos = _parse_mapping(tokens, 0, 0)
    if pos != len(tokens):
        raise ValueError(f"CITATION.cff line {tokens[pos][2]}: unexpected indentation — {tokens[pos][1]!r}")
    return doc


def _cff() -> dict:
    return _parse_cff(_CITATION.read_text(encoding="utf-8"))


def test_citation_cff_exists_and_parses():
    assert _CITATION.is_file()
    assert isinstance(_cff(), dict)


def test_citation_cff_has_the_cff_1_2_0_required_keys():
    # CFF 1.2.0's required top-level keys: cff-version, message, title, authors.
    cff = _cff()
    missing = [k for k in ("cff-version", "message", "title", "authors") if k not in cff]
    assert not missing, f"CITATION.cff is missing CFF 1.2.0 required keys: {missing}"
    assert cff["cff-version"] == "1.2.0"
    assert cff["title"] and cff["message"]
    assert cff["type"] == "software"
    authors = cff["authors"]
    assert isinstance(authors, list) and authors, "authors must be a non-empty sequence"
    for author in authors:
        assert isinstance(author, dict)
        # CFF person entries need at least one name field; this repo's author has both.
        assert author.get("family-names") and author.get("given-names")
    assert {"family-names": "Kadadekar", "given-names": "Sahil"} in authors


def test_citation_version_matches_the_shipped_version():
    # The skew tests/test_meta.py exists for, one file further out: 0.1.0 shipped to
    # PyPI with __init__ trailing pyproject and nothing caught it. A CITATION.cff that
    # names a version the tool does not ship makes every citation of it wrong.
    cff = _cff()
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', pyproject, flags=re.MULTILINE)
    assert match, "pyproject.toml has no version line"
    assert cff["version"] == quantfit.__version__ == match.group(1)


def test_citation_license_and_repository_match_packaging_metadata():
    cff = _cff()
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert cff["license"] == "Apache-2.0" and 'license = "Apache-2.0"' in pyproject
    assert cff["repository-code"] == "https://github.com/Sahil170595/quantfit"
    assert f'Repository = "{cff["repository-code"]}"' in pyproject


def test_citation_date_released_if_present_is_a_quoted_iso_date():
    # Shipped WITHOUT date-released, on purpose: no release date is recorded anywhere in
    # this repository (CHANGELOG.md dates no release heading) and inventing one in the
    # citation file would be a fabricated bibliographic fact. This test does not force
    # the absence — whoever tags the release adds a real date — it forces the FORM.
    #
    # And the form is specifically the QUOTED string, which is what CITATION.cff's own
    # instruction says to write. Unquoted, `2026-08-06` is a YAML date: `yaml.safe_load`
    # returns `datetime.date` and so does `_parse_cff`, which agree with each other but
    # give this file two spellings of one field. One spelling; the instruction and this
    # assertion say the same thing.
    released = _cff().get("date-released")
    if released is None:
        return
    assert isinstance(released, str), (
        f"date-released is {type(released).__name__}, so it was written unquoted. CITATION.cff mandates the quoted "
        f'form: date-released: "{released}"'
    )
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", released), f"date-released must be ISO 8601 yyyy-mm-dd, got {released!r}"


def test_citation_makes_no_unsourced_bibliographic_claim():
    # `references` is omitted because CFF 1.2.0 requires `authors` on every reference and
    # this repository records no author list for arXiv 2606.10154 — it cites the paper by
    # title and URL only (quantfit/policy/probe.py). If a references block is ever added,
    # it must carry authors, which means someone read the arXiv record. The next test
    # proves this assertion is REACHABLE: the nested `authors:` sequence such an entry
    # requires parses, so adding one satisfies this test rather than breaking the reader.
    cff = _cff()
    for reference in cff.get("references", []):
        assert isinstance(reference, dict) and reference.get("authors")
        for author in reference["authors"]:
            assert isinstance(author, dict) and (author.get("family-names") or author.get("name"))


def test_the_references_edit_citation_cff_prescribes_parses_under_both_parsers():
    # CITATION.cff tells a future editor exactly how to resolve the omitted `references`
    # entry: open the arXiv page and copy the authors verbatim. That edit produces a
    # nested block sequence (`authors:` inside an item of `references:`) — the construct
    # CFF 1.2.0 REQUIRES on every reference. If the reader could not hold it, the
    # assertion above could never run: the prescribed edit would error every CFF test in
    # this file instead of satisfying one. So the prescribed edit is exercised here,
    # against the real file's text plus the block, under both parsers.
    prescribed = _CITATION.read_text(encoding="utf-8") + (
        "\n"
        "references:\n"
        '  - type: "article"\n'
        '    title: "Quality Is Not a Safety Proxy Under Quantization"\n'
        '    url: "https://arxiv.org/abs/2606.10154"\n'
        "    authors:\n"
        '      - family-names: "Kadadekar"\n'
        '        given-names: "Sahil"\n'
    )
    parsed = _parse_cff(prescribed)
    assert parsed["references"] == [
        {
            "type": "article",
            "title": "Quality Is Not a Safety Proxy Under Quantization",
            "url": "https://arxiv.org/abs/2606.10154",
            "authors": [{"family-names": "Kadadekar", "given-names": "Sahil"}],
        }
    ]
    # …and the rest of the file still reads the same through the same parser.
    assert parsed["version"] == _cff()["version"]
    if _yaml is not None:
        assert _yaml.safe_load(prescribed) == parsed


@pytest.mark.parametrize(
    "released",
    ['date-released: "2026-08-06"\n', "date-released: 2026-08-06\n"],
    ids=["quoted", "unquoted"],
)
def test_both_parsers_agree_on_date_released_in_either_spelling(released):
    # The other edit CITATION.cff prescribes at tag time. Quoted it is a str; unquoted it
    # is a datetime.date — and the point is that BOTH parsers say the same thing either
    # way, so the file cannot become unparseable by writing the conventional form. Which
    # spelling the file must use is a separate decision, enforced above.
    text = _CITATION.read_text(encoding="utf-8") + released
    parsed = _parse_cff(text)
    assert parsed["date-released"] in ("2026-08-06", date(2026, 8, 6))
    if _yaml is not None:
        assert _yaml.safe_load(text) == parsed


def test_hand_rolled_cff_parser_agrees_with_pyyaml_when_it_is_available():
    # PyYAML is present transitively (huggingface_hub requires pyyaml>=5.1) but is not a
    # DECLARED dependency of this project, so the parity assertions above run on
    # `_parse_cff` and this one checks that reader against a real YAML implementation.
    if _yaml is None:  # pragma: no cover — only reachable if huggingface_hub drops pyyaml
        pytest.skip("PyYAML is not importable; _parse_cff carries the parity assertions alone")
    assert _yaml.safe_load(_CITATION.read_text(encoding="utf-8")) == _cff()


@pytest.mark.parametrize(
    "bad",
    [
        'title: "quantfit" # trailing\n',
        "version: 0.5\n",
        "type: yes\n",
        "authors:\n\t- name: x\n",
        'title: "a" "b"\n',
        "---\n",
        'version: "0.5.2"\nversion: "0.5.3"\n',
        '  version: "0.5.2"\n',
        "authors:\n",
        "authors: [a, b]\n",
        "- ref\n",
    ],
    ids=[
        "trailing-comment",
        "unquoted-number",
        "implicit-boolean",
        "tab-indent",
        "inner-quote",
        "document-marker",
        "duplicate-key",
        "not-at-column-0",
        "key-with-nothing",
        "flow-collection",
        "top-level-sequence",
    ],
)
def test_the_hand_rolled_parser_refuses_rather_than_half_parses(bad):
    # The reader is only trustworthy if it fails loudly on what it does not implement: a
    # parser that silently dropped or mis-resolved a construct would let every parity
    # assertion above pass over a file it never really read. Each case here is something
    # a naive line reader would resolve differently from PyYAML — so refusing IS parity.
    with pytest.raises(ValueError):
        _parse_cff(bad)
