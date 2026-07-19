# Changelog

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
