# Contributing to quantfit

quantfit is a measuring instrument. Almost every rule below exists because a change
to an instrument can silently change what it measures, and a wrong measurement that
still looks auditable is worse than no measurement. Read the rule *and* the reason —
the reason is what tells you whether your change is the exception.

Before anything else, two facts about the project you are contributing to:

- **It is single-maintainer.** There is no review rota, no on-call, and **no review
  SLA** — none is claimed anywhere in this repo and none should be inferred. What
  breaks if the maintainer stops, and what a third party can do about it, is written
  down honestly in [`docs/bus-factor.md`](docs/bus-factor.md).
- **There is no code of conduct file in this repository.** That is a statement of
  fact, not of policy. Do not cite one that does not exist.

Security-relevant reports go through [`SECURITY.md`](SECURITY.md), not a PR.

---

## 1. Dev setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      POSIX: source .venv/bin/activate
pip install -e ".[dev,gguf,inspect]"
```

The extras are declared in `pyproject.toml` under `[project.optional-dependencies]`:

| extra | what it is for |
|---|---|
| `dev` | `pytest`, `ruff>=0.16,<0.17`, `scipy` (the independent reference for the Wilson-CI / power cross-checks), `gguf` |
| `gguf` | GGUF metadata reading — the `verify-safety` GGUF arms resolve `file_type`/`architecture` from the file itself, never the filename |
| `inspect` | `inspect-ai>=0.3.252,<0.4`, for `quantfit/inspect_task.py` and its parity test |
| `awq` | `gptqmodel>=7.1,<8`, needed only to *screen* first-party AWQ checkpoints (`transformers`' `AwqQuantizer` refuses to load autoawq artifacts without it) |

One honest note about the install line above: **`dev` already pulls `gguf`**
(`pyproject.toml:42`), so `[dev,gguf,inspect]` names it twice. That is deliberate —
`gguf` is the extra a non-dev consumer needs, and spelling it out keeps the dev line
and the user line saying the same thing. It costs nothing; pip resolves it once.

`torch` is a hard dependency of the package (`pyproject.toml:26`), so the editable
install above is *not* light. CI's **test** job deliberately does not do this (its
`install-smoke` job deliberately does) — see §2.

---

## 2. Running the suite

```bash
python -X utf8 -m pytest tests/ -q
```

**`-X utf8` is not optional on Windows.** The default console and locale encoding on
a Windows box is `cp1252` (`locale.getpreferredencoding(False)` → `cp1252`;
`sys.stdout.encoding` → `cp1252`), and the tree contains characters `cp1252` cannot
encode — `ε` appears eight times in `quantfit/safety/calibrate.py` and once in
`tests/test_calibrate.py`. Any surface that renders that source or that output to the
default stream — a failing test's source echo, a traceback, a captured stdout dump —
raises `UnicodeEncodeError` and the *reporter* dies rather than the test. You get a
crash that looks nothing like the failure that caused it. `-X utf8` removes the whole
class of failure and costs nothing anywhere else.

CI's `test` job runs the bare `pytest tests/ -q` (`.github/workflows/ci.yml`, job
`test`) because Linux runners are already UTF-8. Do not "fix" the workflow to match
this doc, and do not drop `-X utf8` from your local loop because CI does not need it.

### The hermetic-test rule

**No network. No model loads. No `torch` at module scope.**

Not style — a load-bearing property of **the `test` job specifically**. In
`.github/workflows/ci.yml`, job `test` installs only
`pytest huggingface_hub psutil scipy gguf inspect-ai` (under the caps
`tools/ci_constraints.py` derives from `pyproject.toml`, so CI cannot green-light a
combination the package forbids), then `pip install -e . --no-deps`. **`torch` is never
installed in the test job**, and neither is `transformers`, `datasets` or
`llmcompressor`. That is what keeps it to a light container across the whole 3.10–3.14
matrix instead of pulling multi-GB CUDA wheels five times. A test that imports `torch`
at module scope, or reaches the Hub, or loads weights, does not fail cleanly — it takes
the matrix with it.

**Scope that to the test job, because the same workflow installs torch elsewhere on
purpose.** The `install-smoke` job builds the wheel and runs `pip install dist/*.whl`
(step *Install wheel with full dependencies*) — real dependency resolution, no
`--no-deps`, on `ubuntu-latest` **and** `windows-latest`. That pulls the full runtime
set, `torch` included. It is not an oversight; it is the job's entire purpose — the 0.3
release gate that a clean-venv install of the built wheel works and the CLI runs on both
platforms, which a `--no-deps` install would not test. The workflow says so in its own
comment on that job's setup step: `cache: pip  # the torch wheel dominates install
time; cache it across runs`.

So the accurate rule is: **hermetic tests, non-hermetic install proof, in deliberately
separate jobs.** Write your tests for the first one.

(Jobs and steps are cited here **by name**, not by line. `ci.yml` is edited often
enough that a line number in this file was already stale once.)

Verified state of the tree, so you know what "no torch at module scope" means in
practice: importing every file in `tests/` one at a time leaves `torch` out of
`sys.modules` for **every module except `tests/test_probe.py`**, which is the single
sanctioned exception and gates itself:

```python
# tests/test_probe.py:8
torch = pytest.importorskip("torch")
```

That is the pattern to copy if you genuinely need torch: `importorskip` at module
scope so the module *skips* where torch is absent, with a docstring saying why. An
unconditional `import torch` is a bug. `transformers` and `datasets` stay out of
collection entirely.

The same rule covers the heavy modules under test: `quantfit/__init__.py` re-exports
every heavy surface lazily via PEP 562 `__getattr__` (`quantfit/__init__.py:10-38`),
so `import quantfit` drags neither torch nor transformers nor `huggingface_hub`.
Keep it that way — a new eager top-level import in `__init__.py` breaks CI for
reasons that will not look like your change.

### Lint and format

```bash
ruff check quantfit tests tools
ruff format --check quantfit tests
```

Verbatim the two commands CI runs — steps *Ruff check* and *Ruff format* in the `lint`
job of `.github/workflows/ci.yml`. **Note the asymmetry, it is not a typo**: `check`
covers `tools/` (where `tools/quickstart_check.py` and `tools/ci_constraints.py` live),
`format --check` does not. If you add a file under `tools/`, the lint job will lint it.

`ruff` is pinned `>=0.16,<0.17` in **`pyproject.toml:42`, and only there** — the reason
is that 0.16.0 shipped new default rules mid-cycle and broke a green branch. The `lint`
job no longer restates that cap: it runs `tools/ci_constraints.py` to derive the bounds
from `pyproject.toml` and installs `ruff` under them, so a hand-copied second copy
cannot drift out of sync. **Bump the cap in `pyproject.toml` and CI follows; there is no
workflow-side number to keep in step.**

`line-length = 120`, `target-version = "py310"` (`pyproject.toml:75-77`). Run
`ruff format` (without `--check`) to apply; do not hand-reflow to dodge it.

**Two ways a clean local lint still goes red in CI**, both of which have happened:

- **The cap is a range, so CI may run a newer ruff than you.** A green branch failed on
  0.16.2 while the maintainer's box was on 0.16.0. Before pushing a lint-sensitive
  change, `pip install --upgrade "ruff>=0.16,<0.17"` so you are running what CI resolves.
- **`EXE001` cannot fire on Windows.** "Shebang is present but file is not executable"
  is a check on the file mode, and Windows has none to check — so a new script under
  `tools/` passes locally and fails on the Linux `lint` job. If you add one with a
  `#!/usr/bin/env python3` line, make the shebang true in the index:
  `git update-index --chmod=+x tools/your_script.py`.

---

## 3. The exit-code contract a change must not break

The CLI's exit codes are the CI contract other people's release pipelines are wired
to. They are normative in the spec — **QSR v0 §5.7, "The CI contract (exit codes)"**
(`verify-safety` and `screen`) and **§5.8, "The gate adds exit 5 — 'I cannot resolve
what you asked'"** (the gate) — and pinned by `tests/test_cli.py`
(`test_verify_safety_exit_codes_are_the_ci_contract`,
`test_screen_exit_codes_mirror_the_verify_safety_contract`,
`test_gate_exit_codes_are_relayed_verbatim`, `test_check_exit_codes`,
`test_emit_refuses_wrong_schema_report_with_exit_2`).

`verify-safety` / `screen` (§5.7):

| exit | meaning |
|---|---|
| 0 | measured on both axes, no flip observed — a *bounded* no-detection result |
| 3 | at least one flip observed on either axis |
| 4 | an axis had zero at-risk pairs — nothing was measured; **not a pass** |
| 2 | operational error |

`gate` adds one (§5.8):

| exit | meaning |
|---|---|
| 5 | UNRESOLVABLE — the declared threshold is finer than the printed MDE |

Precedence is **3 > 4 > 5 > 0**, and it is deliberate: an H0 rejection is valid
regardless of power, so an underpowered run never suppresses a flip it did observe.

(Cite those two sections by **title as well as number**. The spec has been renumbered
once already, and a bare "§5.8" is a citation that can silently come to mean a
different section without anything in this file changing.)

**The gate does not simply extend §5.7 — it diverges from it in two ways, and §5.8
says an implementation MUST state them rather than let a reader assume.** Both are
real in the code; neither is inferable from the table above.

1. **Exit 4 is narrowed to the *gated* axis.** Under §5.7, *either* axis having zero
   at-risk pairs exits 4. At the gate only the gated one does — `GATED_AXIS` is
   `"refusal-robustness"` (`quantfit/gate.py:GATED_AXIS`), because the declared
   threshold is a dangerous-axis threshold and an unmeasurable over-refusal axis does
   not invalidate a dangerous-axis verdict. The unmeasurable axis is still carried in
   the artifact and named in the headline. **A consumer must not assume the two
   commands' 4 means the same thing.**
2. **Exit 0 does NOT mean the underlying run detected nothing.** The gate's 3 is
   threshold-relative on *one* axis, so a run whose two-axis protocol verdict (§5.6,
   `verify.SafetyDrift._verdict`) is `REGRESSION DETECTED` on the **ungated**
   over-refusal axis (`quantfit/gate.py:UNGATED_AXIS`) still exits 0. That is not a
   bug and it is not a laundered failure — the gate answers a narrower question than
   the protocol does. It is why a 0 never travels alone: the decision carries
   `underlying_run_verdict` (the protocol's verdict verbatim, unedited),
   `ungated_axis_regressed`, `gated_axis_flips_below_detection_threshold` and
   `verdict_reconciliation`, and `quantfit/gate.py:_headline` puts the regression in
   the printed sentence. **A change that lets an exit 0 be printed without those
   fields, or without the headline sentence, breaks the spec** — a reader must never
   see "PASS" and miss that the underlying run detected a regression somewhere.

Three things a change must not do:

1. **Never map 4 or 5 to 0.** They mean *no answer*, not *pass*. The reference
   Action refuses to offer a `soft-fail` input for exactly this reason
   (`.github/actions/quantfit-gate/action.yml`).
2. **Never let an operational failure eat a verdict.** Code 2 is
   `cli.main`'s handler (`quantfit/cli.py:main`, `cli.py:420-426`), which catches
   `(RuntimeError, OSError)` and prints one clean line. **Every** quantfit operational
   error is a `RuntimeError` subclass — the rule is the invariant, not the roster, so
   this list is deliberately not counted and a new module extends it:
   `gate.py:GateError`, `screen.py:ScreenError`, `safety/report.py:ReportError`,
   `safety/calibrate.py:CalibrationError`, `safety/cache.py:CacheError`,
   `safety/mde.py:MdeError`, `inspect_task.py:InspectTaskError`,
   `refreports.py:RefReportError`, `reproduce.py:ReproduceError`,
   `audit.py:AuditError`, `quantize.py:CannotQuantize` — that last one is a
   `RuntimeError` whose name does not end in `Error`, which is precisely how a grep for
   `*Error(RuntimeError)` misses it and reports a roster one short. The single class that
   sits outside the base is `registry.py:UnsupportedCombo`, a **`ValueError`**: an
   unsupported method × scheme pair is caught alongside `CannotQuantize` by the
   `quantize` branch's own handler (`cli.py:404-406`) and returns the same exit 2, so the
   *contract* holds where the base class does not. Raise one of those
   (or a plain `RuntimeError`) for anything an operator can fix, and let programming
   errors surface raw rather than laundering them into an operational code — note
   that `ValueError` from anywhere in the torch/transformers stack is deliberately
   *not* caught (`cli.py:421-424`). `verify.py:verify_safety` carries the scar of getting this
   wrong: an `OSError` from the opt-in capture used to escape *after* the report was
   written, so a run that had **detected a regression** exited 2 with the verdict
   never printed. It now warns and returns the drift (`quantfit/safety/verify.py:355-376`).
3. **Never add a code without adding it to the spec and to `tests/test_cli.py`.**
   An undocumented exit code is an unannounced break of somebody's release gate.

---

## 4. Pinning discipline

Two kinds of pin, both deliberate, neither bumped as a drive-by.

**Revision pins on the measuring instruments.** The judge and the probe corpus are
loaded at exact revisions, recorded in every report:

```python
# quantfit/safety/verify.py:86-89
JUDGE_MODEL_ID          = "Crusadersk/quantsafe-refusal-modernbert"
JUDGE_REVISION          = "b34061f964619a5b6e0ff24be45a428124fa36bc"
PROBE_DATASET_ID        = "Crusadersk/quantsafe-judge-benchmark"
PROBE_DATASET_REVISION  = "c26cc2e15fcadab9c0ec24a5b57d37b140f7ed58"
```

Bumping either changes what the number *means*, retroactively, for every report ever
published against it. The module says it in one line — *"bump the pins deliberately,
never implicitly"* — and `spec/qsr-v0.md` Appendix A carries the same constants as
normative rows. A pin bump is its own PR, with the reason, and it is a spec-version
question, not a dependency-hygiene question.

**SHA256 pins on executed binaries.** `quantfit/backends/gguf.py` downloads and
**executes** a prebuilt `llama-quantize` / `llama-server`. Every fetched asset is
verified against `_BINARY_SHA256` (`backends/gguf.py:52-55`) *before* extraction
(`_verify_or_die`, `_download_verified`), the clone is checked to sit at
`LLAMACPP_COMMIT` because tags are mutable (`convert_script`, `backends/gguf.py:205-209`),
and an asset with **no pin is a hard refusal**, not a warning. If you add a platform,
you add its hash — obtained by downloading the published asset and hashing it — or
the platform does not ship. `tests/test_gguf_supply_chain.py` pins this behavior
hermetically (no network, no execution).

**Upper bounds on churning dependencies.** `llmcompressor>=0.5,<0.13`, `ruff>=0.16,<0.17`,
`gguf>=0.10,<1.0`, `inspect-ai>=0.3.252,<0.4`, `gptqmodel>=7.1,<8`. The standing ROADMAP
rule, repeated in the `pyproject.toml` comments: **the cap moves only after a validated
run on the new minor**, not because the resolver complained. `gptqmodel`'s cap is the
weakest-evidenced of the five and its comment says so — the loader path it backs is
exercised by no hermetic test, so moving it needs a real AWQ load, not a green suite.

---

## 5. Data handling — anything that touches completions

If your change touches generated text, read
[`docs/data-handling-completions.md`](docs/data-handling-completions.md) first. It is
not guidance; it *is* the recorded decision that makes the capture path legitimate at
all, and ROADMAP's non-goals bar the silent version of it.

The invariants a PR must not quietly move:

- **Reports carry no completion text.** Schema-v2 `DriftReport` has no completion
  field; `SafetyDrift.summary()` is aggregates-only; `calibrate.ingest_labels` writes
  counts, rates and intervals. Adding a text field to any of them is a schema bump
  **and** a supersession of that document — two gates, not one (§5.4).
- **Capture is opt-in, off by default, and cannot change a run.** It is written after
  the drift and after the report, from values the run already computed
  (`quantfit/safety/verify.py:427-481`, *"Nothing above this call sees `path`"*). A
  data-handling choice must never become a measurement variable.
- **Every capture file carries its warning in the file**, not only in the docs
  (`verify.CAPTURE_WARNING`, `verify.py:110`), so a file copied away from the command
  that produced it still states what it holds.
- **The filename convention is a mandate, because no code supplies a default**:
  `<name>.capture.jsonl`, `<name>.labels.csv`, `<name>.labelkey.json`. `.gitignore`
  backstops those three plus `*.baseline-cache.json` and `logs/` / `*.eval` — the
  baseline cache and Inspect eval logs hold completion text the same way a capture
  does — `quantfit/safety/cache.py:COMPLETION_TEXT_WARNING` is the constant, and it is
  written verbatim into every entry header (cited by symbol, not by line, because line
  citations in this repo have rotted before). The
  patterns are a backstop against `git add -A`, **not a boundary**: `git add -f`
  defeats them and a file written outside the convention is unignored.
- **Retention is short and terminal** (§3 of that document). Delete the capture and
  the sheet once every artifact they exist to feed has been produced — and take the
  text-stripped `id,human_label` extract first, because human labels are the one
  thing a re-run does not regenerate.

Never commit a capture, a labeling sheet, a baseline cache or an Inspect eval log,
and never attach one to an issue or a PR.

---

## 6. Merging, versioning, changelog

**Squash merge is the intended convention — and the history has an exception in it.
Both halves are stated because the second is the part a contributor would otherwise
discover by contradiction.**

*Intended:* a merged milestone lands as **one** commit whose title ends in the PR
number, and branch WIP commits do not survive the merge. That is what the history
shows through PR #6 — `feat: routing layer (0.2) … (#1)`, `fix(audit): … (#2)`,
`feat(0.3): … (#3)`, `0.4a — drift report schema v1, revision pins,
scipy-cross-checked stats (#4)`, `0.4b — … (#5)`, `0.5 — QSR spec v0, screen harness,
model-card emit, verified target list (#6)` — six consecutive single-parent commits,
the shape GitHub's squash button produces.

*The exception, on the record:* **the last two merges into `main` are two-parent merge
commits, not squashes.** PR #8 landed as `Merge pull request #8 from
Sahil170595/release/0.6` (parents: the `0.5` squash and the branch tip
`feat(0.6-prep): judge-calibration machinery with GO-gated activation`), and PR #10
landed as `Merge pull request #10 from Sahil170595/fix/calibrate-shuffle-flake`
(parents: the #8 merge and `fix(tests): de-flake the calibration shuffle test, assert
the mechanism instead`). That merge is the current tip of `origin/main`. GitHub's
"Create a merge commit" button was used instead of "Squash and merge".

Two consequences worth knowing before you write a PR:

- **Branch commits from #8 and #10 are reachable from `main`.** "Branch work stays as
  unsquashed WIP until it merges" is the *goal*, not a description of this history —
  those commits are permanently in it. Do not assume `main` is a linear sequence of
  milestone commits; it is not, and a script that assumes one commit per PR will
  miscount.
- **Tag `v0.5.1` points at the #8 merge commit**, so a release tag here does not
  necessarily dereference to a squashed milestone commit.

Prefer squash for the next one. If you use a merge commit anyway, that is a choice to
make deliberately and say in the PR — not a default to fall into because the button is
first.

**Versions do not track ROADMAP milestone numbers**, and `CHANGELOG.md` opens by
saying why: 0.5.1 shipped 0.6's machinery, 0.5.2 shipped 0.7's. A milestone number in
a version would claim a milestone completion that is gated on runs and decisions that
have not happened. `0.10` is reserved for the frozen standard.

**Version parity is tested, not trusted.** `pyproject.toml` `version`,
`quantfit/__init__.py` `__version__` and `CITATION.cff` `version` must agree —
`tests/test_meta.py:test_version_matches_pyproject` pins the first two to each other,
and `tests/test_refreports.py` pins `CITATION.cff`'s `version` to the shipped version
(parsing the CFF with its own `_parse_cff` so the check survives PyYAML being absent).
0.1.0 shipped to PyPI with a skew nothing caught; that is why the tests exist.

---

## 7. What a PR must state

**A PR here must say what it does *not* deliver.** This repo treats honest scope as a
deliverable, and the convention is already in the changelog — every release entry ends
with a paragraph like `CHANGELOG.md:48`:

> **Not delivered, so 0.8 is not claimed gate-passed:** QSR v1 is not frozen, zero
> reference reports exist, the free-tier T4 reproduction has not been attempted,
> there is no launch post […], and none of the three new modules is reachable from
> the CLI.

Write yours in the same register. Concretely, a PR description should carry:

1. **What landed**, in terms of the mechanism, not the intent.
2. **What did NOT land** — every gate this change does not pass, every run that has
   not happened, every command it adds that has never executed on real hardware. If
   the change ships machinery for a milestone whose gate is unmet, say the gate is
   unmet in the same breath.
3. **Which claims are verified and how.** Distinguish *verified from `<file>:<line>`*,
   *inferred from evidence*, and *not checked*. A `[V]`-style marker on a claim you
   did not actually check is the failure mode this project is built to avoid.
4. **Any pin you moved**, with the evidence that justified moving it.
5. **Whether the exit-code contract changed**, and where the spec and
   `tests/test_cli.py` were updated to match.

Things you must not write: a validation claim about hardware you did not run on, a
number without the command that produced it, or a "should work" that has not been
executed. "Not run — needs a T4" is always an acceptable line and is preferred over a
plausible-sounding guess.
