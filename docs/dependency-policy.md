# Dependency policy — what is bounded, what is not, and who is allowed to move a cap

**Status: policy, and enforced.** Every rule in this document is checked by
`tests/test_dependencies.py`. Where the two disagree, the test is the one that runs and
this file is the bug. The reverse also holds and is stated so it is not mistaken for
completeness: that file contains checks this document has no section for (requires-python
vs classifiers vs the CI matrix, extras named in prose, workflow re-declarations). It is
this policy in prose, not a line-by-line mirror of the suite.

The bound the repo did not satisfy when this document was first written — an uncapped
`gptqmodel` — has since been capped; §4 records what closed and what did not.

**Scope.** This document covers ROADMAP 1.0's "dependencies bounded" clause and the
supply-chain surface that sits next to it. "Every requirement" means the hard set, every
extra, **and `[build-system].requires`** — a group that escaped this policy entirely until
§3.6 was written, which is the same failure mode §1 exists to prevent. It makes no claim
about the QSR spec, which is **not frozen** — `spec/qsr-v1-freeze-plan.md` is the blocking
ledger for that and nothing here changes it. It also makes no claim that any command has
been hardware-validated; §8 states what this policy does *not* cover so the gap is visible
rather than implied.

### Confidence legend

Every factual claim carries one of these marks. Unmarked prose is reasoning about marked
claims, never a new claim.

- **[V]** verified in this working tree at the named `file:line` or `file:symbol`, or read
  from installed package metadata in a full-dependency environment.
- **[I]** inferred from marked facts, not observed.
- **[?]** open — a decision or a measurement that does not exist yet, named with what
  would resolve it.

---

## 1. The rule

The standing ROADMAP rule, applying to every milestone, is
`ROADMAP.md:10` **[V]**:

> upper-bound dependency pins + a weekly runtime canary (CPU oneshot on a toy model, plus
> a clean-venv quickstart install from the lockfile)

and its risk-register twin, `ROADMAP.md:116` **[V]**:

> **Upstream churn** (llm-compressor, llama.cpp near-daily releases) — upper-bound pins,
> weekly runtime canary including the quickstart install path.

Read literally that is "cap everything", which is wrong for at least one dependency
(§3.1). The rule this project actually enforces, and the one `tests/test_dependencies.py`
implements, is:

> **Every declared requirement — hard, optional, or a build requirement — carries an
> upper bound, OR appears in a named exemption table with a stated reason and a class.
> There is no third state.**

An unbounded, unexempted requirement is a test failure. Not a warning, not a TODO. The
exemption table lives in `tests/test_dependencies.py:_EXEMPTIONS` so that the
justification and the enforcement cannot drift apart into two files. Three tests apply the
rule to the three groups: `test_every_hard_dependency_is_bounded_or_exempt`,
`test_every_optional_dependency_is_bounded_or_exempt`, and
`test_every_build_requirement_is_bounded_or_exempt` **[V]**.

**A cap is a claim about a validated run, not a guess.** The second half of the standing
rule — "the cap moves only after a validated run on the new minor" — is what makes a cap
mean something. §5 states what that run is, concretely, per dependency class.

**And a cap is the only instrument that stops a major version change.** The two things an
upper bound would have covered, which the exemptions below do not, are recorded rather
than argued away — see §3.7. A floor is not a substitute for a cap, and in this repo most
of the floors cannot even bind.

---

## 2. What is bounded today

Read from `pyproject.toml` **[V]**:

| requirement | group | cap | why this one churns |
|---|---|---|---|
| `llmcompressor>=0.5,<0.13` | hard | `<0.13` | the modifier/oneshot API churns across minors; `backends/compressed_tensors.py` imports `AWQModifier`, `GPTQModifier`, `QuantizationModifier`, `SmoothQuantModifier` and `oneshot` by path **[V]** |
| `inspect-ai>=0.3.252,<0.4` | `inspect` | `<0.4` | `quantfit/inspect_task.py` depends on `inspect_ai` internals (`SampleScore`/`Score`/`Value`, `inspect_ai.score`, the epoch-reduction behaviour of `Score.value`) and is verified against 0.3.252 **[V]** |
| `gguf>=0.10,<1.0` | `gguf`, `dev` | `<1.0` | pre-1.0 and tracks llama.cpp; the enums quantfit reads are append-only in practice, so `<1.0` is the honest cap **[V]** |
| `ruff>=0.16,<0.17` | `dev` | `<0.17` | 0.16.0 shipped new default rules mid-cycle and broke a green branch **[V]** |
| `gptqmodel>=7.1,<8` | `awq` | `<8` | held for transformers' `AwqQuantizer` internals; see §4, where the cap is closed but the floor is not **[V]** |

**No workflow restates a cap by hand any more, and that is a recent change worth being
precise about.** `.github/workflows/ci.yml` used to install `"ruff>=0.16,<0.17"` as a
literal string — one cap, hand-copied, one place to drift. It now derives every bound from
this file instead: the `Derive dependency caps from pyproject` steps in the `test` and
`lint` jobs run `tools/ci_constraints.py --out ci-constraints.txt`, and the installs use
`pip install -c ci-constraints.txt ...` **[V]**. A constraint on a package CI does not
install is inert, so emitting all of them is maintenance-free
(`tools/ci_constraints.py`, module docstring) **[V]**.

That closes a real hole rather than a cosmetic one: `pip install gguf inspect-ai` ignores
the `<1.0` and `<0.4` caps entirely, so CI could have green-lit a combination the package
forbids **[V]**.

**The one hand-written restatement left is not a cap at all.**
`.github/workflows/canary.yml:113` restates four **floors** with no upper bound
(`"transformers>=4.56" "huggingface_hub>=0.25" "datasets>=3.0" "psutil>=5.9"`) **[V]** — a
different claim, and a weaker one; see §3.2 for why four of those floors cannot bind
anyway. `test_requirements_re_declared_in_workflows_match_pyproject` asserts every
restatement it can find — cap or floor — still matches `pyproject.toml`, scanning both
`ci.yml` and `canary.yml` **[V]**. With the ruff string gone, `canary.yml:113` is the only
thing that test currently has to check, which is worth knowing before someone deletes that
line too. **[?]** A workflow that installs a version the package does not declare is a
canary validating something no user gets.

---

## 3. What is deliberately unbounded, and why

**Ten** declared requirements carry no upper bound **[V]**: eight under `[project]`
(`torch`, `transformers`, `huggingface_hub`, `datasets`, `accelerate`, `psutil`, plus
dev-only `pytest` and `scipy`) and **two under `[build-system].requires`**
(`setuptools>=77`, `wheel`) — the group this document did not count at all until §3.6 was
written, and which no test read either. All ten are exempt below.

Filter behind that count: every string in `[project].dependencies`,
`[project.optional-dependencies].*` and `[build-system].requires` whose specifier set
contains no `<`, `<=`, `==` or `~=`. `gguf` is declared twice (`dev` and `gguf`) with an
identical cap and is counted zero times because it is bounded, not because the duplicate
was dropped; `test_a_dependency_declared_twice_carries_the_same_specifier` is what keeps
those two copies identical **[V]**.

Each exemption carries a **class**, and each class is falsifiable in a different way. The
tests do not take the reasons on trust — they check the premise each reason rests on.

### 3.1 `BUILD_SELECTED` — a cap would fight the user's build

**`torch>=2.4`.** torch wheels are selected by *index* as much as by version: the canary
installs from `https://download.pytorch.org/whl/cpu` (`.github/workflows/canary.yml:107`)
**[V]**, and a user with a CUDA or ROCm box installs the wheel matching their driver. An
upper cap in quantfit's own metadata can refuse that wheel, or silently resolve a user
down onto a build their hardware does not want — a worse and much harder-to-diagnose
failure than the API break the cap would have prevented.

**That argument stands alone, and the exemption now says only that.** It does not depend on
any parent: even if nothing else bounded torch, quantfit still must not cap it, because the
failure a cap causes is worse than the failure it prevents. This is the one dependency where
the literal reading of `ROADMAP.md:10` is wrong, and it is stated here rather than quietly
ignored.

**The separate parent-bound fact is a sub-claim, and it is now machine-checked.** The upper
end of a *default* install is closed by the capped `llmcompressor` (`torch<=2.12.0,>=2.10.0`
**[V]**, §3.2). That used to be prose in the exemption's reason with nothing verifying it —
a claim the class system could not check, sitting inside a `BUILD_SELECTED` entry. The entry
now carries the resolution chain `llmcompressor → torch`, and both premise tests
(`test_parent_bounded_exemptions_root_in_a_dependency_quantfit_itself_caps` and
`test_parent_bounded_premises_hold_against_installed_metadata`) run over **every** entry that
names a chain, not only the `PARENT_BOUNDED` ones **[V]**. The sub-claim is scoped: it holds
only where `llmcompressor` is resolved, which the two `--no-deps` paths in §3.2 are not.

The surface quantfit actually uses is narrow and long-stable: `.to(device)`, dtype
introspection, and `torch.cuda` queries **[V]**. Unlike psutil's (§3.3), that surface claim
is **not** machine-checked, and the exemption says so. **[?]**

### 3.2 `PARENT_BOUNDED` — an already-capped dependency does the bounding

`llmcompressor` is a **hard** dependency, so every default `pip install quantfit` resolves
it, and quantfit caps it at `<0.13`. llmcompressor in turn constrains its own stack at
**both** ends. Read from the metadata of the installed `llmcompressor==0.12.0` **[V]**:

```
torch<=2.12.0,>=2.10.0
transformers<=5.10.1,>=5.9.0
datasets<=5.0.0,>=4.8.4
accelerate<=1.13.0,>=1.6.0
```

Those are `<=` pins on exact versions — considerably tighter than anything quantfit would
write. Adding an independent quantfit cap on top would not add safety; it would add a
second opinion that can be *unsatisfiable* against llmcompressor's own upper pin, and an
unresolvable install is harder to diagnose than a caught API break.

| requirement | chain that bounds it |
|---|---|
| `transformers>=4.56` | `llmcompressor` → `transformers` **[V]** |
| `datasets>=3.0` | `llmcompressor` → `datasets` **[V]** |
| `accelerate>=1.0` | `llmcompressor` → `accelerate` **[V]** |
| `huggingface_hub>=0.25` | `llmcompressor` → `transformers` → `huggingface-hub` (`transformers==5.10.1` declares `huggingface-hub<2.0,>=1.5.0`; `datasets==4.8.5` declares `huggingface-hub<2.0,>=0.25.0`) **[V]** |

**The chain is checked, not asserted.** `test_parent_bounded_premises_hold_against_installed_metadata`
walks each link and re-reads the bound from that package's own metadata. This is not
decorative: the first draft of the exemption table claimed `llmcompressor` bounds
`huggingface_hub`, and the test rejected it — llmcompressor declares no constraint on
`huggingface_hub` at all **[V]**. The entry now names the real two-link chain. Separately,
`test_parent_bounded_exemptions_root_in_a_dependency_quantfit_itself_caps` fails the moment
`llmcompressor` loses its own cap, because every entry in this class collapses with it.

**The limitation, stated because it is real.** This argument holds on the *full-dependency*
install path. Two paths in this repo bypass it:

- `.github/workflows/ci.yml:40` installs `pytest huggingface_hub psutil scipy gguf
  inspect-ai` (now under `-c ci-constraints.txt`, §2) and `.github/workflows/ci.yml:43`
  then runs `pip install -e . --no-deps` **[V]** — llmcompressor is never resolved, so
  nothing bounds transformers or huggingface_hub in that job. The constraints file does
  not change this: a constraint bounds a package that IS installed; it does not install
  llmcompressor, so the chain still has no root there.
- `.github/workflows/canary.yml:112-113` does the same for the determinism canary,
  installing `"transformers>=4.56" "huggingface_hub>=0.25" "datasets>=3.0" "psutil>=5.9"`
  by hand **[V]**.

Both are deliberate (they exist to stay light), and both mean the PARENT_BOUNDED protection
does **not** apply there. The canary's `quickstart-install` job is the one that resolves the
real dependency graph (`canary.yml:311-348`, wheel built then installed into a clean venv)
**[V]**, and that is the job where a broken resolution would actually surface. **[?]**
Whether the unit-test job should also run one leg with full dependencies is a maintainer
decision, not a measurement.

**The floors named above cannot bind, and that is the sharpest limitation in this section.**
The transformers entry used to argue that the `>=4.56` floor in `pyproject.toml` was "the
correct instrument" for the `torch_dtype → dtype` break, i.e. the substitute for the cap it
does not have. It is not an instrument at all on the path this exemption is about:
`llmcompressor` requires `transformers>=5.9.0`, so on any default install the parent's floor
is the binding one and quantfit's `>=4.56` is unreachable. The same is true of every floor in
this class, read from installed metadata **[V]**:

| quantfit declares | the chain already requires | so quantfit's floor is |
|---|---|---|
| `torch>=2.4` | `llmcompressor` → `torch>=2.10.0` | inert on a default install |
| `transformers>=4.56` | `llmcompressor` → `transformers>=5.9.0` | inert |
| `datasets>=3.0` | `llmcompressor` → `datasets>=4.8.4` | inert |
| `accelerate>=1.0` | `llmcompressor` → `accelerate>=1.6.0` | inert |
| `huggingface_hub>=0.25` | `llmcompressor` → `transformers` → `huggingface-hub>=1.5.0` | inert |

Where they *do* bind is the two `--no-deps` paths above, where `llmcompressor` is absent —
and `canary.yml:113` restates four of them by hand for exactly that reason **[V]**. So the
floors are not useless; they are scoped to the opposite path from the one the
PARENT_BOUNDED argument covers, and the two must not be quoted as if they reinforced each
other.

`test_floors_that_cannot_bind_are_recorded_not_discovered` computes this table from
installed metadata and pins it **[V]**. It deliberately does **not** fail on the five above:
raising a floor is itself a claim that the new version was validated (§5), and this file does
not own `pyproject.toml`. What it fails on is a *new* inert floor, or one of these five being
raised without the record being updated. **[?]** Raising all five to their parents' floors is
the obvious fix and needs a run to justify; it is a maintainer decision, listed in §5.

**`accelerate` deserves a separate note.** It is a hard dependency that quantfit imports
**nowhere** — asserted by `test_accelerate_is_declared_but_never_imported` **[V]**. The
`device_map="auto"` offload path that justified it was deleted at 0.3 (`CHANGELOG.md:346`,
`ROADMAP.md:24`) **[V]**, and the only surviving mention is a comment at
`backends/compressed_tensors.py:93` saying it is not used **[V]**. The exemption records
that *capping* is not the right instrument here; the right fix is to **delete the
declaration**, which is `pyproject.toml`-owner work. Until then the test pins the
no-import state, so restoring an import forces this section to be rewritten on purpose.

### 3.3 `LEAF_SINGLE_CALL` — one call, no surface to break

**`psutil>=5.9`.** One call site and one API: `psutil.virtual_memory().available` at
`quantfit/fit.py:143` **[V]**. psutil is a leaf C extension with no plugin or entry-point
surface, and that call has been stable since 5.x. The premise is enforced —
`test_psutil_is_used_through_exactly_one_api` asserts the set of `psutil.*` attributes the
package touches is exactly `{virtual_memory}`, so widening the usage retires the exemption
automatically rather than silently.

This is the weakest exemption in the table, and it is the cheapest to withdraw: capping
psutil costs nothing operationally. It is exempt rather than capped only because a cap
would have to be moved on a schedule set by a dependency quantfit barely uses. **[?]**

### 3.4 `ORACLE` — capping it would make the cross-check circular

**`scipy>=1.11`** (`dev` only). scipy exists in this project for exactly one purpose: to be
the *independent* reference implementation. `tests/test_stats_scipy.py` cross-checks
`safety/verify.py:wilson_interval` (with `_Z_95 = 1.959963984540054`) against
`scipy.stats.binomtest(...).proportion_ci(method="wilson")` to 1e-9 **[V]**.

Pinning the oracle to a version quantfit chose is precisely the circularity that
cross-check exists to rule out. The claim worth having is "whatever scipy ships **today**
still agrees with our Wilson interval", and a cap converts it into "the scipy we picked
agrees", which is nearly worthless. No user install resolves scipy.

### 3.5 `DEV_HARNESS` — dev-only, and a break is caught by the run that causes it

**`pytest>=8.0`** (`dev` only). No user install resolves pytest, so a break affects zero
installs and surfaces in the same CI run that introduces it. The suite uses only the most
stable surface — plain `assert`, `tmp_path`, `monkeypatch`, `pytest.raises`,
`importorskip`. The evidence rather than the assumption: the **8 → 9 major bump has already
been absorbed in this tree with no test change** **[V]**.

`test_dev_only_exemptions_are_not_imported_by_the_package` enforces the "dev-only" half of
both §3.4 and §3.5 — the dependency must be declared in an extra, never in the hard set,
and must not be imported by any module under `quantfit/`.

### 3.6 `BUILD_BACKEND` — build-time only, and the build runs

**`setuptools>=77` and `wheel`**, from `pyproject.toml:2` **[V]**. This group is here
because it was **missing**: two unbounded requirements that no test read, that no section
of this document mentioned, and that the §3 count did not include. "It is only the build"
is a reason for a different exemption *class*, not a reason to sit outside the policy —
`[build-system].requires` is resolved against a live index by the PEP 517 frontend on every
sdist install and every `python -m build`.

The argument has two halves and only the second is load-bearing:

- **It never reaches a user's runtime environment.** The frontend resolves these into a
  throwaway isolated build env; nothing installs them alongside quantfit. A user who
  already has a wheel cannot be affected at all. **[I]**
- **A break fails a build that actually runs, before a user sees it.** This is the premise,
  and it is checked rather than assumed:
  `test_build_backend_exemptions_rest_on_a_wheel_build_in_ci` reads both workflows and fails
  if either stops running `python -m build` **[V]**. Both do today —
  `.github/workflows/ci.yml:63-66` on every push, on ubuntu **and** windows, and
  `.github/workflows/canary.yml:333-338` weekly against a re-resolved index **[V]**.

`setuptools>=77` is a real floor claim (PEP 639 license expressions, which
`pyproject.toml:11` uses) **[V]**. `wheel` carries **no specifier of any kind** and
setuptools has vendored its own wheel handling for years, so it is very likely dead weight
rather than a bound worth setting **[I]**. The exemption records that *capping* is not the
answer; the honest fix is to **delete** it, which is `pyproject.toml`-owner work — the same
shape as `accelerate` in §3.2.

### 3.7 What a cap would have covered, and these exemptions do not

Two consequences follow from having no upper bound, and neither is fixed by any argument
above. They are recorded mechanically instead of being left implicit.

**Floors that cannot bind** — §3.2's table. Five of the five chain-bearing floors are inert
on a default install.

**Major version boundaries crossed with nothing stopping them.** A cap is the only
instrument that prevents a major change; these requirements deliberately have none, so what
actually resolves today is recorded. Read from installed metadata in a full-dependency
environment **[V]**:

| requirement | declared floor | resolves to | crossed |
|---|---|---|---|
| `transformers` | `>=4.56` | 5.10.1 | **4 → 5**, hard dependency |
| `datasets` | `>=3.0` | 4.8.5 | **3 → 4**, hard dependency |
| `huggingface_hub` | `>=0.25` | 1.19.0 | **0 → 1**, hard dependency — the largest relative jump here |
| `psutil` | `>=5.9` | 7.2.2 | 5 → 7, but the single call site is premise-tested (§3.3) |
| `pytest` | `>=8.0` | 9.0.3 | 8 → 9, and this one **is** recorded — the absorbed bump is §3.5's evidence |

For the top three: **no cap stopped the crossing, no floor moved, and no validated run on
the new major is recorded anywhere in this repo.** The PARENT_BOUNDED argument is still
sound — `llmcompressor` does bound them at both ends — but "bounded" and "validated" are
different claims, and only the first is true here.
`test_a_major_boundary_crossed_under_an_exemption_is_recorded` pins this list, so a *new*
crossing, or a further major under an already-listed name, fails until it is argued **[V]**.
**[?]** Raising those three floors to the versions that actually resolve is a §5 decision
that needs a run behind it.

---

## 4. `gptqmodel`: the cap is closed, the floor is not

**`pyproject.toml:52` now declares `awq = ["gptqmodel>=7.1,<8"]` **[V]**, and
`tests/test_dependencies.py::test_every_optional_dependency_is_bounded_or_exempt` passes.**
This section is kept rather than deleted because the reasoning is what makes the cap
defensible, and because only half the problem closed.

Why it qualifies for no exemption class in §3, which is why it had to be capped:

- Not `PARENT_BOUNDED`: nothing quantfit declares constrains it. `llmcompressor==0.12.0`
  does not require `gptqmodel` at all **[V]**.
- Not `BUILD_SELECTED`: it is an ordinary PyPI wheel, not an index-selected accelerator build.
- Not dev-only: `quantfit[awq]` is a user-facing extra, documented in
  `docs/reference-reports-v0.md:140` as the install a first-party AWQ artifact needs **[V]**.
- The role it plays is the exact shape that got `inspect-ai` capped: it exists to satisfy
  **transformers' `AwqQuantizer` internals**, which refuses to load autoawq checkpoints
  without it (`pyproject.toml:47-49`) **[V]**. A dependency held for another library's
  internals is the least stable kind there is. **[I]**

**What closed.** The cap. `<8` claims only that 8.x is unvalidated, which is true, and it
is now the thing that stops a silent major change on a user-facing extra.

**What did not close: the floor is still not backed by a run.** The floor was raised from
`>=1.0` to `>=7.1` in the same change **[V]**. That direction is right — the resolvable
version in a full-dependency environment is `gptqmodel==7.1.0` **[V]**, and `>=1.0` was six
majors below it with no quantfit run ever having validated 1.x — but raising a floor is
itself a claim that the new version works, and **no AWQ screening run has happened**. The
comment at `pyproject.toml:48-51` is precise about what the number actually rests on: 7.x is
what the screen's AWQ row was *curated* against, and "the loader path it backs is exercised
by no hermetic test" **[V]**. Curation is not a run.

For the record on the floor's history: stale build metadata in this tree
(`quantfit.egg-info/requires.txt`, `PKG-INFO` `Version: 0.2.0`) records `gptqmodel>=2.0` as
a *hard* dependency **[V]**, so the floor has moved down and then up without a run behind
any of the three values. (That file is build output, not tracked source; it is cited only
as evidence about the floor's history.)

**[?]** What would substantiate it is one load of a first-party AWQ checkpoint through the
transformers path — §5's row for this dependency — on the same hardware ROADMAP 0.5's
screen still needs. Until then the floor is a known unsubstantiated value, and this section
says so rather than letting the closed cap imply the whole entry is settled.

---

## 5. What "a validated run on the new minor" means

A cap moves when someone has *run* something, not when a bot opens a PR. Concretely, per
class:

| dependency | what must run before the cap moves | who can run it |
|---|---|---|
| `llmcompressor` | one `quantfit quantize` on the compressed-tensors path (AWQ or GPTQ) that completes and produces a loadable artifact, **plus** a `verify-safety` pair over that artifact whose report validates against the schema | anyone with a GPU that fits a ~1.5B pair |
| `gguf` | the GGUF arm tests, which craft and read real GGUF files (`tests/test_gguf_arm.py`), **plus** one real quantize+verify pair, since the enums are read from file metadata and never from filenames (spec §3.2) **[V]** | CPU-only is sufficient |
| `inspect-ai` | `tests/test_inspect_task.py:test_inspect_run_reproduces_tabulate` green on the new minor — the runner depends on `inspect_ai` internals, so that parity against `verify._tabulate` is the whole claim (`pyproject.toml:53-59`) **[V]** | CPU-only; CI installs it for exactly this reason |
| `ruff` | `ruff check quantfit tests tools` and `ruff format --check quantfit tests` green on the new minor, locally, before the cap moves in `pyproject.toml`. **Only there now**: `ci.yml`'s `lint` job installs `ruff` under `-c ci-constraints.txt`, derived from this file (§2), so there is no second copy to move **[V]** | anyone |
| `gptqmodel` | one load of a first-party AWQ checkpoint through the transformers path, i.e. the `quantfit[awq]` install actually doing its job. **This is the run the §4 floor is still waiting on** | GPU |
| `setuptools` (§3.6) | nothing extra: the wheel build in `ci.yml` `install-smoke` and `canary.yml` `quickstart-install` IS the validation, which is why the exemption exists **[V]** | CI |

**Raising a FLOOR needs a run too, and this is the half that is easy to forget.** Every row
above is written for a cap, but a floor is the same kind of claim pointed the other way: it
says "this version works, older ones may not". The floors §3.2 lists as inert, and the three
majors §3.7 lists as crossed, would all be fixed by raising a floor — and none of those
raises should happen without the corresponding row's run. That is why this document records
them as open rather than quietly bumping the numbers.

**The rule that makes this more than a checklist:** a cap that is raised without its run is
indistinguishable from a cap that was never there. If the run cannot happen on hardware
this project has, the cap does not move — that is the same standing rule that governs
features (`ROADMAP.md:10`: "if a validation gate cannot run on hardware this project
actually has, the feature does not ship") **[V]**.

---

## 6. The supply-chain posture already shipped

Bounding versions is one surface. These are the others, and each mechanism below was
verified to exist at the named symbol before being written here.

### 6.1 The llama.cpp binary is SHA256-pinned and verified before extraction

quantfit downloads and **executes** a llama.cpp release binary, so this is load-bearing
security logic rather than hygiene.

- The release is pinned: `quantfit/backends/gguf.py:LLAMACPP_TAG = "b9817"` **[V]**.
- Each release asset has a pinned digest:
  `quantfit/backends/gguf.py:_BINARY_SHA256` — two entries, win-cpu-x64 and ubuntu-x64,
  with the comment recording that they were obtained by downloading and hashing the
  published asset **[V]**.
- **Verify before extract, always.** `gguf.py:_verify_or_die` hashes the archive
  (`gguf.py:_sha256`, streaming at 1 MiB) and raises on mismatch **after deleting the bad
  file** (`gguf.py:104-109`) **[V]**.
- **No pin means hard refusal**, not a warning: an asset absent from `_BINARY_SHA256` raises
  "refusing to extract/execute an unverified binary" (`gguf.py:98-102`) **[V]**, and
  `gguf.py:_download_verified` checks that *before spending the download* (`gguf.py:114-115`)
  **[V]**.
- **Download is atomic**: temp file → verify → `os.replace`, so the destination path exists
  only once the bytes are both complete and verified (`gguf.py:112-124`) **[V]**.
- **A cached archive is re-verified before extraction** — "existence != integrity"
  (`gguf.py:158-159`) **[V]**.
- Extraction uses `tarfile.extractall(..., filter="data")` where available
  (`gguf.py:137`) **[V]**, and a corrupt archive is deleted rather than left to be retried
  (`gguf.py:140-142`) **[V]**.

All of this is tested hermetically — no network, no binary execution — in
`tests/test_gguf_supply_chain.py`, whose nine tests cover the accept, mismatch-deletes,
unpinned-refusal, refuse-before-fetch, verify-before-promote, corrupt-archive and
re-verify-cached paths **[V]**.

**And the digest reaches the artifact.** `quantfit/safety/gguf_arm.py:228` records
`"binary_sha256": _sha256(server)` into the arm's engine block as "ground truth for the
same-binary mandate" **[V]**, which is what makes spec §4.2's same-binary requirement
checkable from a report alone, and what `reproduce.py:_T1_GGUF_ARM_FIELDS` compares across
a reproduction **[V]**.

**One thing this does not claim** (`reproduce.py:266` says it in the code) **[V]**:
identical `binary_sha256` does **not** imply identical kernels, because the released CPU
builds dispatch on CPU features at runtime. The pin establishes *which bytes ran*, not
*which code path they took*.

### 6.2 Model and data identity are pinned to exact revisions

- Judge: `quantfit/safety/verify.py:JUDGE_REVISION = "b34061f964619a5b6e0ff24be45a428124fa36bc"`
  **[V]**, passed as `revision=` on both the tokenizer and the model load
  (`verify.py:604-605`) **[V]**.
- Probes: `verify.py:PROBE_DATASET_REVISION = "c26cc2e15fcadab9c0ec24a5b57d37b140f7ed58"`
  **[V]**, passed as `revision=` to `load_dataset` (`verify.py:517`) **[V]**.
- Both revisions are written into every report (`verify.py:399,408`) **[V]**, so a report
  names the judge and probe set it actually used rather than the ones it hoped for.

The consequence a future calibration inherits: a judge-revision bump invalidates any
measured ε, because a calibration report is scoped to its own judge revision
(`safety/calibrate.py:60-63`) **[V]**. That is spec work, tracked in
`spec/qsr-v1-freeze-plan.md` §2.6, and is named here only so the pin's purpose is not
mistaken for tidiness.

### 6.3 Packaging metadata is exercised, not just written

`.github/workflows/ci.yml:43` installs the package itself (`pip install -e . --no-deps`) so
that the entry point and PEP 621/639 metadata are exercised rather than assumed **[V]**,
and the `install-smoke` job builds a wheel and installs it with **full** dependency
resolution on both ubuntu and windows (`ci.yml:48-86`) **[V]**. Real resolution failures
show up there, not in the mocked unit job.

---

## 7. The weekly canary, and what it is not

`.github/workflows/canary.yml` runs weekly (`cron: "17 6 * * 1"`, `canary.yml:47`) and on
`workflow_dispatch` **[V]** — the off-the-hour minute is deliberate, since top-of-hour
crons are the most likely to be delayed or dropped (`canary.yml:46`) **[V]**. It carries the
two halves the standing rule names:

1. **`determinism-canary`** (`canary.yml:78`) **[V]** — the same tiny model on both arms on
   CPU. Under greedy decoding this is zero-flip by construction; it proves the measurement
   harness is not *adding* spurious flips. It also asserts that a gate asked for a threshold
   finer than its own resolution exits **5** (`canary.yml:205`) **[V]**.
2. **`quickstart-install`** (`canary.yml:311`) **[V]** — builds the wheel and installs it
   into a clean venv with full dependency resolution (`canary.yml:333-348`) **[V]**, which
   is the job that would catch a dependency graph that stopped resolving. It deliberately
   does not cache pip: a cached wheel set defeats the point (`docs/ci-integration.md:628`)
   **[V]**.

**What the canary is not**, stated because it is the claim most likely to be over-read —
and `docs/ci-integration.md:631-633` says it directly **[V]**: it is **not** a noise floor,
it says nothing about judge accuracy, and a green canary does **not** stand in for the
sensitivity control. `screens/targets-0.5.json` still records
`sensitivity_control: {"status": "not_run"}` **[V]**.

---

## 8. What this policy does not cover

Named so the gaps are visible rather than implied by omission.

- **It is not a lockfile.** `ROADMAP.md:10` says "clean-venv quickstart install from the
  lockfile" **[V]**; this repo ships **no lockfile** **[V]**. `quickstart-install` installs
  from the built wheel and resolves live, which tests a *stronger* property (today's index
  still resolves) but a *different* one (it is not reproducible). **[?]** Whether to add a
  lockfile for the reference-report path is an open decision; a reproduction claim that
  depends on resolution drift is weaker than one that does not.
- **It says nothing about the spec.** QSR v1 is not frozen and cannot be frozen here;
  `spec/qsr-v1-freeze-plan.md` is the blocking ledger **[V]**.
- **It says nothing about hardware validation.** "Every advertised command
  hardware-validated" is a claim about *runs*. Several commands have never been run on real
  hardware, no cross-hardware T4 reproduction exists, and the 0.5 screen has not run
  (`docs/cross-hardware-tolerance-v0.md:3-5`; `CHANGELOG.md:14` and `CHANGELOG.md:50`, both
  of which say "the 0.5 screen has not run" in as many words) **[V]**. Nothing in this
  document should be read as evidence for any of them. `docs/validation-matrix.md` is the
  per-command ledger of what has and has not run.
- **It does not audit transitive dependencies.** The caps here are on direct requirements.
  A transitive package with a compromised release is not addressed by any mechanism in §6
  except the llama.cpp binary pin, which is not a Python package at all. **[?]** Hash-pinned
  installs (`pip install --require-hashes`) would address this and are not shipped.
- **No third-party reproduction, citation or gate adoption exists**, so ROADMAP 1.0's own
  gate is not met and this document does not claim otherwise.

---

## 9. Changing a cap, or adding an exemption

**To move a cap:** run the validation named in §5 for that dependency, then change
`pyproject.toml` — and, if the dependency is restated in a workflow, change that in the
same commit. `test_requirements_re_declared_in_workflows_match_pyproject` fails if they
diverge. Record the run in `CHANGELOG.md`; a cap whose move is not recorded is a cap that
was raised because it was annoying.

**To add an exemption:** add an entry to `tests/test_dependencies.py:_EXEMPTIONS` with a
class from `_KINDS` and a reason that states the actual argument. The reason is
length-checked (`test_every_exemption_states_a_kind_and_a_substantive_reason`) because a
one-line reason is how "we will fix it later" gets laundered into policy.

**If the reason makes a parent-bound claim, name the chain — even if the class is not
`PARENT_BOUNDED`.** The chain is required for `PARENT_BOUNDED` and permitted for
`BUILD_SELECTED`, which is the pair of classes whose arguments can contain such a claim
(`_CHAIN_BEARING_KINDS`); the other four may not name one, because they make no claim about
a parent for the tests to check. Both premise tests then verify the root is a dependency
quantfit itself caps and re-read every link from installed metadata where it is available.
The rule behind that rule: **if it is written in a reason, it is checked**. `torch`'s entry
is why — it argued a parent bound in prose that nothing verified, inside a class the checks
skipped.

**Exemptions expire on their own.** If a dependency later gains a cap, its exemption
becomes a dead entry and `test_exemption_table_has_no_dead_entries` fails until it is
deleted. The table cannot silently accumulate.
