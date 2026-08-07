"""Reference-report registry — the at-most-three published artifacts, and when they go stale.

ROADMAP 0.8 publishes **three** reference reports on HF: schema-v2 `DriftReport`
artifacts (`quantfit/safety/report.py`) that a third party can fetch, re-hash and
reproduce. This module is the registry that says which three, what each one is bound
to, and — the part that is actually a policy rather than a list — **what makes one
stale**.

--------------------------------------------------------------------------------
## The registry ships EMPTY, and that is a fact about the project, not a stub

**No reference report exists.** None may be fabricated here, because every entry
would be a claim about a run:

  - the 0.5 existence-proof screen has **not run** (`screens/targets-0.5.json` is a
    curated target list, not a result), so there is no report to publish;
  - the 0.8 gate — "one reference report reproduced from scratch on a free T4 within
    the 0.7 tolerance" — has **not been attempted**: `docs/cross-hardware-tolerance-v0.md`
    §6.1 records that no T4/Colab/Kaggle run of any kind has happened;
  - QSR **v1 is not frozen** (QSR v0 §10.3 says so outright), so the spec version a
    v1-bound report would name does not exist yet either.

`REGISTRY` is therefore `()`. An entry lands when — and only when — a run has
produced the report, the file has been uploaded, and its sha256 has been read off the
uploaded bytes. Until then the shape below is the contract, not the content.

--------------------------------------------------------------------------------
## The cap, and why it is a design constant rather than a preference

`MAX_REFERENCE_REPORTS = 3`, enforced on registration. ROADMAP risk 5 is the reason:
*"Report regeneration burden — pinning discipline guarantees recurring regeneration.
Mitigation: reports capped at three, valid as-of their spec version, regenerated only
at spec bumps."* The cap bounds the work a spec bump costs, so a fourth report is a
**budget decision** that changes what a spec bump costs — not a registry edit.

--------------------------------------------------------------------------------
## The validity rule — the whole point of this module

> A published reference report is **VALID** as-of the **spec version** it is bound to.
> A **tool** or **dependency** bump does NOT invalidate it. It becomes **STALE** — and
> only then — when the spec version it is bound to has been **superseded**.

That asymmetry is load-bearing and is exactly what `validity()` implements:
`quantfit_version` is carried on every entry as *provenance* and is never read by the
verdict. QSR v0 §4.4 states the same rule from the pins' side ("published reference
reports are valid as-of their spec version, regenerated only at spec-version bumps —
a pin bump does not invalidate them"), and §10.3 states what a bump does and does not
do: *"A published report is valid as-of the spec version it was produced under and
stays citable at that version — a bump dates it, it does not retroactively invalidate
it."*

So `stale` is **not** `retracted`. A stale entry still backs a citation at its own
spec version; what it does not do is represent the current spec. `validity()` returns
both facts (`regeneration_required`, `still_citable`) rather than one word a reader
would have to interpret.

--------------------------------------------------------------------------------
## What this module refuses, and why each one is ambiguity rather than taste

Duplicate slugs (a slug is a published filename — two entries for one file is a
question with two answers), more than three entries, an unknown spec version (a report
bound to a version this repo never published cannot be dated), a `report_sha256` that
is not lowercase 64-hex (two spellings of one hash is the same ambiguity one level
down), **two entries carrying the same `report_sha256`** (one file registered twice
under two names is the paste error this registry exists to make impossible — a rerun of
one pair is a different file by construction, so equal digests mean equal bytes), a
stratum outside `screen.STRATA`, an `hf_path` that is not a plain relative path to a
`.json` (it is handed to `hf_hub_download`, so it gets the same discipline `slug` gets
and for the same reason), a spec timeline that is not oldest-first (the ordering is what
`validity()` reads supersession out of, so a misordered one would invert the verdict
rather than fail), and two entries claiming the same pair at the same spec version.

`RefReportError` is a `RuntimeError` subclass, and that is stated here as the
*conditional* guarantee it actually is. **No CLI subcommand exposes this module today**:
nothing under `quantfit/` imports `refreports`, and `quantfit/cli.py` has no
reference-report branch. The module is reached as a library surface (`from
quantfit.refreports import ...`, plus whatever `quantfit/__init__.py` re-exports lazily).
What the subclassing buys is that *when* a CLI surface is wired, `cli.py`'s existing
`except (RuntimeError, OSError)` handler already turns these into a clean exit 2 with no
traceback — the same operational class as `ScreenError`, `GateError` and `ReportError`
(QSR v0 §5.7) — instead of that being a second change someone has to remember.

**Verdicts are return values; only operational failures raise.** `verify_published`
on a hash mismatch returns `matches: False` loudly rather than raising: "these bytes
are not the registered bytes" is the answer to the question that was asked, and it is
the answer a third-party auditor most needs to be able to print. An unreadable file is
the operational failure, and that raises. Same split `quantfit/gate.py` and
`quantfit/screen.py` use.

Pure-python and hermetic: nothing here imports torch, transformers or the Hub, and
nothing here performs network I/O. Verifying a published report means hashing a file
you already downloaded — this module never fetches one, because a verifier that
fetches its own evidence is not a verifier.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from quantfit.screen import STRATA

# The registry entry shape gets its own version namespace, in the spirit of QSR v0
# §10.2: report schema 2, manifest schema 1, summary schema 1 and this are four
# independent numbers on one spec version, and a bare "1" means nothing until you know
# which file you are holding.
REFREPORT_SCHEMA_VERSION = 1

# ROADMAP 0.8, capped at three. Enforced on registration; the message carries the
# rationale, because a bare "too many" would read as an arbitrary limit.
MAX_REFERENCE_REPORTS = 3

CAP_RATIONALE = (
    "ROADMAP 0.8 caps reference reports at THREE, and ROADMAP risk 5 is why: pinning discipline guarantees "
    "recurring regeneration, so the cap is what bounds the cost of a spec-version bump ('reports capped at three, "
    "valid as-of their spec version, regenerated only at spec bumps' — the budgeted cost, not an accident). A "
    "fourth reference report is a BUDGET DECISION that changes what every future spec bump costs, not a registry "
    "edit, and this refusal exists so it cannot be made by appending a line."
)

# --- spec versions ----------------------------------------------------------------
# THE spec-version literal for this package. `quantfit/reproduce.py:SPEC_VERSION` and
# `quantfit/inspect_task.py:CONFORMS_TO` name the same version in their own words; this
# constant is the one they are pinned to (`tests/test_refreports.py` asserts all three
# agree), so a spec bump is one edit here plus whatever those two surfaces need — never
# a literal that drifts because nothing compared it. That drift is exactly the class
# `tests/test_meta.py` exists for, one PR further out.
#
# The spec version the shipped implementation conforms to (spec/qsr-v0.md).
CURRENT_SPEC_VERSION = "v0"

# The closed, ordered set of QSR spec versions THIS REPOSITORY HAS PUBLISHED. Ordered
# oldest-first: supersession is index order, so a report is stale exactly when its own
# version sits earlier in this tuple than the current one. The ordering is CHECKED
# (`_validate_spec_timeline`) rather than assumed, because a misordered timeline would
# silently invert every verdict instead of refusing.
#
# "v1" is deliberately ABSENT. QSR v0 §10.3: "v0 is explicitly not frozen: QSR v1
# (ROADMAP 0.8) is the frozen citable standard, adding eps-calibrated MDE, per-format
# runtime/baseline policy, calibrated cross-hardware tolerance and the decision rules a
# gate needs." None of those inputs exists: judge error eps is unmeasured (ROADMAP 0.6,
# gated on the 0.5 GO) and the cross-hardware tolerance is uncalibrated (no T4 run —
# docs/cross-hardware-tolerance-v0.md §6.1). Adding "v1" here is a reviewed edit that
# lands WITH the frozen spec file, never before it; `tests/test_refreports.py` pins its
# absence so it cannot arrive by accident.
KNOWN_SPEC_VERSIONS = (CURRENT_SPEC_VERSION,)

# --- validity verdicts ------------------------------------------------------------
VERDICT_VALID = "valid"
VERDICT_STALE = "stale"

VALIDITY_RULE = (
    "A published reference report is VALID as-of the SPEC version it is bound to, and becomes STALE only when that "
    "spec version is SUPERSEDED. A quantfit release, a dependency pin bump, or a judge/probe/llama.cpp pin bump does "
    "NOT invalidate it (QSR v0 §4.4). STALE is not RETRACTED: a superseded report stays citable at its own spec "
    "version and a bump dates it rather than retroactively invalidating it (QSR v0 §10.3) — what STALE means is that "
    "regeneration is owed before the report may be presented as representing the current spec."
)

# HF exposes model repos at /<repo> and dataset repos at /datasets/<repo>; a registry
# that guessed would produce a URL that 404s for half its entries.
HF_REPO_TYPES = ("model", "dataset")
_HF_URL_PREFIX = {"model": "https://huggingface.co/", "dataset": "https://huggingface.co/datasets/"}

# A slug is a published filename stem and a citation key: no separators, no traversal,
# no leading dot — the same discipline `screen.py` applies to target names, for the
# same reason (these strings become paths).
_SAFE_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
_HF_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*")

# `hf_path` is handed straight to `hf_hub_download(..., filename=hf_path)` by anyone
# following docs/reference-reports-v0.md §7.1, and it also lands on a local filesystem as
# the cached filename — so it gets the discipline `slug` gets, for the identical reason.
# Relative, forward slashes only, no whitespace, no backslash, no leading '/', no empty
# or dot segments (the ".." case is refused separately so the message can name it).
_SAFE_HF_PATH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*(?:/[A-Za-z0-9_][A-Za-z0-9._-]*)*")

# The spec-version naming convention this repository publishes under: "v" + an integer.
# `validity()` reads supersession out of tuple ORDER, so the order has to be checkable —
# and it is exactly this convention that makes it so.
_SPEC_VERSION = re.compile(r"v(\d+)")

_HASH_CHUNK = 1 << 20


class RefReportError(RuntimeError):
    """Malformed registry entry or unreadable report (operational: clean CLI exit 2, no traceback)."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RefReportError(message)


def _text(value, name: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{name} must be a non-empty string")
    return value


def _validate_spec_timeline(known_spec_versions) -> tuple[str, ...]:
    """Refuse a spec timeline that is not strictly oldest-first, and return it.

    `validity()`'s entire semantics rest on index order meaning supersession. That order
    is a public parameter, so an unvalidated one does not fail — it INVERTS: pass
    `("v1", "v0")` and a v1 report evaluated against current "v0" reads as stale while
    the genuinely superseded one reads as valid. A verdict that is wrong in the confident
    direction is worse than a refusal, so the ordering is checked here rather than
    documented as a caller's obligation.

    Checkable because this repository publishes spec versions as `v<integer>` (QSR v0,
    QSR v1): the tuple must be `v<N>` throughout with strictly increasing N. A future
    naming scheme is a reviewed edit to this function, which is the right place for it to
    be noticed.
    """
    known = tuple(known_spec_versions)
    _require(bool(known), "known_spec_versions must be a non-empty, oldest-first tuple of published spec versions")
    numbers: list[int] = []
    for version in known:
        _text(version, "known_spec_versions entry")
        match = _SPEC_VERSION.fullmatch(version)
        _require(
            match is not None,
            f"spec timeline entry {version!r} is not of the form v<integer> (got timeline {'/'.join(known)}). "
            "validity() reads SUPERSESSION out of this tuple's order, so the order must be checkable; the v<N> "
            "convention is what makes it so, and a different naming scheme is a reviewed edit to "
            "_validate_spec_timeline rather than a value this function may guess at.",
        )
        numbers.append(int(match.group(1)))  # type: ignore[union-attr]
    _require(
        all(earlier < later for earlier, later in pairwise(numbers)),
        f"spec timeline {'/'.join(known)} is not strictly OLDEST-FIRST. validity() decides staleness from index "
        "order alone, so a misordered (or duplicated) timeline does not merely fail — it INVERTS the verdict, "
        "reporting a superseded report as valid and a current one as stale. Refused rather than sorted: which "
        "order the caller meant is not this function's to guess.",
    )
    return known


# The shipped timeline is checked at import, exactly like the shipped registry below: a
# constant nobody validates is a constant nobody has read.
_validate_spec_timeline(KNOWN_SPEC_VERSIONS)


@dataclass(frozen=True)
class ReferenceReport:
    """One published reference report: the pair it measured, what it is bound to, where it lives.

    Every field is checkable by a third party who never saw the machine: `report_sha256`
    identifies the bytes, `spec_version` dates the claim, `hf_*` says where to fetch it,
    and `quantfit_version` records which tool produced it — provenance only, never an
    input to `validity()` (module docstring).
    """

    slug: str  # citation key AND published filename stem; unique under casefolding
    baseline: str  # the baseline arm ref, verbatim as the run was given it
    quant: str  # the quantized arm ref, verbatim
    stratum: str  # one of screen.STRATA — a stratum is an instrument at a scale cap (QSR v0 §7)
    spec_version: str  # the QSR spec version this report is BOUND to; the only input to staleness
    quantfit_version: str  # the tool version that produced it: provenance, NEVER validity
    report_sha256: str  # lowercase 64-hex over the published report's bytes
    hf_repo_type: str  # "model" or "dataset" — decides the URL prefix, never guessed
    hf_repo: str  # "<org>/<name>"
    hf_path: str  # path to the report JSON inside that repo
    hf_revision: str | None  # the commit the bytes were read at; None when not yet pinned

    def __post_init__(self) -> None:
        for name in ("slug", "baseline", "quant", "stratum", "spec_version", "quantfit_version", "hf_repo", "hf_path"):
            _text(getattr(self, name), f"reference report {name}")
        _require(
            bool(_SAFE_SLUG.fullmatch(self.slug)),
            f"reference report slug {self.slug!r} is not a safe citation key / filename stem: it must match "
            f"{_SAFE_SLUG.pattern} (lowercase; a slug names a published file and is quoted in citations)",
        )
        _require(
            self.stratum in STRATA,
            f"reference report {self.slug!r} has stratum {self.stratum!r}, not one of {'/'.join(STRATA)}: a stratum "
            "is an instrument at a scale cap (QSR v0 §6.2/§7), and inventing one files a report under a heading the "
            "spec does not bound",
        )
        _require(
            self.spec_version in KNOWN_SPEC_VERSIONS,
            f"reference report {self.slug!r} is bound to spec version {self.spec_version!r}, which this repository "
            f"has not published (known: {'/'.join(KNOWN_SPEC_VERSIONS)}). A report bound to an unknown spec version "
            "cannot be dated, so its validity is undefined rather than valid. Note in particular that 'v1' is NOT a "
            "known version: QSR v0 §10.3 records v0 as explicitly not frozen, and QSR v1 (ROADMAP 0.8) needs the "
            "eps-calibrated MDE and the calibrated cross-hardware tolerance, neither of which has been measured.",
        )
        _require(
            isinstance(self.report_sha256, str) and bool(_SHA256_HEX.fullmatch(self.report_sha256)),
            f"reference report {self.slug!r} has report_sha256 {self.report_sha256!r}, which is not a lowercase "
            "64-hex SHA-256. Lowercase is required rather than normalized: hashlib's hexdigest() is lowercase, and "
            "accepting two spellings of one hash is the ambiguity this registry exists to refuse.",
        )
        _require(
            self.hf_repo_type in HF_REPO_TYPES,
            f"reference report {self.slug!r} has hf_repo_type {self.hf_repo_type!r}, not one of "
            f"{'/'.join(HF_REPO_TYPES)}: model repos live at /<repo> and dataset repos at /datasets/<repo>, so a "
            "guessed type produces a published URL that 404s",
        )
        _require(
            bool(_HF_REPO.fullmatch(self.hf_repo)),
            f"reference report {self.slug!r} has hf_repo {self.hf_repo!r}; expected '<org>/<name>'",
        )
        _require(
            self.hf_path.endswith(".json"),
            f"reference report {self.slug!r} has hf_path {self.hf_path!r}: a reference report is a schema-v2 "
            "DriftReport JSON file (quantfit/safety/report.py), so its published path ends in .json",
        )
        _require(
            ".." not in self.hf_path.split("/"),
            f"reference report {self.slug!r} has hf_path {self.hf_path!r}, which contains a '..' segment. This "
            "string is passed to hf_hub_download and lands on a local filesystem as a cache path, so it gets the "
            "same traversal discipline `slug` gets — a registry that pins bytes must not also name a path that "
            "resolves somewhere other than where it reads.",
        )
        _require(
            bool(_SAFE_HF_PATH.fullmatch(self.hf_path)),
            f"reference report {self.slug!r} has hf_path {self.hf_path!r}, which is not a plain relative repo path: "
            f"it must match {_SAFE_HF_PATH.pattern} — forward slashes only, no leading '/', no backslash, no "
            "whitespace, no empty segment. hf_hub_download resolves it inside the repo and caches it under that "
            "name locally, so an absolute or whitespace-bearing path is the same class of ambiguity a bad slug is.",
        )
        _require(
            self.hf_revision is None or (isinstance(self.hf_revision, str) and bool(self.hf_revision.strip())),
            f"reference report {self.slug!r} hf_revision must be a non-empty commit string or None (not yet pinned)",
        )


# --- the registry -----------------------------------------------------------------
# EMPTY BY CONSTRUCTION, and it stays empty until runs exist. Every field of an entry
# is a claim about a run that has happened: the pair that was measured, the bytes that
# were uploaded, the tool version that produced them. None of those runs has been made
# (module docstring; docs/cross-hardware-tolerance-v0.md §6.1; ROADMAP 0.5's screen is
# unrun), so there is nothing here that would not be invented.
#
# An entry lands only when ALL of these are true, in this order:
#   1. `quantfit verify-safety` produced the schema-v2 report on real hardware;
#   2. the file was uploaded to the HF location named in the entry;
#   3. `report_sha256` was read off the UPLOADED bytes (see `sha256_file`);
#   4. the spec version it is bound to is one this repository has published.
# docs/reference-reports-v0.md is the procedure; this constant is its ledger.
_REGISTRY_ENTRIES: tuple[ReferenceReport, ...] = ()

REGISTRY_STATE = (
    "EMPTY: zero reference reports have been published. The 0.5 existence-proof screen has not run, the 0.8 "
    "free-T4 reproduction has not been attempted (docs/cross-hardware-tolerance-v0.md §6.1), and QSR v1 is not "
    "frozen (QSR v0 §10.3). Entries land only when the runs happen — see docs/reference-reports-v0.md."
)


def validate_registry(entries) -> tuple[ReferenceReport, ...]:
    """Validate a whole registry: the cap, slug and digest uniqueness, one report per pair-and-spec.

    Whole-registry rules live here rather than on the entry, because none of them is a
    property of a single entry: an entry cannot know it is the fourth, it cannot know
    another entry already claims its slug, and it cannot know another entry already
    registered its bytes.
    """
    entries = tuple(entries)
    for index, entry in enumerate(entries):
        _require(
            isinstance(entry, ReferenceReport),
            f"registry[{index}] is {type(entry).__name__}, not a ReferenceReport",
        )
    _require(
        len(entries) <= MAX_REFERENCE_REPORTS,
        f"{len(entries)} reference reports registered, but MAX_REFERENCE_REPORTS is {MAX_REFERENCE_REPORTS}. "
        f"{CAP_RATIONALE}",
    )
    seen_slugs: dict[str, str] = {}
    seen_digests: dict[str, str] = {}
    seen_pairs: dict[tuple[str, str, str, str], str] = {}
    for entry in entries:
        key = entry.slug.casefold()
        _require(
            key not in seen_slugs,
            f"duplicate reference-report slug {entry.slug!r} (collides with {seen_slugs.get(key)!r}; slugs are "
            "published filenames and citation keys, compared case-insensitively because they land on "
            "case-insensitive filesystems and in prose)",
        )
        seen_slugs[key] = entry.slug
        _require(
            entry.report_sha256 not in seen_digests,
            f"reference reports {seen_digests.get(entry.report_sha256)!r} and {entry.slug!r} carry the SAME "
            f"report_sha256 ({entry.report_sha256}), so they register byte-identical files under two names. That is "
            "not possible for two genuine reference reports: even a rerun of one pair produces a different file "
            "(created_utc, runtime_s and judge_runtime_s differ by design — see verify_published), so equal digests "
            "mean one artifact registered twice. It is the paste error this registry exists to remove, and a "
            "verifier who downloaded both would get one file and two citations for it.",
        )
        seen_digests[entry.report_sha256] = entry.slug
        pair = (entry.stratum, entry.baseline, entry.quant, entry.spec_version)
        _require(
            pair not in seen_pairs,
            f"reference reports {seen_pairs.get(pair)!r} and {entry.slug!r} both claim the same pair "
            f"({entry.baseline} vs {entry.quant}, stratum {entry.stratum}) at spec {entry.spec_version}: 'the "
            "reference report for this pair' would then have two answers, which is the ambiguity a registry exists "
            "to remove. Two runs of one pair at one spec version are a rerun (QSR v0 §8), not two references.",
        )
        seen_pairs[pair] = entry.slug
    return entries


REGISTRY: tuple[ReferenceReport, ...] = validate_registry(_REGISTRY_ENTRIES)


def register(entry: ReferenceReport, into: tuple[ReferenceReport, ...] = REGISTRY) -> tuple[ReferenceReport, ...]:
    """Return `into` plus `entry`, re-validated as a whole — or raise.

    Returns a new tuple rather than mutating: a registry a caller could append to after
    the fact is exactly the pin an artifact claims to have. The shipped `REGISTRY` is
    edited in source, reviewed, and re-validated at import.
    """
    _require(isinstance(entry, ReferenceReport), f"register expects a ReferenceReport, got {type(entry).__name__}")
    return validate_registry((*into, entry))


def find(slug: str, registry: tuple[ReferenceReport, ...] = REGISTRY) -> ReferenceReport:
    """Look a report up by slug (case-insensitively), or refuse naming what is registered."""
    _text(slug, "slug")
    key = slug.casefold()
    for entry in registry:
        if entry.slug.casefold() == key:
            return entry
    known = ", ".join(e.slug for e in registry) or f"none — {REGISTRY_STATE}"
    raise RefReportError(f"no reference report with slug {slug!r}; registered: {known}")


def hf_url(entry: ReferenceReport) -> str:
    """The published URL, built from the entry's own fields (never guessed from the id alone).

    Refuses an unpinned entry rather than falling back to `main`. The registry's
    `report_sha256` pins BYTES; a `main` URL resolves to whatever the branch head
    later becomes, so the pair would advertise a citation whose contents can change
    out from under the hash that authenticates them — and `verify_published` would
    then fail against the very URL the registry published. An entry with no commit
    oid is not yet citable, and saying so is the point (`docs/reference-reports-v0.md`
    requires the oid to be read from the commit and stored).
    """
    _require(isinstance(entry, ReferenceReport), f"hf_url expects a ReferenceReport, got {type(entry).__name__}")
    _require(
        bool(entry.hf_revision),
        f"reference report {entry.slug!r} has no hf_revision, so it has no immutable URL: a 'main' link "
        f"can change under the pinned report_sha256. Read the commit oid from the upload (CommitInfo.oid) "
        f"and register it before citing this report.",
    )
    return f"{_HF_URL_PREFIX[entry.hf_repo_type]}{entry.hf_repo}/blob/{entry.hf_revision}/{entry.hf_path}"


# --- validity ---------------------------------------------------------------------


def validity(
    entry: ReferenceReport,
    current_spec_version: str,
    known_spec_versions: tuple[str, ...] = KNOWN_SPEC_VERSIONS,
) -> dict:
    """VALID or STALE, decided by the SPEC version alone.

    `entry.quantfit_version` is deliberately not read here, and that is the rule rather
    than an omission: a tool release or a dependency pin bump must not invalidate a
    published artifact (QSR v0 §4.4), so the only way a bump could do so is if this
    function consulted it. It does not.

    `known_spec_versions` is a parameter so a caller can evaluate against a spec
    timeline other than the shipped one — which is how the spec-bump case is testable
    today without this module pretending QSR v1 exists. It does not: v1 is absent from
    `KNOWN_SPEC_VERSIONS` and stays absent until the frozen spec file lands. Being a
    parameter, its OLDEST-FIRST ordering is validated rather than trusted
    (`_validate_spec_timeline`): the ordering is the whole semantics here, so a
    misordered one would invert this verdict instead of failing it.

    A report bound to a version LATER than the current one is refused rather than
    reported: that is a registry defect (an entry filed against a spec this build does
    not have), not a validity outcome.
    """
    _require(
        isinstance(entry, ReferenceReport),
        f"validity expects a ReferenceReport, got {type(entry).__name__}",
    )
    known = _validate_spec_timeline(known_spec_versions)
    _text(current_spec_version, "current_spec_version")
    _require(
        current_spec_version in known,
        f"current_spec_version {current_spec_version!r} is not a published spec version (known: {'/'.join(known)}): "
        "validity is measured against a spec timeline, so an unknown current version makes every verdict undefined",
    )
    _require(
        entry.spec_version in known,
        f"reference report {entry.slug!r} is bound to spec version {entry.spec_version!r}, which is not in the "
        f"timeline being evaluated against (known: {'/'.join(known)})",
    )
    bound_at, current_at = known.index(entry.spec_version), known.index(current_spec_version)
    _require(
        bound_at <= current_at,
        f"reference report {entry.slug!r} is bound to spec {entry.spec_version!r}, which is LATER than the current "
        f"spec {current_spec_version!r} in the timeline {'/'.join(known)}. That is a registry defect — an entry "
        "filed against a spec version this build does not consider current — not a validity verdict.",
    )
    stale = bound_at < current_at
    if stale:
        reason = (
            f"STALE: bound to QSR spec {entry.spec_version}, superseded by {current_spec_version}. Regeneration is "
            "owed before this report may be presented as representing the current spec — it is the budgeted cost of "
            "pinning discipline (ROADMAP 0.8, risk 5), not an accident. The published artifact remains CITABLE "
            f"as-of spec {entry.spec_version} (QSR v0 §10.3): a bump dates a report, it does not retract it. Whether "
            "its numbers may still appear in one table with current-spec numbers is the bump's own comparability "
            "statement to make (QSR v0 §10.3), not this verdict's."
        )
    else:
        reason = (
            f"VALID: bound to QSR spec {entry.spec_version}, which is the current spec version. Produced by quantfit "
            f"{entry.quantfit_version}; that version is PROVENANCE and was not consulted here. A quantfit release, a "
            "dependency bump, or a judge / probe-dataset / llama.cpp pin bump does not invalidate this report "
            "(QSR v0 §4.4) — only a spec-version bump does."
        )
    return {
        "refreport_schema_version": REFREPORT_SCHEMA_VERSION,
        "slug": entry.slug,
        "verdict": VERDICT_STALE if stale else VERDICT_VALID,
        "spec_version": entry.spec_version,
        "current_spec_version": current_spec_version,
        # Carried, and explicitly NOT an input to the verdict above.
        "quantfit_version": entry.quantfit_version,
        "regeneration_required": stale,
        # True in both branches: staleness dates a report, it never retracts one.
        "still_citable_at_its_own_spec_version": True,
        "invalidated_by_tool_or_dependency_bump": False,
        "reason": reason,
        "rule": VALIDITY_RULE,
    }


def registry_validity(
    current_spec_version: str = CURRENT_SPEC_VERSION,
    registry: tuple[ReferenceReport, ...] = REGISTRY,
    known_spec_versions: tuple[str, ...] = KNOWN_SPEC_VERSIONS,
) -> dict:
    """Every registered report's verdict, plus the count that must be regenerated at a bump."""
    # Checked here too, not only inside validity(): on an EMPTY registry — which is what
    # ships — validity() is never called, and a summary computed against a timeline
    # nobody looked at is the wrong thing to return zeroes from.
    known_spec_versions = _validate_spec_timeline(known_spec_versions)
    _require(
        current_spec_version in known_spec_versions,
        f"current_spec_version {current_spec_version!r} is not a published spec version (known: "
        f"{'/'.join(known_spec_versions)}): an empty registry would otherwise return a clean zero-stale summary "
        "stamped with a spec version that does not exist.",
    )
    verdicts = [validity(e, current_spec_version, known_spec_versions) for e in registry]
    return {
        "refreport_schema_version": REFREPORT_SCHEMA_VERSION,
        "current_spec_version": current_spec_version,
        "n_registered": len(verdicts),
        "max_reference_reports": MAX_REFERENCE_REPORTS,
        "n_stale": sum(1 for v in verdicts if v["verdict"] == VERDICT_STALE),
        "registry_state": REGISTRY_STATE if not verdicts else None,
        "reports": verdicts,
        "rule": VALIDITY_RULE,
    }


# --- publication verification ------------------------------------------------------


def sha256_file(path: str) -> str:
    """Lowercase 64-hex SHA-256 of a file's bytes, read in chunks.

    The registry pins BYTES, not a parsed structure: a report re-serialized with
    different key order or indentation is a different file and must fail verification,
    because "the same numbers" is a weaker claim than "the same artifact" and the
    weaker one is not what a citation rests on.
    """
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            while chunk := handle.read(_HASH_CHUNK):
                digest.update(chunk)
    except OSError as exc:
        raise RefReportError(f"unreadable report {path}: {exc}") from exc
    return digest.hexdigest()


def verify_published(entry: ReferenceReport, local_report_path: str) -> dict:
    """Re-hash a local report and confirm it is the registered artifact.

    Returns the comparison; raises only when the file cannot be read (operational, exit
    2). A mismatch is a RESULT, not an error: "these bytes are not the registered bytes"
    is precisely the finding a third-party auditor needs to be able to print, and an
    exception would make the honest outcome and the broken-path outcome look alike.

    What a match establishes, stated because the surrounding claim is easy to inflate:
    the file is byte-identical to the artifact the registry pinned. It says nothing
    about whether the numbers inside are correct, and nothing about the judge — QSR v0
    §2.7's uncalibrated-judge label rides with the report either way.
    """
    _require(
        isinstance(entry, ReferenceReport),
        f"verify_published expects a ReferenceReport, got {type(entry).__name__}",
    )
    _text(local_report_path, "local_report_path")
    actual = sha256_file(local_report_path)
    matches = actual == entry.report_sha256
    if matches:
        statement = (
            f"MATCH: {local_report_path} is byte-identical to reference report {entry.slug!r} as registered "
            f"(sha256 {actual}). This authenticates the ARTIFACT only — it does not verify the numbers inside it, "
            "and the report's uncalibrated-judge label (QSR v0 §2.7) and its stratum cap (§7) apply unchanged."
        )
    else:
        statement = (
            f"MISMATCH: {local_report_path} is NOT the registered reference report {entry.slug!r}. Registry sha256 "
            f"{entry.report_sha256}, this file {actual}. Do not cite this file as that reference report. Either the "
            "download is corrupt or truncated, the published artifact was replaced without a registry update, or "
            "this is a different run — a rerun of the same pair is a different FILE (timestamps and runtimes differ) "
            "even when its drift block is identical, so re-running does not reproduce the hash and was never meant "
            "to. Reproduction is checked against the tolerance rule in docs/cross-hardware-tolerance-v0.md §1.3, "
            "never against this hash."
        )
    return {
        "refreport_schema_version": REFREPORT_SCHEMA_VERSION,
        "slug": entry.slug,
        "path": str(local_report_path),
        "expected_sha256": entry.report_sha256,
        "actual_sha256": actual,
        "matches": matches,
        "spec_version": entry.spec_version,
        "quantfit_version": entry.quantfit_version,
        # None rather than a `main` link when the entry is not pinned: authenticating
        # bytes you already hold is legitimate before an oid exists, so this must not
        # raise (a mismatch is a result, not an error — above), but neither may it mint
        # a mutable URL. `citable` says which of the two states this is.
        "hf_url": hf_url(entry) if entry.hf_revision else None,
        "citable": bool(entry.hf_revision),
        "statement": statement,
    }
