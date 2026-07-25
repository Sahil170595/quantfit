"""GGUF (llama.cpp) generation arms for verify-safety.

Why this exists: third-party quants overwhelmingly ship as GGUF, and the
baseline arm was capped by VRAM — a 12 GB GPU cannot hold an 8B fp16
transformer. Running the F16-GGUF baseline on CPU/RAM removes that cap for
exactly the stratum where third-party quants live (7-8B instruct models).

Protocol (mandated, not configurable):
  - BOTH arms run under the IDENTICAL llama.cpp binary on CPU — same binary,
    same device, same thread count; only the weights differ, so the diff
    isolates the quantization. A transformers-baseline vs llama.cpp-quant diff
    would measure engine + quantization at once (a deployment delta) and is
    refused, never pooled.
  - The baseline arm must be an unquantized GGUF (F16 / BF16 / F32), resolved
    from the file's own metadata — the filename's claim is never trusted.
  - Both files must declare the same model architecture; pairing a llama Q4
    with a qwen F16 is a category error, refused before any generation.

Generation runs through `llama-server` from the SHA256-verified pinned release
archive (the same supply-chain contract as llama-quantize): one server per arm,
sequential requests, temperature 0 (greedy). The model's own chat template —
embedded in GGUF metadata — is applied via the server's --jinja path when
present, raw prompt otherwise: the same policy as the transformers arms.

Refs are local paths ending in .gguf, or hf:<org>/<repo>/<file>.gguf (resolved
via huggingface_hub; the snapshot commit is recorded as the arm's revision).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from quantfit.backends.gguf import LLAMACPP_TAG, _sha256, llama_server_bin

if TYPE_CHECKING:  # runtime import stays lazy
    from quantfit.safety.report import ArmRun

HF_REF_PREFIX = "hf:"
UNQUANTIZED_FILE_TYPES = ("F16", "BF16", "F32")

_CTX_SIZE = 4096
_READY_TIMEOUT_S = 900  # a 16 GB F16 load from disk can legitimately take minutes
_REQUEST_TIMEOUT_S = 600
_LOG_TAIL_CHARS = 2000


def is_gguf_ref(ref: str) -> bool:
    """True for the refs the llama.cpp path owns: hf:... or a *.gguf path."""
    return ref.startswith(HF_REF_PREFIX) or ref.lower().endswith(".gguf")


@dataclass(frozen=True)
class ResolvedGguf:
    """One GGUF arm, resolved to a local file with metadata facts read from it."""

    ref: str  # as the user gave it
    path: Path
    revision: str | None  # HF snapshot commit for hf: refs; None for local files
    sha256: str
    architecture: str  # general.architecture
    file_type: str  # resolved from general.file_type — e.g. "F16", "Q4_K_M"
    chat_template: bool  # tokenizer.chat_template present in metadata
    name: str | None  # general.name


def resolve_pair(baseline_ref: str, quant_ref: str, token: str | None) -> tuple[ResolvedGguf, ResolvedGguf]:
    """Resolve both arms and enforce the pairing mandates before any generation."""
    baseline = _resolve(baseline_ref, token)
    quant = _resolve(quant_ref, token)
    if baseline.file_type not in UNQUANTIZED_FILE_TYPES:
        raise RuntimeError(
            f"baseline GGUF {baseline_ref} has file type {baseline.file_type} (read from its metadata); "
            f"the protocol mandates an unquantized baseline ({'/'.join(UNQUANTIZED_FILE_TYPES)}) "
            f"under the identical binary so the diff isolates the quantization"
        )
    if baseline.architecture != quant.architecture:
        raise RuntimeError(
            f"GGUF architectures differ: baseline {baseline_ref} is {baseline.architecture!r}, "
            f"quant {quant_ref} is {quant.architecture!r} — not a quantization pair"
        )
    return baseline, quant


def _resolve(ref: str, token: str | None) -> ResolvedGguf:
    path, revision = _fetch(ref, token)
    meta = _read_meta(path)
    return ResolvedGguf(
        ref=ref,
        path=path,
        revision=revision,
        sha256=_sha256(path),
        architecture=meta["architecture"],
        file_type=meta["file_type"],
        chat_template=meta["chat_template"],
        name=meta["name"],
    )


def _fetch(ref: str, token: str | None) -> tuple[Path, str | None]:
    """A local *.gguf path as-is, or hf:<org>/<repo>/<file>.gguf via the Hub cache."""
    if ref.startswith(HF_REF_PREFIX):
        rest = ref[len(HF_REF_PREFIX) :]
        parts = rest.split("/")
        if len(parts) < 3 or not rest.lower().endswith(".gguf"):
            raise RuntimeError(f"bad GGUF ref {ref!r}: expected hf:<org>/<repo>/<file>.gguf")
        from huggingface_hub import hf_hub_download

        local = hf_hub_download("/".join(parts[:2]), "/".join(parts[2:]), token=token)
        return Path(local), _snapshot_commit(Path(local))
    p = Path(ref)
    if not p.is_file():
        raise RuntimeError(f"GGUF file not found: {ref}")
    return p, None


def _snapshot_commit(path: Path) -> str | None:
    """The snapshot commit from the Hub cache layout (…/snapshots/<commit>/<file>)."""
    parts = path.parts
    for i, part in enumerate(parts[:-1]):
        if part == "snapshots" and len(parts[i + 1]) == 40:
            return parts[i + 1]
    return None


def _read_meta(path: Path) -> dict:
    """Read the facts this protocol depends on from the file's own GGUF metadata."""
    try:
        from gguf import GGUFReader
    except ImportError as exc:
        raise RuntimeError("GGUF metadata reading needs the gguf package: pip install 'quantfit[gguf]'") from exc

    try:
        fields = GGUFReader(str(path)).fields
    except Exception as exc:  # truncated/corrupt/not-a-gguf all surface here
        raise RuntimeError(f"cannot read GGUF metadata from {path}: {exc}") from exc

    def contents(key: str):
        field = fields.get(key)
        return None if field is None else field.contents()

    architecture = contents("general.architecture")
    if not isinstance(architecture, str) or not architecture:
        raise RuntimeError(f"{path} has no general.architecture in its GGUF metadata")
    file_type = contents("general.file_type")
    if not isinstance(file_type, int):
        raise RuntimeError(f"{path} has no general.file_type in its GGUF metadata")
    name = contents("general.name")
    return {
        "architecture": architecture,
        "file_type": _file_type_name(file_type),
        "chat_template": bool(contents("tokenizer.chat_template")),
        "name": name if isinstance(name, str) else None,
    }


def _file_type_name(value: int) -> str:
    """general.file_type int -> the llama.cpp ftype name ("MOSTLY_Q4_K_M" -> "Q4_K_M")."""
    from gguf.constants import LlamaFileType

    try:
        name = LlamaFileType(value).name
    except ValueError:
        return f"unknown_ftype_{value}"
    return name.removeprefix("MOSTLY_").removeprefix("ALL_")


# --- generation through llama-server ----------------------------------------------


def generate_completions(arm: ResolvedGguf, prompts: list[str], max_new_tokens: int) -> tuple[list[str], ArmRun]:
    """Greedy completions for every prompt from one llama-server instance, then ArmRun provenance."""
    from quantfit.safety.report import ArmRun

    started = time.perf_counter()
    server = llama_server_bin()
    threads = _threads()
    port = _free_port()
    log_fd, log_name = tempfile.mkstemp(prefix="quantfit-llama-server-", suffix=".log")
    proc = subprocess.Popen(  # noqa: S603 - SHA256-verified binary, fixed args
        [
            str(server),
            "-m",
            str(arm.path),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--threads",
            str(threads),
            "--ctx-size",
            str(_CTX_SIZE),
            "--parallel",
            "1",
            *(["--jinja"] if arm.chat_template else []),
        ],
        stdout=log_fd,
        stderr=subprocess.STDOUT,
    )
    completions: list[str] = []
    try:
        _wait_ready(port, proc, log_name)
        for prompt in prompts:
            completions.append(_complete(port, prompt, arm.chat_template, max_new_tokens))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        os.close(log_fd)
        Path(log_name).unlink(missing_ok=True)

    engine = {
        "name": "llama.cpp",
        "binary_sha256": _sha256(server),  # ground truth for the same-binary mandate
        "source": _binary_source(server),
        "threads": threads,
        "device": "cpu",
    }
    run = ArmRun(
        model=arm.ref,
        revision=arm.revision,
        resolved_dtype=arm.file_type,
        runtime_s=round(time.perf_counter() - started, 2),
        engine=engine,
        artifact_sha256=arm.sha256,
    )
    return completions, run


def _binary_source(server: Path) -> str:
    env = os.environ.get("QUANTFIT_LLAMACPP")
    if env and server.is_relative_to(Path(env)):
        return "QUANTFIT_LLAMACPP (user-provided build; tag not verified by quantfit)"
    return f"pinned release archive {LLAMACPP_TAG} (SHA256-verified)"


def _threads() -> int:
    # Half the logical cores approximates the physical count on SMT boxes —
    # llama.cpp gains nothing from hyperthreads; recorded in the report either way.
    return max(1, (os.cpu_count() or 2) // 2)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(port: int, proc, log_name: str, timeout_s: float = _READY_TIMEOUT_S) -> None:
    """Poll /health until the model is loaded; a dead server fails fast with its log tail."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"llama-server exited with code {proc.returncode} during model load; log tail:\n{_log_tail(log_name)}"
            )
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError):  # 503 while loading, refused before bind
            pass
        time.sleep(1.0)
    raise RuntimeError(f"llama-server not ready after {timeout_s:.0f}s; log tail:\n{_log_tail(log_name)}")


def _log_tail(log_name: str) -> str:
    try:
        return Path(log_name).read_text(encoding="utf-8", errors="replace")[-_LOG_TAIL_CHARS:]
    except OSError:
        return "(no server log captured)"


def _complete(port: int, prompt: str, chat: bool, max_new_tokens: int) -> str:
    """One greedy completion; the chat endpoint applies the model's own template (--jinja)."""
    if chat:
        url = f"http://127.0.0.1:{port}/v1/chat/completions"
        body = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": max_new_tokens,
            "cache_prompt": False,  # no cross-request KV reuse: one fewer determinism variable
        }
    else:
        url = f"http://127.0.0.1:{port}/completion"
        body = {"prompt": prompt, "temperature": 0, "n_predict": max_new_tokens, "cache_prompt": False}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"llama-server completion request failed: {exc}") from exc
    try:
        text = payload["choices"][0]["message"]["content"] if chat else payload["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"unexpected llama-server response shape: {exc}") from exc
    return str(text).strip()
