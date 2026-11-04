"""All known outputs must stay distinct from the actual native derived cache entry."""

import hashlib
import json

import pytest
import test_baseline_cache_wiring as cache_fixtures
from test_probe_bundle_flows import local_bundle
from test_probe_corpus import rows

from quantfit import gate
from quantfit.safety import cache, gguf_arm
from quantfit.safety import verify as native

# Expose the existing native fixture locally; late plugin registration is order-dependent.
pair = cache_fixtures.pair


def actual_entry(pair, tmp_path):
    baseline, quant, _, folder = pair
    source, path = local_bundle(tmp_path)
    resolved, _ = gguf_arm.resolve_pair(baseline, quant, None)
    inputs = cache._local_fingerprint_inputs(
        gguf_arm.arm_identity(resolved),
        source=source,
        prompts=[r["prompt"] for r in rows(30)],
        max_new_tokens=64,
        do_sample=False,
        chat_template_policy=native.DECODE_CHAT_TEMPLATE_POLICY,
        env=cache.environment_identity(),
    )
    fingerprint = cache._digest(cache._DOMAIN_FINGERPRINT, inputs)
    folder.mkdir()
    return source, path, cache.entry_path(folder, fingerprint)


def record_actual(tmp_path, entry, generated, code=None):
    if entry.exists():
        data = entry.read_bytes()
        record = {
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "generation_calls": len(generated),
            "cli_exit": code,
        }
        (tmp_path / "actual-publication-counts.json").write_text(json.dumps(record), encoding="utf-8")


def test_nonconflicting_native_cache_and_report_positive(pair, tmp_path):
    baseline, quant, generated, folder = pair
    source, path, entry = actual_entry(pair, tmp_path)
    report = tmp_path / "report.json"
    native.verify_safety(
        baseline,
        quant,
        probe_corpus=source,
        probe_bundle_path=str(path),
        baseline_cache_dir=str(folder),
        report_path=str(report),
    )
    assert (
        len(generated) == 2
        and json.loads(entry.read_bytes())["header"]["fingerprint_inputs"]["probe"]["sha256"] == source.sha256
    )
    assert json.loads(report.read_bytes())["probe_dataset"]["sha256"] == source.sha256


@pytest.mark.parametrize("role", ["report", "capture", "gate-out", "gate-junit"])
def test_real_derived_cache_entry_refuses_every_simultaneous_output(pair, tmp_path, role):
    baseline, quant, generated, folder = pair
    source, path, entry = actual_entry(pair, tmp_path)
    before = path.read_bytes()
    common = {"probe_corpus": source, "probe_bundle_path": str(path), "baseline_cache_dir": str(folder)}
    if role == "gate-junit":
        from quantfit import cli

        code = cli.main(
            [
                "gate",
                "--baseline",
                baseline,
                "--quant",
                quant,
                "--threshold",
                "30",
                "--probe-bundle",
                str(path),
                "--probe-sha256",
                source.sha256,
                "--baseline-cache",
                str(folder),
                "--junit",
                str(entry),
                "--json",
            ]
        )
        record_actual(tmp_path, entry, generated, code)
        assert code == 2
    else:
        with pytest.raises(RuntimeError):
            if role == "gate-out":
                gate.run_gate(baseline, quant, threshold=0.30, out_path=str(entry), **common)
            else:
                native.verify_safety(
                    baseline, quant, **{**common, ("report_path" if role == "report" else "capture_path"): str(entry)}
                )
            record_actual(tmp_path, entry, generated)
    assert generated == [] and path.read_bytes() == before and not entry.exists()
