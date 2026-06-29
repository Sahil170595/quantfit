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

    common = dict(targets=_TARGETS, ignore=_IGNORE)
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
    packed dataset serves every calibrated method. Deterministic under the spec.
    """
    from datasets import Dataset, load_dataset

    ds = load_dataset(spec.calib_dataset, spec.calib_config, split=spec.calib_split, token=token)
    ds = ds.filter(lambda ex: ex["text"] is not None and ex["text"].strip() != "")
    ds = ds.shuffle(seed=spec.seed)

    needed = spec.calib_samples * spec.calib_seqlen
    buf: list[int] = []
    for ex in ds:
        buf.extend(tokenizer(ex["text"]).input_ids)
        if len(buf) >= needed:
            break
    # Only chunk over tokens actually collected; a short dataset must error, not
    # silently emit empty blocks (range(0, needed, ...) would slice past len(buf)).
    usable = (len(buf) // spec.calib_seqlen) * spec.calib_seqlen
    blocks = [buf[i : i + spec.calib_seqlen] for i in range(0, min(needed, usable), spec.calib_seqlen)]
    if len(blocks) < spec.calib_samples:
        raise ValueError(
            f"calibration set yielded {len(blocks)} of {spec.calib_samples} requested sequences "
            f"({len(buf)} tokens, need {needed}); use a larger calib set or fewer/shorter samples"
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
    offload: bool = False,
) -> Path:
    """Run llm-compressor oneshot for `method`/`scheme` into `out_dir`."""
    from llmcompressor import oneshot
    from transformers import AutoModelForCausalLM, AutoTokenizer

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(model_id, token=token)

    # Default: hand oneshot the model id and let it load onto the GPU. For offload, load
    # with accelerate's device_map so WEIGHTS spill to CPU RAM (the sequential pipeline
    # then quantizes layer-by-layer). Validated on models that fit VRAM; large-model
    # (exceeds-VRAM) offload is the design target, NOT yet validated end-to-end.
    model: object = model_id
    if offload:
        model = AutoModelForCausalLM.from_pretrained(model_id, device_map="auto", torch_dtype="auto", token=token)

    kwargs: dict = dict(
        model=model,
        tokenizer=tokenizer,
        recipe=build_recipe(method, scheme),
        output_dir=str(out),
    )
    if needs_calibration:
        kwargs.update(
            dataset=calib_dataset(spec, tokenizer, token=token),
            num_calibration_samples=spec.calib_samples,
            max_seq_length=spec.calib_seqlen,
        )
    oneshot(**kwargs)
    return out
