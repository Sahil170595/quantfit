"""Actual public Inspect orchestration over synthetic server/file fixtures; no models."""

import asyncio
import hashlib
import os
import sys
from pathlib import Path

import pytest

from quantfit.inspect_task import InspectTaskError


@pytest.fixture
def fixture(monkeypatch, tmp_path):
    pytest.importorskip("inspect_ai")
    from inspect_ai.model import get_model

    import quantfit.inspect_gguf as extension
    from quantfit.safety.gguf_arm import ResolvedGguf

    binary = tmp_path / "server"
    binary.write_bytes(b"synthetic binary")
    arms = []
    for name, dtype in (("base", "F16"), ("quant", "Q4_K_M")):
        path = tmp_path / f"{name}.gguf"
        path.write_bytes(name.encode())
        arms.append(
            ResolvedGguf(
                str(path), path, None, hashlib.sha256(path.read_bytes()).hexdigest(), "llama", dtype, False, name
            )
        )
    monkeypatch.setattr(extension, "_posix_supported", lambda: True)
    monkeypatch.setattr(extension.ga, "_resolve", lambda ref, token, **kw: next(a for a in arms if a.ref == ref))
    monkeypatch.setattr(extension.ga, "llama_server_bin", lambda: binary)
    monkeypatch.setattr(extension.ga, "_threads", lambda: 2)
    monkeypatch.setattr(extension, "_available_ram", lambda: 16 * 1024**3)
    servers = []

    class Server:
        def __init__(self, arm, binary, threads):
            self.arm, self.closed, self.calls = arm, False, 0
            self.facts = {
                "served_model_verified": True,
                "served_build": "synthetic",
                "served_template_sha256": "a" * 64,
                "native_context_size": 4096,
                "total_slots": 1,
            }
            servers.append(self)

        async def complete(self, prompt, max_tokens):
            assert not self.closed and isinstance(prompt, str) and max_tokens > 0
            self.calls += 1
            return f"synthetic {self.arm.name}", "unknown"

        def close(self):
            self.closed = True

    monkeypatch.setattr(extension, "OwnedGgufServer", Server)
    return extension, get_model, arms, servers, binary


def test_public_provider_reuses_one_server_and_reports_actual_calls(fixture):
    _, get_model, arms, servers, _ = fixture
    from inspect_ai.model import GenerateConfig

    model = get_model(f"quantfit_gguf/{arms[0].ref}", memoize=False)

    async def run():
        for _ in range(3):
            out = await model.generate("synthetic", config=GenerateConfig(temperature=0, max_tokens=64))
            assert out.completion == "synthetic base"
        await model.api.aclose()

    asyncio.run(run())
    assert len(servers) == 1 and servers[0].closed and servers[0].calls == 3
    assert model.api.calls == 3


def test_missing_stop_metadata_is_unknown_not_clean_stop(fixture):
    from inspect_ai.model import GenerateConfig

    _, get_model, arms, _, _ = fixture
    model = get_model(f"quantfit_gguf/{arms[0].ref}", memoize=False)
    try:
        output = asyncio.run(model.generate("synthetic", config=GenerateConfig(temperature=0, max_tokens=64)))
        assert output.stop_reason == "unknown"
    finally:
        model.api.close()


@pytest.mark.parametrize(
    "kwargs",
    [{"base_url": "http://example.invalid"}, {"model_path": "forged"}, {"device": "cuda"}, {"revision": "main"}],
)
def test_public_source_or_runtime_override_refuses_before_server(fixture, kwargs):
    _, get_model, arms, servers, _ = fixture
    with pytest.raises((InspectTaskError, TypeError, RuntimeError)):
        get_model(f"quantfit_gguf/{arms[0].ref}", memoize=False, **kwargs)
    assert not servers


@pytest.mark.parametrize(
    "kwargs",
    [
        {"temperature": 1},
        {"top_p": 0.5},
        {"cache": True},
        {"system_message": "forged"},
        {"extra_body": {"seed": 0}},
        {"max_retries": 1},
        {"timeout": 1},
        {"attempt_timeout": 1},
    ],
)
def test_provider_rejects_ignored_generation_knobs(fixture, kwargs):
    from inspect_ai.model import GenerateConfig

    _, get_model, arms, servers, _ = fixture
    model = get_model(f"quantfit_gguf/{arms[0].ref}", memoize=False)
    with pytest.raises(RuntimeError):
        asyncio.run(model.generate("synthetic", config=GenerateConfig(max_tokens=64, **kwargs)))
    assert not servers


def test_pair_ram_admission_happens_before_any_server(fixture, monkeypatch):
    ext, get_model, arms, servers, _ = fixture
    monkeypatch.setattr(ext, "_available_ram", lambda: 1)
    with pytest.raises(InspectTaskError, match="RAM"):
        ext.GgufRunObserver(tuple(f"quantfit_gguf/{a.ref}" for a in arms), (None, None), get_model, None)
    assert not servers


def test_managed_retry_override_is_refused_instead_of_overwritten(fixture):
    from inspect_ai.model import GenerateConfig

    ext, get_model, arms, servers, _ = fixture
    observer = ext.GgufRunObserver(tuple(f"quantfit_gguf/{a.ref}" for a in arms), (None, None), get_model, None)
    try:
        with pytest.raises(InspectTaskError, match="retry"):
            asyncio.run(observer.generate(0, "synthetic", GenerateConfig(temperature=0, max_tokens=64, max_retries=1)))
        assert not servers
    finally:
        observer.close()


def test_public_qsr_eval_missing_hub_pins_refuses_before_any_load(fixture, monkeypatch):
    import quantfit.inspect_task as task
    from quantfit.safety import verify

    ext, _, _, servers, _ = fixture
    monkeypatch.setattr(ext.ga, "_resolve", lambda *a, **kw: pytest.fail("weight resolution forbidden"))
    monkeypatch.setattr(verify, "_load_probes", lambda *a, **kw: pytest.fail("dataset load forbidden"))
    with pytest.raises(InspectTaskError, match="immutable revision"):
        task.qsr_eval("quantfit_gguf/hf:org/repo/base.gguf", "quantfit_gguf/hf:org/repo/quant.gguf")
    assert not servers and not ext.RUN_LOCK.locked()


def test_observer_detects_source_substitution_and_closes_both(fixture):
    from inspect_ai.model import GenerateConfig

    ext, get_model, arms, servers, _ = fixture
    observer = ext.GgufRunObserver(tuple(f"quantfit_gguf/{a.ref}" for a in arms), (None, None), get_model, None)

    async def run():
        await observer.generate(0, "synthetic", GenerateConfig(temperature=0, max_tokens=64))
        await observer.generate(1, "synthetic", GenerateConfig(temperature=0, max_tokens=64))

    asyncio.run(run())
    arms[0].path.write_bytes(b"changed")
    with pytest.raises(InspectTaskError, match="bytes changed"):
        observer.finish(1)
    observer.close()
    assert len(servers) == 2 and all(s.closed for s in servers)


@pytest.mark.parametrize("pin_mode", ["explicit", "omitted"])
def test_actual_public_inspect_full_fixture_batch_closes_before_judge(fixture, monkeypatch, tmp_path, pin_mode):
    import quantfit.inspect_task as task
    from quantfit.safety import verify
    from quantfit.safety.report import DriftReport

    ext, _, arms, servers, binary = fixture
    probes = [
        verify.Probe(f"synthetic {i}", "clear_unsafe" if i < 20 else "clear_safe", "unsafe" if i < 20 else "safe")
        for i in range(40)
    ]
    monkeypatch.setattr(verify, "_load_probes", lambda token: probes)
    batches = []

    def judge(outputs, token):
        assert len(servers) == 2 and all(s.closed for s in servers)
        batches.append(len(outputs))
        return [True] * len(outputs), 0.1

    monkeypatch.setattr(verify, "_classify_refusals", judge)
    import quantfit.safety.report as report_module

    monkeypatch.setattr(
        report_module,
        "environment_fingerprint",
        lambda: {
            "device": "cpu",
            "python": "synthetic",
            "torch": "synthetic",
            "transformers": "synthetic",
            "cuda": None,
        },
    )
    run = task.qsr_eval(
        *(f"quantfit_gguf/{a.ref}" for a in arms),
        **({"gguf_revisions": (None, None)} if pin_mode == "explicit" else {}),
        max_new_tokens=64,
        log_dir=str(tmp_path / "private"),
        display="none",
        max_samples=1,
    )
    assert batches == [80] and len(run.outcomes) == 40
    assert [a.engine["generate_calls"] for a in run.observed_arms] == [40, 40]
    report = tmp_path / "report.json"
    run.write_report(str(report), *run.observed_arms, 64)
    parsed = DriftReport.from_json(str(report))
    from quantfit.bundle import _report
    from quantfit.safety.calibration_binding import measurement_identity

    _report(report.read_bytes())
    assert measurement_identity(parsed)["baseline"]["engine"]["name"] == "inspect_ai:quantfit_gguf"
    assert parsed.baseline.artifact_sha256 == arms[0].sha256
    assert not ext.RUN_LOCK.locked()
    # Prevent any destructive red run: the assembler is an explicit tripwire.
    monkeypatch.setattr(verify, "_write_report", lambda *a, **kw: pytest.fail("writer reached a protected input"))
    with pytest.raises(InspectTaskError, match="protected inputs"):
        task.write_drift_report(str(tmp_path / "bare-report.json"), run.outcomes, *run.observed_arms, 64)
    assert not (tmp_path / "bare-report.json").exists()
    for source in (*[a.path for a in arms], binary):
        original = source.read_bytes()
        with pytest.raises(InspectTaskError, match="overwrite"):
            run.write_report(str(source), *run.observed_arms, 64)
        assert source.read_bytes() == original


def test_async_cancellation_closes_both_without_worker_thread(fixture, monkeypatch):
    from inspect_ai.model import GenerateConfig

    ext, get_model, arms, servers, _ = fixture
    observer = ext.GgufRunObserver(tuple(f"quantfit_gguf/{a.ref}" for a in arms), (None, None), get_model, None)
    original = ext.OwnedGgufServer.complete

    async def run():
        started = asyncio.Event()

        async def blocked(server, prompt, tokens):
            if server.arm.name == "quant":
                started.set()
                await asyncio.Event().wait()
            return await original(server, prompt, tokens)

        monkeypatch.setattr(ext.OwnedGgufServer, "complete", blocked)
        config = GenerateConfig(temperature=0, max_tokens=64)
        await observer.generate(0, "synthetic", config)
        pending = asyncio.create_task(observer.generate(1, "synthetic", config))
        await started.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        observer.close()

    asyncio.run(run())
    assert len(servers) == 2 and all(s.closed for s in servers)
    assert observer.active_arm is None


def test_managed_mode_pins_cache_concurrency_and_observes_request_count(fixture, monkeypatch):
    from inspect_ai.model import GenerateConfig, ModelOutput

    ext, get_model, arms, _, _ = fixture
    observer = ext.GgufRunObserver(tuple(f"quantfit_gguf/{a.ref}" for a in arms), (None, None), get_model, None)
    configs = []

    async def cached(prompt, config):
        configs.append(config)
        return ModelOutput.from_content("synthetic", "synthetic cached")

    monkeypatch.setattr(observer.models[0], "generate", cached)
    with pytest.raises(InspectTaskError, match="cached/retried"):
        asyncio.run(observer.generate(0, "synthetic", GenerateConfig(temperature=0, max_tokens=64)))
    assert configs[0].cache is False and configs[0].max_connections == 1
    assert configs[0].max_retries == 0
    assert configs[0].adaptive_connections is False
    observer.close()


def test_cleanup_failure_does_not_return_observed_arms(fixture, monkeypatch):
    from inspect_ai.model import GenerateConfig

    ext, get_model, arms, servers, _ = fixture
    observer = ext.GgufRunObserver(tuple(f"quantfit_gguf/{a.ref}" for a in arms), (None, None), get_model, None)

    async def run():
        for arm in (0, 1):
            await observer.generate(arm, "synthetic", GenerateConfig(temperature=0, max_tokens=64))

    asyncio.run(run())

    def failed(server):
        server.closed = True
        if server.arm.name == "base":
            raise InspectTaskError("synthetic cleanup failed")

    monkeypatch.setattr(ext.OwnedGgufServer, "close", failed)
    with pytest.raises(InspectTaskError, match="cleanup failed"):
        observer.before_judge(1)
    assert all(s.closed for s in servers) and not hasattr(observer, "_observed_arms")


def test_shared_native_body_is_greedy_and_does_not_reuse_kv():
    import json

    from quantfit.safety.gguf_arm import completion_request

    chat = completion_request(1234, "synthetic", True, 64)
    raw = completion_request(1234, "synthetic", False, 64)
    assert json.loads(chat.data) == {
        "messages": [{"role": "user", "content": "synthetic"}],
        "temperature": 0,
        "max_tokens": 64,
        "cache_prompt": False,
    }
    assert json.loads(raw.data) == {"prompt": "synthetic", "temperature": 0, "n_predict": 64, "cache_prompt": False}


@pytest.mark.parametrize("mismatch", ["quantized-baseline", "architecture", "binary", "threads"])
def test_pair_mismatch_refuses_before_either_server(fixture, monkeypatch, mismatch):
    from dataclasses import replace

    ext, get_model, arms, servers, binary = fixture
    if mismatch == "quantized-baseline":
        arms[0] = replace(arms[0], file_type="Q4_K_M")
    elif mismatch == "architecture":
        arms[1] = replace(arms[1], architecture="different")
    elif mismatch == "binary":
        other = binary.with_name("other-server")
        other.write_bytes(b"different binary")
        choices = iter((binary, other))
        monkeypatch.setattr(ext.ga, "llama_server_bin", lambda: next(choices))
    else:
        choices = iter((2, 3))
        monkeypatch.setattr(ext.ga, "_threads", lambda: next(choices))
    with pytest.raises(InspectTaskError):
        ext.GgufRunObserver(tuple(f"quantfit_gguf/{a.ref}" for a in arms), (None, None), get_model, None)
    assert not servers


@pytest.mark.parametrize(
    "key,value",
    [("model_path", "wrong.gguf"), ("total_slots", True), ("total_slots", 2), ("n_ctx", 4096.0), ("build_info", None)],
)
def test_served_metadata_rejects_alias_types_and_source_mismatch(fixture, key, value):
    _, _, arms, _, _ = fixture
    from quantfit.inspect_gguf import _observe_server_metadata

    props = {
        "model_path": str(arms[0].path),
        "total_slots": 1,
        "build_info": "synthetic",
        "chat_template": "",
        "default_generation_settings": {"n_ctx": 4096},
    }
    if key == "n_ctx":
        props["default_generation_settings"][key] = value
    else:
        props[key] = value
    with pytest.raises(InspectTaskError):
        _observe_server_metadata(props, arms[0])


@pytest.mark.parametrize(
    "chat,reason,expected",
    [
        (True, "length", "max_tokens"),
        (True, "stop", "stop"),
        (True, None, "unknown"),
        (True, "future", "unknown"),
        (False, "limit", "max_tokens"),
        (False, "eos", "stop"),
        (False, "word", "stop"),
        (False, None, "unknown"),
        (False, "none", "unknown"),
    ],
)
def test_endpoint_stop_reason_is_preserved_through_public_output(fixture, monkeypatch, chat, reason, expected):
    from inspect_ai.model import GenerateConfig

    ext, get_model, arms, _, _ = fixture
    if chat:
        payload = {"choices": [{"message": {"content": " synthetic "}, "finish_reason": reason}]}
    else:
        payload = {"content": " synthetic ", "stop_type": reason}

    async def result(server, prompt, tokens):
        return ext._completion_result(payload, chat)

    monkeypatch.setattr(ext.OwnedGgufServer, "complete", result)
    model = get_model(f"quantfit_gguf/{arms[0].ref}", memoize=False)
    try:
        output = asyncio.run(model.generate("synthetic", config=GenerateConfig(temperature=0, max_tokens=64)))
        assert output.completion == "synthetic" and output.stop_reason == expected
    finally:
        model.api.close()


@pytest.mark.skipif(os.name != "posix" or not Path("/proc").is_dir(), reason="owned Linux process-group test")
def test_real_async_http_cancellation_closes_owned_group(monkeypatch, tmp_path):
    """Real socket/POSIX containment over a synthetic stdlib server, no model execution."""
    pytest.importorskip("inspect_ai")
    from inspect_ai.model import GenerateConfig, get_model

    import quantfit.inspect_gguf as ext
    from quantfit.safety.gguf_arm import ResolvedGguf

    weights = tmp_path / "synthetic.gguf"
    weights.write_bytes(b"synthetic weights, not GGUF")
    arm = ResolvedGguf(
        str(weights),
        weights,
        None,
        hashlib.sha256(weights.read_bytes()).hexdigest(),
        "llama",
        "F16",
        False,
        "synthetic",
    )
    binary = tmp_path / "synthetic-server"
    binary.write_text(
        f"#!{sys.executable}\n"
        + """
import http.server, json, pathlib, sys, time
args = sys.argv[1:]
assert args[args.index('--device')+1] == 'none'
assert args[args.index('--n-gpu-layers')+1] == '0' and '--no-op-offload' in args
port = int(args[args.index('--port')+1])
path = args[args.index('-m')+1]
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        data = ({'model_path': path, 'total_slots': 1, 'build_info': 'synthetic',
                 'chat_template': '', 'default_generation_settings': {'n_ctx': 4096}}
                if self.path == '/props' else {})
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        pathlib.Path(path+'.started').write_bytes(b'started')
        time.sleep(30)
http.server.HTTPServer(('127.0.0.1', port), Handler).serve_forever()
""",
        encoding="utf-8",
    )
    binary.chmod(0o700)
    monkeypatch.setattr(ext.ga, "_resolve", lambda *a, **kw: arm)
    monkeypatch.setattr(ext.ga, "llama_server_bin", lambda: binary)
    monkeypatch.setattr(ext.ga, "_threads", lambda: 2)
    monkeypatch.setattr(ext, "_available_ram", lambda: 16 * 1024**3)
    model = get_model(f"quantfit_gguf/{weights}", memoize=False)

    async def run():
        pending = asyncio.create_task(model.generate("synthetic", config=GenerateConfig(temperature=0, max_tokens=64)))
        try:

            async def started():
                while not Path(str(weights) + ".started").exists():
                    if pending.done():
                        await pending
                        pytest.fail("request returned before synthetic blocked endpoint")
                    await asyncio.sleep(0.05)

            await asyncio.wait_for(started(), 15)
        finally:
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            model.api.close()

    asyncio.run(run())
    server = model.api.server
    assert server.closed and server.proc.poll() is not None
    assert server.cleanup["direct_child_reaped"] and server.cleanup["no_live_group_members_observed"] is True
    assert model.api.calls == 0 and model.api.request_calls == 1
