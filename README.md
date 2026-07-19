# quantfit

**Quantize an LLM — and check it still refuses what it should.**

Quantization makes a model cheaper to serve. It can also quietly strip safety
behavior: a 4-bit model that answers prompts the full-precision model refused is a regression
you will not see in a perplexity number. `quantfit` quantizes across the SOTA method
matrix, is honest about whether a model fits your GPU, and — uniquely — measures the
**safety drift** of the quantization it just performed.

```bash
pip install quantfit

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

## GPU-aware quantization

**3-tier capacity.** `check` reads HF metadata (no download) to estimate the footprint:
fits VRAM (and RAM — weights always stage in CPU RAM first) → fast; too big for VRAM
but fits RAM+disk → same mechanism, slower (weights
load into CPU RAM and llm-compressor's default **sequential onloading** streams one
layer at a time to the GPU — no accelerate `device_map`; validated at in-GPU sizes,
the exceeds-VRAM case is the design target — see *What it is — and isn't*); won't fit
even in RAM → refuse, naming the real limit. No OOM 20 minutes into a job.

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
  preservation**. Both run end-to-end and are validated on small models (Qwen-1.5B,
  Llama-1B); exceeds-VRAM quantization (llm-compressor's sequential onloading) is the
  intended design, not yet validated at scale.
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
