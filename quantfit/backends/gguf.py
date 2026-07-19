"""GGUF backend (llama.cpp).

Produces GGUF k-quants (Q4_K_M, etc.) for the Ollama / llama.cpp / LM Studio
world. Quantization is CPU-only. Two tools are provisioned into a cache on first
use (or located via QUANTFIT_LLAMACPP pointing at a llama.cpp checkout):
  - the prebuilt `llama-quantize` binary (from the pinned llama.cpp release asset)
  - the repo's `convert_hf_to_gguf.py` (HF safetensors -> GGUF f16); it imports a
    sibling `conversion` package, so a shallow clone of the repo is required.

Supply-chain contract: the downloaded binary is EXECUTED, so every fetched asset is
SHA256-verified against a pinned hash before it is extracted or run, and the clone is
verified to sit at the pinned commit. Fetches are atomic (temp + os.replace) so an
interrupted download or clone can never poison the cache.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

LLAMACPP_TAG = "b9817"  # pinned release; binary + convert script + commit must match
LLAMACPP_COMMIT = "5397c3619479ef544e340e4b933929d1783de78b"  # tag b9817 dereferences here
_HASH_CHUNK = 1 << 20  # 1 MiB streaming read for sha256

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

# Pinned SHA256 of each b9817 release binary asset. Obtained 2026-06-28 by downloading
# the published asset and hashing it; the binary is executed, so it is verified against
# this before extraction. An asset with no pin here is a hard refusal.
_BINARY_SHA256 = {
    "llama-b9817-bin-win-cpu-x64.zip": "e41b55ff23a22147e221a60dca01df76c2c35e0248d7c3974fe8f2db14874d5d",
    "llama-b9817-bin-ubuntu-x64.tar.gz": "0c141bb5b5a81c85decc0d2164b3a3251ea809dbd6660dcc7e6f420204ace0f0",
}


def _cache_dir() -> Path:
    root = os.environ.get("QUANTFIT_CACHE")
    d = Path(root) if root else Path.home() / ".cache" / "quantfit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _exe_name(base: str = "llama-quantize") -> str:
    return f"{base}.exe" if platform.system() == "Windows" else base


def _binary_asset() -> str:
    sysname = platform.system()
    if sysname == "Windows":
        return f"llama-{LLAMACPP_TAG}-bin-win-cpu-x64.zip"
    if sysname == "Linux":
        return f"llama-{LLAMACPP_TAG}-bin-ubuntu-x64.tar.gz"
    raise RuntimeError(
        f"no prebuilt llama.cpp binary wired for {sysname}; install llama.cpp and "
        f"set QUANTFIT_LLAMACPP to its directory"
    )


def _first_match(root: Path, name: str) -> Path | None:
    if (root / name).exists():
        return root / name
    return next(iter(root.rglob(name)), None)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_or_die(archive: Path, asset: str) -> None:
    """SHA256-check `archive` against the pin; delete + raise on mismatch/no-pin."""
    expected = _BINARY_SHA256.get(asset)
    if expected is None:
        raise RuntimeError(
            f"no pinned SHA256 for {asset!r}; refusing to extract/execute an unverified "
            f"binary. Build llama.cpp yourself and set QUANTFIT_LLAMACPP."
        )
    actual = _sha256(archive)
    if actual != expected:
        archive.unlink(missing_ok=True)
        raise RuntimeError(
            f"SHA256 mismatch for {asset}: expected {expected}, got {actual}. "
            f"Refusing to use a tampered/changed binary; deleted the bad file."
        )


def _download_verified(url: str, asset: str, dest: Path) -> None:
    """Download atomically (temp + os.replace) and verify the pin before `dest` exists."""
    if asset not in _BINARY_SHA256:  # fail before spending the download
        _verify_or_die(dest, asset)
    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), suffix=".part")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        urllib.request.urlretrieve(url, tmp)  # noqa: S310 - fixed github releases URL
        _verify_or_die(tmp, asset)
        os.replace(tmp, dest)  # dest appears only once fully downloaded AND verified
    finally:
        tmp.unlink(missing_ok=True)


def _extract(archive: Path, dest: Path) -> None:
    """Extract a verified .zip or .tar.gz; on a corrupt archive, delete it + raise."""
    dest.mkdir(parents=True, exist_ok=True)
    try:
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as z:
                z.extractall(dest)
        else:
            with tarfile.open(archive, "r:gz") as t:
                try:
                    t.extractall(dest, filter="data")  # py3.12+; bytes are SHA256-verified
                except TypeError:
                    t.extractall(dest)  # older py without the filter kwarg
    except (zipfile.BadZipFile, tarfile.TarError, EOFError) as exc:
        archive.unlink(missing_ok=True)
        raise RuntimeError(f"corrupt archive {archive.name} ({exc}); deleted it — re-run to refetch") from exc


def _llama_bin(base: str) -> Path:
    """Locate (env) or download+verify+extract a binary from the pinned release archive."""
    exe = _exe_name(base)
    env = os.environ.get("QUANTFIT_LLAMACPP")
    if env and (hit := _first_match(Path(env), exe)):
        return hit

    bindir = _cache_dir() / f"llamacpp-bin-{LLAMACPP_TAG}"
    if hit := _first_match(bindir, exe):
        return hit

    asset = _binary_asset()
    archive = _cache_dir() / asset
    if archive.exists():
        _verify_or_die(archive, asset)  # existence != integrity; re-check before extract
    else:
        _download_verified(f"{_RELEASES}/{LLAMACPP_TAG}/{asset}", asset, archive)
    _extract(archive, bindir)
    if hit := _first_match(bindir, exe):
        return hit
    raise RuntimeError(f"{exe} not found inside {asset}")


def llama_quantize_bin() -> Path:
    """The llama-quantize binary, from the SHA256-verified pinned archive (or QUANTFIT_LLAMACPP)."""
    return _llama_bin("llama-quantize")


def llama_server_bin() -> Path:
    """The llama-server binary — same verified archive; verify-safety's GGUF arms run through it."""
    return _llama_bin("llama-server")


def convert_script() -> Path:
    """Locate (env) or shallow-clone convert_hf_to_gguf.py at the pinned commit."""
    name = "convert_hf_to_gguf.py"
    env = os.environ.get("QUANTFIT_LLAMACPP")
    if env and (Path(env) / name).exists():
        return Path(env) / name

    repo = _cache_dir() / f"llama.cpp-{LLAMACPP_TAG}"
    if (repo / name).exists():
        return repo / name
    if repo.exists():
        shutil.rmtree(repo, ignore_errors=True)  # stale/partial clone — clear before re-clone

    # Clone into a temp dir, verify the pinned commit (tags are mutable; this code is
    # executed), then atomically promote — an aborted clone never blocks future runs.
    tmp = Path(tempfile.mkdtemp(dir=str(_cache_dir()), prefix="clone-"))
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", LLAMACPP_TAG, _REPO, str(tmp)],
            check=True,
        )
        head = subprocess.run(
            ["git", "-C", str(tmp), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if head != LLAMACPP_COMMIT:
            raise RuntimeError(
                f"cloned {LLAMACPP_TAG} is at {head}, expected pinned {LLAMACPP_COMMIT}; "
                f"the tag may have moved — refusing to run unverified convert code."
            )
        if not (tmp / name).exists():
            raise RuntimeError(f"{name} missing after cloning {_REPO}@{LLAMACPP_TAG}")
        os.replace(tmp, repo)  # atomic promote
        tmp = None
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
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
    try:
        subprocess.run([str(quant_bin), str(f16), str(final), qtype], check=True, env=env)
    finally:
        f16.unlink(missing_ok=True)  # drop the multi-GB f16 intermediate even on failure
    return out
