"""Forward-only quantization sensitivity probe.

Estimates how much a model degrades under a candidate weight-quantization, WITHOUT
running a full calibrated quant: apply round-to-nearest (RTN) group-wise quant to
the Linear weights in-memory, run a small forward pass, and measure the KL
divergence between the fp16 and quantized next-token distributions. Higher KL =
more degradation.

This is the cheap forward-only proxy from the KL-Lens line of work
(https://arxiv.org/abs/2604.13440) — we *implement* it as a routing input, not as a
novel method. RTN is the worst case (calibrated AWQ/GPTQ refine on top of it), so a
LOW RTN-KL is a strong "this bit-width is safe" signal. The converse does NOT hold:
HIGH RTN-KL over-escalates — models that are fine under calibrated 4-bit can still show
large RTN-4bit KL. Read mean_kl as a per-bit-width sensitivity measurement, not a
method-selection verdict.

Scope: KL is a QUALITY-drift signal, not a safety predictor. Quality preservation
does not imply refusal preservation ("Quality Is Not a Safety Proxy Under
Quantization", https://arxiv.org/abs/2606.10154) — a low-KL bit-width can still
flip refusal behavior. Use `verify-safety` for the safety axis; this probe never
substitutes for it.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantfit.spec import DEFAULT_SPEC
from quantfit.torchrt import CUDA, free_gpu, pick_device

DEFAULT_PROBE_SAMPLES = 8
DEFAULT_PROBE_SEQLEN = 512
# Calibration facts come from the frozen spec — the probe must measure sensitivity
# on the same distribution the quantize path calibrates on, never a stale copy.
DEFAULT_GROUP_SIZE = DEFAULT_SPEC.group_size


@dataclass(frozen=True)
class ProbeResult:
    bits: int
    group_size: int
    # Mean per-token KL(fp16 || RTN-quant) over the packed blocks; higher = more degradation.
    # Since 0.15.0 the blocks are fixed-length (calibset.packed_blocks); earlier releases
    # averaged per-row means over variable-length rows, and those numbers are not comparable.
    mean_kl: float
    n_samples: int
    # Every per-sample KL the mean was taken over. Until 0.13.x the probe reported the mean
    # alone, over 8 samples, with nothing to say whether one outlier row carried it - the
    # first recorded run (validation/2026-09-25-check-and-probe/) could not be judged for
    # stability at all. The spread is DESCRIPTIVE: min, max and sample SD, not an interval,
    # because a per-token KL over 8 rows is neither many nor symmetric and a CI would claim
    # more than the numbers carry.
    per_sample_kl: tuple[float, ...] = ()
    # The model commit the load resolved to (`config._commit_hash`, as verify-safety records
    # it), or None for a local path. The probe loads the caller's id at `main`, so until 0.14.3
    # nothing said which weights a number came from (validation/2026-10-01-probe-at-n64/).
    model_revision: str | None = None

    @property
    def spread(self) -> dict:
        return kl_spread(self.per_sample_kl)


def kl_spread(kls) -> dict:
    """min / max / sample SD of per-sample KLs. SD is None below two samples - one number
    has no spread, and 0.0 would read as a perfectly stable probe."""
    import statistics

    values = list(kls)
    if not values:
        return {"kl_min": None, "kl_max": None, "kl_sd": None}
    return {
        "kl_min": min(values),
        "kl_max": max(values),
        "kl_sd": statistics.stdev(values) if len(values) >= 2 else None,
    }


def probe_sensitivity(
    model_id: str,
    bits: int,
    group_size: int = DEFAULT_GROUP_SIZE,
    n_samples: int = DEFAULT_PROBE_SAMPLES,
    seqlen: int = DEFAULT_PROBE_SEQLEN,
    token: str | None = None,
) -> ProbeResult:
    """Measure RTN-quant sensitivity at `bits` via forward-only logit KL."""
    import torch
    import torch.nn.functional as F
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = pick_device()
    dtype = torch.float16 if device == CUDA else torch.float32
    tokenizer = AutoTokenizer.from_pretrained(model_id, token=token)
    model = AutoModelForCausalLM.from_pretrained(model_id, device_map=device, dtype=dtype, token=token)
    model.eval()

    batch = _probe_batch(tokenizer, n_samples, seqlen, device, token)
    if not batch:
        # RuntimeError: operational (unusable dataset), so the CLI exits cleanly.
        raise RuntimeError("probe batch is empty; calibration dataset returned no usable rows")

    # The reference logits, kept on CPU so the GPU isn't holding N x (T x vocab). They are
    # held in the model's own dtype and turned into log-probs only when used. At fp16 that is
    # half the host RAM of float32 log-probs, and the same numbers: log_softmax(logits.float())
    # runs on the same input on the same device either way.
    ref_logits = []
    with torch.no_grad():
        for inputs in batch:
            ref_logits.append(model(**inputs).logits.cpu())

    _rtn_quantize_linears_(model, bits, group_size)

    kls: list[float] = []
    with torch.no_grad():
        for inputs, ref_cpu in zip(batch, ref_logits):
            q_lp = F.log_softmax(model(**inputs).logits.float(), dim=-1)
            ref = F.log_softmax(ref_cpu.to(q_lp.device).float(), dim=-1)
            # mean per-token KL(fp16 || quant): flatten (1,T,V)->(T,V) so batchmean
            # divides by token count, not the batch dim (=1). Every block is the same
            # length, so the mean over blocks is also the mean over tokens.
            q_flat = q_lp.reshape(-1, q_lp.size(-1))
            ref_flat = ref.reshape(-1, ref.size(-1))
            kls.append(float(F.kl_div(q_flat, ref_flat, log_target=True, reduction="batchmean")))

    model_revision = getattr(model.config, "_commit_hash", None)
    del model, tokenizer
    free_gpu(device)
    return ProbeResult(
        bits=bits,
        group_size=group_size,
        mean_kl=sum(kls) / len(kls),
        n_samples=len(batch),
        per_sample_kl=tuple(kls),
        model_revision=model_revision,
    )


def _probe_batch(tokenizer, n_samples: int, seqlen: int, device: str, token: str | None):
    """`n_samples` packed blocks of exactly `seqlen` tokens, the head of the quantize path's stream.

    Rows used to be tokenized one by one, so a 9-token heading counted as much as a
    437-token paragraph. `calibset.packed_blocks` is the quantize path's own packing; every
    block here is the same length and carries its surrounding text.
    """
    from quantfit.calibset import packed_blocks

    blocks = packed_blocks(DEFAULT_SPEC, tokenizer, n_samples, seqlen, token=token)
    import torch  # after the load: the torch-free tests stop at the dataset call above

    return [
        {
            "input_ids": torch.tensor([block], device=device),
            "attention_mask": torch.ones((1, len(block)), dtype=torch.long, device=device),
        }
        for block in blocks
    ]


def _rtn_quantize_linears_(model, bits: int, group_size: int) -> None:
    """In-place group-wise symmetric RTN over every Linear weight except lm_head."""
    import torch

    for name, module in model.named_modules():
        if "lm_head" in name:
            continue  # the real AWQ/GPTQ paths leave lm_head unquantized
        if isinstance(module, torch.nn.Linear):
            module.weight.data = _rtn(module.weight.data, bits, group_size)


def _rtn(weight, bits: int, group_size: int):
    """Group-wise symmetric round-to-nearest, returned dequantized (error baked in)."""
    import torch

    qmax = 2 ** (bits - 1) - 1
    qmin = -(2 ** (bits - 1))
    out_f, in_f = weight.shape
    g = group_size if in_f % group_size == 0 else in_f  # per-row fallback if not divisible
    w = weight.reshape(out_f, in_f // g, g).float()
    scale = (w.abs().amax(dim=-1, keepdim=True) / qmax).clamp(min=1e-8)
    q = torch.clamp(torch.round(w / scale), qmin, qmax)
    return (q * scale).reshape(out_f, in_f).to(weight.dtype)
