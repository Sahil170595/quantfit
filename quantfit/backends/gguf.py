"""GGUF backend (llama.cpp).

Produces GGUF k-quants (Q4_K_M, etc.) for the Ollama / llama.cpp / LM Studio
world. Quantization is CPU-only. Two tools are provisioned into a cache on first
use (or located via QUANTFIT_LLAMACPP pointing at a llama.cpp checkout):
  - the prebuilt `llama-quantize` binary (from the pinned llama.cpp release zip)
  - the repo's `convert_hf_to_gguf.py` (HF safetensors -> GGUF f16); it imports a
    sibling `conversion` package, so a shallow clone of the repo is required.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

LLAMACPP_TAG = "b9817"  # pinned release; binary + convert script must match
GGUF_TYPES = (
    "Q2_K",
    "Q3_K_S",
    "Q3_K_M",
    "Q4_K_S",
    "Q4_K_M",
    "Q5_K_M",
    "Q6_K",
    "Q8_0",
    "IQ4_XS",
)

_REPO = "https://github.com/ggml-org/llama.cpp"
_RELEASES = "https://github.com/ggml-org/llama.cpp/releases/download"


def _cache_dir() -> Path:
    root = os.environ.get("QUANTFIT_CACHE")
    d = Path(root) if root else Path.home() / ".cache" / "quantfit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _exe_name() -> str:
    return "llama-quantize.exe" if platform.system() == "Windows" else "llama-quantize"


def _binary_asset() -> str:
    sysname = platform.system()
    if sysname == "Windows":
        return f"llama-{LLAMACPP_TAG}-bin-win-cpu-x64.zip"
    if sysname == "Linux":
        return f"llama-{LLAMACPP_TAG}-bin-ubuntu-x64.zip"
    raise RuntimeError(
        f"no prebuilt llama.cpp binary wired for {sysname}; install llama.cpp and "
        f"set QUANTFIT_LLAMACPP to its directory"
    )


def _first_match(root: Path, name: str) -> Path | None:
    if (root / name).exists():
        return root / name
    return next(iter(root.rglob(name)), None)


def llama_quantize_bin() -> Path:
    """Locate (env) or download+extract the llama-quantize binary."""
    exe = _exe_name()
    env = os.environ.get("QUANTFIT_LLAMACPP")
    if env and (hit := _first_match(Path(env), exe)):
        return hit

    bindir = _cache_dir() / f"llamacpp-bin-{LLAMACPP_TAG}"
    if hit := _first_match(bindir, exe):
        return hit

    asset = _binary_asset()
    zip_path = _cache_dir() / asset
    if not zip_path.exists():
        urllib.request.urlretrieve(f"{_RELEASES}/{LLAMACPP_TAG}/{asset}", zip_path)
    bindir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(bindir)
    if hit := _first_match(bindir, exe):
        return hit
    raise RuntimeError(f"{exe} not found inside {asset}")


def convert_script() -> Path:
    """Locate (env) or shallow-clone the repo's convert_hf_to_gguf.py."""
    name = "convert_hf_to_gguf.py"
    env = os.environ.get("QUANTFIT_LLAMACPP")
    if env and (Path(env) / name).exists():
        return Path(env) / name

    repo = _cache_dir() / f"llama.cpp-{LLAMACPP_TAG}"
    if (repo / name).exists():
        return repo / name
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", LLAMACPP_TAG, _REPO, str(repo)],
        check=True,
    )
    if not (repo / name).exists():
        raise RuntimeError(f"{name} missing after cloning {_REPO}@{LLAMACPP_TAG}")
    return repo / name


def quantize_gguf(model_id: str, qtype: str, out_dir: str, token: str | None = None) -> Path:
    """HF model -> GGUF f16 -> quantized GGUF (CPU-only)."""
    from huggingface_hub import snapshot_download

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    quant_bin = llama_quantize_bin()
    convert = convert_script()
    model_dir = snapshot_download(model_id, token=token)

    f16 = out / "model.f16.gguf"
    final = out / f"model.{qtype}.gguf"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

    subprocess.run(
        [sys.executable, str(convert), model_dir, "--outtype", "f16", "--outfile", str(f16)],
        check=True,
        env=env,
    )
    subprocess.run([str(quant_bin), str(f16), str(final), qtype], check=True, env=env)
    f16.unlink(missing_ok=True)  # drop the large f16 intermediate
    return out
