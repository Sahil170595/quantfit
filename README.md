# quantfit

**Quantize an LLM if it fits your GPU.** A small, GPU-aware 4-bit quantization CLI.
Point it at any Hugging Face causal-LM, pick a method, and it checks your GPU
*before* downloading 30 GB of weights — fits, it quantizes; doesn't, it tells you
how much VRAM you'd need instead of dying with an OOM 20 minutes in.

```bash
pip install quantfit

# Will it fit? (no download — reads Hub file metadata)
quantfit check  --model Qwen/Qwen2.5-7B-Instruct

# Quantize (AWQ or GPTQ), optionally push to the Hub
quantfit quantize --model Qwen/Qwen2.5-1.5B-Instruct --method awq  --out ./out
quantfit quantize --model meta-llama/Llama-3.2-3B-Instruct --method gptq \
                  --out ./out --push your-hf-username/llama3.2-3b-gptq-4bit
```

## What it does

- **GPU pre-flight.** Estimates the FP16 footprint from Hub metadata × a
  calibration-overhead factor + headroom, and compares to free VRAM. A clear
  `CAN'T QUANTIZE: needs ~X GB, Y GB free` beats a mid-run crash.
- **One frozen calibration spec.** AWQ and GPTQ use the *same* calibration data
  (wikitext-103, 128 samples, seq-len 2048, seed 42, group-size 128) so the two
  methods are comparable, not confounded by differing calibration.
- **Methods.** `awq` (W4A16 via llm-compressor) and `gptq` (W4A16 via GPTQModel).
  Both auto-load in vLLM.
- **Provenance.** Every output carries the spec fingerprint in its model card.

## Not in scope

quantfit only quantizes. Evaluation, safety/quality measurement, and
benchmarking live elsewhere — this tool produces the artifact, nothing more.

## License

Apache-2.0.
