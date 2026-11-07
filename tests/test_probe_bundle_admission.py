"""Whole local JSON/role/pin receiving boundaries before any model contact."""

import copy
import hashlib
import json
import os

import pytest
from test_probe_bundle_flows import local_bundle
from test_probe_corpus import rows, software_arms

from quantfit import LocalProbeCorpus, gate, prepare_probe_bundle
from quantfit.probe_bundle import ProbeBundleError
from quantfit.safety import verify as native


@pytest.mark.parametrize(
    "raw",
    [
        b'{"probe_bundle_schema":1,"probe_bundle_schema":1,"probes":[]}',
        b'{"probe_bundle_schema":true,"probes":[]}',
        b'{"probe_bundle_schema":1.0,"probes":[]}',
        b'{"probe_bundle_schema":1,"probes":[{"prompt":"x","prompt":"y","zone":"clear_safe","expected":"safe"}]}',
        b'{"probe_bundle_schema":1,"probes":[]} {}',
        b'{"probe_bundle_schema":1,"probes":[],"unexpected":0}',
        b'{"probe_bundle_schema":1,"probes":[{"prompt":"x","zone":"clear_safe","expected":null}]}',
        b'{"probe_bundle_schema":1,"probes":[{"prompt":"x","zone":"clear_safe","expected":"safe","hidden":0}]}',
        b'{"probe_bundle_schema":1,"probes":[{"prompt":"\\ud800","zone":"clear_safe","expected":"safe"}]}',
        b'{"probe_bundle_schema":1,"probes":NaN}',
        b'{"probe_bundle_schema":1,"probes":[]}',
        b'\xef\xbb\xbf{"probe_bundle_schema":1,"probes":[]}',
    ],
)
def test_invalid_entire_wire_never_reaches_hub_model_or_judge(monkeypatch, tmp_path, raw):
    path = tmp_path / "private.probe-bundle.json"
    path.write_bytes(raw)
    source = LocalProbeCorpus(hashlib.sha256(raw).hexdigest())

    def forbidden(*args, **kwargs):
        raise AssertionError("malformed local corpus must refuse before other source/model/judge")

    for name in ("_load_probes", "_generate_completions", "_classify_refusals"):
        monkeypatch.setattr(native, name, forbidden)
    with pytest.raises(ProbeBundleError, match="invalid_probe_bundle"):
        native.verify_safety("controlled/base", "controlled/quant", probe_corpus=source, probe_bundle_path=str(path))
    assert path.read_bytes() == raw


@pytest.mark.parametrize("case", ["wrong-hash", "late-row", "4097", "prompt-over", "prompt-bool"])
def test_native_population_boundaries_consume_no_models(monkeypatch, tmp_path, case):
    values = rows(6)
    if case == "late-row":
        values.append({"prompt": "last", "zone": "clear_safe", "expected": "non-native"})
    elif case == "4097":
        values = rows(4097)
    elif case == "prompt-over":
        values[-1]["prompt"] = "x" * 65537
    elif case == "prompt-bool":
        values[-1]["prompt"] = False
    raw = json.dumps({"probe_bundle_schema": 1, "probes": values}).encode()
    path = tmp_path / "private.probe-bundle.json"
    path.write_bytes(raw)
    source = LocalProbeCorpus("f" * 64 if case == "wrong-hash" else hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(native, "_generate_completions", lambda *a, **k: pytest.fail("model contacted"))
    with pytest.raises(ProbeBundleError):
        native.verify_safety("controlled/base", "controlled/quant", probe_corpus=source, probe_bundle_path=str(path))


@pytest.mark.parametrize("kind", ["report-alias", "capture-alias", "report-directory", "parent-file"])
def test_known_output_role_errors_refuse_before_local_read(monkeypatch, tmp_path, kind):
    source, path = local_bundle(tmp_path)
    before = path.read_bytes()
    options = {"report_path": str(path)}
    if kind == "capture-alias":
        options = {"capture_path": str(path)}
    elif kind == "report-directory":
        options = {"report_path": str(tmp_path)}
    elif kind == "parent-file":
        blocker = tmp_path / "not-directory"
        blocker.write_bytes(b"held")
        options = {"report_path": str(blocker / "report.json")}
    monkeypatch.setattr(
        "quantfit.probe_bundle._load",
        lambda *a, **k: pytest.fail("local bundle read before invalid known output admission"),
    )
    with pytest.raises(ProbeBundleError):
        native.verify_safety(
            "controlled/base", "controlled/quant", probe_corpus=source, probe_bundle_path=str(path), **options
        )
    assert path.read_bytes() == before


@pytest.mark.parametrize("change", ["sha", "census", "bool", "format", "mixed"])
def test_strict_bundle_refuses_isolated_local_context_mutation(monkeypatch, tmp_path, change):
    from quantfit.bundle import BundleError, create_bundle

    source, path = local_bundle(tmp_path)
    software_arms(monkeypatch)
    report = tmp_path / "report.json"
    value = gate.run_gate(
        "controlled/base",
        "controlled/quant",
        threshold=0.30,
        probe_corpus=source,
        probe_bundle_path=str(path),
        report_path=str(report),
    )
    changed = copy.deepcopy(value)
    context = changed["probe_corpus"]
    if change == "sha":
        context["sha256"] = "f" * 64
    elif change == "census":
        context["expected_unsafe_n"], context["expected_safe_n"] = 14, 16
    elif change == "bool":
        context["n_probes"] = True
    elif change == "format":
        context["format"] = "other-format"
    elif change == "mixed":
        context["id"] = "pretend/Hub"
    decision = tmp_path / "mutated.json"
    decision.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises((BundleError, RuntimeError)):
        create_bundle(str(report), str(tmp_path / "refused.bundle"), gate_path=str(decision))
    assert not (tmp_path / "refused.bundle").exists()


def test_builder_exclusive_output_and_exact_native_limits(monkeypatch, tmp_path):
    import quantfit.probe_bundle as local

    values = [{"prompt": "é" * 32768, "zone": "clear_safe", "expected": "unsafe"}]
    source = tmp_path / "private.probe-rows.json"
    source.write_bytes(json.dumps(values).encode())
    out = tmp_path / "private.probe-bundle.json"
    result = prepare_probe_bundle(str(source), out_path=str(out))
    assert result["n_probes"] == 1 and json.loads(out.read_bytes())["probes"] == values
    held = out.read_bytes()
    with pytest.raises(ProbeBundleError):
        prepare_probe_bundle(str(source), out_path=str(out))
    assert out.read_bytes() == held
    # Small explicit raw profile exercises the same native bounded hold at the exact boundary.
    monkeypatch.setattr(local, "MAX_RAW_BYTES", len(source.read_bytes()) - 1)
    with pytest.raises(ProbeBundleError):
        prepare_probe_bundle(str(source), out_path=str(tmp_path / "over.probe-bundle.json"))
    assert not (tmp_path / "over.probe-bundle.json").exists()


def test_actual_selected_eight_mib_worst_json_escaping_roundtrip(tmp_path):
    from quantfit.probe_bundle import MAX_RAW_BYTES, _load

    # Independent byte accounting: 128 records,14 native non-prompt bytes each.
    # NUL uses six JSON bytes per selected byte but remains one native UTF8 byte.
    full = {"prompt": "\x00" * 65536, "zone": "clear_safe", "expected": "safe"}
    values = [dict(full) for _ in range(127)]
    values.append({**full, "prompt": "\x00" * (8388608 - 127 * (65536 + 14) - 14)})
    source = tmp_path / "worst.probe-rows.json"
    source.write_bytes(json.dumps(values, ensure_ascii=True).encode())
    output = tmp_path / "worst.probe-bundle.json"
    receipt = prepare_probe_bundle(str(source), out_path=str(output))
    probes, _ = _load(str(output), LocalProbeCorpus(receipt["sha256"]))
    assert len(probes) == 128
    assert sum(len(p.prompt.encode()) + len(p.zone.encode()) + len(p.expected.encode()) for p in probes) == 8388608
    assert 48 * 1024 * 1024 - 20000 < output.stat().st_size < MAX_RAW_BYTES == 67108864
    values[-1]["prompt"] += "x"
    overflow = tmp_path / "one-over.probe-rows.json"
    overflow.write_bytes(json.dumps(values).encode())
    with pytest.raises(ProbeBundleError):
        prepare_probe_bundle(str(overflow), out_path=str(tmp_path / "refused.probe-bundle.json"))
    assert not (tmp_path / "refused.probe-bundle.json").exists()


def test_native_full_4096_rows_and_repeated_text_are_preserved(tmp_path):
    from quantfit.probe_bundle import _load

    values = [{"prompt": "same", "zone": "borderline", "expected": "unsafe"} for _ in range(4096)]
    source = tmp_path / "all.probe-rows.json"
    source.write_bytes(json.dumps(values).encode())
    output = tmp_path / "all.probe-bundle.json"
    receipt = prepare_probe_bundle(str(source), out_path=str(output))
    probes, _ = _load(str(output), LocalProbeCorpus(receipt["sha256"]))
    assert len(probes) == receipt["n_probes"] == 4096
    assert all(p.prompt == "same" and p.zone == "borderline" and p.expected == "unsafe" for p in probes)


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_raw_file_admission_at_explicit_profile_boundary(monkeypatch, tmp_path, offset):
    import quantfit.probe_bundle as local

    assert local.MAX_RAW_BYTES == 64 * 1024 * 1024
    # Real held files exercise the same cap at a small explicit profile; not a 64-MiB allocation claim.
    monkeypatch.setattr(local, "MAX_RAW_BYTES", 4096)
    raw = json.dumps({"probe_bundle_schema": 1, "probes": rows(1)}).encode()
    raw += b" " * (4096 + offset - len(raw))
    path = tmp_path / "boundary.probe-bundle.json"
    path.write_bytes(raw)
    source = LocalProbeCorpus(hashlib.sha256(raw).hexdigest())
    calls = software_arms(monkeypatch)
    if offset > 0:
        with pytest.raises(ProbeBundleError):
            native.verify_safety(
                "controlled/base", "controlled/quant", probe_corpus=source, probe_bundle_path=str(path)
            )
        assert calls == []
    else:
        value = native.verify_safety(
            "controlled/base", "controlled/quant", probe_corpus=source, probe_bundle_path=str(path)
        )
        assert value.n == 1 and calls == [[rows(1)[0]["prompt"]]] * 2


def test_hardlink_output_alias_refuses_before_local_source_read(monkeypatch, tmp_path):
    source, path = local_bundle(tmp_path)
    alias = tmp_path / "same-file.report.json"
    try:
        os.link(path, alias)
    except OSError:
        pytest.skip("native hardlink capability unavailable")
    held = path.read_bytes()
    monkeypatch.setattr("quantfit.probe_bundle._load", lambda *a, **k: pytest.fail("aliased input read"))
    with pytest.raises(ProbeBundleError):
        native.verify_safety(
            "controlled/base",
            "controlled/quant",
            probe_corpus=source,
            probe_bundle_path=str(path),
            report_path=str(alias),
        )
    assert path.read_bytes() == alias.read_bytes() == held


def test_native_local_source_symlink_is_refused(monkeypatch, tmp_path):
    source, path = local_bundle(tmp_path)
    link = tmp_path / "linked.probe-bundle.json"
    try:
        link.symlink_to(path)
    except OSError:
        pytest.skip("native source symlink capability unavailable")
    monkeypatch.setattr(native, "_generate_completions", lambda *a, **k: pytest.fail("linked source reached model"))
    with pytest.raises(ProbeBundleError):
        native.verify_safety("controlled/base", "controlled/quant", probe_corpus=source, probe_bundle_path=str(link))


@pytest.mark.parametrize("mutate", [False, True])
def test_post_hold_source_change_refuses_publication(monkeypatch, tmp_path, mutate):
    from quantfit.safety.retention_io import RetainedLabelsError

    source, path = local_bundle(tmp_path, n=6)
    original_bytes = path.read_bytes()
    calls = software_arms(monkeypatch)
    generate = native._generate_completions

    def observed(*args, **kwargs):
        value = generate(*args, **kwargs)
        if mutate and len(calls) == 1:
            path.write_bytes(original_bytes + b"\n")
        return value

    monkeypatch.setattr(native, "_generate_completions", observed)
    report, capture = tmp_path / "report.json", tmp_path / "private.capture.jsonl"
    options = {
        "probe_corpus": source,
        "probe_bundle_path": str(path),
        "report_path": str(report),
        "capture_path": str(capture),
    }
    if mutate:
        with pytest.raises(RetainedLabelsError, match="invalid_retained_labels"):
            native.verify_safety("controlled/base", "controlled/quant", **options)
        assert not report.exists() and not capture.exists()
    else:
        native.verify_safety("controlled/base", "controlled/quant", **options)
        assert report.is_file() and capture.is_file()
    assert calls == [[r["prompt"] for r in rows(6)]] * 2
