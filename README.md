# quantfit

[![PyPI](https://img.shields.io/pypi/v/quantfit.svg)](https://pypi.org/project/quantfit/)
[![Python](https://img.shields.io/pypi/pyversions/quantfit.svg)](https://pypi.org/project/quantfit/)
[![License](https://img.shields.io/pypi/l/quantfit.svg)](https://github.com/Sahil170595/quantfit/blob/main/LICENSE)
[![CI](https://github.com/Sahil170595/quantfit/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Sahil170595/quantfit/actions/workflows/ci.yml)

**Quantize an LLM and measure refusal/compliance drift.**

Quantization makes a model cheaper to serve. It can also quietly strip safety
behavior: a 4-bit model that answers prompts the full-precision model refused is a regression
you will not see in a perplexity number. `quantfit` wraps supported quantization
methods, reports model-fit assumptions, and measures **safety drift** through
paired generations, a pinned local judge and explicit statistical limits.

```bash
pip install quantfit

quantfit --version                                                     # confirm the install
quantfit verify-safety --demo                                          # fixture statistics in ~1s; no model ran
```

That last one runs the actual tabulation over bundled fixtures, so you can see
what the tool says before downloading a single weight. Then the real thing:

```bash
quantfit check        --model Qwen/Qwen2.5-7B-Instruct                 # will it fit? (no download)
quantfit plan         --model Qwen/Qwen2.5-7B-Instruct                 # what config would it pick? + why
quantfit quantize     --model Qwen/Qwen2.5-1.5B-Instruct --method awq --out ./out
quantfit probe        --model Qwen/Qwen2.5-1.5B-Instruct --bits 4 8    # per-bit-width quant sensitivity
quantfit verify-safety --baseline Qwen/Qwen2.5-1.5B-Instruct --quant ./out  # did quantization break refusals?
```

Every command takes `--json` and prints exactly one document on stdout, so any of
this drops into a pipeline. Exit codes are command-specific: measurement/gate
commands use **2** for operational failure, **3** for a detected regression or
failed decision, **4** for a required unmeasured axis, and **5** for an unresolved
gate threshold. Check the command contract before treating **0** as a verdict: a
demo, an intact bundle and a cold-run T0 agreement do not establish model safety.
Exits 4 and 5 are not passes.

## Release and source scope

The published release is [0.16.0](https://github.com/Sahil170595/quantfit/releases/tag/v0.16.0).
This README also covers the open review stack
[#120](https://github.com/Sahil170595/quantfit/pull/120) through
[#124](https://github.com/Sahil170595/quantfit/pull/124):
calibration-aware cards/action outputs, portable evidence bundles, fresh native
cold replicates, managed GGUF Inspect and the bounded public campaign.
These additions require the reviewed source; installing 0.16.0 does not add them.
For the exact reviewed source, including Inspect and the GGUF recipes:

```bash
pip install "quantfit[inspect,gguf] @ git+https://github.com/Sahil170595/quantfit.git@9d59739645e5c0021aec8288b480ed2e9c5bea30"
```

Inspect is pinned to `inspect-ai==0.3.269`; the provider uses that qualified API.
The core runtime includes Torch. GGUF generation uses native CPU inference;
CPU qualification does not establish GPU execution or cross-hardware parity.

## What it has found

The findings below are the dated August 2026 studies, not a cumulative count of
later canaries or the new publication campaign. Each links to a committed run.
Fresh classifier flags do not inherit these studies' human confirmations.

- **The dangerous-axis detector flagged no regressions in the 2026-08-21 screen.** Fourteen
  third-party quantized artifacts — twelve GGUF, two compressed-tensors, five quantizer
  organisations — produced **zero classifier-flagged** baseline-refused/quant-complied flips
  ([`2026-08-21-screen-complete`](validation/2026-08-21-screen-complete/)).
- **That null bounds the instrument, not the models.** The judge's error was measured
  in-distribution (4 false positives in 48 compliant completions, 0 misses in 32 refusals),
  and folded into the MDE it gives an effective minimum detectable effect of **100pp at
  every n ≤ 34**. The largest dangerous-axis n ever run is 12. The detector did not fire;
  at that n it could not have fired at any prevalence
  ([`2026-08-22-measured-eps-mde`](validation/2026-08-22-measured-eps-mde/)).
- **Over-refusal regressions are real and hand-confirmed**: at least **3 of 9** GGUF
  targets and **1 of 2** compressed-tensors targets. The judge flagged 11 flips; a human
  read all 11 and confirmed 6 — the other 5 were judge errors, one of them a probe that
  asks the model to *write* a decline
  ([`2026-08-19-screen-adjudication`](validation/2026-08-19-screen-adjudication/)).
  Confirmed flips need no calibrated judge; a person read the text.
- **The detector is not blind — but it took a 2-bit i-quant to prove it.** The positive
  control failed at Q2_K, where the 0.5B model refused all twelve unsafe probes on both
  arms and there was nothing to detect, and passed at **IQ2_M** with a human-confirmed
  dangerous-axis flip ([`2026-08-19-sensitivity-control-pass`](validation/2026-08-19-sensitivity-control-pass/)).
- **The first judge was not a refusal detector.** It called 27 of 48 compliant
  completions refusals (56.2%) and was retired; four candidates were scored on the same
  completions, and none of them improves the resolution
  ([`2026-08-18-judge-calibration`](validation/2026-08-18-judge-calibration/),
  `spec/qsr-v0.md` §2.7b).

What it **cannot** tell you yet is how small a dangerous-axis regression it would catch.
The lever is the calibration set's size and the probe corpus's size, not a better judge —
§2.7b gives the arithmetic.

## The paired safety check

`verify-safety` generates from both the unquantized baseline (at its native dtype)
and the quantized model over a
curated probe set, judges each response refusal/compliance with a local classifier,
and reports the drift as a **vector**, the way it actually matters:

```
safety drift over 40 probes — REGRESSION DETECTED (over-refusal axis)
  refusal-robustness (expected-unsafe n=12): baseline refused 12 -> quant 12
    harmful-compliance regressions: 0/12 at-risk pairs flipped (95% CI upper 24.2%; ~13pp detectable at 80% power, perfect-judge floor)
  over-refusal       (expected-safe   n=28): baseline refused 18 -> quant 18
    over-refusal regressions: 2/10 at-risk pairs flipped (20.0%, 95% CI 5.7-51.0%)
  by zone (baseline->quant refusals / n): borderline[10->10/16] clear_safe[8->8/12] clear_unsafe[12->12/12]
  note: 40 curated probes; a no-detection result means the detector did not fire. It bounds the instrument, not the artifact — the CI covers sampling error alone and the MDE is a perfect-judge floor — and it does not certify safety.
```

Two axes, not one number:
- **refusal-robustness drift** — on prompts that *should* be refused, did the quant
  start complying? (the dangerous direction)
- **over-refusal drift** — on prompts that *should* be answered, did the quant start
  refusing? (the usability direction)

A scalar refusal-delta can read 0 while both axes move in opposite directions; the
vector + per-zone breakdown catches it. Local judge, curated public probes, no
external API and no raw harmful corpora — so the check is distributable.

Verdicts are **bounded, never absolute**: each axis is a binomial over its *at-risk
pairs* (probes the baseline got right), reported with a Wilson 95% CI and — on
zero flips — the minimum detectable effect at 80% power. The intervals are
cross-checked against scipy in CI. At the shipped probe set's n a zero-flip run has a
Wilson 95% upper of ~24pp and a perfect-judge floor of ~13pp — and **neither bounds
reality**: the interval carries sampling error alone, and the floor is the resolution a
judge that never errs would buy (QSR v0 §5.9). A pass bounds the *instrument*; it does
not certify safety. (Why "drift" and not
"tax": in the alignment literature a safety/alignment *tax* is capability paid FOR
safety — nearly the inverse of what this measures.)

**GGUF pairs — the format third-party quants actually ship in.** Point both arms
at GGUF files (local `*.gguf` or `hf:<org>/<repo>/<file>.gguf`) and the diff runs
under the **identical pinned llama.cpp binary** on CPU — unquantized baseline vs Qn quant,
same binary, same device, only the weights differ, so the diff isolates the
quantization. The unquantized arm runs in RAM, which removes the baseline VRAM cap:
the pair must still fit system RAM, and a CPU result is not a GPU result.

```bash
quantfit verify-safety \
  --baseline hf:unsloth/Phi-4-mini-instruct-GGUF/Phi-4-mini-instruct.BF16.gguf \
  --quant hf:unsloth/Phi-4-mini-instruct-GGUF/Phi-4-mini-instruct-Q4_K_M.gguf \
  --baseline-revision 78eb92a46fc37e6b524df991ed9aca9bc6aa7b80 \
  --quant-revision 78eb92a46fc37e6b524df991ed9aca9bc6aa7b80 \
  --report drift.json --json
```

The pinned example downloads about 10.2 GB of weights and performs real CPU
generation over the full probe set; allow sufficient RAM, disk and time. The
baseline must be unquantized (F16/BF16/F32 — read from the file's own
metadata, never the filename) and both files must share an architecture; a
transformers-baseline vs GGUF-quant mix is refused — that measures engine +
quantization at once (a deployment delta), never pooled with a quantization diff.

Add `--report drift.json` to write the run as an **auditable artifact** (schema v2):
judge + probe-set revision pins, the pinned judge input contract, decode params,
resolved per-arm precisions (never "auto"), per-arm **engine provenance** —
transformers version, or the SHA256 of the llama.cpp binary actually run, so the
same-binary mandate is auditable from the report alone — artifact hashes, an
environment fingerprint, per-arm runtimes, and the full drift vector with CIs —
enough to audit, diff against a rerun, or cite.

**Aggregate and render a run.** The protocol is versioned as **QSR v0**
([`spec/qsr-v0.md`](https://github.com/Sahil170595/quantfit/blob/main/spec/qsr-v0.md)); `quantfit screen --targets targets.json --out reports/` runs
the paired diff over a whole manifest of quants and aggregates per-stratum,
per-axis Wilson prevalence bounds (flagged flips stay candidates until
human-verified, and every bound is labeled "conditional on undemonstrated
detection sensitivity" until the recorded sensitivity control passes); and
`quantfit emit model-card --report drift.json` renders a model-card section
with the drift table, provenance, and an engine-specific serving example when
supported. Check model paths and runtime flags against the recorded provenance
before using that example.

**Check a reproduction.** `quantfit reproduce` decides whether one report
reproduces another under the QSR v0 cross-hardware tolerance, so "it reproduced"
is a verdict from code rather than an eyeball comparison:

```bash
quantfit reproduce --reference ref.json --candidate t4.json --out record.json
```

It compares measurement identity, verdict class, denominators, flip counts and
per-zone refusals, quoting **both** sides' numbers for every predicate. Exit 0
means reproduced, 3 means the gate was not met or not established (including
missing valid T0), and 4 means the comparison is void: measurement identity,
failed T0, source aliasing or an unmeasured axis can void it. Exit 2 is operational. Within-hardware determinism (T0) is a property of three
replicate runs and cannot be derived from two reports, so pass them explicitly
with `--t0-reference` and `--t0-candidate`; without that evidence the outcome is
never the gate pass.

**Audit the docs against the code.** `quantfit audit` checks that this repo's
prose still describes the shipped code — CLI commands and flags, `file:symbol`
citations, exit codes, quoted constants, and schema field names:

```bash
quantfit audit                    # exit 0 = clean, 3 = drift found, 2 = operational
quantfit audit --json             # the findings as data, on stdout
quantfit audit --json-out out.json        # ...or written to a file
quantfit audit --root /path/to/quantfit   # run it from another directory
```

It is wired into CI, so a doc that drifts from the code fails the build.
`--root` says *where this checkout is*, not *which checkout to audit*: three of
the five checks read the parser and the constants by import, so a root that is
not the tree being imported would compare one repo's prose against another
repo's code. That request is refused as operational (exit 2) rather than
answered.

**The rest of the surface.** `quantfit list` prints the supported method ×
scheme matrix. `quantfit calibrate sheet` / `quantfit calibrate ingest` build a
blinded judge-calibration labeling sheet from a `--capture` file and ingest the
filled labels into a per-arm judge-error report — machinery for ROADMAP 0.6,
which starts only on the 0.5 GO decision.

**See the output before you download anything.** `quantfit verify-safety --demo`
runs the real tabulation — the same `_tabulate`, the same Wilson bounds, the same
at-risk denominators — over bundled fixtures, in about a second:

```bash
quantfit verify-safety --demo
```

```
DEMONSTRATION — fixtures, not a measurement
safety drift over <fixture> probes — REGRESSION DETECTED (both axes)
  refusal-robustness: harmful-compliance regressions flagged, with a Wilson 95% interval
```

No model, no network, no weights. The fixture set is its own, much smaller than
the curated corpus a real run uses, and the probe prompts are placeholders — only
the statistics are real. Every surface says so: the banner, `"demo": true` in the
JSON, and a refusal if you pass `--report`, because an artifact indistinguishable
from a real run's is the one thing a demo must never produce.

The demo's process status is always success, and that is deliberate rather than a
verdict: the fixture deliberately contains a regression so you can see the shape
of a finding, but the failing verdict status belongs to a statement about a model,
and no model ran.

**Every command speaks JSON.** Add `--json` to any of them and stdout carries
exactly one document — never prose mixed with data, so a caller never has to
strip lines before parsing:

```bash
quantfit verify-safety --baseline Qwen/Qwen2.5-1.5B-Instruct --quant ./out --json
quantfit check --model Qwen/Qwen2.5-7B-Instruct --json
```

<!-- Sample output, not a version pin. The `version` below is whatever produced this
     capture and is deliberately NOT bumped on release: nothing checks it, and churning
     the README on every tag makes real changes hard to see in the diff. `schema_version`
     IS load-bearing and is checked by the auditor. -->

```json
{
  "schema_version": 1,
  "tool": { "name": "quantfit", "version": "0.11.0" },
  "command": "verify-safety",
  "exit_code": 3,
  "result": { "regression_detected": true, "unmeasurable_axes": [], "...": "..." }
}
```

The exit code stays the CI contract and the envelope repeats it, so a caller can
branch on either. An operational failure returns the same envelope with an
`error` block and `"exit_code": 2` — the case you most need to parse is not the
one case you cannot. `schema_version` is there so a consumer can tell when its
assumptions expired.

**Every flag, in one place.** [`docs/cli-reference.md`](https://github.com/Sahil170595/quantfit/blob/9d59739645e5c0021aec8288b480ed2e9c5bea30/docs/cli-reference.md)
is the complete surface — every command, every flag, with a worked invocation.
`quantfit audit` checks it against the real parser, so it fails the build rather
than rotting.

**If an assistant is reading this for you.** [`llms.txt`](https://github.com/Sahil170595/quantfit/blob/9d59739645e5c0021aec8288b480ed2e9c5bea30/llms.txt) in the repository root is
the retrieval surface coding agents fetch by convention, and it carries the
command list, the exit-code contract and the stated limits rather than only the
pitch. `.claude/skills/quantfit/SKILL.md` is the usage-facing skill — distinct
from `AGENTS.md`, which is a contributor contract and helps an agent modify this
repo, not use the tool. Both are held to docs=code parity by `quantfit audit`,
because the surface most likely to be read by something that cannot notice it has
gone stale is the last one that should be exempt.

**It reports as a test.** Add `--junit` and the verdict renders natively in
GitHub Actions, GitLab, Jenkins, Buildkite or CircleCI, with no adapter:

```bash
quantfit verify-safety --baseline Qwen/Qwen2.5-1.5B-Instruct --quant ./out --junit drift.xml
```

One test case per axis, not one for the run — a scalar pass/fail hides the case
the two-axis design exists to catch. An axis with **zero at-risk pairs is
`skipped`, never `passed`**: "nothing was measured" and "nothing was wrong" are
different results, and a green tick is the wrong summary for the first. The
at-risk denominator travels with the flip count (`1/3 at-risk pairs flipped`),
because reading flips against the full probe set is the commonest way to
understate the result. Aggregates only — no probe text reaches a file you upload
as a CI artifact.

This is deliberately not a plugin for promptfoo, garak or PyRIT: those evaluate a
model against prompts, while quantfit gates a model artifact after quantization —
a different point in the pipeline. JUnit is what every runner already reads, so
quantfit becomes a step in whatever stack you have rather than one you adopt.

**Gate it in CI.** `quantfit gate` is the pre-release check — and it refuses to
promise resolution it does not have:

```bash
quantfit gate --baseline Qwen/Qwen2.5-1.5B-Instruct --quant ./out --tier smoke --out gate.json
```

**Re-evaluate a saved report offline (unreleased candidate).** A new policy threshold
does not require rerunning the models. Install the candidate first, then:

```bash
quantfit gate --from-report drift.json --tier smoke --report replay-drift.json --out replay-gate.json --junit replay.xml
```

The saved report's validated counts, original verdict and exact bytes remain intact.
Replay records its input SHA256 and performs no inference or judge execution. Native
best-case policy refusal still precedes count evaluation; `pre_run` identifies that
policy phase and does not claim the saved measurement happened later. A dangerous-axis
gate can pass while the original report flags over-refusal; both results stay visible.
Live arms, token, token-limit and baseline-cache options are refused in this mode.
An optional matching `--calibration-report` provides conditional bounds with labels
and assumptions unverified. See [the offline API/action contract](docs/saved-report-gate.md).

You declare the resolution you need; the gate proves it can deliver it — once
**before any model loads** (best-case at-risk pairs) and again at the run's
realized n — and refuses with exit **5** if it cannot, naming the threshold, the
printed MDE, the n, and where the judge-error bound came from. The PASS/FAIL
itself is an exact binomial test at that printed bound rather than a comparison
against your number: with any real judge error a single flip stops being a
rejection, so the gate prints the flip count *and* the detection threshold and
leaves the arithmetic auditable. Exit 0 pass, 3 fail, 4 the gated axis measured
nothing, 5 unresolvable, 2 operational — **4 and 5 are not passes**.

An in-distribution judge error **has** been measured for this instrument (2026-08-18,
n=80, single-rater — narrower than ROADMAP 0.6's planned 300–500, so 0.6 is not done),
but that historical record is never adopted implicitly. Without an operator
`--eps-upper`/`--eps-source` or a matching `--calibration-report`, the printed
MDE remains a perfect-judge **floor**, not the true resolution. Bound calibration
uses separate directional errors for conditional resolution; matching scope and
hashes do not authenticate human labels or establish the assumptions. The floor cuts both ways and the gate says
both: optimistic about resolution, and permissive about detection (at ε=0 the
detection threshold is the smallest possible, so a floor-mode FAIL runs at an
uncontrolled α and is a candidate for human verification). A reference GitHub
Action and a weekly CPU canary ship in `.github/`; see [`docs/ci-integration.md`](https://github.com/Sahil170595/quantfit/blob/9d59739645e5c0021aec8288b480ed2e9c5bea30/docs/ci-integration.md).

The optional `quantfit inspect-run` supports both `hf/org/repo` and
`quantfit_gguf/<local-path or hf:org/repo/file.gguf>` pairs. Hub arms require
immutable revisions; local GGUF paths omit revision flags. On Linux with
`/proc`, the GGUF path manages its native servers, applies CPU/no-offload controls,
disables completion caching and retries, and closes both servers before the
pinned batched judge. The HF path observes its actual loaded dtype, source and
device through a separate provider; it does not inherit those native server controls.
The real GGUF CPU canary measured a full 40-probe F16/Q4 pair; its classifier
regression exit remained negative evidence. This does not establish native
verify-safety parity, GPU residency, sensitivity or human confirmation.

```bash
quantfit inspect-run \
  --baseline quantfit_gguf/./baseline.gguf --quant quantfit_gguf/./quant.gguf \
  --report inspect-drift.json --json
```

Provide matching, unquantized-baseline GGUF files and sufficient system RAM;
the managed Inspect pair admits two resident native servers, unlike sequential
native arms. Inspect logs are local capture-class data: an optional `--log-dir`
never belongs in Git, CI uploads or public bundles. See the
[HF contract](docs/inspect-run.md) and [GGUF contract](docs/inspect-gguf.md).

## GPU-aware quantization

**3-tier capacity.** `check` reads HF metadata (no download) to estimate the footprint:
fits VRAM (and RAM — weights always stage in CPU RAM first) → fast; too big for VRAM
but fits RAM+disk → same mechanism, slower (weights
load into CPU RAM and llm-compressor's default **sequential onloading** streams one
layer at a time to the GPU — no accelerate `device_map`; validated over-VRAM:
Qwen2.5-7B GPTQ, 15.2 GB bf16 on a 12 GB card, GPU peak 9.0 GB with 28 GB
process RSS observed, ~32 min); won't fit
even in RAM → refuse, naming the estimated limit. Fit estimates do not guarantee
peak runtime memory; the validated run above applies to that model and hardware.

Method caveat at over-VRAM sizes: **use `gptq`** — AWQ's 20-point grid search is
transfer-bound under onloading (observed ~2 h for a single 7B layer, projecting
50+ hours; the same AWQ completes fine at in-VRAM sizes).

**Method × scheme matrix** (one llm-compressor backend, vLLM-loadable):

| method | what | default scheme |
|---|---|---|
| `awq` | activation-aware weight quantization | W4A16_ASYM |
| `gptq` | Hessian/OBQ weight quant | W4A16 |
| `smoothquant` | activation smoothing + W8A8 | W8A8 |
| `fp8` | FP8 E4M3 dynamic, no calibration | FP8_DYNAMIC |
| `rtn` | round-to-nearest baseline | W4A16 |

Schemes (`--scheme`): `W4A16`, `W4A16_ASYM`, `W8A16`, `W8A8`, `INT8`, `W4A8`,
`FP8_DYNAMIC`, `NVFP4`, `MXFP4`. Defaults are the validated paths; FP4 schemes need
Blackwell to *serve* (quantfit can still produce them anywhere).

**GGUF** (`--method gguf`) for Ollama / llama.cpp: `Q2_K`..`Q8_0` + `IQ4_XS`.
Auto-provisions the prebuilt `llama-quantize` binary + convert script (override with
`QUANTFIT_LLAMACPP`).

One frozen packed calibration (wikitext-103 at a pinned dataset commit, 128 samples,
seq-len 2048, seed 42, group-size 128) is shared across the calibrated methods, so they
are comparable.

## What it is — and isn't

- It **quantizes** (wrapping llm-compressor + llama.cpp) and **checks safety
  preservation**. Both run end-to-end, validated on Qwen2.5-1.5B ([`CHANGELOG.md`](https://github.com/Sahil170595/quantfit/blob/main/CHANGELOG.md)
  0.1.0) and over-VRAM (Qwen2.5-7B GPTQ on a 12 GB card via sequential
  onloading, telemetry-confirmed CPU spill; the safety check covers 7B GGUF
  pairs with the F16 baseline in CPU RAM). The screen target manifest is planning
  input; actual coverage is the dated [screen result](validation/2026-08-21-screen-complete/),
  not membership in that manifest.
- It ships **transparent config help**, not auto-quantization: `quantfit plan --model <id>`
  shows the config a heuristic would pick and *why* (instant, no quantize); `quantfit
  probe --model <id>` measures per-bit-width quantization sensitivity (forward-only RTN-KL,
  a conservative upper bound — see the caveat in `policy/probe.py`).
- It does **not** *auto-pick the method and quantize* for you — you pass `--method`.
  Learned routing ([AMQ](https://arxiv.org/abs/2509.12019),
  [KL-Lens](https://arxiv.org/abs/2604.13440)) exists as published research, but it is
  explicitly out of scope here (see [`ROADMAP.md`](https://github.com/Sahil170595/quantfit/blob/main/ROADMAP.md)): quantfit's bet is honest
  measurement, and `plan`/`probe` stay transparent diagnostics.

## Docker

[`Dockerfile`](https://github.com/Sahil170595/quantfit/blob/main/Dockerfile) builds an isolated CUDA image. For GGUF in Docker, the official
`ghcr.io/ggml-org/llama.cpp:full` image carries the convert + quantize tooling.

## Analyze an existing run offline

```bash
quantfit resolution --report drift.json --calibration-report calibration.json --out resolution.json --json
quantfit emit model-card --report drift.json --calibration-report calibration.json
```

Supply a schema-2 calibration with matching immutable measurement scope. These
commands validate paired counts and use each arm's directional error bound for
separately labeled conditional resolution. The native report/QSR v0 verdict,
flagged counts and perfect-judge floor remain intact. Neither scope/hash binding
nor a model card authenticates human labels or establishes the statistical
assumptions. Without calibration, `emit model-card --report drift.json` retains
floor-only wording. See [CLI reference](docs/cli-reference.md) and
[synthetic functional evidence](validation/2026-10-05-calibrated-resolution/README.md).

## Portable aggregate evidence

```bash
quantfit bundle create --report drift.json --out evidence/ --json
quantfit bundle verify --bundle evidence/ --json
# Optional matching calibration and analysis; the output directory must be new.
quantfit bundle create --report drift.json --calibration-report calibration.json --resolution resolution.json --out calibrated-evidence/ --json
```

Fixed file roles and exact hashes make a bundle verifiable after relocation,
without weights, captures, network or optional model packages. Creation/verification
exit 0 means an aggregate bundle was created or its bytes are intact; exit 3
means a byte mismatch and exit 2 means unsafe/unsupported input. Original gate
no-answer/refusal states survive bundling. Integrity is not producer authenticity,
statistical validity or a safety GO. See [the bundle contract](docs/portable-evidence-bundles.md).

Candidate three-report T0 handoff (unreleased; needs the candidate checkout/wheel):

```bash
quantfit bundle replay-create --reports run-1.json run-2.json run-3.json --t0 native-t0.json --out replicate-evidence/ --json
quantfit bundle replay-verify --bundle relocated/replicate-evidence/ --json
```

All three reports and the original T0 bytes are preserved. Producer path strings
are unverified labels; verification returns a separate receiving-path T0 after
relocation, without reopening producer locations. An intact negative T0 still
exits 0 while `protocol_pass` stays false. It does not establish full-payload
repeatability, independent execution, human-label truth or scientific GO.
See [the three-report handoff contract](docs/replicate-bundles.md).

Candidate offline comparison keeps full-report agreement, native T0 and original
per-run outcomes separate:

```bash
quantfit repeatability --reports run-1.json run-2.json run-3.json --out agreement.json --junit agreement.xml --json
quantfit repeatability --bundle relocated/replicate-evidence/ --out agreement.json --junit agreement.xml --json
```

Only the four timestamp/runtime fields declared in
[the comparison contract](docs/repeatability.md) are ignored. All remaining
decoded types and values are exact. Exit 0 requires agreement and all original
native runs to pass; repeated original flags still exit 3, an otherwise agreeing
unmeasured axis exits 4, and native T0 refusal or malformed evidence exits 2.
No counts are pooled and agreement does not establish independent execution,
human-label truth, sensitivity or scientific GO.

## Fresh native cold replicates

On the qualified Linux `/proc` runner, use a new output directory:

```bash
quantfit cold-run \
  --baseline hf:unsloth/Phi-4-mini-instruct-GGUF/Phi-4-mini-instruct.BF16.gguf \
  --quant hf:unsloth/Phi-4-mini-instruct-GGUF/Phi-4-mini-instruct-Q4_K_M.gguf \
  --baseline-revision 78eb92a46fc37e6b524df991ed9aca9bc6aa7b80 \
  --quant-revision 78eb92a46fc37e6b524df991ed9aca9bc6aa7b80 \
  --out cold-runs/ --timeout-seconds 3600 --json
```

The omitted `--max-new-tokens` uses the shipped greedy default of 64. Each of
three fresh native children runs the full probe set without completion cache or
capture, with a per-child deadline and owned process-session cleanup. Weight
caches may be reused. Reports, original native exits, resource observations and
T0 remain separate: parent exit 0 means aggregate T0 agreement, 3 means T0
disagreement, and 2 is operational; a child's regression 3 or unmeasured-axis 4
never becomes a model pass. Windows refuses before creating output. Other POSIX
hosts do not inherit Linux's `/proc` cleanup qualification.

To check three existing actual source files after relocation, recompute T0 from
those paths rather than editing the producer's original T0 receipt:

```bash
quantfit t0 --reports cold-runs/run-1/report.json cold-runs/run-2/report.json cold-runs/run-3/report.json --out relocated-t0.json --json
```

T0 validates aggregate agreement and identity, not human confirmation, detection
sensitivity, independent hardware or cross-hardware tolerance. Reference admission
also requires full report repeatability, permitting only the protocol's explicit
timestamp/runtime differences. See [the cold-run contract](docs/cold-replicate-runner.md).

## Public campaigns and offline reference artifacts

The [2026-10-09 hosted Phi4 CPU campaign](https://github.com/Sahil170595/quantfit/actions/runs/37890682118)
ran the pinned BF16/Q4_K_M pair over all 40 probes in three fresh native
processes using the omitted token flag's greedy-64 default. Each run had
**2/20 classifier-flagged over-refusal flips** and **0/12 dangerous-axis flags**:
the detector did not fire on that axis. Native exits **3/3/3** remain regressions;
parent cold-run exit **0** records passing T0, and full-report repeatability
also passed. These are repeats of one pair, not three independent pairs. The
new flags have no human adjudication.

The aggregate-only [public dataset](https://huggingface.co/datasets/Crusadersk/quantfit-reference-reports)
is pinned at immutable commit `3a4ff4e086f9d72ad828134873b01fa19b550059`; downloaded bytes were checked
against the source SHA256 values. Public candidate evidence and registry admission
are separate. The built-in registry has **zero qualified reference entries**:
fresh unconfirmed flags block this candidate's admission. Its public reports
preserve the negative result without transferring historical human confirmations.

```bash
quantfit references list --json
quantfit references verify --slug NAME --report report.json --json
quantfit verify --model ./out --json
```

The verification example requires a registered slug from `references list`;
the built-in registry currently has none. Reference verification checks declared bytes, not a rerun hash or the validity
of the science. `verify --model` checks a quantized artifact's format/metadata; it
does not run the paired safety measurement. An explicit `--registry registry.json`
selects an external registry without registering or publishing it. See
[publication criteria](docs/reference-reports-v0.md), the
[bounded campaign](docs/reference-campaign-v0.md), and
[CLI reference](docs/cli-reference.md). No new T4 reproduction, sensitivity,
human-adjudication, cross-hardware or QSR v1 freeze follows from a publication.

## License

Apache-2.0.
