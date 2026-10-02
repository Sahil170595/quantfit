"""compressed-tensors backend (llm-compressor): the method × scheme matrix.

awq / gptq / smoothquant calibrate; fp8 / rtn do not. All emit
compressed-tensors (vLLM-loadable). For the calibrated algorithms the only
cross-method difference is the algorithm itself — same calibration, same format
— so the methods are comparable, not confounded.
"""

from __future__ import annotations

from pathlib import Path

from quantfit.spec import QuantSpec

_TARGETS = ["Linear"]
_IGNORE = ["lm_head"]
_SMOOTHING_STRENGTH = 0.8  # SmoothQuant migration strength (standard default)


def build_recipe(method: str, scheme: str):
    """Construct the llm-compressor recipe (modifier or modifier list) for a method."""
    from llmcompressor.modifiers.awq import AWQModifier
    from llmcompressor.modifiers.quantization import GPTQModifier, QuantizationModifier
    from llmcompressor.modifiers.smoothquant import SmoothQuantModifier

    common = {"targets": _TARGETS, "ignore": _IGNORE}
    if method == "awq":
        return AWQModifier(scheme=scheme, **common)
    if method == "gptq":
        return GPTQModifier(scheme=scheme, **common)
    if method == "smoothquant":
        return [
            SmoothQuantModifier(smoothing_strength=_SMOOTHING_STRENGTH),
            GPTQModifier(scheme=scheme, **common),
        ]
    if method in ("fp8", "rtn"):
        return QuantizationModifier(scheme=scheme, **common)
    raise ValueError(f"no compressed-tensors recipe for method {method!r}")


def calib_dataset(spec: QuantSpec, tokenizer, token: str | None = None):
    """Packed fixed-length calibration: concatenate text, chunk into seq-len blocks.

    Uniform-length sequences are required by AutoRound (it stacks samples and
    rejects ragged lengths) and are the standard GPTQ/AWQ calibration form, so one
    packed dataset serves every calibrated method. Deterministic under the spec. The
    packing is `calibset.packed_blocks`, shared with `probe`, so the probe measures the
    first tokens of exactly this stream.
    """
    from datasets import Dataset

    from quantfit.calibset import packed_blocks

    blocks = packed_blocks(spec, tokenizer, spec.calib_samples, spec.calib_seqlen, token=token)
    if len(blocks) < spec.calib_samples:
        # RuntimeError: operational (dataset too short), so the CLI exits cleanly. A short set
        # must error here, not silently calibrate on fewer sequences.
        raise RuntimeError(
            f"calibration set yielded {len(blocks)} of {spec.calib_samples} requested sequences of "
            f"{spec.calib_seqlen} tokens; use a larger calib set or fewer/shorter samples"
        )
    return Dataset.from_dict({"input_ids": blocks, "attention_mask": [[1] * len(b) for b in blocks]})


def quantize_ct(
    model_id: str,
    method: str,
    scheme: str,
    out_dir: str,
    spec: QuantSpec,
    needs_calibration: bool,
    token: str | None = None,
) -> Path:
    """Run llm-compressor oneshot for `method`/`scheme` into `out_dir`."""
    from llmcompressor import oneshot
    from transformers import AutoModelForCausalLM, AutoTokenizer

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(model_id, token=token)

    # Load on CPU (no device_map) — llm-compressor's recommended pattern. Its default
    # sequential-onloading pipeline moves one layer at a time to the GPU during
    # calibration, so the same path serves models that fit VRAM and models that don't.
    # accelerate's device_map="auto" is NOT used: it fights the sequential pipeline.
    # In-GPU-sized models are validated end-to-end; exceeds-VRAM models remain the
    # design target, not yet validated at scale (see ROADMAP 0.4b).
    model = AutoModelForCausalLM.from_pretrained(model_id, dtype="auto", token=token)

    kwargs: dict = {
        "model": model,
        "tokenizer": tokenizer,
        "recipe": build_recipe(method, scheme),
        "output_dir": str(out),
    }
    if needs_calibration:
        kwargs.update(
            dataset=calib_dataset(spec, tokenizer, token=token),
            num_calibration_samples=spec.calib_samples,
            max_seq_length=spec.calib_seqlen,
        )
    oneshot(**kwargs)
    return out
