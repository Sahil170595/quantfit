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

DEFAULT_PROBE_SAMPLES = 8
DEFAULT_PROBE_SEQLEN = 512
DEFAULT_GROUP_SIZE = 128
DEFAULT_SEED = 42
_CALIB_DATASET = "Salesforce/wikitext"
_CALIB_CONFIG = "wikitext-103-raw-v1"
_MIN_PROBE_TOKENS = 8  # skip near-empty rows
_CUDA = "cuda"
_CPU = "cpu"


@dataclass(frozen=True)
class ProbeResult:
    bits: int
    group_size: int
    mean_kl: float  # mean KL(fp16 || RTN-quant) over the probe batch; higher = more degradation
    n_samples: int


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

    device = _CUDA if torch.cuda.is_available() else _CPU
    dtype = torch.float16 if device == _CUDA else torch.float32
    tokenizer = AutoTokenizer.from_pretrained(model_id, token=token)
    model = AutoModelForCausalLM.from_pretrained(model_id, device_map=device, dtype=dtype, token=token)
    model.eval()

    batch = _probe_batch(tokenizer, n_samples, seqlen, device, token)
    if not batch:
        # RuntimeError: operational (unusable dataset), so the CLI exits cleanly.
        raise RuntimeError("probe batch is empty; calibration dataset returned no usable rows")

    # fp16 reference log-probs, kept on CPU so the GPU isn't holding 8 x (T x vocab).
    fp16_logprobs = []
    with torch.no_grad():
        for inputs in batch:
            lp = F.log_softmax(model(**inputs).logits.float(), dim=-1)
            fp16_logprobs.append(lp.cpu())

    _rtn_quantize_linears_(model, bits, group_size)

    kls: list[float] = []
    with torch.no_grad():
        for inputs, ref_cpu in zip(batch, fp16_logprobs):
            q_lp = F.log_softmax(model(**inputs).logits.float(), dim=-1)
            ref = ref_cpu.to(q_lp.device)
            # mean per-token KL(fp16 || quant): flatten (1,T,V)->(T,V) so batchmean
            # divides by token count, not the batch dim (=1) — makes variable-length
            # rows comparable instead of summing KL over all T positions.
            q_flat = q_lp.reshape(-1, q_lp.size(-1))
            ref_flat = ref.reshape(-1, ref.size(-1))
            kls.append(float(F.kl_div(q_flat, ref_flat, log_target=True, reduction="batchmean")))

    del model, tokenizer
    _free_gpu(device)
    return ProbeResult(bits=bits, group_size=group_size, mean_kl=sum(kls) / len(kls), n_samples=len(batch))


def _probe_batch(tokenizer, n_samples: int, seqlen: int, device: str, token: str | None):
    """A few tokenized calibration rows for the forward pass."""
    from datasets import load_dataset

    ds = load_dataset(_CALIB_DATASET, _CALIB_CONFIG, split="train", token=token)
    ds = ds.filter(lambda ex: ex["text"] is not None and ex["text"].strip() != "")
    ds = ds.shuffle(seed=DEFAULT_SEED).select(range(min(n_samples * 4, len(ds))))

    batch = []
    for row in ds:
        enc = tokenizer(row["text"], return_tensors="pt", truncation=True, max_length=seqlen)
        if enc["input_ids"].shape[1] >= _MIN_PROBE_TOKENS:
            batch.append({k: v.to(device) for k, v in enc.items()})
        if len(batch) >= n_samples:
            break
    return batch


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


def _free_gpu(device: str) -> None:
    import gc

    import torch

    gc.collect()
    if device == _CUDA:
        torch.cuda.empty_cache()
