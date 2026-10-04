"""Real, public pinned-model CPU quantization -> reload -> inference qualification.

Backend serialization/inference only; no safety/sensitivity or GPU/offload claim.
Produces aggregates and hashes, never generated text or model weights in artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import tempfile
import time
from pathlib import Path

MODEL = "HuggingFaceTB/SmolLM2-135M-Instruct"
REVISION = "12fd25f77366fa6b3b4b768ec3050bf629380bac"
CT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
CT_REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"


def ct_acceptance(root: Path) -> dict:
    import torch
    from huggingface_hub import snapshot_download
    from safetensors import safe_open
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from quantfit.backends.compressed_tensors import quantize_ct
    from quantfit.spec import DEFAULT_SPEC

    # SmolLM2-135M has 576 columns, incompatible with the published group-128
    # scheme. Qwen's 896 columns support it without weakening the recipe.
    source = snapshot_download(
        CT_MODEL, revision=CT_REVISION, allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model"]
    )
    assert CT_REVISION in Path(source).parts, "Hub source did not resolve to the preregistered commit"
    out = quantize_ct(source, "rtn", "W4A16", str(root / "ct"), DEFAULT_SPEC, False)
    config = json.loads((out / "config.json").read_text())
    assert config["quantization_config"]["quant_method"] == "compressed-tensors"
    integer_tensors = 0
    for file in out.glob("*.safetensors"):
        with safe_open(str(file), framework="pt", device="cpu") as handle:
            for key in handle.keys():  # noqa: SIM118 - safetensors safe_open is not iterable
                if handle.get_tensor(key).dtype in (torch.int8, torch.int16, torch.int32, torch.uint8):
                    integer_tensors += 1
    assert integer_tensors > 0, "a subprocess exit or config alone is not evidence of quantization"
    # Transformers' supported loader decompresses these RTN weights for CPU inference.
    model = AutoModelForCausalLM.from_pretrained(out, device_map="cpu", dtype=torch.float32).eval()
    tokenizer = AutoTokenizer.from_pretrained(out)
    encoded = tokenizer("The capital of France is", return_tensors="pt")
    with torch.inference_mode():
        assert torch.isfinite(model(**encoded).logits).all()
        generated = model.generate(**encoded, max_new_tokens=4, do_sample=False)
    added = generated.shape[-1] - encoded["input_ids"].shape[-1]
    assert 0 < added <= 4
    return {
        "scheme": "W4A16",
        "integer_tensors": integer_tensors,
        "generated_tokens": added,
        "token_ids_sha256": hashlib.sha256(generated.numpy().tobytes()).hexdigest(),
        "finite_logits": True,
    }


def gguf_acceptance(root: Path) -> dict:
    from gguf import GGUFReader

    from quantfit.backends.gguf import quantize_gguf
    from quantfit.safety.gguf_arm import _resolve, generate_completions

    out = quantize_gguf(MODEL, "Q4_K_M", str(root / "gguf"), revision=REVISION)
    file = out / "model.Q4_K_M.gguf"
    arm = _resolve(str(file), None)
    assert arm.file_type == "Q4_K_M"
    reader = GGUFReader(str(file))
    packed = sum(int(t.tensor_type) not in (0, 1) for t in reader.tensors)
    assert packed > 0, "metadata without packed tensors does not establish quantization"
    del reader
    outputs, provenance = generate_completions(arm, ["The capital of France is"], 4)
    assert len(outputs) == 1 and outputs[0].strip(), "loaded quantized model must generate"
    return {
        "scheme": "Q4_K_M",
        "packed_tensors": packed,
        "artifact_sha256": arm.sha256,
        "inference_sha256": hashlib.sha256(outputs[0].encode()).hexdigest(),
        "engine": provenance.engine,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("ct", "gguf"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
    with tempfile.TemporaryDirectory(prefix="quantfit-cpu-") as name:
        result = (ct_acceptance if args.backend == "ct" else gguf_acceptance)(Path(name))
    payload = {
        "kind": "real CPU backend qualification; not safety sensitivity",
        "backend": args.backend,
        "source_model": CT_MODEL if args.backend == "ct" else MODEL,
        "source_revision": CT_REVISION if args.backend == "ct" else REVISION,
        "result": result,
        "runtime_s": round(time.perf_counter() - started, 3),
        "python": platform.python_version(),
        "versions": {
            p: importlib.metadata.version(p) for p in ("quantfit", "torch", "transformers", "llmcompressor", "gguf")
        },
        "source_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
