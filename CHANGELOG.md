# Changelog

> Note on versions: tool versions do not track ROADMAP milestone numbers. 0.5.1
> shipped 0.6's machinery, 0.5.2 ships 0.7's; a milestone number in a version
> would claim milestone completion, and those completions are gated on runs and
> decisions that have not happened. 1.0 is the frozen standard (ROADMAP 1.0).

## 0.5.2

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
