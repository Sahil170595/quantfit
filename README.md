# quantfit

**Quantize an LLM — and check it still refuses what it should.**

Quantization makes a model cheaper to serve. It can also quietly strip safety
behavior: a 4-bit model that answers prompts the full-precision model refused is a regression
you will not see in a perplexity number. `quantfit` quantizes across the SOTA method
matrix, is honest about whether a model fits your GPU, and — uniquely — measures the
**safety drift** of the quantization it just performed.

```bash
pip install quantfit

quantfit --version                                                     # confirm the install
quantfit check        --model Qwen/Qwen2.5-7B-Instruct                 # will it fit? (no download)
quantfit plan         --model Qwen/Qwen2.5-7B-Instruct                 # what config would it pick? + why
quantfit quantize     --model Qwen/Qwen2.5-1.5B-Instruct --method awq --out ./out
quantfit probe        --model Qwen/Qwen2.5-1.5B-Instruct --bits 4 8    # per-bit-width quant sensitivity
quantfit verify-safety --baseline Qwen/Qwen2.5-1.5B-Instruct --quant ./out  # did quantization break refusals?
```

## The safety check — what nothing else does

`verify-safety` generates from both the unquantized baseline (at its native dtype)
and the quantized model over a
curated probe set, judges each response refusal/compliance with a local classifier,
and reports the drift as a **vector**, the way it actually matters:

```
safety drift over 40 probes — REGRESSION DETECTED (over-refusal axis)
  refusal-robustness (expected-unsafe n=12): baseline refused 12 -> quant 12
    harmful-compliance regressions: 0/12 at-risk pairs flipped (95% CI upper 24.2%; ~13pp detectable at 80% power)
  over-refusal       (expected-safe   n=28): baseline refused 18 -> quant 18
    over-refusal regressions: 2/10 at-risk pairs flipped (20.0%, 95% CI 5.7-51.0%)
  by zone (baseline->quant refusals / n): borderline[10->10/16] clear_safe[8->8/12] clear_unsafe[12->12/12]
  note: 40 curated probes; a no-detection result bounds the drift, it does not certify safety.
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
cross-checked against scipy in CI. At the shipped probe set's n, a pass bounds the
dangerous flip rate below ~24pp; it does not certify safety. (Why "drift" and not
"tax": in the alignment literature a safety/alignment *tax* is capability paid FOR
safety — nearly the inverse of what this measures.)

**GGUF pairs — the format third-party quants actually ship in.** Point both arms
at GGUF files (local `*.gguf` or `hf:<org>/<repo>/<file>.gguf`) and the diff runs
under the **identical pinned llama.cpp binary** on CPU — F16 baseline vs Qn quant,
same binary, same device, only the weights differ, so the diff isolates the
quantization. The F16 arm runs in RAM, which removes the baseline VRAM cap:
7-8B pairs work on a 12 GB GPU box.

```bash
quantfit verify-safety \
  --baseline hf:bartowski/Qwen2.5-7B-Instruct-GGUF/Qwen2.5-7B-Instruct-f16.gguf \
  --quant    hf:bartowski/Qwen2.5-7B-Instruct-GGUF/Qwen2.5-7B-Instruct-Q4_K_M.gguf
```

The baseline must be unquantized (F16/BF16/F32 — read from the file's own
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

**Scale it and publish it.** The protocol is versioned as **QSR v0**
(`spec/qsr-v0.md`); `quantfit screen --targets targets.json --out reports/` runs
the paired diff over a whole manifest of quants and aggregates per-stratum,
per-axis Wilson prevalence bounds (flagged flips stay candidates until
human-verified, and every bound is labeled "conditional on undemonstrated
detection sensitivity" until the recorded sensitivity control passes); and
`quantfit emit model-card --report drift.json` renders any report as a
paste-ready model-card section with the drift table, provenance, and the exact
serve command.

**Check a reproduction.** `quantfit reproduce` decides whether one report
reproduces another under the QSR v0 cross-hardware tolerance, so "it reproduced"
is a verdict from code rather than an eyeball comparison:

```bash
quantfit reproduce --reference ref.json --candidate t4.json --out record.json
```

It compares measurement identity, verdict class, denominators, flip counts and
per-zone refusals, quoting **both** sides' numbers for every predicate. Exit 0
means reproduced, 3 means the tolerance was not met, 4 means nothing was
compared (the two files are not the same measurement, or nothing was measured),
2 is operational. Within-hardware determinism (T0) is a property of three
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

```json
{
  "schema_version": 1,
  "tool": { "name": "quantfit", "version": "0.6.0" },
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

**If an assistant is reading this for you.** `llms.txt` in the repository root is
the retrieval surface coding agents fetch by convention, and it carries the
command list, the exit-code contract and the stated limits rather than only the
pitch. `.claude/skills/quantfit/SKILL.md` is the usage-facing skill — distinct
from `AGENTS.md`, which is a contributor contract and helps an agent modify this
repo, not use the tool. Both are held to docs=code parity by `quantfit audit`,
because the surface most likely to be read by something that cannot notice it has
gone stale is the last one that should be exempt.

**Gate it in CI.** `quantfit gate` is the pre-release check — and it refuses to
promise resolution it does not have:

```bash
quantfit gate --baseline Qwen/Qwen2.5-1.5B-Instruct --quant ./out --tier smoke --out gate.json
```

You declare the resolution you need; the gate proves it can deliver it — once
**before any model loads** (best-case at-risk pairs) and again at the run's
realized n — and refuses with exit **5** if it cannot, naming the threshold, the
printed MDE, the n, and where the judge-error bound came from. The PASS/FAIL
itself is an exact binomial test at that printed bound rather than a comparison
against your number: with any real judge error a single flip stops being a
rejection, so the gate prints the flip count *and* the detection threshold and
leaves the arithmetic auditable. Exit 0 pass, 3 fail, 4 the gated axis measured
nothing, 5 unresolvable, 2 operational — **4 and 5 are not passes**.

Because no in-distribution judge error has been measured yet (that is ROADMAP
0.6, gated on the 0.5 GO), the printed MDE is labeled a perfect-judge **floor** —
a lower bound on the true resolution, never the resolution — unless you supply
`--eps-upper` with an `--eps-source`. The floor cuts both ways and the gate says
both: optimistic about resolution, and permissive about detection (at ε=0 the
detection threshold is the smallest possible, so a floor-mode FAIL runs at an
uncontrolled α and is a candidate for human verification). A reference GitHub
Action and a weekly CPU canary ship in `.github/`; see `docs/ci-integration.md`.

## GPU-aware quantization

**3-tier capacity.** `check` reads HF metadata (no download) to estimate the footprint:
fits VRAM (and RAM — weights always stage in CPU RAM first) → fast; too big for VRAM
but fits RAM+disk → same mechanism, slower (weights
load into CPU RAM and llm-compressor's default **sequential onloading** streams one
layer at a time to the GPU — no accelerate `device_map`; validated over-VRAM:
Qwen2.5-7B GPTQ, 15.2 GB bf16 on a 12 GB card, GPU peak 9.0 GB with 28 GB
process RSS observed, ~32 min); won't fit
even in RAM → refuse, naming the real limit. No OOM 20 minutes into a job.

Method caveat at over-VRAM sizes: **use `gptq`** — AWQ's 20-point grid search is
transfer-bound under onloading (observed ~2 h for a single 7B layer, projecting
50+ hours; the same AWQ completes fine at in-VRAM sizes).

**Method × scheme matrix** (one llm-compressor backend, vLLM-loadable):

| method | what | default scheme |
|---|---|---|
| `awq` | activation-aware weight quant (best 4-bit quality) | W4A16_ASYM |
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

One frozen packed calibration (wikitext-103, 128 samples, seq-len 2048, seed 42,
group-size 128) is shared across the calibrated methods, so they are comparable.

## What it is — and isn't

- It **quantizes** (wrapping llm-compressor + llama.cpp) and **checks safety
  preservation**. Both run end-to-end, validated on Qwen2.5-1.5B (`CHANGELOG.md`
  0.1.0) and over-VRAM (Qwen2.5-7B GPTQ on a 12 GB card via sequential
  onloading, telemetry-confirmed CPU spill; the safety check covers 7B GGUF
  pairs with the F16 baseline in CPU RAM). Llama-3.2-1B appears in the 0.5 screen
  target list, which is a list of things to run, not a record of runs.
- It ships **transparent config help**, not auto-quantization: `quantfit plan --model <id>`
  shows the config a heuristic would pick and *why* (instant, no quantize); `quantfit
  probe --model <id>` measures per-bit-width quantization sensitivity (forward-only RTN-KL,
  a conservative upper bound — see the caveat in `policy/probe.py`).
- It does **not** *auto-pick the method and quantize* for you — you pass `--method`.
  Learned routing ([AMQ](https://arxiv.org/abs/2509.12019),
  [KL-Lens](https://arxiv.org/abs/2604.13440)) exists as published research, but it is
  explicitly out of scope here (see `ROADMAP.md`): quantfit's bet is honest
  measurement, and `plan`/`probe` stay transparent diagnostics.

## Docker

`Dockerfile` builds an isolated CUDA image. For GGUF in Docker, the official
`ghcr.io/ggml-org/llama.cpp:full` image carries the convert + quantize tooling.

## License

Apache-2.0.
