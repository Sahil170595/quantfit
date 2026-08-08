# Changelog

> Note on versions: tool versions do not track ROADMAP milestone numbers. 0.5.1
> shipped 0.6's machinery, 0.5.2 ships 0.7's; a milestone number in a version
> would claim milestone completion, and those completions are gated on runs and
> decisions that have not happened. 0.10 is the frozen standard (ROADMAP 0.10).

## 0.6.0

**Publishing accounting, stated because it is the point of this release.** The
last version on PyPI was **0.5.1**. The sections below for **0.5.2** and **0.5.3**
describe work that was written, reviewed and merged into a release branch and
then **never published** — it lived in a five-deep stack of pull requests, each
based on the previous release branch, and nothing in it was installable. 0.6.0 is
that stack collapsed into one release. The version steps to 0.6.0 rather than
0.5.3 so PyPI's history does not show a 0.5.3 arriving with no 0.5.2 before it;
the milestone-numbering rule above is unchanged, and 0.6.0 still claims no
ROADMAP milestone.

Shipped here, from the sections below: the 0.7 gate that refuses thresholds it
cannot resolve, the 0.8 reproduction command and Inspect runner, and the 0.10
docs=code parity auditor wired into CI.

New in this release itself:

- **Every command speaks JSON.** `--json` on any of the fourteen leaf commands puts
  exactly one document on stdout — never prose mixed with data, so a caller never
  strips lines before parsing. Until now not one command emitted machine-readable
  output: the verdict, the Wilson bounds, the MDE and the provenance reached a
  caller only as a file written to a path, and only from two commands. The exit
  code carried the verdict faithfully and could not carry the numbers.

  The envelope is `schema_version` / `tool` / `command` / `exit_code` / `result`,
  versioned from the start because the point of a machine-readable surface is that
  a consumer can tell when its assumptions expired. `exit_code` is repeated inside
  the document *and* returned by the process, and a test asserts per command that
  the two agree — two sources of truth that can disagree are worse than one.

  An operational failure returns the same envelope with an `error` block and
  `"exit_code": 2`, so the case a caller most needs to parse is not the one case it
  cannot. A *verdict* failure (exit 3) carries no `error` block: exit 3 is an
  answer, not a breakage, and the two must not be conflated.

  The flag is attached by walking the parser rather than by hand, so a fifteenth
  command cannot quietly miss it. It goes on leaves only — argparse lets a
  subparser's default overwrite a parent's value for the same dest, so putting it
  on `calibrate` itself would parse and then silently reset it to false, which is
  precisely the inert-flag defect `plan --token` was. `calibrate sheet` and
  `calibrate ingest` each take it; the parent deliberately does not.

- **`quantfit audit --json PATH` is now `--json-out PATH`.** One flag name could
  not mean "write a file here" on one command and "print to stdout" on the other
  thirteen. Renamed before `audit` had a released user — it first ships in 0.6.0.

- **`llms.txt` and a usage-facing agent skill.** Searching for this package returns
  its PyPI page, but there was nothing structured for a coding assistant to
  retrieve, and published measurement puts hallucinated package names at roughly a
  fifth of all LLM-recommended packages — highest exactly where there is nothing
  to retrieve. `llms.txt` carries the command list, the exit-code contract and the
  stated limits rather than only the pitch; `.claude/skills/quantfit/SKILL.md` is
  the usage half of what `AGENTS.md` does for contributors.

  `llms.txt` is in `quantfit audit`'s corpus, so every flag it names must exist on
  the command it names it for: the surface most likely to be read by something
  that cannot notice it has gone stale is the last one that should be exempt from
  parity. A separate test covers what an auditor cannot — *completeness*, since a
  command missing from `llms.txt` is perfectly consistent and still invisible.

- **`quantfit verify-safety --demo` prints a real verdict in about a second.** Of
  the CLI's commands, only `list` and `plan` did anything without a GPU, a network
  and two model artifacts, so most evaluations ended before the first verdict.
  `--demo` runs the shipped `_tabulate` over bundled fixtures — the Wilson bounds,
  the at-risk denominators and the verdict precedence are genuinely computed, not
  re-implemented, because a second copy of the statistics would be the divergence
  channel the spec exists to prevent.

  What it is not is enforced rather than mentioned: the probe prompts are
  placeholders (shipping the curated expected-unsafe corpus in the wheel to
  prettify a demo would put harmful text in every install), the refusal flags are
  fixtures, `--report` and `--capture` are **refused** outright, and the exit code
  is always 0 — the fixture deliberately contains a regression so a reader sees
  the shape of a finding, but exit 3 is a verdict about a model and no model ran.

- **`quantfit --version`** answers instead of exiting 2. The subcommand is
  required, so the top-level parser previously rejected `--version` with a usage
  dump — the first thing anyone runs to confirm an install looked like a broken
  install. The `version` action exits during parsing, ahead of that check.

- **`LICENSE` is the canonical Apache-2.0 text again.** The file had been
  truncated at 154 lines with the `APPENDIX` section removed, which put it below
  the similarity threshold GitHub's licence classifier needs: the repository
  reported `spdx_id: NOASSERTION`, licence "Other". Corporate policy scanners and
  dependency-review bots read that field and frequently block on it. The declared
  `license = "Apache-2.0"` in `pyproject.toml` never changed; only the file did.

- **The ROADMAP milestone called "1.0" was a mis-render of "0.10"**, and read as a
  major release this package has not earned. Renamed across 25 references in 11
  files. Not renamed, because they are not the milestone: the `release/1.0*`
  branch names (a doc recording which branch it was written against stays true
  only if left alone), the QSR spec's `v0 → v1` (a spec version, legitimately v1),
  and `gguf<1.0` / `accelerate>=1.0` / `0.1.0`, which are different numbers.

## 0.5.3 — merged, never published

ROADMAP 0.8 machinery: the reproduction gate as code, an Inspect-API runner, the
reference-report registry, and the QSR v1 freeze plan. Scoped to what can be true
today — **v1 is not frozen** (it needs the ε-calibrated MDE from GO-gated 0.6 and
the calibrated tolerance from an unrun T4), and **no reference report exists**
(the 0.5 screen has not run). This ships the machinery and the plan; it
fabricates neither.

- **`quantfit.reproduce`** turns ROADMAP 0.8's gate — *"one reference report
  reproduced from scratch on a free T4 within the 0.7 tolerance"* — into a
  decision made by code. `docs/cross-hardware-tolerance-v0.md` defines the
  tolerance as a T1–T5 rule over two schema-v2 reports; every predicate quotes
  BOTH sides' numbers, so a breach is auditable from the artifact alone.
  Outcomes are a closed vocabulary plus one minted name,
  `reproduced_t0_unverified`: T0 is a within-hardware property of three
  replicates and is not computable from the two reports a comparison receives,
  so omitting that evidence yields a name strictly *harder* than the reserved
  gate pass rather than the gate pass itself.
- **`quantfit.inspect_task`** — a QSR-conformant paired diff on the Inspect API,
  importing quantfit's own judge, at-risk definitions and tabulation. One
  protocol, one implementation: a second copy would be the divergence channel
  the spec exists to prevent. The arm and epochs pins are enforced at the layer
  that can actually see a bypass, and the judge is loaded once per run rather
  than once per probe.
- **`quantfit.refreports` + `CITATION.cff`** — the registry ships **empty**,
  with the three-report cap enforced in code and the rule ROADMAP risk 5 turns
  on: a report stays valid across tool and dependency bumps and goes stale only
  when its *spec* version is superseded.
- **`spec/qsr-v1-freeze-plan.md`** — the blocking ledger with evidence, the
  section-by-section v0→v1 diff, and the comparability decision under §10.2, so
  freezing v1 later is transcription plus measured values rather than redesign.
- **Decode comparability**: T1 compares decode as protocol facts — length and
  greediness — rather than as prose. Comparing the chat-template policy string
  for equality had made every honest cross-runner comparison read "not the same
  measurement", punishing a runner for wording rather than for behavior.
- CI installs `inspect-ai` (new `inspect` extra) so the Inspect parity test
  actually runs; `.gitignore` covers Inspect eval logs, which carry completion
  text the same way captures do.

**Not delivered, so 0.8 is not claimed gate-passed:** QSR v1 is not frozen, zero
reference reports exist, the free-tier T4 reproduction has not been attempted,
and there is no launch post (the 0.5 screen has not run, so there are no findings
to lead with). Of the three new modules, `reproduce` and `audit` became CLI
commands in the 0.10 work below; `refreports` is still library-only, by design —
the registry is empty, so a command would be a facade over nothing.

### ROADMAP 0.10 machinery: the checks that keep the docs honest

0.10 is the frozen standard, and none of its gate clauses is met here. What ships
is the machinery that makes the claims checkable, plus the corrections that
machinery found.

- **`quantfit audit`** — docs=code parity as a command and a CI job: CLI commands
  and flags walked off the real argparse parser, `file:symbol` citations resolved
  by `ast`, exit codes, quoted constants, and schema field names. Exit 0 clean, 3
  drift, 2 operational. It proved itself on its authors: wiring it made it fail
  immediately with eight undocumented flags. Documents can say "this token is an
  example, not a claim" with an `<!-- audit: ... -->` marker, because an auditor
  that cannot be told about a counter-example is an auditor that gets switched off.
- **`quantfit reproduce`** — the cross-hardware tolerance as a command. Replicate
  files become a T0 result at the CLI boundary, so the record states which files
  supplied it, and without `--t0-*` the outcome can never be the gate pass.
- **The README quickstart is gated against the installed wheel**, with a
  `--min-commands` floor so a fence-desynced README fails the build instead of
  quietly shrinking the audited surface to nothing.
- **CI derives dependency caps from `pyproject.toml`** (`tools/ci_constraints.py`).
  The test job had been installing `gguf` and `inspect-ai` with no constraint at
  all, ignoring the very caps pyproject declares — CI could have gone green on a
  combination the package forbids. Restating the caps in the workflow would have
  swapped one drift for another.
- **The dependency policy is a test, not a paragraph** — every declared
  requirement, including `[build-system].requires`, is bounded or carries a
  classified exemption whose premise is re-checked against installed metadata.
  Inert floors and majors crossed under an exemption are recorded, so a *new* one
  fails rather than accumulating quietly.

Fixes this round, each found by one of the above or by review of it:

- **`detect_target()` crashed instead of exiting cleanly on a masked GPU.** With
  `CUDA_VISIBLE_DEVICES=""`, `torch.cuda.is_available()` is True while
  `device_count()` is 0; probing the device then raised `AssertionError: Invalid
  device id`, which is outside quantfit's `(RuntimeError, OSError)` taxonomy, so
  `quantfit plan` exited 1 with a traceback rather than the documented 2. Zero
  visible devices is now read as what it is — a CPU machine — and any other probe
  failure becomes a `RuntimeError`.
- **`plan --token` was inert**: accepted by the parser, never read, and nothing in
  `plan`'s path reaches the Hub. Removed, with a test that accepting a token and
  using one must be the same set of commands.
- **Spec §5.8 was two different sections.** The no-detection section is now §5.9,
  and every citation moved with it — cited by title as well as number, because a
  bare number can come to mean something else without the citing file changing.
- **The GGUF report no longer overstates its own supply chain**: the SHA256 pin
  gates *provisioning*, and a cached binary is not re-hashed, so the arm records
  "provisioned from" rather than a verification it did not perform on that run.
  `SECURITY.md` now discloses the same gap instead of implying the check.
- **README no longer claims validation on Llama-1B** — that model appears in the
  0.5 screen *target list*, which is a list of things to run, not a record of runs.

## 0.5.2 — merged, never published

ROADMAP 0.7 machinery: the pre-release gate, its CI integration, and the
protocols they need — built to the milestone's stated goal, *"the pre-release
check a quantizer runs on their own GPU, which refuses to promise resolution it
does not have."*

- **`quantfit gate --baseline B --quant Q --tier smoke|full` (or `--threshold PP`)**:
  runs the paired diff and answers PASS/FAIL on the refusal-robustness axis —
  but only after proving it can resolve the resolution you declared. Resolution
  is checked twice: **before any model loads**, against the best-case at-risk
  pairs the pinned probe set can supply, and again against the realized at-risk
  n after the run. Either refusal exits **5** and names the threshold, the
  printed MDE, the n, and where epsilon came from. A gate that cannot fail is
  refused too (a declared threshold coarser than 30pp is an operational error).
  Note what the threshold does and does not do: it governs the *resolution* leg
  only. The verdict is an exact binomial test at the printed bound, not a
  comparison of the observed rate against your number — with any real judge
  error a single flip stops being a rejection — and the gate prints both the
  flip count and the detection threshold so the arithmetic is auditable.
- **Exit codes as a CI contract** (now spec §5.8): 0 pass, 3 fail (H0 rejected
  on the gated axis), 4 the gated axis had zero at-risk pairs, 5 unresolvable,
  2 operational. **4 and 5 are not passes** and must fail a build. Two stated
  divergences from `verify-safety`: the gate's 4 is narrowed to the gated axis,
  and its 3 is threshold-relative on one axis — so when the underlying run
  detects an over-refusal regression the gate can still exit 0, and it therefore
  carries the protocol's own verdict verbatim, flags the ungated axis, and names
  it in the headline.
- **The floor disclosure.** No in-distribution judge error has been measured
  (ROADMAP 0.6 is GO-gated), so without an operator-supplied `--eps-upper` the
  gate prints a **perfect-judge floor** — a lower bound on the true resolution,
  never the resolution — and says so on every surface. The floor cuts both ways
  and the gate discloses both: it is optimistic about resolution, and at
  epsilon = 0 the detection threshold is the smallest possible, so a floor-mode
  FAIL runs at an uncontrolled alpha and is a candidate for human verification.
  `--eps-upper` requires `--eps-source`; an unsourced epsilon is not evidence,
  and an epsilon of exactly 0 is refused (no Wilson upper bound is ever 0).
- **Fingerprint-keyed baseline caching** (`quantfit.safety.cache`): a wrong hit
  fabricates half a paired diff, so the fingerprint covers every input that can
  change a completion — model, digest-shaped revision, resolved precision,
  engine identity (transformers version, or llama.cpp binary hash + threads +
  device), decode params, probe pins, and the execution environment. A floating
  ref like `main` confers no content identity and is refused rather than cached.
  Entries re-derive their own fingerprint on load, so a hand-edited entry is
  never served. Cache entries hold completion text and are governed by
  `docs/data-handling-completions.md`; `.gitignore` backstops
  `*.baseline-cache.json`. Budgets assume zero hits — a hit is a speedup, never
  a planning assumption.
- **Reference CI integration**: a composite action (`.github/actions/quantfit-gate`)
  a third-party quantizer copies, a weekly CPU canary
  (`.github/workflows/canary.yml`) that asserts the determinism canary's
  zero-flips-by-construction property without downloading a large model, and
  `docs/ci-integration.md` — the exit-code table, what the gate does not
  promise, secret handling, and artifact rules.
- **`docs/cross-hardware-tolerance-v0.md`**: the tolerance protocol 0.8's
  reproduction gate will consume — what a tolerance covers (GPU model, driver,
  kernel nondeterminism, host threads, and the judge's own forward pass) versus
  what it cannot, which of those the shipped report can witness from its own
  fields, and the recorded deviation where ROADMAP's "dtype pinned fp16 on all
  arms" cannot hold on the GGUF stratum by construction.

**Not in this release:** the cross-hardware T4 run, the injected-catastrophe
canary, a rendered HF model-card page, and any measured judge error — so ROADMAP
0.7's gate criteria are not claimed as met. The baseline cache is library
surface: `quantfit gate` does not yet call it.

## 0.5.1

Judge-calibration MACHINERY for ROADMAP 0.6 — with GO-gated activation. The
0.6 milestone's expensive work (hand-labeling 300-500 completions, corpus v2
curation) starts only on the 0.5 GO decision, which has not run; this release
ships everything a GO needs on day one without starting any of it. No epsilon
has been measured: reports continue to print the perfect-judge MDE, and every
error-aware number in the docs is a labeled hypothetical.

- **Completion capture, opt-in** (`verify-safety --capture PATH`): writes a
  local JSONL of every completion for calibration labeling — the single,
  explicitly recorded exception to the no-persisted-completions invariant
  (`docs/data-handling-completions.md` IS the recorded data-handling decision:
  local-only, warning header, never committed/redistributed/attached to a
  report; `.gitignore` backstops the filename convention). Capture changes
  nothing the run computes, and a failed capture write degrades to a warning —
  it can never cost a completed run its report or verdict.
- **`quantfit calibrate sheet` / `calibrate ingest`**: capture -> blinded
  labeling sheet (secret-salted opaque ids, arms and judge labels hidden,
  concordant pairs included against verification bias) + unblinding key with
  per-row completion hashes (an edited sheet cannot be attributed to text the
  judge never scored); filled sheet + key -> calibration report with per-arm
  judge error: marginal epsilon with Wilson CIs, per-DIRECTION error rates
  (false-compliance / false-refusal, each over its own denominator), per-arm
  unusable counts, and `mde_epsilon_upper` — the exact value the MDE machinery
  consumes. Degenerate sessions refuse or carry `unmeasured_arms`; a filled
  sheet can never be silently overwritten, even mangled by a spreadsheet.
- **Error-aware MDE machinery** (`quantfit.safety.mde`): how judge error
  inflates the minimum detectable effect on the paired protocol. Conservative
  false-flip bound (per-arm epsilon = upper bound on BOTH directional error
  rates — the marginal-rate version was proven not to bound), exact binomial
  detection thresholds, power at pre-registered effect sizes, all pure python
  cross-checked against scipy in CI, reducing exactly to the shipped
  `detectable_flip_rate` at epsilon = 0. Honest headline: at the shipped n=12
  with a hypothetical 5% per-arm error, the effective MDE is ~46pp — the
  arithmetic for why 0.6 couples corpus expansion to calibration.
- **`docs/judge-calibration-v0.md`**: the labeling protocol a GO activates —
  computed sample-size tables, annotation rules, blinding, arm-correlated
  error limits, XSTest contamination rule, retention sequencing.
- **`docs/injected-control-design.md`**: closes ROADMAP's open question. The
  Egashira-style injected control (arXiv 2405.18137) was never about 3-bit:
  quantfit's own W4A16 RTN satisfies the attack's closed-form requirements
  (verified against compressed-tensors by construction), while GGUF k-quants'
  nested argmin scale search does not transfer. Decision ladder for the 0.6
  full-scale control, with the Q2_K surrogate as the stated-weaker fallback.
  Design only — no training code, never uploaded, GO-gated run.

## 0.5.0

The CI-verifiable half of ROADMAP milestone 0.5: the QSR spec, the screen
harness, the model-card emitter, the sensitivity-control procedure, and a
verified target list. The hunt runs themselves, the control run, the
replication package, outreach, and the GO/NO-GO clock are NOT in this release —
they run against it.

- **QSR spec v0** (`spec/qsr-v0.md`): the versioned protocol document — paired
  diff, engine rules (same-binary GGUF mandate), provenance rules (schema v2
  field-by-field), statistics (at-risk denominators, Wilson, MDE, exit-code CI
  contract), screen aggregation, hardware caps, determinism canary,
  sensitivity-control conditionality labeling, versioning rules. Every numeric
  claim was verified by executing the shipped code; the tool is the spec's
  reference implementation.
- **`quantfit screen --targets targets.json --out DIR`**: runs verify-safety
  sequentially over a target manifest and writes one drift report per target
  plus `screen-summary.json`. Aggregation is per-stratum AND per-axis — each
  axis has its own at-risk denominator, so a dangerous-axis flip on a target
  whose over-refusal axis was unmeasurable still enters the dangerous-axis
  bound (never silently dropped). Bounds are flagged-basis with
  `n_regressed_human_verified` reported separately; the summary carries the
  §7 caps as data; per-target operational failures (RuntimeError AND the
  OSError family — gated repos) become rows, not screen deaths; target names
  are collision-checked case-insensitively (Windows/macOS filesystems). Exit
  codes mirror verify-safety: 0/3/4/2.
- **Sensitivity-control conditionality is machine-carried**: the manifest
  accepts a `sensitivity_control` block (status pass/fail/unmeasurable/
  not_run; absent = not_run); any status but "pass" stamps ROADMAP 0.5's
  literal label — "conditional on undemonstrated detection sensitivity" — into
  every bound's `conditionality` field. The control's procedure and decision
  rule (keyed on the report's `unmeasurable_axes`, never the exit code) live
  in `docs/sensitivity-control-v0.md`.
- **`quantfit emit model-card --report drift.json`**: renders a schema-v2
  report as a paste-ready markdown model-card section — verdict verbatim, both
  axes with CI/MDE (zero-flip rates withheld, as verify-safety prints them),
  full provenance incl. the same-binary hash statement, the §7 cap line, and
  the exact serve command (`vllm serve` for transformers arms, `llama-server`
  for GGUF). Wrong-schema reports exit 2. Exposed as
  `quantfit.model_card_fragment`.
- **Screen target list** (`screens/targets-0.5.json` + curation audit trail):
  15 targets — 12 GGUF pairs across 9 model families and 4 quantizer orgs,
  3 transformers pairs — every filename/revision/size verified twice against
  the HF API, with disclosed corrections (one candidate removed because its
  "BF16 baseline" was an upcast of FP8-quantized weights; the maintainer's own
  anchor quant disclosed as self-produced; a first-party autoawq artifact
  disclosed as requiring the new `quantfit[awq]` extra).
- **Verdict strings now name every unmeasurable axis**: a run whose
  over-refusal axis had zero at-risk pairs no longer prints a plain clean
  verdict alongside exit 4.

## 0.4.1

GGUF judging + over-VRAM validation (ROADMAP milestone 0.4b — the
hardware-gated half of 0.4).

- **verify-safety runs on GGUF pairs** — the format third-party quants actually
  ship in. Both arms run under the IDENTICAL pinned llama.cpp `llama-server`
  binary (same SHA256-verified b9817 release archive as `llama-quantize`) on
  CPU: F16-GGUF baseline vs Qn-GGUF quant, so the diff isolates the
  quantization and the baseline arm is no longer VRAM-capped — 7-8B pairs fit
  in RAM. Refs are local `*.gguf` paths or `hf:<org>/<repo>/<file>.gguf`.
  Greedy decoding via one server per arm, sequential requests, no prompt-cache
  reuse; the model's own chat template (GGUF metadata) is applied via
  `--jinja` when present, raw prompt otherwise — the same policy as the
  transformers arms. The judge is unchanged.
- **Pairing mandates, enforced not documented**: the baseline must be an
  unquantized GGUF (F16/BF16/F32) — resolved from the file's own
  `general.file_type` metadata, never trusted from the filename; both files
  must declare the same architecture; and a transformers-baseline vs
  llama.cpp-quant mix is refused outright — that diff measures engine +
  quantization at once (a deployment delta) and is never pooled with a
  quantization diff.
- **Drift report schema v2** (breaking, replaces v1; no v1 reference reports
  were ever published): each arm now records `engine` provenance —
  transformers version, or the llama.cpp binary's SHA256 (of the executable
  actually run), source, thread count, and device — plus `artifact_sha256`
  for single-file GGUF artifacts. The same-binary mandate is auditable from
  the report alone: the two arms' `binary_sha256` must be equal.
  `resolved_dtype` widens to "precision actually loaded": a torch dtype for
  transformers arms, a GGUF file type ("F16", "Q4_K_M") for llama.cpp arms.
  v1 reports are refused on parse with a clear message.
- **Hardware gates (ROADMAP 0.4b), both passed on an RTX 4080 Laptop (12 GB)**:
  (1) end-to-end paired diff on a real third-party pair —
  `bartowski/Qwen2.5-7B-Instruct-GGUF` Q4_K_M vs its F16 under the identical
  pinned binary, the 15.24 GB F16 arm entirely in CPU RAM (F16 arm 559 s, Q4
  arm 225 s, 16 threads). Verdict: over-refusal drift 2/14 at-risk pairs
  (14.3%, 95% CI 4.0-39.9%) with the scalar refusal count UNCHANGED (14 -> 14)
  — offsetting flips a flat counter would call clean; dangerous axis 0/12
  (upper 24.2%). Drift vector byte-identical on rerun (0.5B pair).
  (2) over-VRAM quantize: Qwen2.5-7B GPTQ (15.2 GB bf16) through
  llm-compressor's default sequential onloading — GPU peak 9,047 MiB on a
  12,282 MiB card while process RSS peaked at 28.1 GB (telemetry-sampled every
  5 s), ~32 min end-to-end, `verify` PASS on the artifact.
- **Method guidance from the same evidence**: at over-VRAM sizes use `gptq` —
  AWQ's 20-point grid search is transfer-bound under onloading (observed ~2 h
  for one 7B layer, projecting 50+ h; AWQ remains fine at in-VRAM sizes).
  README capacity/limits wording updated to match what was actually measured.

## 0.4.0

Provenance schema + stats hardening (ROADMAP milestone 0.4a — the CI-gated half
of 0.4; the hardware-gated half, GGUF judging + over-VRAM validation, is 0.4b).

- **Drift report schema v1** (`verify-safety --report out.json`): runs can emit an
  auditable JSON artifact recording judge + probe-dataset `revision` pins, the
  pinned judge input contract, decode parameters, RESOLVED per-arm dtypes (the
  literal "auto" is rejected by schema — it is an input, not a provenance fact),
  an environment fingerprint (python/torch/transformers/CUDA/GPU), per-arm and
  judge runtimes, and the full drift vector with CIs and MDEs. Wrong-schema or
  malformed reports are refused on parse, never coerced. Exposed as
  `quantfit.safety.DriftReport` with round-trip `to_json`/`from_json`.
- **Loads are revision-pinned**: judge and probe dataset load at pinned commit
  hashes (bumped deliberately, never implicitly). The judge input contract —
  completion text alone, truncated to 512 judge tokens, prompt never
  concatenated — is PINNED as quantfit's stated protocol: the judge card
  (re-read 2026-07-11) documents response-level classification but not whether
  prompts were concatenated in training. The card's external XSTest accuracy
  (0.9773) rides along in reports explicitly labeled uncalibrated /
  out-of-distribution for these probes.
- **Stats cross-checked against scipy in CI**: Wilson intervals match
  `scipy.stats.binomtest(...).proportion_ci(method="wilson")` to 1e-9 across a
  grid, and the MDE is verified to deliver its stated 80% power via
  `scipy.stats.binom`. The z quantile is now full-precision, so the shipped
  numbers ARE the scipy numbers (the 0/12 upper bound prints 24.2%, not the
  z=1.96 rounding's 24.3%).
- **Hermetic supply-chain + dispatch tests** (CPU-only, no network): GGUF binary
  SHA256 pin/verify/delete-on-mismatch, refuse-before-download for unpinned
  assets, atomic promote-after-verify, corrupt-archive cleanup, per-platform
  asset selection; and quantize() routing (compressed-tensors vs GGUF vs refusal
  vs `--no-check`) with card provenance.
- **Vocabulary: "fp16" -> "baseline"** everywhere the unquantized arm is meant —
  the live report proved the arm loads at its NATIVE dtype (bf16 for Qwen2.5).
  Schema v1 keys are `baseline_refused`/`quant_refused` and flip counts use the
  dataclass names (`harmful_compliance_regressions`/`overrefusal_regressions`);
  `SafetyDrift` fields renamed to match; the CLI flag is now `--baseline`
  (`--fp16` kept as a legacy alias); `verify_safety`'s first param is
  `baseline_model_id`.
- **Exit-code coherence for `check` and `verify`**: verdicts moved off the
  operational-error code — `check` won't-fit and `verify` FAIL now exit 3
  (0 = pass, 2 = operational error), matching verify-safety's contract; all
  three help strings document their codes.
- **Public API reflects what quantfit is**: the package root lazily (PEP 562)
  re-exports `verify_safety`/`SafetyDrift`/`DriftReport`, `quantize`, and
  `capacity_plan`/`CapacityPlan`; `import quantfit` no longer drags
  huggingface_hub. The 0.1-era `check_fit`/`FitReport` (VRAM-only, a different
  verdict than the shipped 3-tier plan) are removed; `fit.plan` is renamed
  `capacity_plan` (the word "plan" now means only the routing pick);
  `wilson_interval`/`detectable_flip_rate` are exported from `quantfit.safety`;
  the never-used `DEFAULT_BUDGET` is gone.
- **One fact, one place**: GPU device-pick + memory hygiene unified in
  `quantfit.torchrt` (was triplicated); the probe sources its calibration
  corpus/config/seed/group-size from the frozen `QuantSpec` instead of shadow
  constants; the `Engine` protocol slims to `feasible()` — execution has exactly
  one path (`quantize` -> backends), never a parallel one via engines.
- Error-taxonomy stragglers fixed: a weightless/gated repo in `check` now exits
  2 cleanly (was a raw ValueError traceback); docs corrected where they
  overstated the code (spec "override on the CLI", README tier-1 RAM
  precondition, GGUF IQ family -> `IQ4_XS`, `verify`'s GGUF magic-only scope).

## 0.3.0

Reconcile and make the verdict honest (ROADMAP milestone 0.3). PyPI still served
0.1.0 (uploaded 2026-06-27) while the repo sat at an unpublished 0.2.0 with
`__init__.__version__` stuck at 0.1.0 — 0.3.0 supersedes both.

- **Bounded verdict statistics** for `verify-safety`: the single-flip CLEAN/REGRESSION
  binary is gone. Each axis is now a binomial over its *at-risk pairs* (probes the
  fp16 baseline got right), reported with a Wilson 95% CI; a zero-flip axis prints its
  CI upper bound and the minimum detectable effect at 80% power
  ("NO REGRESSION DETECTED (dangerous-axis MDE ~13pp at n=12)"). New helpers
  `wilson_interval` / `detectable_flip_rate`, unit-tested against known values.
- **Rename: safety tax -> safety drift vector** (`SafetyTax` -> `SafetyDrift`,
  README, package description). "Safety tax" collides with the literature's
  alignment-tax usage (capability paid FOR safety) — near-inverse of what this
  measures. Breaking, while real users are ~zero. A repo-wide test now enforces the
  purge on shipped surfaces.
- **Determinism canary documented**: an fp16-vs-fp16 rerun is zero-flip by
  construction under greedy decoding — it validates determinism only and is never a
  judge noise floor.
- **Deprecated offload path deleted**: the accelerate `device_map="auto"` branch (and
  the `--offload` flag) are gone. Models load on CPU and llm-compressor's default
  sequential onloading streams layers to the GPU — one code path for every size.
  Because the load is now CPU-first, **RAM gates every mode** in the capacity plan:
  a big-VRAM/small-RAM machine refuses up front instead of OOM-ing mid-load.
  Exceeds-VRAM validation stays a 0.4b gate; the README says so.
- **CI-contract exit codes for `verify-safety`**: 0 = measured, no regression
  detected; 3 = regression detected; 4 = an axis had zero at-risk pairs (an
  unmeasured run is not a pass); 2 = operational failure. Previously a regression
  and a crashed run both exited 2.
- **Probe scope corrected**: RTN-KL is a quality-drift signal, not a safety predictor
  (arXiv 2606.10154); `verify-safety` owns the safety axis.
- `from_pretrained` calls use `dtype=` (the `torch_dtype` kwarg is deprecated);
  transformers floor raised to >=4.56 accordingly.
- Dropped the never-imported `gptqmodel` dependency; upper-bounded `llmcompressor`
  (<0.13) pending validated runs on newer minors. quantfit's own operational errors
  (short calibration set, empty probe batch, unroutable host) now raise
  `RuntimeError`, so the CLI exits 2 with a clean message while programming errors
  — including third-party `ValueError`s — still surface as tracebacks.
- `__init__.__version__` / pyproject parity is now enforced by a test; CI gained an
  install-smoke job (build the wheel, install it into a clean env on Ubuntu +
  Windows, run the CLI).

## 0.2.0 (never published — superseded by 0.3.0)

Routing diagnostics + a pre-release blind-audit hardening pass.

- **`quantfit plan <model>`** — transparent heuristic router: shows the (method, scheme)
  it would pick for your GPU and *why*, instant, no quantize. Wraps a new engine
  abstraction (`engines/`) over compressed-tensors + GGUF.
- **`quantfit probe <model> [--bits ...]`** — forward-only RTN-KL sensitivity per
  bit-width. Low KL = safe bit-width; it over-escalates as a method selector, so it
  ships as a diagnostic, not an auto-router.
- **Audit hardening:** GGUF binary download is SHA256-verified before extract/execute and
  downloaded/cloned atomically; offload claims scoped to what's validated; Dockerfile
  build tooling fixed (PEP 639 setuptools); calibration packing guards short datasets;
  per-token KL normalization in the probe; clean refusal (not a traceback) on CPU-only
  hosts; a `--token` flag across commands; the router gains unit tests.

## 0.1.0

First release — a GPU-aware quantization CLI.

- **Quantization** via one llm-compressor backend: `awq` / `gptq` / `smoothquant` /
  `fp8` / `rtn` × W4A16 / W8A16 / W8A8 / W4A8 / FP8 / NVFP4 / MXFP4, plus a GGUF
  backend (`Q2_K`..`Q8_0`) — all vLLM- or llama.cpp-loadable.
- **GPU-aware capacity:** `check` reads HF metadata (no download) and refuses with the
  real limiting resource; models too big for VRAM auto-offload to CPU instead of OOM-ing.
- **Safety-tax check** (`verify-safety`): does the quantized model still refuse what the
  fp16 baseline refused? Local ModernBERT judge + curated public probe set;
  aggregates-only output; umbrella-free (no external API, no raw harmbench/advbench).
- One frozen packed calibration (wikitext-103, 128 samples, seq-len 2048, seed 42,
  group-size 128) shared across the calibrated methods, so they're comparable.
- Commands: `check` / `list` / `quantize` / `verify` / `verify-safety`. Dockerfile + CI.
- Validated end-to-end on qwen2.5-1.5b: AWQ / FP8 / GPTQ / SmoothQuant / GGUF-Q4_K_M,
  CPU-offload, a transformers load-smoke-test, and a safety-delta run.
