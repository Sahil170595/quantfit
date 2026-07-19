"""GGUF verify-safety arms — hermetic (tiny crafted GGUFs, stub HTTP server, no binaries).

The pairing mandates (unquantized baseline, same architecture, one binary) are
protocol, not convenience — these tests pin them down without a single real
model file or llama-server process.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import quantfit.safety.gguf_arm as ga
from quantfit.safety.gguf_arm import (
    _complete,
    _fetch,
    _file_type_name,
    _read_meta,
    _snapshot_commit,
    _wait_ready,
    is_gguf_ref,
    resolve_pair,
)

Q4_K_M, F16 = 15, 1  # LlamaFileType values, verified against gguf.constants below


def _write_gguf(path, arch="llama", file_type=Q4_K_M, chat_template=None, name=None):
    from gguf import GGUFWriter

    w = GGUFWriter(str(path), arch=arch)
    w.add_file_type(file_type)
    if chat_template:
        w.add_chat_template(chat_template)
    if name:
        w.add_name(name)
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()
    return path


# --- ref classification + resolution ----------------------------------------------


def test_is_gguf_ref():
    assert is_gguf_ref("model.Q4_K_M.gguf")
    assert is_gguf_ref(r"C:\out\model.GGUF")
    assert is_gguf_ref("hf:org/repo/file.gguf")
    assert not is_gguf_ref("Qwen/Qwen2.5-1.5B-Instruct")
    assert not is_gguf_ref("./quant-output-dir")


@pytest.mark.parametrize("bad", ["hf:org/file.gguf", "hf:org/repo/notgguf.bin", "hf:justonepart"])
def test_bad_hf_ref_refused(bad):
    with pytest.raises(RuntimeError, match="expected hf:"):
        _fetch(bad, token=None)


def test_missing_local_file_refused(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        _fetch(str(tmp_path / "nope.gguf"), token=None)


def test_snapshot_commit_parsed_from_hub_cache_layout(tmp_path):
    commit = "a" * 40
    p = tmp_path / "models--org--repo" / "snapshots" / commit / "file.gguf"
    assert _snapshot_commit(p) == commit
    assert _snapshot_commit(tmp_path / "elsewhere" / "file.gguf") is None


# --- metadata: facts come from the file, not the filename --------------------------


def test_file_type_names_match_llamacpp_enum():
    from gguf.constants import LlamaFileType

    assert LlamaFileType.MOSTLY_Q4_K_M.value == Q4_K_M and LlamaFileType.MOSTLY_F16.value == F16
    assert _file_type_name(Q4_K_M) == "Q4_K_M"
    assert _file_type_name(F16) == "F16"
    assert _file_type_name(LlamaFileType.ALL_F32.value) == "F32"
    assert _file_type_name(LlamaFileType.MOSTLY_BF16.value) == "BF16"
    assert _file_type_name(999999).startswith("unknown_ftype_")


def test_read_meta_from_crafted_gguf(tmp_path):
    p = _write_gguf(tmp_path / "t.gguf", arch="qwen2", file_type=F16, chat_template="{{ messages }}", name="tiny")
    meta = _read_meta(p)
    assert meta == {"architecture": "qwen2", "file_type": "F16", "chat_template": True, "name": "tiny"}


def test_read_meta_without_chat_template(tmp_path):
    meta = _read_meta(_write_gguf(tmp_path / "t.gguf"))
    assert meta["chat_template"] is False and meta["file_type"] == "Q4_K_M"


def test_read_meta_refuses_non_gguf(tmp_path):
    junk = tmp_path / "junk.gguf"
    junk.write_bytes(b"not a gguf at all")
    with pytest.raises(RuntimeError, match="cannot read GGUF metadata"):
        _read_meta(junk)


# --- pairing mandates --------------------------------------------------------------


def test_quantized_baseline_refused(tmp_path):
    # The filename SAYS f16; the metadata says Q4_K_M. Metadata wins, pair refused.
    base = _write_gguf(tmp_path / "model-f16.gguf", file_type=Q4_K_M)
    quant = _write_gguf(tmp_path / "model-q4.gguf", file_type=Q4_K_M)
    with pytest.raises(RuntimeError, match="mandates an unquantized baseline"):
        resolve_pair(str(base), str(quant), token=None)


def test_architecture_mismatch_refused(tmp_path):
    base = _write_gguf(tmp_path / "base.gguf", arch="llama", file_type=F16)
    quant = _write_gguf(tmp_path / "quant.gguf", arch="qwen2", file_type=Q4_K_M)
    with pytest.raises(RuntimeError, match="architectures differ"):
        resolve_pair(str(base), str(quant), token=None)


def test_valid_pair_resolves_with_provenance(tmp_path):
    base = _write_gguf(tmp_path / "base.gguf", arch="llama", file_type=F16, chat_template="{{ m }}")
    quant = _write_gguf(tmp_path / "quant.gguf", arch="llama", file_type=Q4_K_M, chat_template="{{ m }}")
    b, q = resolve_pair(str(base), str(quant), token=None)
    assert (b.file_type, q.file_type) == ("F16", "Q4_K_M")
    assert b.sha256 != q.sha256 and len(b.sha256) == 64
    assert b.revision is None  # local files carry no HF revision


def test_mixed_arms_refused_before_any_load():
    # String-level check — no probes, no network, no model load.
    from quantfit.safety.verify import verify_safety

    with pytest.raises(RuntimeError, match="deployment delta"):
        verify_safety("Qwen/Qwen2.5-1.5B-Instruct", "quant.Q4_K_M.gguf")


# --- llama-server client -----------------------------------------------------------


class _StubHandler(BaseHTTPRequestHandler):
    def _json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._json({"status": "ok"}) if self.path == "/health" else self.send_error(404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body.get("temperature") == 0, "greedy decoding is the protocol"
        if self.path == "/v1/chat/completions":
            text = "chat:" + body["messages"][0]["content"]
            self._json({"choices": [{"message": {"content": text}}]})
        elif self.path == "/completion":
            self._json({"content": "raw:" + body["prompt"]})
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


@pytest.fixture
def stub_server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    thread.join(timeout=5)


class _FakeProc:
    def __init__(self, returncode=None):
        self.returncode = returncode

    def poll(self):
        return self.returncode


def test_complete_chat_and_raw_endpoints(stub_server):
    assert _complete(stub_server, "hello", chat=True, max_new_tokens=8) == "chat:hello"
    assert _complete(stub_server, "hello", chat=False, max_new_tokens=8) == "raw:hello"


def test_wait_ready_returns_on_health(stub_server, tmp_path):
    log = tmp_path / "s.log"
    log.write_text("", encoding="utf-8")
    _wait_ready(stub_server, _FakeProc(), str(log), timeout_s=10)  # must not raise


def test_wait_ready_reports_dead_server_with_log_tail(tmp_path):
    log = tmp_path / "s.log"
    log.write_text("gguf_init: tensor mismatch — boom", encoding="utf-8")
    with pytest.raises(RuntimeError, match="boom"):
        _wait_ready(1, _FakeProc(returncode=7), str(log), timeout_s=10)


def test_generate_completions_hermetic(stub_server, tmp_path, monkeypatch):
    # Full arm flow with a fake binary + fake process, real HTTP against the stub:
    # command shape, --jinja policy, and the ArmRun provenance all in one pass.
    fake_bin = tmp_path / "llama-server.exe"
    fake_bin.write_bytes(b"fake server binary")
    spawned = {}

    class _FakeServerProc(_FakeProc):
        def __init__(self, cmd, **kwargs):
            super().__init__()
            spawned["cmd"] = cmd

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(ga, "llama_server_bin", lambda: fake_bin)
    monkeypatch.setattr(ga, "_free_port", lambda: stub_server)
    monkeypatch.setattr(ga.subprocess, "Popen", _FakeServerProc)

    path = _write_gguf(tmp_path / "m.gguf", arch="llama", file_type=F16, chat_template="{{ m }}")
    arm = ga._resolve(str(path), token=None)
    completions, run = ga.generate_completions(arm, ["p1", "p2"], max_new_tokens=8)

    assert completions == ["chat:p1", "chat:p2"]
    assert "--jinja" in spawned["cmd"] and "--parallel" in spawned["cmd"]
    assert run.resolved_dtype == "F16" and run.artifact_sha256 == arm.sha256
    assert run.engine["name"] == "llama.cpp" and run.engine["device"] == "cpu"
    from quantfit.backends.gguf import _sha256

    assert run.engine["binary_sha256"] == _sha256(fake_bin)  # the binary actually "run"


def test_generate_completions_no_jinja_without_chat_template(stub_server, tmp_path, monkeypatch):
    fake_bin = tmp_path / "llama-server.exe"
    fake_bin.write_bytes(b"fake")
    spawned = {}

    class _FakeServerProc(_FakeProc):
        def __init__(self, cmd, **kwargs):
            super().__init__()
            spawned["cmd"] = cmd

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(ga, "llama_server_bin", lambda: fake_bin)
    monkeypatch.setattr(ga, "_free_port", lambda: stub_server)
    monkeypatch.setattr(ga.subprocess, "Popen", _FakeServerProc)

    arm = ga._resolve(str(_write_gguf(tmp_path / "m.gguf", file_type=F16)), token=None)
    completions, run = ga.generate_completions(arm, ["p1"], max_new_tokens=8)
    assert completions == ["raw:p1"]  # no chat template -> raw /completion endpoint
    assert "--jinja" not in spawned["cmd"]
