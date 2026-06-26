# quantfit

**Quantize an LLM if it fits your GPU.** A small, GPU-aware quantization CLI that
covers the SOTA method matrix and tells you up front whether a model will fit —
*before* downloading 30 GB of weights.

```bash
pip install quantfit

quantfit check  --model Qwen/Qwen2.5-7B-Instruct          # will it fit? (no download)
quantfit list                                             # every method + scheme
quantfit quantize --model Qwen/Qwen2.5-1.5B-Instruct --method awq --out ./out
quantfit verify --model ./out                             # load it + generate
```

## Why

Most quantization runs die one of two ways: an OOM crash 20 minutes into a job, or
a pile of hand-made checkpoints with drifting calibration. quantfit fixes both — a
capacity pre-flight that refuses (or offloads) honestly, and one frozen calibration
spec shared across methods so results are comparable.

## What it does

**GPU-aware, 3-tier capacity.** Reads HF file metadata (no download) to estimate the
footprint, then decides:
- fits VRAM → quantize in-GPU (fast)
- too big for VRAM but fits RAM+disk → **CPU offload** (slower; a 27B can quantize on a 12 GB GPU)
- won't fit even offloaded → refuse, naming the actual limit (disk / machine)

**SOTA method × scheme matrix** (one `llm-compressor` backend, vLLM-loadable):

| method | what | default scheme |
|---|---|---|
| `awq` | activation-aware weight quant (best 4-bit quality) | W4A16_ASYM |
| `gptq` | Hessian/OBQ weight quant | W4A16 |
| `smoothquant` | activation smoothing + W8A8 | W8A8 |
| `fp8` | FP8 E4M3 dynamic, no calibration | FP8_DYNAMIC |
| `rtn` | round-to-nearest baseline, no calibration | W4A16 |

Schemes (override with `--scheme`): `W4A16`, `W4A16_ASYM`, `W8A16`, `W8A8`, `INT8`,
`W4A8`, `FP8_DYNAMIC`, `NVFP4`, `MXFP4`.

**GGUF** (`--method gguf`) for the Ollama / llama.cpp / LM Studio world: `Q2_K`..`Q8_0`
plus `IQ4_XS`. Auto-provisions the prebuilt `llama-quantize` binary + convert script
(override with `QUANTFIT_LLAMACPP=/path/to/llama.cpp`).

**One frozen calibration spec.** AWQ/GPTQ/AutoRound/SmoothQuant all calibrate on the
*same* data (wikitext-103, 128 samples, seq-len 2048, seed 42, group-size 128) — so
the methods are comparable, not confounded. fp8/rtn/gguf skip calibration.

## Examples

```bash
# 4-bit AWQ, push to the Hub
quantfit quantize --model meta-llama/Llama-3.2-3B-Instruct --method awq \
                  --out ./out --push you/llama3.2-3b-awq-4bit

# FP8 (no calibration), or a frontier FP4 scheme
quantfit quantize --model Qwen/Qwen2.5-1.5B-Instruct --method fp8 --out ./out
quantfit quantize --model Qwen/Qwen2.5-1.5B-Instruct --method rtn --scheme NVFP4 --out ./out

# Big model on a small GPU (auto-offloads; force with --offload)
quantfit quantize --model Qwen/Qwen2.5-32B-Instruct --method gptq --out ./out

# GGUF for Ollama
quantfit quantize --model Qwen/Qwen2.5-1.5B-Instruct --method gguf --scheme Q4_K_M --out ./out
```

## Docker

`Dockerfile` builds an isolated CUDA image so quantfit never touches your global Python.
For GGUF in Docker, the official `ghcr.io/ggml-org/llama.cpp:full` image carries the
convert + quantize tooling.

## Scope

quantfit only quantizes. Evaluation, safety/quality measurement, and benchmarking live
elsewhere — this tool produces the artifact, nothing more.

## License

Apache-2.0.
