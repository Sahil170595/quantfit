"""Native opted boundaries and source commitments; no remote/model execution."""

import json

import pytest
from test_corpus_gate import alternative, manifest, native_runtime
from test_probe_corpus import BAD_POPULATIONS, invalid_population, rows

from quantfit import gate
from quantfit.safety import verify as v

pytest_plugins = ["test_probe_corpus"]


@pytest.mark.parametrize("route", ["gate", "screen"])
@pytest.mark.parametrize("case", BAD_POPULATIONS)
def test_malformed_whole_source_refuses_before_any_model_or_output(sdk, monkeypatch, tmp_path, route, case):
    from quantfit.screen import run_screen

    source = alternative(sdk)
    invalid_population(sdk, case)

    def forbidden(*a, **k):
        pytest.fail("invalid whole population reached a model or judge")

    monkeypatch.setattr(v, "_generate_completions", forbidden)
    monkeypatch.setattr(v, "_classify_refusals", forbidden)
    out = tmp_path / "output"
    with pytest.raises(RuntimeError):
        if route == "gate":
            gate.run_gate("controlled/base", "controlled/quant", threshold=0.30, probe_corpus=source, out_path=str(out))
        else:
            config = tmp_path / "manifest.json"
            manifest(config)
            run_screen(str(config), str(out), probe_corpus=source)
    assert len(sdk["loads"]) == 1 and not out.exists()


@pytest.mark.parametrize(
    "options",
    [
        {"threshold": 0.3, "axis_thresholds": {"over-refusal": 0.3}},
        {"threshold": 0},
        {"threshold": 0.3, "max_new_tokens": True},
        {"threshold": 0.3, "eps_upper": 0, "eps_source": "not measured"},
        {"threshold": 0.3, "baseline_cache_dir": "unused"},
    ],
)
def test_bad_local_gate_options_precede_even_hub(sdk, tmp_path, options):
    source = alternative(sdk)
    out = tmp_path / "sentinel"
    out.write_bytes(b"held")
    with pytest.raises(RuntimeError):
        gate.run_gate("controlled/base", "controlled/quant", probe_corpus=source, out_path=str(out), **options)
    assert not sdk["loads"] and out.read_bytes() == b"held"


@pytest.mark.parametrize("kind", ["valid", "directory", "parent_file"])
def test_known_output_paths_are_admitted_before_source_contact(sdk, tmp_path, kind):
    source = alternative(sdk)
    target = tmp_path / "target"
    if kind == "directory":
        target.mkdir()
    elif kind == "parent_file":
        target.write_bytes(b"held")
        target = target / "child.json"
    if kind == "valid":
        result = gate.run_gate(
            "controlled/base", "controlled/quant", threshold=0.3, probe_corpus=source, out_path=str(target)
        )
        assert result["exit_code"] == 5 and len(sdk["loads"]) == 1
    else:
        with pytest.raises(RuntimeError):
            gate.run_gate(
                "controlled/base", "controlled/quant", threshold=0.3, probe_corpus=source, out_path=str(target)
            )
        assert not sdk["loads"], "known-invalid publication role contacted the corpus source"


@pytest.mark.parametrize("revision,split", [("d" * 40, v.PROBE_SPLIT), (v.PROBE_DATASET_REVISION, "validation")])
def test_same_id_different_native_pin_is_not_canonical_and_capture_binds_it(
    sdk, monkeypatch, tmp_path, revision, split
):
    from quantfit.screen import run_screen

    source = v.ProbeCorpus(v.PROBE_DATASET_ID, revision, split)
    sdk["hash"], sdk["rows"] = revision, rows(6)
    native_runtime(monkeypatch)
    config, out, captures = tmp_path / "manifest.json", tmp_path / "reports", tmp_path / "captures"
    manifest(config)
    result = run_screen(str(config), str(out), capture_dir=str(captures), probe_corpus=source)
    assert not v._canonical_source(source)
    assert result["control_evidence_verified"] is False
    first = json.loads((captures / "first.capture.jsonl").read_text().splitlines()[0])
    assert first["binding"]["identity"]["probe_dataset"] == {
        "id": source.id,
        "revision": revision,
        "split": split,
        "n_probes": 6,
    }
    assert sdk["loads"][0][1]["revision"] == revision and sdk["split"] == split


def test_selected_absent_expected_axis_is_pre5_without_models(sdk, monkeypatch):
    source = alternative(sdk)
    sdk["rows"] = [{"prompt": "controlled", "zone": "borderline", "expected": "safe"}]

    def forbidden(*a, **k):
        pytest.fail("absent expected axis ran a model")

    monkeypatch.setattr(v, "verify_safety", forbidden)
    result = gate.run_gate(
        "controlled/base", "controlled/quant", probe_corpus=source, axis_thresholds={"refusal-robustness": 0.3}
    )
    assert result["exit_code"] == 5 and result["drift"] is None
    assert result["probe_corpus"]["expected_unsafe_n"] == 0


@pytest.mark.parametrize("detected", [False, True])
def test_observed_detection_outranks_other_selected_unknown(sdk, monkeypatch, tmp_path, detected):
    source = alternative(sdk)
    sdk["rows"] = rows(30)
    native_runtime(monkeypatch)
    original = v._generate_completions

    def generate(model, prompts, max_tokens, token):
        values, arm = original(model, prompts, max_tokens, token)
        values = ["refused" if detected else "answered"] * len(values)
        if detected and "quant" in model:
            values[0] = "answered"
        return values, arm

    monkeypatch.setattr(v, "_generate_completions", generate)
    result = gate.run_gate(
        "controlled/base",
        "controlled/quant",
        probe_corpus=source,
        axis_thresholds={"refusal-robustness": 0.3, "over-refusal": 0.3},
    )
    assert result["exit_code"] == (3 if detected else 4)


@pytest.mark.parametrize(
    "mutation", ["source", "split", "float", "bool", "axis", "zone", "basis", "extra", "kind", "overall", "MDE", "SHA"]
)
def test_strict_actual_bundle_rejects_forged_opted_context_and_native_decision(sdk, monkeypatch, tmp_path, mutation):
    from quantfit.bundle import create_bundle

    source = alternative(sdk)
    sdk["rows"] = rows(30)
    native_runtime(monkeypatch)
    report, artifact = tmp_path / "report.json", tmp_path / "gate.json"
    value = gate.run_gate(
        "controlled/base",
        "controlled/quant",
        probe_corpus=source,
        axis_thresholds={"refusal-robustness": 0.3},
        report_path=str(report),
    )
    value = gate.evaluate_report(str(report), probe_corpus=source, axis_thresholds={"refusal-robustness": 0.3})
    ctx = value["probe_corpus"]
    if mutation == "source":
        ctx["revision"] = "e" * 40
    elif mutation == "split":
        ctx["split"] = "test"
    elif mutation == "float":
        ctx["n_probes"] = 30.0
    elif mutation == "bool":
        ctx["expected_safe_n"] = True
    elif mutation == "axis":
        ctx["expected_unsafe_n"] += 1
        ctx["expected_safe_n"] -= 1
    elif mutation == "zone":
        ctx["zone_counts"]["clear_safe"] += 1
    elif mutation == "basis":
        ctx["population_basis"] = "resolved_native_population"
    elif mutation == "extra":
        ctx["curation_authenticated"] = True
    elif mutation == "kind":
        value["decision_schema_version"] = True
    elif mutation == "overall":
        value["exit_code"] = 3
    elif mutation == "MDE":
        value["axis_results"]["refusal-robustness"]["mde_block"]["n_at_risk"] += 1
    else:
        value["source_evidence"]["report_sha256"] = "0" * 64
    artifact.write_text(json.dumps(value))
    with pytest.raises(RuntimeError):
        create_bundle(str(report), str(tmp_path / "refused.zip"), gate_path=str(artifact))


def test_partial_resume_reuses_held_population_every_retry_and_preserves_present(sdk, monkeypatch, tmp_path):
    from quantfit.screen import run_screen

    source = alternative(sdk)
    native_runtime(monkeypatch)
    config, out = tmp_path / "manifest.json", tmp_path / "reports"
    manifest(config)
    run_screen(str(config), str(out), probe_corpus=source)
    last = (out / "last.json").read_bytes()
    (out / "first.json").unlink()
    sdk["loads"].clear()
    sdk["iterations"] = 0
    original = v.verify_safety
    identities = []

    def retry(*args, **kwargs):
        identities.append(id(kwargs["_prepared_population"]))
        if len(identities) == 1:
            raise RuntimeError("controlled transient before native report")
        return original(*args, **kwargs)

    monkeypatch.setattr(v, "verify_safety", retry)
    result = run_screen(str(config), str(out), probe_corpus=source, resume=True, attempts=2)
    assert len(sdk["loads"]) == sdk["iterations"] == 1
    assert len(identities) == 2 and len(set(identities)) == 1
    assert result["resume_receipt"]["n_executed"] == result["resume_receipt"]["n_skipped"] == 1
    assert (out / "last.json").read_bytes() == last


def test_late_local_target_refuses_before_first_source_or_model_contact(sdk, monkeypatch, tmp_path):
    from quantfit.screen import run_screen

    source = alternative(sdk)
    native_runtime(monkeypatch)
    config, out = tmp_path / "manifest.json", tmp_path / "reports"
    manifest(config)
    value = json.loads(config.read_bytes())
    value["targets"][-1]["quant"] = "quant.gguf"
    config.write_text(json.dumps(value))
    with pytest.raises(RuntimeError):
        run_screen(str(config), str(out), probe_corpus=source)
    assert not sdk["loads"] and not out.exists()


def test_late_saved_source_mismatch_prevents_any_missing_target_regeneration(sdk, monkeypatch, tmp_path):
    from quantfit.screen import run_screen

    source = alternative(sdk)
    native_runtime(monkeypatch)
    config, out = tmp_path / "manifest.json", tmp_path / "reports"
    manifest(config)
    run_screen(str(config), str(out), probe_corpus=source)
    (out / "first.json").unlink()
    value = json.loads((out / "last.json").read_bytes())
    value["probe_dataset"]["split"] = "foreign"
    (out / "last.json").write_text(json.dumps(value))
    before = {p.name: p.read_bytes() for p in out.iterdir()}

    def forbidden(*a, **k):
        pytest.fail("late held mismatch reached a loader/model")

    monkeypatch.setattr(v, "_prepare_probes", forbidden)
    monkeypatch.setattr(v, "verify_safety", forbidden)
    with pytest.raises(RuntimeError):
        run_screen(str(config), str(out), probe_corpus=source, resume=True)
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before
