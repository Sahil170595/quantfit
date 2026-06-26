"""compressed-tensors backend (llm-compressor): the method × scheme matrix.

awq / gptq / autoround / smoothquant calibrate; fp8 / rtn do not. All emit
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

    ds = load_dataset(
        spec.calib_dataset, spec.calib_config, split=spec.calib_split, token=token
    )
    ds = ds.filter(lambda ex: ex["text"] is not None and ex["text"].strip() != "")
    ds = ds.shuffle(seed=spec.seed)

    needed = spec.calib_samples * spec.calib_seqlen
    buf: list[int] = []
    for ex in ds:
        buf.extend(tokenizer(ex["text"]).input_ids)
        if len(buf) >= needed:
            break
    blocks = [
        buf[i : i + spec.calib_seqlen]
        for i in range(0, needed, spec.calib_seqlen)
    ]
    return Dataset.from_dict(
        {"input_ids": blocks, "attention_mask": [[1] * len(b) for b in blocks]}
    )


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
    from transformers import AutoTokenizer

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(model_id, token=token)

    kwargs: dict = dict(
        model=model_id,
        tokenizer=tokenizer,
        recipe=build_recipe(method, scheme),
        output_dir=str(out),
    )
    if offload:
        # Quantize layer-by-layer with the model held on CPU -> fits any size.
        kwargs["sequential_offload_device"] = "cpu"
    if needs_calibration:
        kwargs.update(
            dataset=calib_dataset(spec, tokenizer, token=token),
            num_calibration_samples=spec.calib_samples,
            max_seq_length=spec.calib_seqlen,
        )
    oneshot(**kwargs)
    return out
