"""Complete crafted files and bounded fake native lifecycle; no real models."""

import asyncio
import hashlib
import json
import struct

import pytest

from quantfit.gguf_verify import verify_gguf


def string(raw):
    raw = raw.encode() if isinstance(raw, str) else raw
    return struct.pack("<Q", len(raw)) + raw


def fixture_bytes(*, dims=(32, 2), kind=2, tensors=None, metadata=(), payload_size=36, version=3):
    values = tensors or [("test.weight", dims, kind, 0)]
    raw = b"GGUF" + struct.pack("<IQQ", version, len(values), len(metadata))
    for name, tag, data in metadata:
        raw += string(name) + struct.pack("<I", tag) + data
    for name, shape, tag, offset in values:
        raw += string(name) + struct.pack("<I", len(shape))
        raw += b"".join(struct.pack("<Q", n) for n in shape) + struct.pack("<IQ", tag, offset)
    raw += b"\x00" * (-len(raw) % 32)
    return raw + b"\x00" * payload_size


def write(tmp_path, raw, name="model.gguf"):
    path = tmp_path / name
    path.write_bytes(raw)
    return path


def test_magic_only_can_never_be_structural_pass(tmp_path):
    result = verify_gguf(str(write(tmp_path, b"GGUF")))
    assert result["exit_code"] == 3 and result["structure"]["status"] == "fail"


@pytest.mark.parametrize("version", [2, 3])
def test_complete_quantized_rows_pass_structure_not_weight_quality(tmp_path, version):
    result = verify_gguf(str(write(tmp_path, fixture_bytes(version=version))))
    assert result["exit_code"] == 0 and result["structure"]["packed_tensors"] == 1
    assert result["runtime"]["status"] == "not_requested"
    assert result["quantization_quality_verified"] is False


def test_declared_ne0_not_reversed_numpy_shape_controls_row_divisibility(tmp_path):
    result = verify_gguf(str(write(tmp_path, fixture_bytes(dims=(16, 2), payload_size=18))))
    assert result["exit_code"] == 3


@pytest.mark.parametrize(
    "fault",
    [
        "magic",
        "truncated",
        "extent",
        "overlap",
        "misaligned",
        "duplicate-tensor",
        "duplicate-key",
        "bad-bool",
        "bad-key",
        "alignment-type",
        "alignment-value",
    ],
)
def test_known_invalid_binary_is_a_structural_failure(tmp_path, fault):
    metadata = []
    tensors = None
    if fault == "bad-bool":
        metadata = [("test.flag", 7, b"\x02")]
    elif fault == "bad-key":
        metadata = [("Test.Bad", 0, b"\x00")]
    elif fault == "duplicate-key":
        metadata = [("test.key", 0, b"\x00")] * 2
    elif fault == "alignment-type":
        metadata = [("general.alignment", 10, struct.pack("<Q", 32))]
    elif fault == "alignment-value":
        metadata = [("general.alignment", 4, struct.pack("<I", 3))]
    elif fault in ("overlap", "duplicate-tensor"):
        tensors = [("a", (32,), 2, 0), ("a" if fault == "duplicate-tensor" else "b", (32,), 2, 0)]
    elif fault == "misaligned":
        tensors = [("a", (32,), 2, 1)]
    raw = fixture_bytes(metadata=metadata, tensors=tensors)
    raw = (
        b"XXXX" + raw[4:]
        if fault == "magic"
        else raw[:10]
        if fault == "truncated"
        else raw[:-1]
        if fault == "extent"
        else raw
    )
    assert verify_gguf(str(write(tmp_path, raw)))["exit_code"] == 3


@pytest.mark.parametrize(
    "raw",
    [
        b"GGUF" + struct.pack(">IQQ", 3, 0, 0),
        fixture_bytes(version=1),
        fixture_bytes(version=4),
        fixture_bytes(metadata=[("test.array", 9, struct.pack("<IQ", 9, 1))]),
    ],
)
def test_outside_supported_binary_profile_is_unverified_not_corrupt(tmp_path, raw):
    result = verify_gguf(str(write(tmp_path, raw)))
    assert result["exit_code"] == 2 and result["structure"]["status"] == "unverified"


def test_binary_ieee_nonfinite_float_metadata_is_valid_encoding(tmp_path):
    raw = fixture_bytes(metadata=[("test.score", 6, struct.pack("<f", float("inf")))])
    assert verify_gguf(str(write(tmp_path, raw)))["exit_code"] == 0


def test_explicit_blob_path_and_readonly_symlink_need_no_model_copy(tmp_path):
    path = write(tmp_path, fixture_bytes(), "canonical-blob")
    assert verify_gguf(str(path))["exit_code"] == 0
    link = tmp_path / "model.gguf"
    try:
        link.symlink_to(path)
    except OSError:
        pytest.skip("symlink creation unavailable")
    assert verify_gguf(str(link))["path"] == str(path)


@pytest.mark.parametrize(
    "case", ["key-length", "tensor-length", "utf8", "bool-array", "zero-dimension", "huge-dimensions"]
)
def test_known_format_limits_and_encodings_fail_without_tensor_allocation(tmp_path, case):
    metadata, tensors = [], None
    if case == "key-length":
        metadata = [("a" * 65536, 0, b"\x00")]
    elif case == "tensor-length":
        tensors = [("a" * 65, (32,), 2, 0)]
    elif case == "utf8":
        metadata = [("test.string", 8, string(b"\xff"))]
    elif case == "bool-array":
        metadata = [("test.array", 9, struct.pack("<IQ", 7, 2) + b"\x00\x02")]
    elif case == "zero-dimension":
        tensors = [("a", (0,), 0, 0)]
    else:
        tensors = [("a", (2**64 - 32, 2**64 - 1, 2**64 - 1, 2**64 - 1), 2, 0)]
    assert verify_gguf(str(write(tmp_path, fixture_bytes(metadata=metadata, tensors=tensors))))["exit_code"] == 3


def test_gaps_trailing_padding_and_empty_tensor_name_are_not_invented_corruption(tmp_path):
    raw = fixture_bytes(tensors=[("", (32,), 2, 32)], payload_size=80)
    assert verify_gguf(str(write(tmp_path, raw)))["exit_code"] == 0


def test_no_reader_mmap_or_numpy_product_is_used(tmp_path, monkeypatch):
    import gguf
    import numpy

    monkeypatch.setattr(gguf, "GGUFReader", lambda *a, **k: pytest.fail("unbounded reader"))
    monkeypatch.setattr(numpy, "memmap", lambda *a, **k: pytest.fail("mmap allocation"))
    monkeypatch.setattr(numpy, "prod", lambda *a, **k: pytest.fail("overflowing product"))
    assert verify_gguf(str(write(tmp_path, fixture_bytes())))["exit_code"] == 0


@pytest.mark.parametrize("budget", ["directory", "metadata", "array"])
def test_valid_files_beyond_chosen_budgets_are_unverified(tmp_path, monkeypatch, budget):
    import quantfit.gguf_structure as parser

    metadata = [("test.array", 9, struct.pack("<IQ", 0, 2) + b"\x01\x02")]
    monkeypatch.setattr(
        parser,
        {"directory": "MAX_DIRECTORY_BYTES", "metadata": "MAX_METADATA", "array": "MAX_ARRAY_ITEMS"}[budget],
        0 if budget == "metadata" else 1,
    )
    result = verify_gguf(str(write(tmp_path, fixture_bytes(metadata=metadata))))
    assert result["exit_code"] == 2 and not result["passed"]


@pytest.fixture
def native_fixture(tmp_path, monkeypatch):
    import quantfit.gguf_runtime as runtime

    path = write(tmp_path, fixture_bytes(metadata=[("general.architecture", 8, string("llama"))]))
    binary = tmp_path / "binary"
    binary.write_bytes(b"synthetic executable provenance only")
    monkeypatch.setattr(runtime, "_supported", lambda: True)
    monkeypatch.setattr(runtime.ga, "llama_server_bin", lambda: binary)
    monkeypatch.setattr(runtime.ga, "_threads", lambda: 2)
    servers = []

    class Server:
        def __init__(self, arm, binary, threads):
            self.closed, self.cleanup = False, None
            self.facts = {
                "served_model_verified": True,
                "native_context_size": 4096,
                "total_slots": 1,
                "served_build": "synthetic",
                "served_template_sha256": "a" * 64,
            }
            servers.append(self)

        async def complete(self, prompt, max_tokens):
            assert prompt == "The capital of France is" and max_tokens == 8
            return "synthetic output discarded", "unknown"

        def close(self):
            self.closed = True
            self.cleanup = {
                "direct_child_reaped": True,
                "no_live_group_members_observed": True,
                "grandchild_reaping_verified": False,
            }

    monkeypatch.setattr(runtime, "OwnedGgufServer", Server)
    return path, binary, runtime, Server, servers


def test_native_fake_success_requires_cleanup_and_discards_text(native_fixture):
    path, binary, _, _, servers = native_fixture
    result = verify_gguf(str(path), runtime=True)
    assert result["exit_code"] == 0 and result["runtime"]["requests_observed"] == 1 and servers[0].closed
    assert result["runtime"]["served_bytes_authenticated"] is False
    assert "synthetic output" not in str(result)
    assert result["runtime"]["binary_sha256_before"] == hashlib.sha256(binary.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "fault", ["deadline", "request", "metadata", "empty", "model", "binary", "cleanup", "cleanup-type"]
)
def test_native_failure_or_changed_provenance_never_qualifies(native_fixture, fault):
    path, binary, _, Server, servers = native_fixture

    async def complete(self, *args):
        if fault == "deadline":
            await asyncio.sleep(5)
        if fault in ("request", "metadata"):
            raise RuntimeError("synthetic raw error must not enter receipt")
        if fault == "model":
            path.write_bytes(b"changed model")
        if fault == "binary":
            binary.write_bytes(b"changed binary")
        return ("" if fault == "empty" else "discard this synthetic text"), "unknown"

    Server.complete = complete
    if fault in ("cleanup", "cleanup-type"):

        def close(self):
            self.closed = True
            self.cleanup = {
                "direct_child_reaped": False if fault == "cleanup" else 1,
                "no_live_group_members_observed": True,
            }

        Server.close = close
    result = verify_gguf(str(path), runtime=True, timeout_seconds=0.01 if fault == "deadline" else 120)
    assert result["exit_code"] == 2 and not result["passed"] and result["structure"]["status"] == "pass"
    assert result["runtime"]["status"] == "unverified" and all(s.closed for s in servers)
    assert "synthetic raw error" not in str(result) and "discard this" not in str(result)


def test_native_async_cancellation_closes_owned_server(native_fixture):
    path, _, runtime, Server, servers = native_fixture
    from quantfit.gguf_structure import scan

    _, selected, identity = scan(str(path))

    async def complete(self, *a):
        await asyncio.sleep(30)

    Server.complete = complete

    async def run():
        task = asyncio.create_task(runtime._native(path, selected, identity, 120, 8))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert servers and all(s.closed for s in servers)


def test_runtime_platform_refuses_before_binary_provision(native_fixture, monkeypatch):
    path, _, runtime, _, servers = native_fixture
    monkeypatch.setattr(runtime, "_supported", lambda: False)
    monkeypatch.setattr(runtime.ga, "llama_server_bin", lambda: pytest.fail("binary provisioning"))
    result = verify_gguf(str(path), runtime=True)
    assert result["exit_code"] == 2 and result["runtime"]["status"] == "unverified" and not servers


def test_native_ram_admission_precedes_binary_and_server(native_fixture, monkeypatch):
    from types import SimpleNamespace

    import psutil

    path, _, runtime, _, servers = native_fixture
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(available=1))
    monkeypatch.setattr(runtime.ga, "llama_server_bin", lambda: pytest.fail("binary provisioning before admission"))
    result = verify_gguf(str(path), runtime=True)
    assert result["exit_code"] == 2 and "RAM" in result["runtime"]["reason"] and not servers


@pytest.mark.parametrize(
    "kwargs",
    [
        {"runtime": 1},
        {"timeout_seconds": True},
        {"timeout_seconds": float("nan")},
        {"max_new_tokens": True},
        {"max_new_tokens": 0},
    ],
)
def test_invalid_options_cannot_be_ignored_into_a_green_result(tmp_path, kwargs):
    assert verify_gguf(str(write(tmp_path, fixture_bytes())), **kwargs)["exit_code"] == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("served_model_verified", False),
        ("total_slots", True),
        ("native_context_size", 2048),
        ("raw_extra", "synthetic private value"),
    ],
)
def test_native_missing_or_changed_served_facts_prevent_qualification(native_fixture, field, value):
    path, _, _, Server, servers = native_fixture

    async def complete(self, *a):
        self.facts[field] = value
        return "discarded output", "stop"

    Server.complete = complete
    assert verify_gguf(str(path), runtime=True)["exit_code"] == 2
    assert all(s.closed for s in servers)


@pytest.mark.parametrize(
    "fault", ["normal", "props-oversize", "output-oversize", "compression", "metadata-change", "cancel"]
)
def test_shared_owned_http_is_bounded_cancellable_and_requests_identity(tmp_path, monkeypatch, fault):
    from types import SimpleNamespace

    import httpx

    import quantfit.gguf_server as shared

    path = write(tmp_path, fixture_bytes())
    server = object.__new__(shared.OwnedGgufServer)
    server.arm = SimpleNamespace(path=path, chat_template=False)
    server.proc = SimpleNamespace(poll=lambda: None)
    server.closed = False
    server.port = 1234
    server.facts = None
    factory = httpx.AsyncClient
    clients = []
    streams = []
    requests = []
    props_calls = 0
    monkeypatch.setattr(shared, "_MAX_HTTP_BYTES", 1024)

    class Stream(httpx.AsyncByteStream):
        def __init__(self, raw, block=False):
            self.raw = raw
            self.block = block
            self.closed = False

        async def __aiter__(self):
            if self.block:
                await asyncio.sleep(30)
            yield self.raw

        async def aclose(self):
            self.closed = True

    def handle(request):
        nonlocal props_calls
        requests.append(request)
        assert request.headers["accept-encoding"] == "identity"
        if request.url.path == "/health":
            raw = b"{}"
        elif request.url.path == "/props":
            props_calls += 1
            props = {
                "model_path": str(path),
                "total_slots": 1,
                "build_info": "synthetic",
                "chat_template": "changed" if fault == "metadata-change" and props_calls > 1 else "",
                "default_generation_settings": {"n_ctx": 4096},
            }
            raw = b"x" * 2048 if fault == "props-oversize" else json.dumps(props).encode()
        else:
            raw = (
                b"x" * 2048
                if fault == "output-oversize"
                else json.dumps({"content": "synthetic value", "stop_type": "limit"}).encode()
            )
        stream = Stream(raw, fault == "cancel" and request.method == "POST")
        streams.append(stream)
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip"} if fault == "compression" and request.method == "POST" else {},
            stream=stream,
        )

    def client(**kw):
        instance = factory(**kw, transport=httpx.MockTransport(handle))
        clients.append(instance)
        return instance

    monkeypatch.setattr(shared.httpx, "AsyncClient", client)

    async def run():
        if fault == "cancel":
            task = asyncio.create_task(server.complete("synthetic fixed input", 8))
            while not any(r.method == "POST" for r in requests):
                await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif fault == "normal":
            assert await server.complete("synthetic fixed input", 8) == ("synthetic value", "max_tokens")
        else:
            with pytest.raises(RuntimeError):
                await server.complete("synthetic fixed input", 8)

    asyncio.run(run())
    assert all(c.is_closed for c in clients) and all(s.closed for s in streams)
