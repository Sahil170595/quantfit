"""ROADMAP 1.0: "dependencies bounded" as a test rather than a promise.

The standing ROADMAP rule is `ROADMAP.md:10` and `ROADMAP.md:116`: upper-bound pins for
churning dependencies, and the cap moves only after a validated run on the new minor.
Until this file existed the rule was prose — `llmcompressor`, `ruff`, `gguf` and
`inspect-ai` carried caps because someone remembered to add one, and nothing noticed the
ones that did not.

This module makes the rule mechanical. Every requirement quantfit declares must either
carry an upper bound or appear in `_EXEMPTIONS` below with a named exemption class and a
stated reason. There is deliberately no third option and no "TODO" state: an unbounded,
unexempted dependency is a test failure, not a warning.

The exemption table is the part that rots, so the premises are checked too:

- a `PARENT_BOUNDED` exemption must name a resolution chain rooted in a dependency quantfit
  itself caps (`test_parent_bounded_exemptions_root_in_a_dependency_quantfit_itself_caps`),
  and, where a link of that chain is installed, its declared bound is re-read from that
  package's own metadata rather than trusted from this docstring. That check is not
  decorative: it caught this table's first draft claiming `llmcompressor` bounds
  `huggingface_hub`, which it does not;
- `LEAF_SINGLE_CALL` and the dev-only exemptions assert the usage claim they rest on;
- an exemption for a dependency that has since been capped is a dead entry and fails, so
  the table cannot silently accumulate.

Everything here is hermetic: it reads `pyproject.toml`, two workflow files and the package
source. It imports no backend, loads no model and touches no network.

`docs/dependency-policy.md` is this file in prose. If the two disagree, this file is the
one that runs.
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


def _all_requirements() -> list[tuple[str, _Requirement]]:
    """(group, requirement) for every declared requirement. Group "" is the hard set."""
    out: list[tuple[str, _Requirement]] = [("", req) for req in _hard_requirements()]
    for extra, reqs in _optional_requirements().items():
        out.extend((extra, req) for req in reqs)
    return out


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
    }
)


@dataclass(frozen=True)
class _Exemption:
    kind: str
    reason: str
    # PARENT_BOUNDED only: the resolution chain from a dependency quantfit itself caps, down to
    # the dependency that actually constrains the exempted one. `("llmcompressor", "transformers")`
    # means: pyproject caps llmcompressor, llmcompressor caps transformers, transformers caps this.
    # A chain rather than a single name because the first draft of this table asserted
    # llmcompressor constrained huggingface_hub — it does not, and the premise test below caught it.
    chain: tuple[str, ...] = ()


_EXEMPTIONS: dict[str, _Exemption] = {
    "torch": _Exemption(
        kind="BUILD_SELECTED",
        reason=(
            "An upper cap in quantfit's own metadata fights the accelerator build the user installed "
            "deliberately. torch wheels are selected by index as much as by version — "
            ".github/workflows/canary.yml installs torch from https://download.pytorch.org/whl/cpu — so a cap "
            "here can refuse, or silently downgrade, the CUDA/ROCm wheel that matches the driver on the box, "
            "which is a worse failure than the API break the cap would prevent. quantfit's torch surface is "
            "narrow and long-stable: .to(device), dtype introspection and torch.cuda queries. The upper end of "
            "a default install is set by llmcompressor, which quantfit does cap."
        ),
    ),
    "transformers": _Exemption(
        kind="PARENT_BOUNDED",
        reason=(
            "llmcompressor is a hard dependency and is capped (<0.13), and it constrains transformers tightly "
            "at BOTH ends from its own metadata. An independent quantfit cap would not add safety; it would "
            "risk being unsatisfiable against llmcompressor's own upper pin, which is the harder failure to "
            "diagnose. quantfit's transformers surface is the Auto* from_pretrained classes plus __version__; "
            "the one churn that has bitten this project (torch_dtype -> dtype at 4.56) is recorded as the "
            "FLOOR in pyproject, which is the correct instrument for that break."
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
}


# --------------------------------------------------------------------------------------
# 1. The policy itself
# --------------------------------------------------------------------------------------


def _unbounded_and_unexempt(pairs: list[tuple[str, _Requirement]]) -> list[str]:
    offenders = []
    for group, req in pairs:
        if req.has_upper_bound or req.name in _EXEMPTIONS:
            continue
        where = f"optional-dependencies.{group}" if group else "dependencies"
        offenders.append(f"{req.raw!r} in [project.{where}]")
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
        if ex.kind != "PARENT_BOUNDED" and ex.chain:
            problems.append(f"{name}: only PARENT_BOUNDED entries may name a chain")
    assert not problems, problems


def test_parent_bounded_exemptions_root_in_a_dependency_quantfit_itself_caps():
    """The whole PARENT_BOUNDED argument collapses the moment the root of the chain loses its cap."""
    declared = {req.name: req for _, req in _all_requirements()}
    problems = []
    for name, ex in _EXEMPTIONS.items():
        if ex.kind != "PARENT_BOUNDED":
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


def test_parent_bounded_premises_hold_against_installed_metadata():
    """Re-read the parent's own constraint instead of trusting this file's prose.

    Skips where the parent is not installed — CI's unit-test job installs the package with
    `--no-deps` (`.github/workflows/ci.yml`), so llmcompressor is absent there. This runs on any
    full-dependency environment (a dev box, the install-smoke image) and is what would catch a
    future llmcompressor minor that drops its transformers/torch caps.
    """
    import importlib.metadata as md

    def bounds_declared_by(dist: str) -> dict[str, str] | None:
        """{canonical name: raw specifier} for every DEFAULT-install requirement `dist` caps."""
        try:
            requires = md.requires(dist) or []
        except md.PackageNotFoundError:
            return None
        out = {}
        for raw in requires:
            if "extra ==" in raw:  # a bound behind an extra is not a bound on a default install
                continue
            req = _parse_requirement(raw)
            if req.has_upper_bound:
                out[req.name] = raw
        return out

    checked = 0
    problems = []
    for name, ex in _EXEMPTIONS.items():
        if ex.kind != "PARENT_BOUNDED":
            continue
        # Walk chain[0] -> chain[1] -> ... -> name; every link must be a real declared cap.
        for link, target in zip(ex.chain, (*ex.chain[1:], name)):
            bounds = bounds_declared_by(link)
            if bounds is None:  # not installed here; nothing to verify for this link
                continue
            checked += 1
            if _canonical(target) not in bounds:
                problems.append(
                    f"{name}: PARENT_BOUNDED via {' -> '.join(ex.chain)}, but installed "
                    f"{link}=={md.version(link)} declares no upper bound on {target}. That link is broken: "
                    f"cap {name} in pyproject.toml or re-argue the entry."
                )
    if not checked:
        pytest.skip("no PARENT_BOUNDED chain link is installed here (CI's unit job installs with --no-deps)")
    assert not problems, problems


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


def test_a_dependency_declared_twice_carries_the_same_specifier():
    """`gguf` is declared in two extras. Two copies of a bound is two places for it to drift."""
    seen: dict[str, dict[str, frozenset[tuple[str, str]]]] = {}
    for group, req in _all_requirements():
        seen.setdefault(req.name, {})[group or "dependencies"] = req.specs
    divergent = {name: groups for name, groups in seen.items() if len({frozenset(s) for s in groups.values()}) > 1}
    assert not divergent, f"the same dependency is declared with different specifiers: {divergent}"


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
