"""Native cache/T1 source identity controls; crafted GGUF headers, no inference."""

import hashlib
import json

import pytest
import test_baseline_cache_wiring as cache_fixtures
from test_probe_bundle_flows import local_bundle
from test_probe_corpus import rows, software_arms

from quantfit import LocalProbeCorpus
from quantfit.safety import cache, gguf_arm
from quantfit.safety import verify as native

# Expose the existing native fixture locally; late plugin registration is order-dependent.
pair = cache_fixtures.pair


def test_real_gguf_cache_relocation_and_same_prompts_different_raw_rekey(pair, tmp_path):
    baseline, quant, generated, folder = pair
    source, path = local_bundle(tmp_path, n=6)
    options = {"probe_corpus": source, "probe_bundle_path": str(path), "baseline_cache_dir": str(folder)}
    first = native.verify_safety(baseline, quant, **options)
    assert len(generated) == 2
    second = native.verify_safety(baseline, quant, **options)
    assert len(generated) == 3 and first.to_dict() == second.to_dict()
    relocated = tmp_path / "same-private-bytes.probe-bundle.json"
    relocated.write_bytes(path.read_bytes())
    native.verify_safety(baseline, quant, **{**options, "probe_bundle_path": str(relocated)})
    assert len(generated) == 4
    relocated.write_bytes(relocated.read_bytes() + b" \n")
    changed = LocalProbeCorpus(hashlib.sha256(relocated.read_bytes()).hexdigest())
    native.verify_safety(baseline, quant, **{**options, "probe_corpus": changed, "probe_bundle_path": str(relocated)})
    assert len(generated) == 6
    entries = [json.loads(p.read_bytes()) for p in folder.glob("*.baseline-cache.json")]
    assert len(entries) == 2
    identities = [e["header"]["fingerprint_inputs"]["probe"] for e in entries]
    assert {p["sha256"] for p in identities} == {source.sha256, changed.sha256}
    assert all(set(p) == {"source_kind", "format", "sha256", "n_prompts", "prompts_sha256"} for p in identities)
    assert all(p["source_kind"] == "local" and p["n_prompts"] == 6 for p in identities)
    assert len({p["prompts_sha256"] for p in identities}) == 1


def test_actual_derived_cache_filename_cannot_replace_its_consumed_bundle(pair, monkeypatch, tmp_path):
    baseline, quant, generated, folder = pair
    source, path = local_bundle(tmp_path, n=6)
    resolved, _ = gguf_arm.resolve_pair(baseline, quant, None)
    inputs = cache._local_fingerprint_inputs(
        gguf_arm.arm_identity(resolved),
        source=source,
        prompts=[r["prompt"] for r in rows(6)],
        max_new_tokens=64,
        do_sample=False,
        chat_template_policy=native.DECODE_CHAT_TEMPLATE_POLICY,
        env=cache.environment_identity(),
    )
    fingerprint = cache._digest(cache._DOMAIN_FINGERPRINT, inputs)
    folder.mkdir()
    alias = cache.entry_path(folder, fingerprint)
    assert alias.is_relative_to(tmp_path)
    before = path.read_bytes()
    alias.write_bytes(before)

    def forbidden(*args, **kwargs):
        raise AssertionError("derived input alias must refuse before native cache load/store")

    monkeypatch.setattr(cache, "load_served", forbidden)
    monkeypatch.setattr(cache, "store", forbidden)
    with pytest.raises(RuntimeError, match="invalid_probe_bundle_paths"):
        native.verify_safety(
            baseline, quant, probe_corpus=source, probe_bundle_path=str(alias), baseline_cache_dir=str(folder)
        )
    assert alias.read_bytes() == before and generated == []


def test_native_t1_compares_full_local_identity_and_local_t0_refuses(monkeypatch, tmp_path):
    from quantfit.reproduce import ReproduceError, compare, within_hardware_identical

    source, path = local_bundle(tmp_path)
    first, same, changed_report = tmp_path / "first.json", tmp_path / "same.json", tmp_path / "changed.json"
    software_arms(monkeypatch)
    native.verify_safety(
        "controlled/base", "controlled/quant", probe_corpus=source, probe_bundle_path=str(path), report_path=str(first)
    )
    data = json.loads(first.read_bytes())
    data["created_utc"] = "2026-11-01T00:00:00+00:00"
    same.write_text(json.dumps(data), encoding="utf-8")
    matched = compare(str(first), str(same))
    assert matched["checks"]["T1_same_measurement"]["pass"] is True
    assert "probe_dataset.id" not in matched["checks"]["T1_same_measurement"]["absent_on_both"]
    path.write_bytes(path.read_bytes() + b" \n")
    changed = LocalProbeCorpus(hashlib.sha256(path.read_bytes()).hexdigest())
    software_arms(monkeypatch)
    native.verify_safety(
        "controlled/base",
        "controlled/quant",
        probe_corpus=changed,
        probe_bundle_path=str(path),
        report_path=str(changed_report),
    )
    mismatched = compare(str(first), str(changed_report))
    t1 = mismatched["checks"]["T1_same_measurement"]
    assert t1["pass"] is False
    assert any(p["predicate"] == "T1.equal.probe_dataset.sha256" and p["pass"] is False for p in t1["predicates"])
    with pytest.raises(ReproduceError, match="local probe"):
        within_hardware_identical([str(first), str(same), str(changed_report)])
