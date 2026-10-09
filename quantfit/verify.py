"""Smoke-verify a quantized artifact: does it actually load and generate?

compressed-tensors outputs load via transformers and generate a few tokens.
GGUF files use bounded structure validation. Optional native usability is exposed
separately by verify_gguf; the legacy tuple API keeps its Transformers behavior.
"""

from __future__ import annotations

from pathlib import Path

_PROMPT = "The capital of France is"
_GGUF_MAGIC = b"GGUF"


def gguf_path(path: str) -> Path | None:
    """Choose one explicit GGUF/symlink or unambiguous directory member."""
    p = Path(path)
    if p.is_dir():
        selected = None
        for child in p.iterdir():
            if child.suffix.lower() == ".gguf" and child.is_file():
                if selected is not None:
                    raise RuntimeError("multiple GGUF files; choose an explicit member")
                selected = child
        return selected
    return p if p.suffix.lower() == ".gguf" else None


def verify(path: str, max_new_tokens: int = 8) -> tuple[bool, str]:
    """Return (ok, message) for a quantized output dir or .gguf file."""
    p = Path(path)
    gguf = gguf_path(path)
    if gguf is not None:
        return _verify_gguf(gguf)
    return _verify_transformers(str(p), max_new_tokens)


def _verify_gguf(path: Path) -> tuple[bool, str]:
    from quantfit.gguf_verify import verify_gguf

    result = verify_gguf(str(path))
    if result["exit_code"] == 2:
        raise RuntimeError(result["message"])
    return result["passed"], result["message"]


def _verify_transformers(path: str, max_new_tokens: int) -> tuple[bool, str]:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from quantfit.torchrt import free_gpu, pick_device

    device = pick_device()
    model = None
    try:
        model = AutoModelForCausalLM.from_pretrained(path, device_map=device, dtype="auto")
        tokenizer = AutoTokenizer.from_pretrained(path)
        ids = tokenizer(_PROMPT, return_tensors="pt").to(device)
        out = model.generate(**ids, max_new_tokens=max_new_tokens, do_sample=False)
        gen = tokenizer.decode(out[0][ids.input_ids.shape[1] :], skip_special_tokens=True)
        return len(gen.strip()) > 0, f"{_PROMPT!r} -> {gen!r}"
    except Exception as exc:  # noqa: BLE001 - a smoke test reports ANY load/gen failure as a clean FAIL
        return False, f"failed to load/generate from {path}: {exc}"
    finally:
        del model  # free the one resident model before returning (happy or unhappy path)
        free_gpu(device)
