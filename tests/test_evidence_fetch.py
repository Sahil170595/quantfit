"""Approved public aggregate bytes over a fake HTTP transport, no local network."""

import asyncio
import copy
import json
import os
import subprocess
from pathlib import Path

import httpx
import pytest

from quantfit import evidence

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "validation/2026-10-09-phi4-public-candidate"


def originals():
    return {
        path: (
            SOURCE / "public-dataset-card.md"
            if path == "README.md"
            else SOURCE / "public-manifest.json"
            if path == evidence.PREFIX + "manifest.json"
            else SOURCE / "producer" / path.removeprefix(evidence.PREFIX)
        ).read_bytes()
        for path, _, _ in evidence.INVENTORY
    }


class Stream(httpx.AsyncByteStream):
    def __init__(self, raw):
        self.raw, self.closed = raw, False

    async def __aiter__(self):
        for index in range(0, len(self.raw), 97):
            yield self.raw[index : index + 97]

    async def aclose(self):
        self.closed = True


def transport(monkeypatch, held=None, headers=None):
    held = originals() if held is None else held
    calls, streams = [], []
    factory = httpx.AsyncClient

    def handle(request):
        calls.append(request)
        path = request.url.path.split(evidence.REVISION + "/", 1)[1]
        stream = Stream(held[path])
        streams.append(stream)
        return httpx.Response(200, headers=headers or {}, stream=stream)

    def client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return factory(**kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(evidence.httpx, "AsyncClient", client)
    return calls, streams


def test_fetch_preserves_all_originals_and_negative_receiving_analysis(tmp_path, monkeypatch):
    calls, streams = transport(monkeypatch)
    out = tmp_path / "received"
    result = evidence.fetch_evidence(str(out))
    assert result["integrity_verified"] is True and result["exit_code"] == 0
    assert result["receiving_analysis"]["exit_code"] == 3
    assert result["receiving_analysis"]["full_report_repeatability"]["pass"] is True
    assert result["receiving_analysis"]["native_t0"]["result"]["protocol_pass"] is True
    assert len(calls) == 12 and all(s.closed for s in streams)
    assert all("authorization" not in r.headers and "cookie" not in r.headers for r in calls)
    assert {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()} == originals()


@pytest.mark.parametrize("fault", ["truncated", "extra", "substitution", "compression"])
def test_bad_stream_never_publishes_a_target(tmp_path, monkeypatch, fault):
    held = originals()
    held["README.md"] = (
        held["README.md"][:-1]
        if fault == "truncated"
        else held["README.md"] + b"x"
        if fault == "extra"
        else b"x" + held["README.md"][1:]
    )
    transport(monkeypatch, held, {"Content-Encoding": "gzip"} if fault == "compression" else {})
    out = tmp_path / "received"
    with pytest.raises(evidence.EvidenceError):
        evidence.fetch_evidence(str(out))
    assert not out.exists() and not list(tmp_path.glob(".quantfit-evidence-*"))


@pytest.mark.parametrize("timeout", [0, -1, True, "1", float("inf"), float("nan"), 601])
def test_invalid_timeout_is_refused_before_http(tmp_path, monkeypatch, timeout):
    monkeypatch.setattr(evidence, "_download", lambda *a: pytest.fail("network workflow created"))
    with pytest.raises(evidence.EvidenceError):
        evidence.fetch_evidence(str(tmp_path / "new"), timeout_seconds=timeout)


def test_existing_target_refused_before_http(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "_download", lambda *a: pytest.fail("network workflow created"))
    with pytest.raises(evidence.EvidenceError):
        evidence.fetch_evidence(str(tmp_path))


def test_receiving_paths_canonicalize_without_resolving_producer_locators(tmp_path, monkeypatch):
    transport(monkeypatch)
    (tmp_path / "existing").mkdir()
    original = Path.resolve

    def resolve(path, *a, **kw):
        assert not str(path).startswith("/home/runner"), "followed original producer locator"
        return original(path, *a, **kw)

    monkeypatch.setattr(Path, "resolve", resolve)
    result = evidence.fetch_evidence(str(tmp_path / "existing/../new"))
    assert result["output_path"] == str(tmp_path / "new")
    assert all(".." not in r["path"] for r in result["receiving_analysis"]["runs"])
    assert result["original_t0"]["reports"][0]["path"].startswith("/home/runner/")


def test_symlink_parent_refuses_before_network(tmp_path, monkeypatch):
    real, link = tmp_path / "real", tmp_path / "linked"
    real.mkdir()
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    monkeypatch.setattr(evidence, "_download", lambda *a: pytest.fail("network workflow created"))
    with pytest.raises(evidence.EvidenceError):
        evidence.fetch_evidence(str(link / "new"))
    assert not list(real.iterdir())


@pytest.mark.skipif(os.name != "nt", reason="Windows junction profile")
def test_junction_output_parent_refuses_before_network(tmp_path, monkeypatch):
    link = tmp_path / "junction"
    quoted_link, quoted_target = [str(p).replace("'", "''") for p in (link, tmp_path)]
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f"New-Item -ItemType Junction -Path '{quoted_link}' -Target '{quoted_target}' | Out-Null",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    try:
        monkeypatch.setattr(evidence, "_download", lambda *a: pytest.fail("network workflow created"))
        with pytest.raises(evidence.EvidenceError):
            evidence.fetch_evidence(str(link / "new"))
    finally:
        link.rmdir()  # Remove only this owned link, never its target tree.


@pytest.mark.parametrize("fault", ["duplicate", "nonfinite", "private", "boolean-number"])
def test_strict_json_rejects_untrusted_types_before_any_publication(fault):
    held = originals()
    path = evidence.PREFIX + "assessment.json"
    raw = held[path]
    if fault == "duplicate":
        raw = b'{"assessment_schema_version":1,' + raw[1:]
    elif fault == "nonfinite":
        raw = raw.replace(b'"assessment_schema_version": 1', b'"assessment_schema_version": Infinity')
    elif fault == "private":
        raw = b'{"response":"synthetic forbidden field",' + raw[1:]
    else:
        raw = raw.replace(b'"assessment_schema_version": 1', b'"assessment_schema_version": true')
    held[path] = raw
    with pytest.raises(RuntimeError):
        evidence._validate_held(held, ["receiving-1", "receiving-2", "receiving-3"])


@pytest.mark.parametrize(
    "field",
    [
        "human_labels_authenticated",
        "scientific_go",
        "independent_execution_verified",
        "reference_registered",
        "sensitivity_established",
    ],
)
@pytest.mark.parametrize("bad", [True, 0, "false", {}])
def test_file_specific_false_claims_remain_false_even_with_new_byte_pins(monkeypatch, field, bad):
    held = originals()
    path = evidence.PREFIX + "assessment.json"
    value = json.loads(held[path])
    value[field] = bad
    held[path] = json.dumps(value).encode()
    with pytest.raises(evidence.EvidenceError):
        evidence._validate_held(held, ["receiving-1", "receiving-2", "receiving-3"])


@pytest.mark.parametrize("declared", ["0", "999999999", "invalid"])
def test_content_length_is_only_advisory(tmp_path, monkeypatch, declared):
    transport(monkeypatch, headers={"Content-Length": declared})
    assert evidence.fetch_evidence(str(tmp_path / "new"))["integrity_verified"]


def test_sdk_anonymous_headers_never_look_up_credentials_or_use_hub_cache(tmp_path, monkeypatch):
    import huggingface_hub
    from huggingface_hub.utils import _headers

    monkeypatch.setattr(_headers, "get_token", lambda: pytest.fail("cached credential read"))
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", lambda *a, **k: pytest.fail("Hub disk cache"))
    calls, _ = transport(monkeypatch, headers={"Set-Cookie": "secret=not-a-real-secret; Path=/"})
    evidence.fetch_evidence(str(tmp_path / "new"))
    assert all("cookie" not in r.headers and "authorization" not in r.headers for r in calls)
    assert not list(tmp_path.rglob(".cache"))


@pytest.mark.parametrize("kind", ["host", "scheme", "credentials", "revision", "path", "repo", "hops", "status"])
def test_redirects_are_bounded_and_validated_before_following(tmp_path, monkeypatch, kind):
    factory = httpx.AsyncClient
    calls = []

    def handle(request):
        calls.append(request)
        url = str(request.url)
        location = (
            url.replace("huggingface.co", "example.org")
            if kind == "host"
            else url.replace("https:", "http:")
            if kind == "scheme"
            else url.replace("https://", "https://user:pass@")
            if kind == "credentials"
            else url.replace(evidence.REVISION, "0" * 40)
            if kind == "revision"
            else url.replace("README.md", "unknown.json")
            if kind == "path"
            else url.replace(evidence.REPO, "unapproved-owner/unapproved-repo")
            if kind == "repo"
            else url
        )
        return httpx.Response(404 if kind == "status" else 302, headers={"location": location})

    monkeypatch.setattr(
        evidence.httpx, "AsyncClient", lambda **kw: factory(**kw, transport=httpx.MockTransport(handle))
    )
    with pytest.raises(evidence.EvidenceError):
        evidence.fetch_evidence(str(tmp_path / "new"))
    assert len(calls) == (4 if kind == "hops" else 1)


def test_supported_relative_api_redirect_is_anonymous_and_exact(tmp_path, monkeypatch):
    factory, held, calls = httpx.AsyncClient, originals(), []

    def handle(request):
        calls.append(request)
        path = request.url.path.split(evidence.REVISION + "/", 1)[1]
        if "/resolve/" in request.url.path:
            return httpx.Response(
                307,
                headers={
                    "location": "/api/resolve-cache/datasets/" + evidence.REPO + "/" + evidence.REVISION + "/" + path,
                    "Set-Cookie": "secret=not-real; Path=/",
                },
            )
        return httpx.Response(200, stream=Stream(held[path]))

    monkeypatch.setattr(
        evidence.httpx, "AsyncClient", lambda **kw: factory(**kw, transport=httpx.MockTransport(handle))
    )
    assert evidence.fetch_evidence(str(tmp_path / "new"))["integrity_verified"]
    assert len(calls) == 24 and all("cookie" not in r.headers for r in calls)


def test_one_deadline_covers_all_twelve_requests_and_closes_client(tmp_path, monkeypatch):
    factory, clients, calls = httpx.AsyncClient, [], []
    held = originals()

    async def handle(request):
        calls.append(request)
        await asyncio.sleep(0.02)
        path = request.url.path.split(evidence.REVISION + "/", 1)[1]
        return httpx.Response(200, stream=Stream(held[path]))

    def client(**kw):
        instance = factory(**kw, transport=httpx.MockTransport(handle))
        clients.append(instance)
        return instance

    monkeypatch.setattr(evidence.httpx, "AsyncClient", client)
    with pytest.raises(evidence.EvidenceError):
        evidence.fetch_evidence(str(tmp_path / "new"), timeout_seconds=0.05)
    assert 0 < len(calls) < 12 and all(c.is_closed for c in clients)
    assert not (tmp_path / "new").exists()


def test_active_loop_refusal_creates_no_coroutine_or_http(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "_download", lambda *a: pytest.fail("coroutine created"))

    async def run():
        with pytest.raises(evidence.EvidenceError, match="active event loop"):
            evidence.fetch_evidence(str(tmp_path / "new"))

    asyncio.run(run())


@pytest.mark.parametrize(
    "fault", ["duplicate", "traversal", "absolute", "backslash", "extra", "size-bool", "size-limit", "hash"]
)
def test_unsupported_inventory_is_refused_before_network(tmp_path, monkeypatch, fault):
    inventory = list(evidence.INVENTORY)
    path, size, sha = inventory[0]
    inventory[0] = (
        inventory[1][0]
        if fault == "duplicate"
        else "../README.md"
        if fault == "traversal"
        else "/README.md"
        if fault == "absolute"
        else "dir\\README.md"
        if fault == "backslash"
        else path,
        True if fault == "size-bool" else 22784 if fault == "size-limit" else size,
        "x" * 64 if fault == "hash" else sha,
    )
    if fault == "extra":
        inventory.append(("extra.json", 2, "0" * 64))
    monkeypatch.setattr(evidence, "INVENTORY", tuple(inventory))
    monkeypatch.setattr(evidence, "_download", lambda *a: pytest.fail("network workflow created"))
    with pytest.raises(evidence.EvidenceError):
        evidence.fetch_evidence(str(tmp_path / "new"))


@pytest.mark.parametrize(
    "fault",
    [
        "axes-count",
        "confirmed",
        "registered-bool",
        "registered-count",
        "private-root",
        "private-nested",
        "nested-false-marker",
        "membership",
        "circular",
        "report-identity",
        "report-cache",
        "native-count",
    ],
)
def test_semantic_profiles_and_same_held_relationships_reject_forgery_independently_of_network_sha(fault):
    held = originals()
    name = (
        "assessment.json"
        if fault in ("axes-count", "confirmed", "private-root", "private-nested", "nested-false-marker")
        else "manifest.json"
        if fault.startswith("registered") or fault in ("membership", "circular")
        else "native-cold-run.json"
        if fault == "native-count"
        else "run-2/report.json"
    )
    path = evidence.PREFIX + name
    value = json.loads(held[path])
    if fault == "axes-count":
        value["axes_by_run"][0]["over-refusal"]["flagged_flips"] = 1
    elif fault == "confirmed":
        value["axes_by_run"][0]["over-refusal"]["human_confirmed_flips"] = 2
    elif fault == "registered-bool":
        value["registered_reference_count"] = False
    elif fault == "registered-count":
        value["registered_reference_count"] = 1
    elif fault == "private-root":
        value["completion"] = "synthetic forbidden payload"
    elif fault == "private-nested":
        value["t0"]["completion"] = "synthetic forbidden payload"
    elif fault == "nested-false-marker":
        value["t0"]["human_labels_authenticated"] = False
    elif fault == "membership":
        value["files"][0] = copy.deepcopy(value["files"][1])
    elif fault == "circular":
        value["files"][0]["path"] = evidence.PREFIX + "manifest.json"
    elif fault == "report-identity":
        value["baseline"]["engine"]["binary_sha256"] = "0" * 64
    elif fault == "report-cache":
        value["baseline"]["engine"]["baseline_cache"] = {"served": True}
    else:
        value["runs"][0]["native_exit_code"] = 0
    held[path] = json.dumps(value).encode()
    with pytest.raises(RuntimeError):
        evidence._validate_held(held, ["receiving-1", "receiving-2", "receiving-3"])


@pytest.mark.parametrize(
    "fault", ["short", "partial", "flush", "close", "cancel", "persisted", "promote", "target-race"]
)
def test_failed_owned_staging_never_publishes_partial_or_overwrites_existing(tmp_path, monkeypatch, fault):
    transport(monkeypatch)
    opener, out = Path.open, tmp_path / "new"

    class File:
        def __init__(self, path, *a, **kw):
            self.file = opener(path, *a, **kw)

        def __enter__(self):
            return self

        def write(self, raw):
            if fault in ("partial", "short"):
                self.file.write(raw[:1])
                if fault == "partial":
                    raise OSError("synthetic partial failure")
                return 1
            if fault == "cancel":
                raise KeyboardInterrupt()
            return self.file.write(raw)

        def flush(self):
            self.file.flush()
            if fault == "flush":
                raise OSError("synthetic flush failure")

        def __exit__(self, *a):
            self.file.close()
            if fault == "close":
                raise OSError("synthetic close failure")

    def open_file(path, *a, **kw):
        return File(path, *a, **kw) if a and a[0] == "xb" else opener(path, *a, **kw)

    monkeypatch.setattr(Path, "open", open_file)
    if fault == "persisted":
        monkeypatch.setattr(evidence, "_read", lambda *a: b"changed after flush")
    if fault == "promote":
        monkeypatch.setattr(
            evidence, "_promoter", lambda: lambda *a: (_ for _ in ()).throw(OSError("synthetic promote failure"))
        )
    if fault == "target-race":
        promote = evidence._promoter()

        def race(stage, target):
            target.mkdir()
            return promote(stage, target)

        monkeypatch.setattr(evidence, "_promoter", lambda: race)
    with pytest.raises(KeyboardInterrupt if fault == "cancel" else evidence.EvidenceError):
        evidence.fetch_evidence(str(out))
    assert out.exists() is (fault == "target-race")
    assert not list(tmp_path.glob(".quantfit-evidence-*"))
    if out.exists():
        assert not list(out.iterdir())


@pytest.mark.parametrize("json_mode", [False, True])
def test_actual_cli_stream_success_with_fixture_transport_and_model_imports_blocked(tmp_path, json_mode):
    import sys

    import quantfit

    stub = tmp_path / "blocked"
    stub.mkdir()
    for name in ("torch", "transformers", "datasets", "llmcompressor"):
        (stub / f"{name}.py").write_text("raise ImportError('model backend deliberately blocked')", encoding="utf-8")
    origin = str(Path(quantfit.__file__).resolve().parents[1])
    code = f"""
import sys
sys.path.insert(0, {origin!r})
from pathlib import Path
import httpx
from quantfit import evidence
from quantfit.cli import main
source=Path({str(SOURCE)!r})
held={{path:(source/'public-dataset-card.md' if path=='README.md' else source/'public-manifest.json' if path==evidence.PREFIX+'manifest.json' else source/'producer'/path.removeprefix(evidence.PREFIX)).read_bytes() for path,_,_ in evidence.INVENTORY}}
class Stream(httpx.AsyncByteStream):
 async def __aiter__(self): yield self.raw
 async def aclose(self): pass
def handler(request):
 path=request.url.path.split(evidence.REVISION+'/',1)[1]
 stream=Stream(); stream.raw=held[path]
 return httpx.Response(200,stream=stream)
factory=httpx.AsyncClient
evidence.httpx.AsyncClient=lambda **kw:factory(**kw,transport=httpx.MockTransport(handler))
raise SystemExit(main(sys.argv[1:]))
"""
    out = tmp_path / "received"
    command = [sys.executable, "-c", code, "evidence", "fetch", "--out", str(out)]
    if json_mode:
        command.append("--json")
    env = dict(os.environ, PYTHONPATH=str(stub), CUDA_VISIBLE_DEVICES="-1")
    process = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, check=False, timeout=30)
    assert process.returncode == 0, process.stdout + process.stderr
    if json_mode:
        envelope = json.loads(process.stdout)
        assert envelope["command"] == "evidence" and envelope["exit_code"] == 0
        assert envelope["result"]["receiving_analysis"]["exit_code"] == 3
    else:
        assert (
            b"Public aggregate byte integrity: PASS" in process.stdout
            and b"receiving analysis exit 3" in process.stdout
        )
    moved = tmp_path / "relocated"
    out.rename(moved)
    assert {p.relative_to(moved).as_posix(): p.read_bytes() for p in moved.rglob("*") if p.is_file()} == originals()
