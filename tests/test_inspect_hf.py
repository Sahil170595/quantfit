"""Hermetic observed-HF boundary tests; these fake weights do not qualify a provider."""

import asyncio
import json
import types

import pytest

from quantfit import inspect_hf as hf

SHA = "a" * 40
_REAL_SNAPSHOT = hf._snapshot


def snapshot(tmp_path):
    path = tmp_path / "snapshots" / SHA
    path.mkdir(parents=True)
    (path / "config.json").write_text("{}")
    (path / "tokenizer.json").write_text("{}")
    (path / "model.safetensors").write_bytes(b"fixture weights")
    return path


def loaded(path, *, dtype="torch.float32", tokenizer_path=None):
    weights = types.SimpleNamespace(
        name_or_path=str(path),
        dtype=dtype,
        device="cpu",
        config=types.SimpleNamespace(_commit_hash=None, quantization_config=None),
    )
    weights.generate = lambda **kwargs: [123]
    provider = types.SimpleNamespace(
        model=weights,
        tokenizer=types.SimpleNamespace(name_or_path=str(tokenizer_path or path), chat_template="fixture"),
        do_sample=False,
    )

    async def generate(prompt, config):
        provider.model.generate()
        return types.SimpleNamespace(completion="fixture")

    return types.SimpleNamespace(api=provider, generate=generate)


@pytest.fixture
def factory(monkeypatch, tmp_path):
    path = snapshot(tmp_path)
    monkeypatch.setattr(hf, "_inspect_version", lambda: "0.3.269")
    monkeypatch.setattr(hf, "_snapshot", lambda repo, revision, token: path)
    monkeypatch.setattr(hf, "_provider_type", lambda: types.SimpleNamespace)
    # Fake weights have fixture versions; unit jobs need neither runtime package.
    real_version = hf.importlib.metadata.version
    versions = {"transformers": "fixture-transformers", "torch": "fixture-torch"}
    monkeypatch.setattr(
        hf.importlib.metadata, "version", lambda name: versions[name] if name in versions else real_version(name)
    )
    return path


def observer(factory, get_model=None):
    return hf.HfRunObserver(
        ("hf/example/base", "hf/example/quant"),
        (SHA, SHA),
        get_model or (lambda spec, **kwargs: loaded(factory)),
        None,
    )


@pytest.mark.parametrize("revision", [None, "main", "a" * 39, "z" * 40])
def test_revision_refused_before_download(factory, monkeypatch, revision):
    monkeypatch.setattr(hf, "_snapshot", lambda *args: pytest.fail("must refuse before network"))
    with pytest.raises(RuntimeError, match="immutable"):
        hf.HfRunObserver(("hf/example/base", "hf/example/quant"), (revision, SHA), lambda *a, **k: None, None)


def test_unverified_inspect_version_refused(factory, monkeypatch):
    monkeypatch.setattr(hf, "_inspect_version", lambda: "0.3.270")
    with pytest.raises(RuntimeError, match="0.3.269"):
        observer(factory)


@pytest.mark.parametrize("dtype", [None, "auto", "", "not-a-dtype"])
def test_missing_loaded_precision_refused(factory, dtype):
    with pytest.raises(RuntimeError, match="precision"):
        observer(factory, lambda *a, **k: loaded(factory, dtype=dtype))


def test_tokenizer_and_weights_must_be_actual_snapshot(factory):
    with pytest.raises(RuntimeError, match="tokenizer"):
        observer(factory, lambda *a, **k: loaded(factory, tokenizer_path=factory.parent))


def test_wrong_loaded_weight_path_refused(factory):
    with pytest.raises(RuntimeError, match="weights"):
        observer(factory, lambda *a, **k: loaded(factory.parent))


def test_containment_and_per_arm_calls(factory):
    calls = []

    def get_model(spec, **kwargs):
        calls.append((spec, kwargs))
        return loaded(factory)

    run = observer(factory, get_model)
    assert all(c[1]["model_path"] == c[1]["tokenizer_path"] == str(factory) for c in calls)
    assert all(c[1]["do_sample"] is False for c in calls)
    for arm in (0, 1, 0, 1):
        asyncio.run(run.generate(arm, "fixture", None))
    arms = run.finish(2)
    assert all(a.revision == SHA and a.resolved_dtype == "torch.float32" and a.runtime_s > 0 for a in arms)
    assert all(a.engine["generate_calls"] == 2 for a in arms)
    assert all(a.engine["transformers_version"] == "fixture-transformers" for a in arms)
    assert all(a.engine["torch_version"] == "fixture-torch" for a in arms)
    assert all(a.engine["tokenizer_revision"] == SHA for a in arms)
    assert arms[0].engine["snapshot_manifest_sha256"] == arms[1].engine["snapshot_manifest_sha256"]
    assert str(factory) not in json.dumps([a.engine for a in arms])


def test_identical_memoized_model_keeps_separate_arm_timing(factory):
    model = loaded(factory)
    run = observer(factory, lambda *a, **k: model)
    asyncio.run(run.generate(0, "fixture", None))
    asyncio.run(run.generate(1, "fixture", None))
    assert [a.engine["generate_calls"] for a in run.finish(1)] == [1, 1]


def test_no_actual_weight_generation_refused(factory):
    model = loaded(factory)

    async def cached(prompt, config):
        return types.SimpleNamespace(completion="fixture")

    model.generate = cached
    run = observer(factory, lambda *a, **k: model)
    with pytest.raises(RuntimeError, match="actual.*generate"):
        asyncio.run(run.generate(0, "fixture", None))
    run.close()


def test_snapshot_changed_after_loading_refused(factory):
    run = observer(factory)
    for arm in (0, 1):
        asyncio.run(run.generate(arm, "fixture", None))
    (factory / "model.safetensors").write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="changed"):
        run.finish(1)
    run.close()


def test_runtime_overlaps_refused(factory):
    run = observer(factory)
    run.active_arm = 1
    with pytest.raises(RuntimeError, match="concurrent"):
        asyncio.run(run.generate(0, "fixture", None))
    run.close()


def test_loaded_precision_changes_inside_actual_generate_refused(factory):
    model = loaded(factory)

    def change(**kwargs):
        model.api.model.dtype = "torch.float16"
        return [123]

    model.api.model.generate = change
    run = observer(factory, lambda *a, **k: model)
    with pytest.raises(RuntimeError, match="changed"):
        asyncio.run(run.generate(0, "fixture", None))
    run.close()


def test_wrong_arm_weight_routing_refused(factory):
    models = [loaded(factory), loaded(factory)]
    run = observer(factory, lambda *a, **k: models.pop(0))

    async def wrong(prompt, config):
        run.models[1].api.model.generate()
        return types.SimpleNamespace(completion="fixture")

    run.models[0].generate = wrong
    with pytest.raises(RuntimeError, match="another arm"):
        asyncio.run(run.generate(0, "fixture", None))
    run.close()


def test_retries_are_not_one_qsr_call(factory):
    model = loaded(factory)

    async def retry(prompt, config):
        model.api.model.generate()
        model.api.model.generate()
        return types.SimpleNamespace(completion="fixture")

    model.generate = retry
    run = observer(factory, lambda *a, **k: model)
    with pytest.raises(RuntimeError, match="exactly one"):
        asyncio.run(run.generate(0, "fixture", None))
    run.close()


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("device", None, "device"),
        ("config_commit_hash", "b" * 40, "revision"),
        ("do_sample", True, "greedy"),
        ("tokenizer", None, "unavailable"),
    ],
)
def test_actual_source_metadata_must_be_consistent(factory, field, value, match):
    model = loaded(factory)
    if field == "config_commit_hash":
        model.api.model.config._commit_hash = value
    elif field == "do_sample" or field == "tokenizer":
        setattr(model.api, field, value)
    else:
        setattr(model.api.model, field, value)
    with pytest.raises(RuntimeError, match=match):
        observer(factory, lambda *a, **k: model)


def test_snapshot_receipt_rejects_moved_revision(monkeypatch, factory):
    import huggingface_hub

    monkeypatch.setattr(
        huggingface_hub,
        "HfApi",
        lambda **k: types.SimpleNamespace(model_info=lambda *a, **k: types.SimpleNamespace(sha="b" * 40)),
    )
    with pytest.raises(RuntimeError, match="resolve"):
        _REAL_SNAPSHOT("example/base", SHA, None)


def test_snapshot_receipt_rejects_non_snapshot_directory(monkeypatch, factory):
    import huggingface_hub

    monkeypatch.setattr(
        huggingface_hub,
        "HfApi",
        lambda **k: types.SimpleNamespace(model_info=lambda *a, **k: types.SimpleNamespace(sha=SHA)),
    )
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda *a, **k: str(factory.parent))
    with pytest.raises(RuntimeError, match="identity"):
        _REAL_SNAPSHOT("example/base", SHA, None)


def test_known_hub_http_failure_is_operational(monkeypatch):
    import httpx
    import huggingface_hub

    def failure(*a, **k):
        raise httpx.ConnectError("synthetic offline boundary")

    monkeypatch.setattr(huggingface_hub, "HfApi", lambda **k: types.SimpleNamespace(model_info=failure))
    with pytest.raises(RuntimeError, match="cannot resolve immutable"):
        _REAL_SNAPSHOT("example/base", SHA, None)


def test_quantization_metadata_is_hashed_not_published(factory):
    model = loaded(factory)
    model.api.model.config.quantization_config = {
        "quant_method": "fixture",
        "calibration_text": "local capture fixture",
    }
    run = observer(factory, lambda *a, **k: model)
    for arm in (0, 1):
        asyncio.run(run.generate(arm, "fixture", None))
    arms = run.finish(1)
    assert "local capture fixture" not in json.dumps([a.engine for a in arms])
    assert all(len(a.engine["quantization_config_sha256"]) == 64 for a in arms)


def test_mutated_nested_quantization_config_refused(factory):
    model = loaded(factory)
    model.api.model.config.quantization_config = {"quant_method": "fixture", "bits": 4}
    run = observer(factory, lambda *a, **k: model)
    model.api.model.config.quantization_config["bits"] = 8
    with pytest.raises(RuntimeError, match="changed"):
        asyncio.run(run.generate(0, "fixture", None))
    run.close()


@pytest.mark.parametrize("value", [float("nan"), object()])
def test_non_json_observation_metadata_refused(factory, value):
    model = loaded(factory)
    model.api.model.config.quantization_config = {"bits": value}
    with pytest.raises(RuntimeError, match="finite JSON"):
        observer(factory, lambda *a, **k: model)


def test_snapshot_positive_receipt_uses_exact_sha_for_download(monkeypatch, factory):
    import huggingface_hub

    requested = []
    monkeypatch.setattr(
        huggingface_hub,
        "HfApi",
        lambda **k: types.SimpleNamespace(model_info=lambda *a, **k: types.SimpleNamespace(sha=SHA)),
    )

    def download(repo, **kwargs):
        requested.append(kwargs)
        return str(factory)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
    assert _REAL_SNAPSHOT("example/base", SHA, None) == factory
    assert requested[0]["revision"] == SHA


def test_no_partial_generation_can_be_finalized(factory):
    run = observer(factory)
    asyncio.run(run.generate(0, "fixture", None))
    with pytest.raises(RuntimeError, match="full pinned corpus"):
        run.finish(1)
    run.close()


def test_nonfinite_measured_runtime_is_not_reportable(factory):
    run = observer(factory)
    for arm in (0, 1):
        asyncio.run(run.generate(arm, "fixture", None))
    run.runtime[1] = float("nan")
    with pytest.raises(RuntimeError, match="runtime unavailable"):
        run.finish(1)
    run.close()


def test_quantization_config_object_conversion_is_hashed(factory):
    model = loaded(factory)
    model.api.model.config.quantization_config = types.SimpleNamespace(
        to_dict=lambda: {"quant_method": "fixture", "bits": 4}
    )
    run = observer(factory, lambda *a, **k: model)
    assert run.facts[0]["quantization_method"] == "fixture"
    run.close()
