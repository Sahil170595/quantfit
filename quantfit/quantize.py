"""Dispatcher: validate the request, GPU pre-flight, route to a backend, card it."""
from __future__ import annotations

from pathlib import Path

from quantfit.gpufit import check_fit
from quantfit.registry import BACKEND_CT, resolve
from quantfit.spec import DEFAULT_SPEC, QuantSpec


class CannotQuantize(RuntimeError):
    """Raised when the model won't fit the GPU (pre-flight refusal)."""


def quantize(
    model_id: str,
    method: str,
    out_dir: str,
    scheme: str | None = None,
    spec: QuantSpec = DEFAULT_SPEC,
    token: str | None = None,
    run_check: bool = True,
    offload: bool = False,
) -> Path:
    """Quantize `model_id` with `method` (+ optional `scheme`) into `out_dir`."""
    m, resolved_scheme = resolve(method, scheme)

    # Offload mode fits any size by holding the model on CPU, so skip the VRAM gate.
    if run_check and not offload:
        report = check_fit(model_id, token=token)
        if not report.fits:
            raise CannotQuantize(report.reason() + "  (try --offload to quantize on CPU)")

    if m.backend == BACKEND_CT:
        from quantfit.backends.compressed_tensors import quantize_ct

        out = quantize_ct(
            model_id, m.name, resolved_scheme, out_dir, spec,
            m.needs_calibration, token=token, offload=offload,
        )
    else:
        raise NotImplementedError(f"backend {m.backend!r} is not wired yet")

    _write_card(Path(out), model_id, m.name, resolved_scheme, spec)
    return Path(out)


def _write_card(out: Path, model_id: str, method: str, scheme: str, spec: QuantSpec) -> None:
    card = f"""---
base_model: {model_id}
tags: [quantized, {method}, {scheme.lower()}, compressed-tensors, quantfit]
---

# {out.name}

{method.upper()} quantization ({scheme}) of `{model_id}`, produced with
[quantfit](https://github.com/Sahil170595/quantfit).

## Provenance
- method: {method}, scheme: {scheme}, group_size {spec.group_size}
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
