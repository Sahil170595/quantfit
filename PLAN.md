# quantfit — build plan

A GPU-aware, SOTA-flexible LLM quantization CLI. `pip install quantfit`, point at any
Hugging Face causal-LM, pick a method + target precision, and it quantizes **if it fits**
(or offloads if it doesn't), emitting a vLLM- or llama.cpp-loadable artifact.

## Principle
Build it right, ship only what runs. Every method is validated end-to-end on real
hardware before it lands — no method ships on `py_compile` alone.

## Status
- **v0.1 (done):** `check` GPU pre-flight, AWQ/GPTQ via llm-compressor, HF push, Docker, tests.
- **M1 ✅ pushed** — base engine validated (qwen2.5-1.5b AWQ → real artifact; load-smoke-test PASS).
- **M2 ✅ pushed** — method×scheme matrix; AWQ + FP8 + GPTQ validated on qwen2.5-1.5b.
- **M3 ✅ pushed** — 3-tier capacity (gpu/offload/refuse), cache-aware disk, named limits; offload codepath validated.
- **M4 ✅ pushed** — GGUF backend (llama.cpp), auto-provisions binary + repo; validated qwen2.5-1.5b → Q4_K_M (0.92 GB, valid GGUF, f16 cleaned).
- **M5 ✅ pushed** — `verify` command (smoke-load), README refresh, CI workflow; 19 tests.
- **M6 🔶 next** — regenerate the real spine via the tool (gemma-2-2b, controlled wikitext-103) → push to HF.
- **M7** — release polish (version, PyPI metadata, tag).

## v0.2 — the great tool

### Backends
1. **compressed-tensors** (llm-compressor) — the workhorse, vLLM-loadable:
   - Algorithms: `awq`, `gptq`, `autoround`, `smoothquant`, `rtn`
   - Schemes: `W4A16`, `W4A16_ASYM`, `W8A16`, `W8A8`, `INT8`, `W4A8`, `FP8_DYNAMIC`, `NVFP4`, `MXFP4`
2. **gguf** (llama.cpp) — `Q2_K`..`Q8_0` + IQ-quants → Ollama/llama.cpp (best-effort; may be Docker-only on Windows)
3. **Deferred / opt-in:** gptq-format (gptqmodel), HQQ, bitsandbytes, AQLM/QuIP# (sub-3-bit). Only if each actually runs.

### Capabilities
- **3-tier fit:** fits VRAM → in-GPU (fast); else CPU/disk **offload** (any size — 27B on a 12 GB GPU); else refuse.
- **Frozen calibration spec** (wikitext-103, 128 samples, seq-len 2048, seed 42, gs 128) shared across methods → comparable, not confounded.
- `quantfit list` — print every supported (method × scheme) combo.
- Auto model card with full provenance fingerprint.

### Architecture
```
quantfit/
  backends/  base.py · compressed_tensors.py · gguf.py
  registry.py   # method/scheme catalog + valid combos
  fit.py        # 3-tier capacity logic (vram / offload / refuse)
  spec.py · gpufit.py (done) · cli.py (expanded)
tests/
```

### Milestones (each milestone = one validated, pushed chunk)
- **M1** — base engine validated end-to-end (qwen2.5-1.5b AWQ) + v0.1 pushed.  *(in progress)*
- **M2** — backend abstraction + registry + compressed-tensors full method×scheme matrix. Validate: awq-W4A16, gptq-W4A16, fp8-dynamic, w8a8 on qwen2.5-1.5b.
- **M3** — 3-tier fit + offload. Validate: offload-quantize a 7B on the 12 GB GPU.
- **M4** — GGUF backend. Validate: produce Q4_K_M + load it.
- **M5** — CLI expansion (`list`, `--method/--scheme/--bits/--offload/--push`) + docs + tests.
- **M6** — regenerate the real spine via the tool (gemma-2-2b + re-standardized AWQ/GPTQ) → push to HF.
- **M7** — v0.2 release polish (README, CI, PyPI metadata) + tag.

### Execution model
Main thread drives, integrates, validates on real GPU, and pushes each milestone. Workflows /
subagents fan out the parallelizable parts (multi-library API research, independent module drafts,
test authoring); their output is re-verified on the main thread before commit. GPU validation
serializes (one GPU).

## Decision log (autonomous)
- **D1** — Tier-2 sub-3-bit (AQLM/QuIP#) **deferred** to opt-in extras; "ensure it works" wins over breadth. Revisit after the reliable matrix ships.
- **D2** — Both AWQ and GPTQ route through llm-compressor (one library, shared calibration, compressed-tensors output) → algorithm-only comparison, and dodges gptqmodel's Windows cp1252 logger crash.
- **D3** — Calibration set is pre-tokenized in-tool (not llm-compressor's text_column auto-path, which fed float input_ids into the embedding). Deterministic under the frozen spec.
- **D4** — Name `quantfit` (PyPI-available); GPU-fit is the headline so the name carries the value prop.
- **D5** — Disk is a first-class capacity tier (needed in both gpu and offload modes), cache-aware (don't count a download you already have); refusals name the actual limiting resource (disk vs machine).
- **D6** — The dev machine's C: is ~99% full (~14 GB free), so real large-model offload can't be demonstrated locally for lack of download space. The 3-tier routing is unit-tested + validated on real model metadata; the offload codepath is validated on a cached small model. Full large-model offload validation is a Docker/cloud task — a machine constraint, not a tool defect.
