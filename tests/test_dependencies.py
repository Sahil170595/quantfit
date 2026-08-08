"""ROADMAP 0.10: "dependencies bounded" as a test rather than a promise.

The standing ROADMAP rule is `ROADMAP.md:10` and `ROADMAP.md:116`: upper-bound pins for
churning dependencies, and the cap moves only after a validated run on the new minor.
Until this file existed the rule was prose — `llmcompressor`, `ruff`, `gguf` and
`inspect-ai` carried caps because someone remembered to add one, and nothing noticed the
ones that did not.

This module makes the rule mechanical. Every requirement quantfit declares — the runtime
set, every extra, AND `[build-system].requires`, which a user's build frontend really does
resolve and install — must either carry an upper bound or appear in `_EXEMPTIONS` below
with a named exemption class and a stated reason. There is deliberately no third option
and no "TODO" state: an unbounded, unexempted dependency is a test failure, not a warning.

The exemption table is the part that rots, so the premises are checked too:

- an exemption that names a resolution `chain` must root in a dependency quantfit itself
  caps (`test_parent_bounded_exemptions_root_in_a_dependency_quantfit_itself_caps`), and,
  where a link of that chain is installed, its declared bound is re-read from that
  package's own metadata rather than trusted from this docstring. Both tests run over
  EVERY entry that names a chain, not only the `PARENT_BOUNDED` ones: `torch`'s
  `BUILD_SELECTED` entry makes a parent-bound *sub*-claim, and an unchecked sub-claim is
  exactly how prose gets laundered into policy. The check is not decorative — it caught
  this table's first draft claiming `llmcompressor` bounds `huggingface_hub`, which it
  does not;
- `LEAF_SINGLE_CALL` and the dev-only exemptions assert the usage claim they rest on;
- `BUILD_BACKEND` asserts that a wheel build actually runs in CI, which is the entire
  reason a build requirement is allowed to go uncapped;
- an exemption for a dependency that has since been capped is a dead entry and fails, so
  the table cannot silently accumulate.

**Two things an upper bound does not cover**, recorded mechanically because several
exemptions lean on floors instead:

- a declared FLOOR below the floor the parent chain already imposes can never bind on a
  default install — it is an inert instrument, not a weak one
  (`test_floors_that_cannot_bind_are_recorded_not_discovered`);
- a dependency can cross a MAJOR version boundary under its exemption with no cap moving,
  no floor moving and no run happening
  (`test_a_major_boundary_crossed_under_an_exemption_is_recorded`).

Both are pinned as recorded tables rather than asserted away, so a *new* inert floor or a
*new* major crossing fails the build and has to be argued, while the ones that are already
true of this repo stay visible instead of being silently tolerated.

Everything here is hermetic: it reads `pyproject.toml`, two workflow files and the package
source. It imports no backend, loads no model and touches no network. The four tests that
read INSTALLED package metadata skip themselves where the dependency is absent (CI's unit
job installs with `--no-deps`).

`docs/dependency-policy.md` argues this policy in prose and names the tests that enforce
the parts it discusses. It is deliberately NOT a line-by-line mirror: the
packaging-metadata tests here (requires-python vs classifiers vs the CI matrix, extras
named in prose, workflow re-declarations) have no counterpart section there. Where the two
disagree, this file is the one that runs.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

try:  # stdlib on 3.11+
    import tomllib
except ModuleNotFoundError:  # 3.10: pytest itself declares `tomli>=1` there, so this resolves
    import tomli as tomllib

try:  # present transitively (huggingface_hub and datasets both require pyyaml>=5.1); never declared here
    import yaml as _yaml
except ImportError:  # pragma: no cover
    _yaml = None

_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _ROOT / "pyproject.toml"
_CI = _ROOT / ".github" / "workflows" / "ci.yml"
_CANARY = _ROOT / ".github" / "workflows" / "canary.yml"
_PKG = _ROOT / "quantfit"


# --------------------------------------------------------------------------------------
# Requirement parsing. Deliberately minimal: this repo's requirement strings are plain
# `name>=x[,<y]` with no markers, extras or URLs, and a parser that quietly accepted more
# than that could quietly mis-read a bound.
# --------------------------------------------------------------------------------------

_REQ_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?P<extras>\[[^\]]*\])?\s*(?P<specs>[^;]*?)\s*(?:;.*)?$"
)
_SPEC_RE = re.compile(r"^\s*(?P<op><=|>=|==|~=|!=|<|>)\s*(?P<version>[^\s,]+)\s*$")

# `==` and `~=` bound the upper end just as surely as `<` does; `!=` does not.
_UPPER_BOUND_OPS = frozenset({"<", "<=", "==", "~="})


def _canonical(name: str) -> str:
    """PEP 503 name normalization, enough for the names this project declares."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class _Requirement:
    raw: str
    name: str  # canonicalized
    specs: frozenset[tuple[str, str]]

    @property
    def has_upper_bound(self) -> bool:
        return any(op in _UPPER_BOUND_OPS for op, _ in self.specs)


def _parse_requirement(raw: str) -> _Requirement:
    match = _REQ_RE.match(raw)
    assert match, f"unparseable requirement string in pyproject.toml: {raw!r}"
    specs = []
    for chunk in match.group("specs").split(","):
        if not chunk.strip():
            continue
        spec = _SPEC_RE.match(chunk)
        assert spec, f"unparseable version specifier {chunk!r} in requirement {raw!r}"
        specs.append((spec.group("op"), spec.group("version")))
    return _Requirement(raw=raw, name=_canonical(match.group("name")), specs=frozenset(specs))


def _pyproject() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def _hard_requirements() -> list[_Requirement]:
    return [_parse_requirement(r) for r in _pyproject()["project"]["dependencies"]]


def _optional_requirements() -> dict[str, list[_Requirement]]:
    optional = _pyproject()["project"].get("optional-dependencies", {})
    return {extra: [_parse_requirement(r) for r in reqs] for extra, reqs in optional.items()}


# `[build-system].requires` is a real install: the PEP 517 frontend resolves it into an
# isolated build environment for every `pip install quantfit` that builds from an sdist,
# and for every `python -m build`. It sat outside this file's reach until it was added
# here, which is exactly the "nothing noticed the ones that did not" failure the module
# docstring describes — so it is a group like any other, not a special case.
_BUILD_SYSTEM_GROUP = "build-system"


def _build_requirements() -> list[_Requirement]:
    return [_parse_requirement(r) for r in _pyproject().get("build-system", {}).get("requires", [])]


def _all_requirements() -> list[tuple[str, _Requirement]]:
    """(group, requirement) for every declared requirement.

    Group "" is the hard runtime set, `_BUILD_SYSTEM_GROUP` is `[build-system].requires`,
    and anything else is the extra of that name.
    """
    out: list[tuple[str, _Requirement]] = [("", req) for req in _hard_requirements()]
    for extra, reqs in _optional_requirements().items():
        assert extra != _BUILD_SYSTEM_GROUP, f"an extra named {extra!r} collides with the build-system group key"
        out.extend((extra, req) for req in reqs)
    out.extend((_BUILD_SYSTEM_GROUP, req) for req in _build_requirements())
    return out


def _location(group: str) -> str:
    """Where a requirement lives, spelled the way pyproject.toml spells it."""
    if group == _BUILD_SYSTEM_GROUP:
        return "[build-system].requires"
    return f"[project.optional-dependencies.{group}]" if group else "[project.dependencies]"


def _package_sources() -> list[Path]:
    return sorted(_PKG.rglob("*.py"))


# --------------------------------------------------------------------------------------
# The exemption table.
#
# An entry here is a claim that an upper bound would be WRONG or REDUNDANT for this
# dependency, not that adding one is inconvenient. Each entry names its class, states the
# reason, and — for the parent-bounded ones — names the dependency whose own cap is doing
# the work, which the tests below then verify is itself capped.
# --------------------------------------------------------------------------------------

_KINDS = frozenset(
    {
        "BUILD_SELECTED",  # a cap fights a build the user selected out-of-band (index URL, accelerator)
        "PARENT_BOUNDED",  # an already-capped direct dependency bounds this one transitively
        "LEAF_SINGLE_CALL",  # leaf utility, one call site, no API surface quantfit pins behaviour against
        "ORACLE",  # the dependency's job is to be the independent reference; capping it makes the check circular
        "DEV_HARNESS",  # dev-only, never installed by a user, break is caught by the run that introduces it
        "BUILD_BACKEND",  # build-time only, resolved into a throwaway env; a break fails the wheel build in CI
    }
)

# Classes whose argument contains a parent-bound claim, and which may therefore name a
# `chain`. PARENT_BOUNDED rests entirely on it; BUILD_SELECTED may add it as a sub-claim
# (torch: the cap would be WRONG *and* the upper end is not in fact open). Every other
# class makes no claim about a parent, so naming one there would be decoration the tests
# would then have to verify for no reason.
_CHAIN_BEARING_KINDS = frozenset({"PARENT_BOUNDED", "BUILD_SELECTED"})


@dataclass(frozen=True)
class _Exemption:
    kind: str
    reason: str
    # The resolution chain from a dependency quantfit itself caps, down to the dependency
    # that actually constrains the exempted one. `("llmcompressor", "transformers")` means:
    # pyproject caps llmcompressor, llmcompressor caps transformers, transformers caps this.
    # A chain rather than a single name because the first draft of this table asserted
    # llmcompressor constrained huggingface_hub — it does not, and the premise test below
    # caught it. REQUIRED for PARENT_BOUNDED; optional for BUILD_SELECTED, where it exists so
    # the entry's parent-bound sub-claim is machine-checked instead of merely asserted.
    chain: tuple[str, ...] = ()


_EXEMPTIONS: dict[str, _Exemption] = {
    "torch": _Exemption(
        kind="BUILD_SELECTED",
        reason=(
            "An upper cap in quantfit's own metadata fights the accelerator build the user installed "
            "deliberately. torch wheels are selected by index as much as by version — "
            ".github/workflows/canary.yml installs torch from https://download.pytorch.org/whl/cpu — so a cap "
            "here can refuse, or silently downgrade, the CUDA/ROCm wheel that matches the driver on the box, "
            "which is a worse failure than the API break the cap would prevent. That is the whole argument, and "
            "it does not depend on any parent: even with no parent cap at all, quantfit still must not cap torch. "
            "The separate, weaker fact that the upper end of a DEFAULT install is nonetheless closed by the "
            "capped llmcompressor is recorded as the chain below rather than left as prose, so it is re-read from "
            "llmcompressor's own metadata by the same two premise tests the PARENT_BOUNDED entries face. It is a "
            "sub-claim, not the reason: it holds only where llmcompressor is resolved, which the --no-deps paths "
            "in ci.yml and canary.yml are not. quantfit's torch surface is .to(device), dtype introspection and "
            "torch.cuda queries; unlike psutil's, that surface claim is NOT machine-checked here."
        ),
        chain=("llmcompressor",),
    ),
    "transformers": _Exemption(
        kind="PARENT_BOUNDED",
        reason=(
            "llmcompressor is a hard dependency and is capped (<0.13), and it constrains transformers tightly "
            "at BOTH ends from its own metadata. An independent quantfit cap would not add safety; it would "
            "risk being unsatisfiable against llmcompressor's own upper pin, which is the harder failure to "
            "diagnose. quantfit's transformers surface is the Auto* from_pretrained classes plus __version__. "
            "The churn that has bitten this project (torch_dtype -> dtype at 4.56) is recorded as the FLOOR in "
            "pyproject — but that floor is INERT wherever this exemption's own argument applies: llmcompressor "
            "requires transformers>=5.9.0, so on any default install the parent's floor is the binding one and "
            "quantfit's >=4.56 can never be reached. It binds only on the two --no-deps paths where llmcompressor "
            "is absent (ci.yml's unit job, canary.yml's determinism job, which restates it by hand). Stated here "
            "rather than implied, and pinned by test_floors_that_cannot_bind_are_recorded_not_discovered."
        ),
        chain=("llmcompressor",),
    ),
    "datasets": _Exemption(
        kind="PARENT_BOUNDED",
        reason=(
            "Same chain as transformers: the capped llmcompressor constrains datasets at both ends. quantfit "
            "calls load_dataset with an explicit pinned revision and split (safety/verify.py:517) and builds "
            "calibration blocks with Dataset.from_dict (backends/compressed_tensors.py:70); both are the "
            "stable surface."
        ),
        chain=("llmcompressor",),
    ),
    "accelerate": _Exemption(
        kind="PARENT_BOUNDED",
        reason=(
            "Bounded through the capped llmcompressor, which requires accelerate at both ends. Note the "
            "stronger fact recorded by test_accelerate_is_declared_but_never_imported: quantfit imports "
            "accelerate NOWHERE — the device_map='auto' offload path that justified it was deleted at 0.3 "
            "(CHANGELOG.md:346, ROADMAP.md:24). The honest fix is to drop the declaration, not to cap it; "
            "the exemption records why capping is not the answer, not that the declaration is correct."
        ),
        chain=("llmcompressor",),
    ),
    "huggingface-hub": _Exemption(
        kind="PARENT_BOUNDED",
        reason=(
            "Bounded two links down, not one: pyproject caps llmcompressor, llmcompressor caps transformers, "
            "and transformers caps huggingface-hub (<2.0). llmcompressor itself declares NO constraint on "
            "huggingface_hub — the first draft of this entry claimed it did, and the premise test caught it. "
            "quantfit uses only the long-stable hub surface: HfApi().model_info, snapshot_download, "
            "hf_hub_download and the HF_HUB_CACHE constant. A third independent cap in this project would be "
            "the first one to go unsatisfiable against those two."
        ),
        chain=("llmcompressor", "transformers"),
    ),
    "psutil": _Exemption(
        kind="LEAF_SINGLE_CALL",
        reason=(
            "One call site and one API: psutil.virtual_memory().available at fit.py, asserted by "
            "test_psutil_is_used_through_exactly_one_api. psutil is a leaf C extension with no plugin or "
            "entry-point surface, and that call has been stable since 5.x. If the call set ever widens, the "
            "premise test fails and this entry has to be re-argued."
        ),
    ),
    "scipy": _Exemption(
        kind="ORACLE",
        reason=(
            "scipy exists in this project to be the INDEPENDENT reference implementation: "
            "tests/test_stats_scipy.py cross-checks safety/verify.py:wilson_interval against "
            "scipy.stats.binomtest(...).proportion_ci(method='wilson'). Pinning the oracle to a version "
            "quantfit picked is exactly the circularity the cross-check exists to rule out — the claim worth "
            "having is that whatever scipy ships today still agrees. Dev-only; no user install resolves it."
        ),
    ),
    "pytest": _Exemption(
        kind="DEV_HARNESS",
        reason=(
            "Dev-only; no user install resolves pytest, so a break affects zero installs and is caught by the "
            "same CI run that introduces it. The test suite uses only the most stable surface (plain assert, "
            "tmp_path, monkeypatch, pytest.raises, importorskip), and the 8 -> 9 major bump was absorbed in "
            "this tree with no test change, which is the evidence for the claim rather than an assumption."
        ),
    ),
    "setuptools": _Exemption(
        kind="BUILD_BACKEND",
        reason=(
            "Build-time only: the PEP 517 frontend resolves [build-system].requires into a throwaway isolated "
            "environment and it is never installed alongside quantfit at runtime, so a break cannot reach a "
            "user who already has a wheel. It also cannot rot unnoticed, which is the actual premise: this "
            "repo builds a wheel from the same pyproject on every push and on the weekly canary, on both ubuntu "
            "and windows, so a setuptools release that breaks the build fails install-smoke and "
            "quickstart-install first — asserted by test_build_backend_exemptions_rest_on_a_wheel_build_in_ci. "
            "The >=77 floor is a real claim (PEP 639 license expressions, which this project's metadata uses); "
            "the open upper end says only that no known setuptools release breaks this build."
        ),
    ),
    "wheel": _Exemption(
        kind="BUILD_BACKEND",
        reason=(
            "Same throwaway-build-environment argument as setuptools, and weaker still: this requirement carries "
            "no specifier of any kind, and setuptools>=70 vendors its own wheel handling, so it is very likely "
            "dead weight rather than a bound worth setting. Capping it would pin a package this build does not "
            "meaningfully use; the honest fix is to DELETE it from [build-system].requires, which is "
            "pyproject.toml-owner work. The exemption records why capping is not the answer, not that the "
            "declaration is correct — the same shape as the accelerate entry above."
        ),
    ),
}


# --------------------------------------------------------------------------------------
# 1. The policy itself
# --------------------------------------------------------------------------------------


def _unbounded_and_unexempt(pairs: list[tuple[str, _Requirement]]) -> list[str]:
    offenders = []
    for group, req in pairs:
        if req.has_upper_bound or req.name in _EXEMPTIONS:
            continue
        offenders.append(f"{req.raw!r} in {_location(group)}")
    return offenders


def test_every_hard_dependency_is_bounded_or_exempt():
    offenders = _unbounded_and_unexempt([("", req) for req in _hard_requirements()])
    assert not offenders, (
        "ROADMAP standing rule (ROADMAP.md:10): upper-bound pins for churning dependencies. "
        f"These declare no upper bound and carry no exemption in tests/test_dependencies.py:_EXEMPTIONS: "
        f"{offenders}. Fix by adding a cap in pyproject.toml, or by adding a justified exemption entry - "
        "not by widening the exemption table with an unstated reason."
    )


def test_every_optional_dependency_is_bounded_or_exempt():
    pairs = [(extra, req) for extra, reqs in _optional_requirements().items() for req in reqs]
    offenders = _unbounded_and_unexempt(pairs)
    assert not offenders, (
        "Optional dependencies are held to the same rule as hard ones - an extra is still something a user "
        f"installs. Unbounded and unexempt: {offenders}. Add a cap in pyproject.toml, or an exemption entry "
        "with a stated reason in tests/test_dependencies.py:_EXEMPTIONS."
    )


def test_every_build_requirement_is_bounded_or_exempt():
    """`[build-system].requires` is installed by the build frontend, so the rule applies there too.

    This is the group the policy originally missed entirely: two requirements
    (`setuptools>=77`, `wheel`) that no test read and no document mentioned. A build
    requirement is a real resolution against a live index on every sdist install and every
    `python -m build`; "it is only the build" is a reason for a different exemption CLASS
    (`BUILD_BACKEND`), not for sitting outside the policy.
    """
    build = _build_requirements()
    assert build, "pyproject declares no [build-system].requires; this reader is stale"
    offenders = _unbounded_and_unexempt([(_BUILD_SYSTEM_GROUP, req) for req in build])
    assert not offenders, (
        f"unbounded and unexempt build requirements: {offenders}. Cap them in pyproject.toml, or add a "
        "BUILD_BACKEND exemption in tests/test_dependencies.py:_EXEMPTIONS that states why a cap is wrong."
    )


# --------------------------------------------------------------------------------------
# 2. The exemption table cannot rot
# --------------------------------------------------------------------------------------


def test_exemption_table_has_no_dead_entries():
    """An exemption for something that is declared nowhere, or has since been capped, is dead."""
    declared = {req.name: req for _, req in _all_requirements()}
    dead = []
    for name in _EXEMPTIONS:
        req = declared.get(name)
        if req is None:
            dead.append(f"{name}: exempted but not declared in pyproject.toml at all")
        elif req.has_upper_bound:
            dead.append(f"{name}: exempted but now carries an upper bound ({req.raw!r}) — delete the exemption")
    assert not dead, f"stale entries in _EXEMPTIONS: {dead}"


def test_every_exemption_states_a_kind_and_a_substantive_reason():
    problems = []
    for name, ex in _EXEMPTIONS.items():
        if ex.kind not in _KINDS:
            problems.append(f"{name}: unknown exemption class {ex.kind!r} (known: {sorted(_KINDS)})")
        # A one-liner is how "we'll fix it later" gets recorded as policy. The bar is an argument.
        if len(ex.reason.split()) < 25:
            problems.append(f"{name}: reason is {len(ex.reason.split())} words; state the actual argument")
        if ex.kind == "PARENT_BOUNDED" and not ex.chain:
            problems.append(f"{name}: PARENT_BOUNDED must name the resolution chain whose cap does the work")
        if ex.kind not in _CHAIN_BEARING_KINDS and ex.chain:
            problems.append(f"{name}: {ex.kind} makes no parent-bound claim, so it may not name a chain")
    assert not problems, problems


def test_parent_bounded_exemptions_root_in_a_dependency_quantfit_itself_caps():
    """The whole PARENT_BOUNDED argument collapses the moment the root of the chain loses its cap.

    Runs over every entry that NAMES a chain, not only the PARENT_BOUNDED ones. `torch` is
    BUILD_SELECTED and its parent-bound half is a sub-claim rather than the reason, but a
    sub-claim the class system cannot verify is exactly how an exemption reason drifts from
    what is true. If it is written down, it is checked.
    """
    declared = {req.name: req for _, req in _all_requirements()}
    problems = []
    for name, ex in _EXEMPTIONS.items():
        if not ex.chain:
            continue
        root = declared.get(_canonical(ex.chain[0]))
        if root is None:
            problems.append(f"{name}: chain root {ex.chain[0]!r} is not a dependency quantfit declares")
        elif not root.has_upper_bound:
            problems.append(
                f"{name}: chain root {ex.chain[0]!r} ({root.raw!r}) has no upper bound, so it bounds nothing — "
                f"either re-cap {ex.chain[0]} or cap {name} directly"
            )
    assert not problems, problems


def _requirements_declared_by(dist: str) -> list[_Requirement] | None:
    """Every DEFAULT-install requirement `dist` declares, or None when `dist` is absent.

    Requirements behind an extra are dropped: a bound that only applies to
    `parent[something]` is not a bound on the install a user actually gets.
    """
    import importlib.metadata as md

    try:
        requires = md.requires(dist) or []
    except md.PackageNotFoundError:
        return None
    return [_parse_requirement(raw) for raw in requires if "extra ==" not in raw]


def _lower_bound(req: _Requirement) -> str | None:
    lowers = [v for op, v in req.specs if op == ">="]
    return lowers[0] if len(lowers) == 1 else None


def _version_key(raw: str) -> tuple[int, ...]:
    """Leading numeric release segments, enough to order the versions this repo declares."""
    parts: list[int] = []
    for chunk in raw.split("."):
        digits = re.match(r"\d+", chunk)
        if not digits:
            break
        parts.append(int(digits.group(0)))
    assert parts, f"unorderable version string {raw!r}"
    return tuple(parts)


def test_parent_bounded_premises_hold_against_installed_metadata():
    """Re-read the parent's own constraint instead of trusting this file's prose.

    Runs over every entry that names a chain (see the sibling root test for why that is
    wider than PARENT_BOUNDED). Skips where the parent is not installed — CI's unit-test job
    installs the package with `--no-deps` (`.github/workflows/ci.yml`), so llmcompressor is
    absent there. This runs on any full-dependency environment (a dev box, the install-smoke
    image) and is what would catch a future llmcompressor minor that drops its
    transformers/torch caps.
    """
    import importlib.metadata as md

    def bounds_declared_by(dist: str) -> dict[str, str] | None:
        """{canonical name: raw specifier} for every DEFAULT-install requirement `dist` caps."""
        requirements = _requirements_declared_by(dist)
        if requirements is None:
            return None
        return {req.name: req.raw for req in requirements if req.has_upper_bound}

    checked = 0
    problems = []
    for name, ex in _EXEMPTIONS.items():
        if not ex.chain:
            continue
        # Walk chain[0] -> chain[1] -> ... -> name; every link must be a real declared cap.
        for link, target in zip(ex.chain, (*ex.chain[1:], name)):
            bounds = bounds_declared_by(link)
            if bounds is None:  # not installed here; nothing to verify for this link
                continue
            checked += 1
            if _canonical(target) not in bounds:
                problems.append(
                    f"{name}: {ex.kind} claims a bound via {' -> '.join(ex.chain)}, but installed "
                    f"{link}=={md.version(link)} declares no upper bound on {target}. That link is broken: "
                    f"cap {name} in pyproject.toml or re-argue the entry."
                )
    if not checked:
        pytest.skip("no exemption chain link is installed here (CI's unit job installs with --no-deps)")
    assert not problems, problems


# The floors quantfit declares that CANNOT bind on a default install, because the chain the
# exemption names already imposes a higher one. Recorded, not asserted away: each is a real
# limitation of this policy, and pinning them means a NEW inert floor fails the build while
# the known ones stay visible. Value = the floor spec pyproject declares today.
#
# Raising any of these to the parent's floor (see the failure message for the number) makes
# the entry disappear from the computed set, which fails this test and forces the line below
# to be deleted on purpose. That is the intended way out.
_INERT_FLOORS: dict[str, str] = {
    "torch": ">=2.4",  # llmcompressor requires torch>=2.10.0
    "transformers": ">=4.56",  # llmcompressor requires transformers>=5.9.0
    "datasets": ">=3.0",  # llmcompressor requires datasets>=4.8.4
    "accelerate": ">=1.0",  # llmcompressor requires accelerate>=1.6.0
    "huggingface-hub": ">=0.25",  # transformers requires huggingface-hub>=1.5.0
}


def test_floors_that_cannot_bind_are_recorded_not_discovered():
    """A floor below the parent chain's own floor is an INERT instrument, not a weak one.

    Several exemptions argue that a cap is unnecessary and point at the floor as the
    instrument that survives. For every chain-bearing entry in this table that argument is
    only half true: on a DEFAULT install the parent's floor is strictly higher, so
    quantfit's floor is unreachable and does nothing. It binds solely on the `--no-deps`
    paths (ci.yml's unit job, canary.yml's determinism job) where the parent is absent.

    This does not fail the build for the floors that are already inert — the fix is a
    pyproject change this file does not own, and the fix is not free either, since raising a
    floor is itself a claim that the new version was validated. What it does is make the set
    closed: a new inert floor, or a floor silently raised without deleting its entry here,
    fails until someone writes down which of the two happened.
    """
    installed_any = False
    observed: dict[str, tuple[str, str, str]] = {}  # name -> (own floor, parent, parent floor)
    declared = {req.name: req for _, req in _all_requirements()}

    for name, ex in _EXEMPTIONS.items():
        req = declared.get(name)
        own = _lower_bound(req) if req else None
        if not ex.chain or own is None:
            continue
        parent = ex.chain[-1]  # the link that actually constrains `name`
        parent_requirements = _requirements_declared_by(parent)
        if parent_requirements is None:
            continue
        installed_any = True
        for candidate in parent_requirements:
            parent_floor = _lower_bound(candidate)
            if candidate.name != _canonical(name) or parent_floor is None:
                continue
            if _version_key(own) < _version_key(parent_floor):
                observed[name] = (f">={own}", parent, f">={parent_floor}")

    if not installed_any:
        pytest.skip("no exemption chain parent is installed here (CI's unit job installs with --no-deps)")

    unrecorded = {n: v for n, v in observed.items() if n not in _INERT_FLOORS}
    stale = {n: v for n, v in _INERT_FLOORS.items() if n not in observed}
    drifted = {
        n: (_INERT_FLOORS[n], observed[n][0])
        for n in observed.keys() & _INERT_FLOORS.keys()
        if _INERT_FLOORS[n] != observed[n][0]
    }
    assert not unrecorded, (
        f"new inert floor(s): {unrecorded} (name -> own floor, parent, parent's floor). quantfit's floor is "
        "below the one the parent already imposes, so it can never bind on a default install. Either raise it "
        "to the parent's floor AFTER a validated run on that version, or add it to _INERT_FLOORS with the "
        "parent's floor in the comment and say so in the exemption's reason."
    )
    assert not stale, (
        f"_INERT_FLOORS records {stale} as inert, but they are not (any more). Delete those entries — and if a "
        "floor was raised to make this happen, record the run that justified it in CHANGELOG.md."
    )
    assert not drifted, f"_INERT_FLOORS is out of date with pyproject.toml (recorded vs declared): {drifted}"


# A dependency that has crossed a MAJOR version boundary above its declared floor, under an
# exemption, with no cap to stop it and no run recorded on the new major. `name: (floor,
# major observed when this was recorded)`. A NEW name here, or a FURTHER major crossed by a
# name already here, fails the test and has to be argued.
_MAJOR_CROSSED: dict[str, tuple[str, int]] = {
    "transformers": (">=4.56", 5),  # hard dep; floor never moved, no validated run on 5.x recorded
    "datasets": (">=3.0", 4),  # hard dep; same
    "huggingface-hub": (">=0.25", 1),  # hard dep; 0.x -> 1.x, the largest relative jump in the set
    "psutil": (">=5.9", 7),  # LEAF_SINGLE_CALL: two majors, but the single call site is premise-tested
    "pytest": (">=8.0", 9),  # DEV_HARNESS: the 8 -> 9 bump IS recorded, in the exemption reason itself
}


def test_a_major_boundary_crossed_under_an_exemption_is_recorded():
    """An uncapped dependency can change major version under you; the table has to admit it.

    A cap is the instrument that stops this and these requirements deliberately have none,
    so the honest substitute is a recorded list. Resolved against INSTALLED metadata, so it
    describes a real resolution rather than a guess about the index. Skips entirely where
    nothing is installed (CI's `--no-deps` unit job).

    `[build-system].requires` is deliberately outside this check, and the exclusion is not
    a convenience: a build requirement's *installed* version is not the version that built
    anything. PEP 517 frontends build in an isolated environment this metadata cannot see,
    so what `md.version("setuptools")` reports is whatever the interpreter image happens to
    ship — 79 on GitHub's 3.10 and 3.11 runners, absent entirely on 3.12+, which no longer
    bundle it, and 70.2.0 on the maintainer's box. Reading it measured the runner rather
    than quantfit: the check passed everywhere setuptools was old or missing and turned CI
    red on exactly the two images where it was new. Build requirements remain fully inside
    the bounded-or-exempt policy (`test_every_build_requirement_is_bounded_or_exempt`);
    it is only this ambient-metadata inference they are excluded from.
    """
    import importlib.metadata as md

    observed: dict[str, tuple[str, int]] = {}
    resolved = 0
    for group, req in _all_requirements():
        if group == _BUILD_SYSTEM_GROUP:
            continue
        floor = _lower_bound(req)
        if floor is None or req.name not in _EXEMPTIONS:
            continue
        try:
            version = md.version(req.name)
        except md.PackageNotFoundError:
            continue
        resolved += 1
        floor_major, installed_major = _version_key(floor)[0], _version_key(version)[0]
        if installed_major > floor_major:
            observed[req.name] = (f">={floor}", installed_major)

    if not resolved:
        pytest.skip("no exempt dependency is installed here (CI's unit job installs with --no-deps)")

    new = {n: v for n, v in observed.items() if n not in _MAJOR_CROSSED}
    further = {
        n: (_MAJOR_CROSSED[n][1], v[1])
        for n, v in observed.items()
        if n in _MAJOR_CROSSED and v[1] > _MAJOR_CROSSED[n][1]
    }
    assert not new, (
        f"newly crossed a major boundary under an exemption: {new} (name -> declared floor, installed major). "
        "No cap stopped it, the floor did not move, and no run on the new major is recorded. Either cap it in "
        "pyproject.toml, raise the floor after a validated run (docs/dependency-policy.md §5), or record it in "
        "_MAJOR_CROSSED with the reason it is tolerable."
    )
    assert not further, (
        f"crossed a FURTHER major since this was recorded (recorded -> installed): {further}. Re-argue the "
        "exemption on the new major or move the floor; do not just bump the number."
    )


def test_the_major_crossing_check_ignores_build_requirements():
    """Pin the exclusion above, because reverting it turns CI red on two images only.

    The build requirements are exempt AND uncapped AND carry floors, so they satisfy every
    precondition of the major-crossing scan; the only thing keeping them out is the group
    check. Without it, `setuptools>=77` against the 79 that GitHub's 3.10 and 3.11 images
    ship is a "newly crossed a major boundary" failure — on those two jobs and nowhere
    else, since 3.12+ images do not bundle setuptools at all. That is a hard failure to
    diagnose from a local run, so it gets a test rather than a comment alone.
    """
    build = [req for group, req in _all_requirements() if group == _BUILD_SYSTEM_GROUP]
    assert build, "pyproject declares no [build-system].requires; this reader is stale"
    qualifying = [
        req.name
        for req in build
        if _lower_bound(req) is not None and req.name in _EXEMPTIONS and not req.has_upper_bound
    ]
    assert qualifying, (
        "no build requirement is exempt-with-a-floor any more, so this guard has no subject. "
        "Re-point it or delete it deliberately."
    )
    # The scan must not observe them even when they are installed with a higher major.
    import importlib.metadata as md

    for name in qualifying:
        try:
            md.version(name)
        except md.PackageNotFoundError:
            continue
        break
    else:
        pytest.skip("no qualifying build requirement is installed here, so there is nothing to have excluded")

    test_a_major_boundary_crossed_under_an_exemption_is_recorded()  # must not fail on their account


def test_psutil_is_used_through_exactly_one_api():
    """The premise of psutil's LEAF_SINGLE_CALL exemption, checked rather than asserted."""
    used = set()
    for path in _package_sources():
        used.update(re.findall(r"\bpsutil\.(\w+)", path.read_text(encoding="utf-8")))
    assert used == {"virtual_memory"}, (
        f"psutil's exemption rests on a single stable call; the package now uses {sorted(used)}. "
        "Either narrow the usage or replace the LEAF_SINGLE_CALL exemption with a real cap."
    )


def test_accelerate_is_declared_but_never_imported():
    """`accelerate` is a hard dependency with no import anywhere in the package.

    The `device_map="auto"` offload path that justified it was deleted at 0.3
    (`CHANGELOG.md:346`, `ROADMAP.md:24`) and the only surviving mention is a comment at
    `backends/compressed_tensors.py:93` saying it is NOT used. This test pins that state: if
    quantfit starts importing accelerate again, the dependency-policy entry has to be rewritten
    on purpose rather than inherited.
    """
    importers = [
        str(p.relative_to(_ROOT))
        for p in _package_sources()
        if re.search(r"^\s*(?:import|from)\s+accelerate\b", p.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    assert not importers, (
        f"quantfit now imports accelerate ({importers}), which contradicts docs/dependency-policy.md. "
        "Update the policy doc and this test together, on purpose."
    )


def test_dev_only_exemptions_are_not_imported_by_the_package():
    """ORACLE / DEV_HARNESS exemptions claim "no user install resolves this". Check it."""
    dev_only = [n for n, ex in _EXEMPTIONS.items() if ex.kind in {"ORACLE", "DEV_HARNESS"}]
    assert dev_only, "the ORACLE/DEV_HARNESS classes exist to be used; none are in the table"
    optional_names = {req.name for reqs in _optional_requirements().values() for req in reqs}
    hard_names = {req.name for req in _hard_requirements()}
    problems = []
    for name in dev_only:
        if name in hard_names:
            problems.append(f"{name}: claimed dev-only but declared as a hard dependency")
        elif name not in optional_names:
            problems.append(f"{name}: claimed dev-only but declared in no extra")
        module = name.replace("-", "_")
        importers = [
            str(p.relative_to(_ROOT))
            for p in _package_sources()
            if re.search(rf"^\s*(?:import|from)\s+{re.escape(module)}\b", p.read_text(encoding="utf-8"), re.MULTILINE)
        ]
        if importers:
            problems.append(f"{name}: claimed dev-only but imported by shipped code {importers}")
    assert not problems, problems


def test_build_backend_exemptions_rest_on_a_wheel_build_in_ci():
    """BUILD_BACKEND's premise: a build requirement break must fail a build that actually runs.

    The class argues "it never reaches a user's runtime environment, and a break fails the
    wheel build first". The second half is the load-bearing one and it is false the moment
    nothing builds a wheel, so it is read out of the workflows rather than assumed. Both
    surfaces are asserted because they fail at different times: `ci.yml`'s `install-smoke`
    is per-push, `canary.yml`'s `quickstart-install` is weekly against a re-resolved index.
    """
    if not [n for n, ex in _EXEMPTIONS.items() if ex.kind == "BUILD_BACKEND"]:
        pytest.skip("no BUILD_BACKEND exemption to substantiate")
    missing = [
        path.name for path in (_CI, _CANARY) if not re.search(r"python -m build\b", path.read_text(encoding="utf-8"))
    ]
    assert not missing, (
        f"{missing} no longer builds a wheel, so nothing exercises [build-system].requires before a user "
        "does. Either restore the build step or cap the build requirements in pyproject.toml — the "
        "BUILD_BACKEND exemptions are not defensible without it."
    )


def test_a_dependency_declared_twice_carries_the_same_specifier():
    """`gguf` is declared in two extras. Two copies of a bound is two places for it to drift.

    Accumulated per OCCURRENCE, not per group. Keying by group made two divergent copies
    inside the SAME group (`dev = ["gguf>=0.10,<1.0", "gguf>=0.9"]`) overwrite each other and
    vanish — the exact drift this test exists to catch, silently swallowed by its own index.
    """
    seen: dict[str, list[tuple[str, str]]] = {}
    for group, req in _all_requirements():
        seen.setdefault(req.name, []).append((_location(group), req.raw))
    divergent = {
        name: occurrences
        for name, occurrences in seen.items()
        if len({_parse_requirement(raw).specs for _where, raw in occurrences}) > 1
    }
    assert not divergent, (
        f"the same dependency is declared with different specifiers: {divergent}. Two copies of a bound is two "
        "places for it to drift; make them identical in pyproject.toml."
    )


# --------------------------------------------------------------------------------------
# 3. requires-python, classifiers and the CI matrix are one claim in three places
# --------------------------------------------------------------------------------------

_CLASSIFIER_PREFIX = "Programming Language :: Python :: "


def _classifier_versions() -> list[tuple[int, int]]:
    out = []
    for classifier in _pyproject()["project"]["classifiers"]:
        if not classifier.startswith(_CLASSIFIER_PREFIX):
            continue
        tail = classifier[len(_CLASSIFIER_PREFIX) :].strip()
        if re.fullmatch(r"\d+\.\d+", tail):  # skips the bare "3" umbrella classifier
            major, minor = tail.split(".")
            out.append((int(major), int(minor)))
    assert out, "pyproject declares no `Programming Language :: Python :: X.Y` classifiers"
    return sorted(out)


def _requires_python_specs() -> frozenset[tuple[str, str]]:
    return _parse_requirement("python" + _pyproject()["project"]["requires-python"]).specs


def test_requires_python_agrees_with_the_classifiers():
    """The floor is asserted. The CEILING loop below is a no-op today, deliberately.

    `requires-python = ">=3.10"` carries no upper bound, so the `for op, raw in specs` loop
    at the end of this test never executes a body. That is a decision, not an oversight, and
    it is written here so the emptiness is not mistaken for coverage:

    - a ceiling in `requires-python` is enforced by the INSTALLER, not by a test. Shipping
      `>=3.10,<3.15` makes every already-published quantfit release uninstallable on 3.15
      the day it ships, for users whose code is fine — a resolver failure with no fix
      available to them, which is worse than running on a Python this project has not tested;
    - the honest instrument for "which Pythons are supported" is the classifier list, which
      is a claim rather than a constraint, and `test_ci_matrix_covers_exactly_the_advertised_python_versions`
      is what turns it into evidence by forcing the CI matrix to equal it exactly.

    The residual risk is real and is not being hidden: `pip install quantfit` will succeed on
    a Python newer than anything CI has tested, and the classifiers will not stop it. The
    loop below is kept live so that if `pyproject.toml` ever DOES gain a ceiling, it must
    agree with the top classifier instead of being a second, quieter support claim.
    """
    versions = _classifier_versions()
    specs = _requires_python_specs()
    lowers = [v for op, v in specs if op == ">="]
    assert len(lowers) == 1, f"expected exactly one `>=` lower bound in requires-python, got {sorted(specs)}"
    lower = tuple(int(p) for p in lowers[0].split("."))
    assert lower == versions[0], (
        f"requires-python floor is {lowers[0]} but the lowest advertised classifier is "
        f"{'.'.join(map(str, versions[0]))}. One of the two is lying to installers."
    )
    for op, raw in specs:
        if op not in _UPPER_BOUND_OPS:
            continue
        cap = tuple(int(p) for p in raw.split("."))
        top = versions[-1]
        expected = top if op == "<=" else (top[0], top[1] + 1)
        assert cap == expected, (
            f"requires-python carries `{op}{raw}` but the highest advertised classifier is "
            f"{'.'.join(map(str, top))}; the cap and the classifier list disagree."
        )


def test_the_open_requires_python_ceiling_is_a_decision():
    """Pin the absence, so adding or removing a ceiling is deliberate rather than incidental.

    Without this, `test_requires_python_agrees_with_the_classifiers`'s ceiling loop passes
    whether the ceiling exists or not, and nothing anywhere records that the open end was
    chosen. See that test's docstring for the argument; this one only makes flipping it a
    two-line change that a reviewer sees.
    """
    caps = sorted((op, v) for op, v in _requires_python_specs() if op in _UPPER_BOUND_OPS)
    assert not caps, (
        f"requires-python has gained a ceiling ({caps}). That is allowed, but it is a support-policy change: "
        "update this test and docs/dependency-policy.md §3 together, and confirm the cap matches the highest "
        "advertised classifier (the sibling test checks that once a cap exists)."
    )


def test_classifier_python_versions_are_contiguous():
    """A gap means either a dropped version nobody documented or a typo nobody caught."""
    versions = _classifier_versions()
    expected = [(versions[0][0], versions[0][1] + i) for i in range(len(versions))]
    assert versions == expected, f"advertised python classifiers are not contiguous: {versions}"


def _ci_matrix_pythons_hand_rolled() -> list[str]:
    """The `test` job's matrix, read without PyYAML so the check never depends on a transitive dep.

    ci.yml uses the flow-sequence form on exactly one line; the other jobs pin a scalar
    `python-version: "3.12"`, which this pattern deliberately does not match.
    """
    text = _CI.read_text(encoding="utf-8")
    matches = re.findall(r"^[ \t]*python-version:[ \t]*\[(?P<items>[^\]]*)\][ \t]*$", text, re.MULTILINE)
    assert len(matches) == 1, (
        f"expected exactly one matrix `python-version: [...]` line in {_CI.name}, found {len(matches)}. "
        "This parser is intentionally narrow — widen it deliberately if the workflow gains a second matrix."
    )
    return [item.strip().strip("\"'") for item in matches[0].split(",") if item.strip()]


def test_ci_matrix_covers_exactly_the_advertised_python_versions():
    advertised = {".".join(map(str, v)) for v in _classifier_versions()}
    matrix = set(_ci_matrix_pythons_hand_rolled())
    assert matrix == advertised, (
        f"CI tests {sorted(matrix)} but the package advertises {sorted(advertised)}. "
        f"Untested-but-advertised: {sorted(advertised - matrix)}; tested-but-unadvertised: "
        f"{sorted(matrix - advertised)}. A classifier is a support claim; the matrix is the evidence."
    )


def test_hand_rolled_matrix_parse_agrees_with_pyyaml():
    """PyYAML is authoritative where present; the hand-rolled reader is what makes the check unskippable."""
    if _yaml is None:  # pragma: no cover — only reachable if huggingface_hub drops pyyaml
        pytest.skip("PyYAML not installed")
    workflow = _yaml.safe_load(_CI.read_text(encoding="utf-8"))
    parsed = workflow["jobs"]["test"]["strategy"]["matrix"]["python-version"]
    assert [str(v) for v in parsed] == _ci_matrix_pythons_hand_rolled()


# --------------------------------------------------------------------------------------
# 4. Extras named in prose must exist, and CI must install what the package declares
# --------------------------------------------------------------------------------------

# `quantfit[x]` or `.[x]`, single or comma-joined. The leading letter requirement keeps
# markdown footnote/link syntax (`word.[1]`) out of the match.
_EXTRA_RE = re.compile(r"(?:quantfit|\.)\[([a-z][a-z0-9_-]*(?:,[a-z][a-z0-9_-]*)*)\]")

# CHANGELOG and ROADMAP are history and plan respectively — the same carve-out
# tests/test_meta.py:test_no_safety_tax_on_shipped_surfaces makes, and for the same reason:
# a renamed extra must not retroactively falsify a release note.
_PROSE_SURFACES = ("README.md", "docs/*.md", "spec/*.md", ".github/workflows/*.yml", ".github/actions/*/action.yml")


def _prose_files() -> list[Path]:
    files: list[Path] = []
    for pattern in _PROSE_SURFACES:
        files.extend(sorted(_ROOT.glob(pattern)))
    assert files, "the prose-surface glob matched nothing; the surface list is stale"
    return files


def test_every_extra_named_in_prose_exists_in_pyproject():
    declared = set(_optional_requirements())
    missing = []
    for path in _prose_files():
        for match in _EXTRA_RE.finditer(path.read_text(encoding="utf-8")):
            for extra in match.group(1).split(","):
                if extra not in declared:
                    missing.append(
                        f"{path.relative_to(_ROOT)} names quantfit[{extra}], which pyproject does not define"
                    )
    assert not missing, f"{missing}; declared extras are {sorted(declared)}"


def test_the_documented_extras_exist():
    """An explicit floor, so deleting an extra fails even if no prose currently names it."""
    declared = set(_optional_requirements())
    expected = {"gguf", "awq", "inspect", "dev"}
    assert expected <= declared, f"missing documented extras: {sorted(expected - declared)}"


def _quoted_requirements_in(path: Path) -> list[_Requirement]:
    pattern = re.compile(r"\"([A-Za-z][A-Za-z0-9._-]*(?:<=|>=|==|~=|!=|<|>)[^\"]*)\"")
    return [_parse_requirement(raw) for raw in pattern.findall(path.read_text(encoding="utf-8"))]


def test_requirements_re_declared_in_workflows_match_pyproject():
    """CI must exercise the versions the package declares, not a second opinion.

    `.github/workflows/canary.yml` installs the verify-safety dependency set by hand after an
    `-e . --no-deps` install, and `.github/workflows/ci.yml` installs ruff by hand. Both restate
    specifiers that live in pyproject.toml, so both are places a bumped floor or a new cap can
    fail to propagate — and the canary is precisely the job whose value depends on installing
    what a user would get.
    """
    declared: dict[str, set[frozenset[tuple[str, str]]]] = {}
    for _, req in _all_requirements():
        declared.setdefault(req.name, set()).add(req.specs)

    mismatches = []
    checked = 0
    for path in (_CI, _CANARY):
        for req in _quoted_requirements_in(path):
            if req.name not in declared:
                continue
            checked += 1
            if req.specs not in declared[req.name]:
                expected = sorted({",".join(f"{op}{v}" for op, v in sorted(s)) for s in declared[req.name]})
                mismatches.append(f"{path.name} installs {req.raw!r}; pyproject.toml declares {expected}")
    assert checked, "no workflow re-declares a quantfit dependency; the surface list is stale"
    assert not mismatches, mismatches
