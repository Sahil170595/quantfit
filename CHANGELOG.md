# Changelog

## 0.2.0 (unreleased)

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
