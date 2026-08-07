# Dependency policy — what is bounded, what is not, and who is allowed to move a cap

**Status: policy, and enforced.** Every rule in this document is checked by
`tests/test_dependencies.py`. Where the two disagree, the test is the one that runs and
this file is the bug. One rule below is **not satisfied by the repo as it stands** and is
marked as an open defect in §4 rather than described as if it were met.

**Scope.** This document covers ROADMAP 1.0's "dependencies bounded" clause and the
supply-chain surface that sits next to it. It makes no claim about the QSR spec, which is
**not frozen** — `spec/qsr-v1-freeze-plan.md` is the blocking ledger for that and nothing
here changes it. It also makes no claim that any command has been hardware-validated; §7
states what this policy does *not* cover so the gap is visible rather than implied.

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

> **Every declared requirement — hard or optional — carries an upper bound, OR appears in
> a named exemption table with a stated reason and a class. There is no third state.**

An unbounded, unexempted requirement is a test failure. Not a warning, not a TODO. The
exemption table lives in `tests/test_dependencies.py:_EXEMPTIONS` so that the
justification and the enforcement cannot drift apart into two files.

**A cap is a claim about a validated run, not a guess.** The second half of the standing
rule — "the cap moves only after a validated run on the new minor" — is what makes a cap
mean something. §5 states what that run is, concretely, per dependency class.

---

## 2. What is bounded today

Read from `pyproject.toml` **[V]**:

| requirement | group | cap | why this one churns |
|---|---|---|---|
| `llmcompressor>=0.5,<0.13` | hard | `<0.13` | the modifier/oneshot API churns across minors; `backends/compressed_tensors.py` imports `AWQModifier`, `GPTQModifier`, `QuantizationModifier`, `SmoothQuantModifier` and `oneshot` by path **[V]** |
| `inspect-ai>=0.3.252,<0.4` | `inspect` | `<0.4` | `quantfit/inspect_task.py` depends on `inspect_ai` internals (`SampleScore`/`Score`/`Value`, `inspect_ai.score`, the epoch-reduction behaviour of `Score.value`) and is verified against 0.3.252 **[V]** |
| `gguf>=0.10,<1.0` | `gguf`, `dev` | `<1.0` | pre-1.0 and tracks llama.cpp; the enums quantfit reads are append-only in practice, so `<1.0` is the honest cap **[V]** |
| `ruff>=0.16,<0.17` | `dev` | `<0.17` | 0.16.0 shipped new default rules mid-cycle and broke a green branch **[V]** |

Two of these caps are restated in CI — `.github/workflows/ci.yml:82` installs
`"ruff>=0.16,<0.17"` by hand **[V]** — and
`test_requirements_re_declared_in_workflows_match_pyproject` asserts every such restatement
still matches `pyproject.toml`, in both `ci.yml` and `canary.yml`. A workflow that installs
a version the package does not declare is a canary validating something no user gets.

---

## 3. What is deliberately unbounded, and why

Nine declared requirements carry no upper bound **[V]**. Eight are exempt below; the ninth
is §4's open defect.

Each exemption carries a **class**, and each class is falsifiable in a different way. The
tests do not take the reasons on trust — they check the premise each reason rests on.

### 3.1 `BUILD_SELECTED` — a cap would fight the user's build

**`torch>=2.4`.** torch wheels are selected by *index* as much as by version: the canary
installs from `https://download.pytorch.org/whl/cpu` (`.github/workflows/canary.yml:107`)
**[V]**, and a user with a CUDA or ROCm box installs the wheel matching their driver. An
upper cap in quantfit's own metadata can refuse that wheel, or silently resolve a user
down onto a build their hardware does not want — a worse and much harder-to-diagnose
failure than the API break the cap would have prevented.

The surface quantfit actually uses is narrow and long-stable: `.to(device)`, dtype
introspection, and `torch.cuda` queries **[V]**. And the upper end is not in fact open on a
default install — see §3.2.

This is the one dependency where the literal reading of `ROADMAP.md:10` is wrong, and it is
stated here rather than quietly ignored.

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

- `.github/workflows/ci.yml:30-33` installs `pytest huggingface_hub psutil scipy gguf
  inspect-ai` and then `pip install -e . --no-deps` **[V]** — llmcompressor is never
  resolved, so nothing bounds transformers or huggingface_hub in that job.
- `.github/workflows/canary.yml:112-113` does the same for the determinism canary,
  installing `"transformers>=4.56" "huggingface_hub>=0.25" "datasets>=3.0" "psutil>=5.9"`
  by hand **[V]**.

Both are deliberate (they exist to stay light), and both mean the PARENT_BOUNDED protection
does **not** apply there. The canary's `quickstart-install` job is the one that resolves the
real dependency graph (`canary.yml:311-348`, wheel built then installed into a clean venv)
**[V]**, and that is the job where a broken resolution would actually surface. **[?]**
Whether the unit-test job should also run one leg with full dependencies is a maintainer
decision, not a measurement.

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

---

## 4. The open defect: `gptqmodel` is unbounded and unexempt

**`gptqmodel>=1.0`** in the `awq` extra has no upper bound and no defensible exemption
**[V]**. `tests/test_dependencies.py::test_every_optional_dependency_is_bounded_or_exempt`
**fails on the repo as it stands**, and it is written to fail rather than to record the gap
as a comment.

Why it does not qualify for any class in §3:

- Not `PARENT_BOUNDED`: nothing quantfit declares constrains it. `llmcompressor==0.12.0`
  does not require `gptqmodel` at all **[V]**.
- Not `BUILD_SELECTED`: it is an ordinary PyPI wheel, not an index-selected accelerator build.
- Not dev-only: `quantfit[awq]` is a user-facing extra, documented in
  `docs/reference-reports-v0.md:140` as the install a first-party AWQ artifact needs **[V]**.
- The role it plays is the exact shape that got `inspect-ai` capped: it exists to satisfy
  **transformers' `AwqQuantizer` internals**, which refuses to load autoawq checkpoints
  without it (`pyproject.toml:47-49`) **[V]**. A dependency held for another library's
  internals is the least stable kind there is. **[I]**

**The floor is also not backed by anything.** The resolvable version in a full-dependency
environment is `gptqmodel==7.1.0` **[V]** — six major versions above the declared `>=1.0`
floor, and no quantfit run has ever validated 1.x. Stale build metadata in this tree
(`quantfit.egg-info/requires.txt`, `PKG-INFO` `Version: 0.2.0`) records `gptqmodel>=2.0`
as a *hard* dependency **[V]**, so the declared floor has moved **down** at some point
without a run justifying either value. (That file is build output, not tracked source; it
is cited only as evidence about the floor's history.)

**What has to change, and who owns it.** `pyproject.toml` is orchestrator-owned. The
minimal change that satisfies the policy, verified to turn the suite green:

```toml
awq = ["gptqmodel>=1.0,<8"]
```

The stronger option — `gptqmodel>=7.1,<8` — is **not** recommended without a run, because
raising the floor is itself a claim that 7.1 works, and no AWQ screening run has happened
(the hardware for it is the same hardware ROADMAP 0.5's screen still needs). Capping at
`<8` claims only that 8.x is unvalidated, which is true. **[?]** The floor stays a known
unsubstantiated value either way, and that is the honest state to leave it in.

---

## 5. What "a validated run on the new minor" means

A cap moves when someone has *run* something, not when a bot opens a PR. Concretely, per
class:

| dependency | what must run before the cap moves | who can run it |
|---|---|---|
| `llmcompressor` | one `quantfit quantize` on the compressed-tensors path (AWQ or GPTQ) that completes and produces a loadable artifact, **plus** a `verify-safety` pair over that artifact whose report validates against the schema | anyone with a GPU that fits a ~1.5B pair |
| `gguf` | the GGUF arm tests, which craft and read real GGUF files (`tests/test_gguf_arm.py`), **plus** one real quantize+verify pair, since the enums are read from file metadata and never from filenames (spec §3.2) **[V]** | CPU-only is sufficient |
| `inspect-ai` | `tests/test_inspect_task.py:test_inspect_run_reproduces_tabulate` green on the new minor — the runner depends on `inspect_ai` internals, so that parity against `verify._tabulate` is the whole claim (`pyproject.toml:50-56`) **[V]** | CPU-only; CI installs it for exactly this reason |
| `ruff` | `ruff check quantfit tests` and `ruff format --check quantfit tests` green on the new minor, locally, before the cap moves in both `pyproject.toml` and `.github/workflows/ci.yml:82` — the two must move together, which `test_requirements_re_declared_in_workflows_match_pyproject` enforces **[V]** | anyone |
| `gptqmodel` (once capped) | one load of a first-party AWQ checkpoint through the transformers path, i.e. the `quantfit[awq]` install actually doing its job | GPU |

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

`.github/workflows/ci.yml:33` installs the package itself (`pip install -e . --no-deps`) so
that the entry point and PEP 621/639 metadata are exercised rather than assumed **[V]**,
and the `install-smoke` job builds a wheel and installs it with **full** dependency
resolution on both ubuntu and windows (`ci.yml:38-67`) **[V]**. Real resolution failures
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
  (`docs/cross-hardware-tolerance-v0.md:3-5`, `CHANGELOG.md:69-71`) **[V]**. Nothing in this
  document should be read as evidence for any of them.
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
one-line reason is how "we will fix it later" gets laundered into policy. If the class is
`PARENT_BOUNDED`, name the full resolution chain — the tests verify the root is a
dependency quantfit itself caps, and re-read every link from installed metadata where it is
available.

**Exemptions expire on their own.** If a dependency later gains a cap, its exemption
becomes a dead entry and `test_exemption_table_has_no_dead_entries` fails until it is
deleted. The table cannot silently accumulate.
