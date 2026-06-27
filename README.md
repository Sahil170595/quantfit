# quantfit

**Quantize an LLM — and check it still refuses what it should.**

Quantization makes a model cheaper to serve. It can also quietly strip safety
behavior: a 4-bit model that answers prompts the fp16 model refused is a regression
you will not see in a perplexity number. `quantfit` quantizes across the SOTA method
matrix, is honest about whether a model fits your GPU, and — uniquely — measures the
**safety tax** of the quantization it just performed.

```bash
pip install quantfit

quantfit check        --model Qwen/Qwen2.5-7B-Instruct                 # will it fit? (no download)
quantfit quantize     --model Qwen/Qwen2.5-1.5B-Instruct --method awq --out ./out
quantfit verify-safety --fp16 Qwen/Qwen2.5-1.5B-Instruct --quant ./out  # did quantization break refusals?
```

## The safety check — what nothing else does

`verify-safety` generates from both the fp16 baseline and the quantized model over a
curated probe set, judges each response refusal/compliance with a local classifier,
and reports the tax as a **vector**, the way it actually matters:

```
safety-tax over 40 probes (REGRESSION):
  refusal-robustness (expected-unsafe n=12): fp16 refused 12 -> quant 12 | 0 harmful-compliance regressions
  over-refusal       (expected-safe   n=28): fp16 refused 18 -> quant 18 | 2 new false refusals
  by zone: borderline[10->10/16] clear_safe[8->8/12] clear_unsafe[12->12/12]
```

Two axes, not one number:
- **refusal-robustness** — on prompts that *should* be refused, did the quant start
  complying? (the dangerous direction)
- **over-refusal** — on prompts that *should* be answered, did the quant start
  refusing? (the usability direction)

A scalar refusal-delta can read 0 while both axes move in opposite directions; the
vector + per-zone breakdown catches it. Local judge, curated public probes, no
external API and no raw harmful corpora — so the check is distributable.

## GPU-aware quantization

**3-tier capacity.** `check` reads HF metadata (no download) to estimate the footprint:
fits VRAM → quantize in-GPU; too big for VRAM but fits RAM+disk → **CPU offload** (a
27B can quantize on a 12 GB GPU); won't fit even offloaded → refuse, naming the real
limit. No OOM 20 minutes into a job.

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

**GGUF** (`--method gguf`) for Ollama / llama.cpp: `Q2_K`..`Q8_0` + IQ-quants.
Auto-provisions the prebuilt `llama-quantize` binary + convert script (override with
`QUANTFIT_LLAMACPP`).

One frozen packed calibration (wikitext-103, 128 samples, seq-len 2048, seed 42,
group-size 128) is shared across the calibrated methods, so they are comparable.

## What it is — and isn't

- It **quantizes** (wrapping llm-compressor + llama.cpp) and **checks safety
  preservation**. Both are real and validated end-to-end.
- It does **not** auto-select the config for you yet — you pick `--method`. Automatic
  config selection is a real capability, but it is published research
  ([AMQ](https://arxiv.org/abs/2509.12019),
  [KL-Lens](https://arxiv.org/abs/2604.13440)); a routing layer that *implements* it is
  planned, not claimed here.

## Docker

`Dockerfile` builds an isolated CUDA image. For GGUF in Docker, the official
`ghcr.io/ggml-org/llama.cpp:full` image carries the convert + quantize tooling.

## License

Apache-2.0.
