"""Smoke-verify a quantized artifact: does it actually load and generate?

compressed-tensors outputs load via transformers and generate a few tokens.
GGUF files are checked structurally (magic) — full GGUF inference needs a
llama.cpp runtime, out of scope for a quick verify.
"""

from __future__ import annotations

from pathlib import Path

_PROMPT = "The capital of France is"
_GGUF_MAGIC = b"GGUF"


def verify(path: str, max_new_tokens: int = 8) -> tuple[bool, str]:
    """Return (ok, message) for a quantized output dir or .gguf file."""
    p = Path(path)
    gguf = None
    if p.is_dir():
        gguf = next(iter(p.glob("*.gguf")), None)
    elif p.suffix == ".gguf":
        gguf = p
    if gguf is not None:
        return _verify_gguf(gguf)
    return _verify_transformers(str(p), max_new_tokens)


def _verify_gguf(path: Path) -> tuple[bool, str]:
    with open(path, "rb") as fh:
        magic = fh.read(4)
    ok = magic == _GGUF_MAGIC
    note = "OK" if ok else f"BAD (got {magic!r})"
    return ok, f"GGUF magic {note}; run with llama.cpp / Ollama to generate."


def _verify_transformers(path: str, max_new_tokens: int) -> tuple[bool, str]:
    import gc

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = None
    try:
        model = AutoModelForCausalLM.from_pretrained(path, device_map=device, torch_dtype="auto")
        tokenizer = AutoTokenizer.from_pretrained(path)
        ids = tokenizer(_PROMPT, return_tensors="pt").to(device)
        out = model.generate(**ids, max_new_tokens=max_new_tokens, do_sample=False)
        gen = tokenizer.decode(out[0][ids.input_ids.shape[1] :], skip_special_tokens=True)
        return len(gen.strip()) > 0, f"{_PROMPT!r} -> {gen!r}"
    except Exception as exc:  # noqa: BLE001 - a smoke test reports ANY load/gen failure as a clean FAIL
        return False, f"failed to load/generate from {path}: {exc}"
    finally:
        del model  # free the one resident model before returning (happy or unhappy path)
        gc.collect()
        if device == "cuda":
            torch.cuda.empty_cache()
