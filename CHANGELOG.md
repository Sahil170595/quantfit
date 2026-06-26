# Changelog

## 0.2.0
- **SOTA method × scheme matrix** via one `llm-compressor` backend: awq, gptq,
  autoround, smoothquant, fp8, rtn × W4A16 / W8A16 / W8A8 / W4A8 / FP8 / NVFP4 / MXFP4.
- **GGUF backend** (llama.cpp): Q2_K..Q8_0 + IQ-quants; auto-provisions the prebuilt
  `llama-quantize` binary + convert script (override with `QUANTFIT_LLAMACPP`).
- **3-tier capacity**: in-GPU / CPU-offload / refuse, with cache-aware disk accounting;
  refusals name the actual limiting resource. Big models auto-offload instead of failing.
- **`quantfit list`** (catalog) and **`quantfit verify`** (smoke-load + generate).
- One frozen calibration spec shared across calibrated methods (wikitext-103, 128
  samples, seq-len 2048, seed 42, group-size 128) so methods are comparable.
- CI (unit tests on push/PR); README + Docker.
- Validated end-to-end on qwen2.5-1.5b: AWQ / FP8 / GPTQ / GGUF-Q4_K_M, CPU-offload,
  and a transformers load-smoke-test ("Paris, and the largest city in France").

## 0.1.0
- Initial: GPU pre-flight `check`, AWQ/GPTQ via llm-compressor, HF push, Docker, tests.
