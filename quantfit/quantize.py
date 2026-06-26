"""The quantization engine — AWQ/GPTQ under the frozen spec.

Both methods run through llm-compressor, so they share calibration data and
output format (compressed-tensors, vLLM-loadable). The only difference is the
algorithm: AWQ activation-aware scaling (W4A16 asymmetric) vs GPTQ Hessian
(W4A16 symmetric). Same calibration + same format => the two are comparable,
not confounded.
"""
from __future__ import annotations

from pathlib import Path

from quantfit.gpufit import check_fit
from quantfit.spec import DEFAULT_SPEC, QuantSpec

METHODS = ("awq", "gptq")
# compressed-tensors scheme per method; AWQ is asymmetric, GPTQ symmetric — both
# 4-bit weights / 16-bit activations, group_size 128 (the scheme preset).
_SCHEME = {"awq": "W4A16_ASYM", "gptq": "W4A16"}
_IGNORE = ["lm_head"]
_TARGETS = ["Linear"]


class CannotQuantize(RuntimeError):
    """Raised when the model won't fit the GPU (pre-flight refusal)."""


def _recipe(method: str):
    from llmcompressor.modifiers.awq import AWQModifier
    from llmcompressor.modifiers.quantization import GPTQModifier

    scheme = _SCHEME[method]
    if method == "awq":
        return AWQModifier(scheme=scheme, targets=_TARGETS, ignore=_IGNORE)
    return GPTQModifier(scheme=scheme, targets=_TARGETS, ignore=_IGNORE)


def quantize(
    model_id: str,
    method: str,
    out_dir: str,
    spec: QuantSpec = DEFAULT_SPEC,
    token: str | None = None,
    run_check: bool = True,
) -> Path:
    """Quantize `model_id` with `method` into `out_dir`. Refuses if it won't fit."""
    method = method.lower()
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; choose from {METHODS}")

    if run_check:
        report = check_fit(model_id, token=token)
        if not report.fits:
            raise CannotQuantize(report.reason())

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    from llmcompressor import oneshot

    oneshot(
        model=model_id,
        dataset=spec.calib_dataset,
        dataset_config_name=spec.calib_config,
        splits=spec.calib_split,
        num_calibration_samples=spec.calib_samples,
        max_seq_length=spec.calib_seqlen,
        text_column="text",
        pad_to_max_length=False,
        shuffle_calibration_samples=True,
        recipe=_recipe(method),
        output_dir=str(out),
    )
    _write_card(out, model_id, method, spec)
    return out


def _write_card(out: Path, model_id: str, method: str, spec: QuantSpec) -> None:
    asym = "asymmetric" if method == "awq" else "symmetric"
    card = f"""---
base_model: {model_id}
tags: [quantized, {method}, w{spec.bits}a16, compressed-tensors, quantfit]
---

# {out.name}

{method.upper()} {spec.bits}-bit (W{spec.bits}A16, {asym}) quantization of
`{model_id}`, produced with [quantfit](https://github.com/Sahil170595/quantfit).

## Provenance
- method: {method} (W{spec.bits}A16 {asym}, group_size {spec.group_size})
- calibration: {spec.calib_dataset}/{spec.calib_config} [{spec.calib_split}], \
{spec.calib_samples} samples, seq-len {spec.calib_seqlen}, seed {spec.seed}
- spec fingerprint: `{spec.fingerprint()}`

Loads in vLLM via the compressed-tensors backend.
"""
    (out / "README.md").write_text(card, encoding="utf-8")


def push(out_dir: str, repo_id: str, token: str | None = None, private: bool = False) -> str:
    """Upload a quantized output folder to the Hub."""
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.create_repo(repo_id, exist_ok=True, private=private, repo_type="model")
    api.upload_folder(folder_path=str(out_dir), repo_id=repo_id, repo_type="model")
    return f"https://huggingface.co/{repo_id}"
