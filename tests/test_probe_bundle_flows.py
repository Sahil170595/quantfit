"""Whole local-source native decisions and receiving, using controlled arms only."""

import json
from xml.etree import ElementTree as ET

import pytest
from test_probe_corpus import rows, software_arms

from quantfit import LocalProbeCorpus, gate, prepare_probe_bundle
from quantfit.safety import verify as native
from quantfit.safety.report import DriftReport


def local_bundle(tmp_path, n=30):
    source = tmp_path / "private.probe-rows.json"
    source.write_bytes(json.dumps(rows(n)).encode())
    path = tmp_path / "private.probe-bundle.json"
    receipt = prepare_probe_bundle(str(source), out_path=str(path))
    return LocalProbeCorpus(receipt["sha256"]), path


@pytest.mark.parametrize("selected", [False, True])
def test_actual_local_gate_strict_bundle_junit_and_offline_replay(monkeypatch, tmp_path, selected):
    from quantfit.bundle import create_bundle, verify_bundle
    from quantfit.junit import gate_to_junit

    source, path = local_bundle(tmp_path)
    calls = software_arms(monkeypatch)
    observed, decision = tmp_path / "observed.json", tmp_path / "gate.json"
    policy = (
        {"axis_thresholds": {"refusal-robustness": 0.30, "over-refusal": 0.30}} if selected else {"threshold": 0.30}
    )
    value = gate.run_gate(
        "controlled/base",
        "controlled/quant",
        probe_corpus=source,
        probe_bundle_path=str(path),
        report_path=str(observed),
        out_path=str(decision),
        **policy,
    )
    assert value["exit_code"] == 0 and value["schema_version"] == 3
    expected = {
        "source_kind": "local",
        "format": "quantfit-probe-bundle-v1",
        "sha256": source.sha256,
        "n_probes": 30,
        "expected_unsafe_n": 15,
        "expected_safe_n": 15,
        "zone_counts": {"clear_safe": 10, "clear_unsafe": 10, "borderline": 10},
        "population_basis": "resolved_native_population",
    }
    assert value["probe_corpus"] == expected
    literal_prompts = [
        "same controlled row" if i in (0, 5, 10, 15, 20, 25) else f"  controlled corpus row {i}\r\n" for i in range(30)
    ]
    assert calls == [literal_prompts] * 2 and literal_prompts.count("same controlled row") == 6
    assert value["drift"]["refusal_robustness"]["expected_unsafe_n"] == 15
    assert value["drift"]["refusal_robustness"]["at_risk"] == 15
    assert value["drift"]["refusal_robustness"]["harmful_compliance_regressions"] == 0
    assert value["drift"]["over_refusal"]["expected_safe_n"] == 15
    assert value["drift"]["over_refusal"]["at_risk"] == 15
    assert value["drift"]["over_refusal"]["overrefusal_regressions"] == 0
    xml = ET.fromstring(gate_to_junit(value, baseline="controlled/base", quant="controlled/quant"))
    assert value["resolution_is_a_floor"] is True
    assert len(xml.findall(".//testcase")) == (5 if selected else 3)
    assert not xml.findall(".//failure") and not xml.findall(".//error")
    assert len(xml.findall(".//skipped")) == (
        2 if selected else 0
    )  # preserve each native renderer's actual floor representation
    assert json.loads(xml.find("system-out").text.rsplit("probe_corpus=", 1)[1]) == expected
    target = tmp_path / "aggregate.bundle"
    create_bundle(str(observed), str(target), gate_path=str(decision))
    received = verify_bundle(str(target))
    assert received["integrity_verified"] is True and received["scientific_claims_verified"] is False
    assert received["declared_results"]["gate"]["probe_corpus"] == expected
    assert received["declared_results"]["gate"]["exit_code"] == 0
    path.unlink()

    def forbidden(*args, **kwargs):
        raise AssertionError("offline saved replay must not load local source or execute models")

    monkeypatch.setattr(native, "_prepare_probes", forbidden)
    monkeypatch.setattr(native, "_generate_completions", forbidden)
    monkeypatch.setattr("quantfit.probe_bundle._load", forbidden)
    saved = gate.evaluate_report(str(observed), probe_corpus=source, **policy)
    assert saved["exit_code"] == 0 and saved["probe_corpus"]["sha256"] == source.sha256
    assert saved["probe_corpus"] == {**expected, "population_basis": "saved_report_native_counts"}


def test_local_native_preflight_uses_actual_small_census_without_model(monkeypatch, tmp_path):
    source, path = local_bundle(tmp_path, n=6)

    def forbidden(*args, **kwargs):
        raise AssertionError("unresolvable local population must stop before model or judge")

    monkeypatch.setattr(native, "_generate_completions", forbidden)
    monkeypatch.setattr(native, "_classify_refusals", forbidden)
    value = gate.run_gate(
        "controlled/base", "controlled/quant", threshold=0.30, probe_corpus=source, probe_bundle_path=str(path)
    )
    assert value["exit_code"] == 5
    assert value["probe_corpus"]["expected_unsafe_n"] == 3


def test_native_local_screen_one_read_then_deleted_source_offline(monkeypatch, tmp_path):
    from test_corpus_gate import manifest, native_runtime

    import quantfit.probe_bundle as local
    from quantfit.saved_screen import summarize_screen
    from quantfit.screen import ScreenError, run_screen

    source, path = local_bundle(tmp_path, n=6)
    config, out = tmp_path / "manifest.json", tmp_path / "reports"
    manifest(config)
    calls = native_runtime(monkeypatch)
    reads = []
    original = local._load

    def held_once(*args, **kwargs):
        reads.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr("quantfit.probe_population._load", held_once)
    result = run_screen(str(config), str(out), probe_corpus=source, probe_bundle_path=str(path))
    assert reads == [True]
    assert [name for name, _ in calls] == [
        "controlled/base1",
        "controlled/quant1",
        "controlled/base2",
        "controlled/quant2",
    ]
    assert all(prompts == [r["prompt"] for r in rows(6)] for _, prompts in calls)
    assert result["probe_corpus"]["sha256"] == source.sha256 and result["probe_corpus"]["n_probes"] == 6
    assert result["control_evidence_verified"] is False
    assert all(a["refusal_robustness"]["conditionality"] for a in result["by_stratum"].values())
    path.unlink()

    def forbidden(*args, **kwargs):
        raise AssertionError("saved and complete resume may not open the deleted bundle or execute")

    monkeypatch.setattr(local, "_load", forbidden)
    monkeypatch.setattr("quantfit.probe_population._load", forbidden)
    monkeypatch.setattr(native, "verify_safety", forbidden)
    saved = summarize_screen(str(config), str(out), probe_corpus=source)
    assert saved["saved_screen_summary_schema_version"] == 2
    resumed = run_screen(str(config), str(out), probe_corpus=source, resume=True)
    assert resumed["probe_corpus"] == saved["probe_corpus"]
    assert [r["action"] for r in resumed["resume_receipt"]["targets"]] == ["skipped", "skipped"]
    with pytest.raises(ScreenError):
        run_screen(str(config), str(out), probe_corpus=source, probe_bundle_path=str(path), resume=True)


def test_local_screen_retries_and_partial_resume_reuse_each_held_population(monkeypatch, tmp_path):
    from test_corpus_gate import manifest, native_runtime

    import quantfit.probe_population as population
    from quantfit.screen import run_screen

    source, path = local_bundle(tmp_path, n=6)
    config, out = tmp_path / "manifest.json", tmp_path / "reports"
    manifest(config)
    native_runtime(monkeypatch)
    original_load, original_generate = population._load, native._generate_completions
    reads, calls = [], []

    def held(*args, **kwargs):
        reads.append(True)
        return original_load(*args, **kwargs)

    def flaky(model, prompts, *args, **kwargs):
        calls.append((model, list(prompts)))
        if len(calls) == 2:
            raise RuntimeError("controlled first-attempt failure")
        return original_generate(model, prompts, *args, **kwargs)

    monkeypatch.setattr(population, "_load", held)
    monkeypatch.setattr(native, "_generate_completions", flaky)
    value = run_screen(str(config), str(out), probe_corpus=source, probe_bundle_path=str(path), attempts=2)
    assert reads == [True] and [name for name, _ in calls] == [
        "controlled/base1",
        "controlled/quant1",
        "controlled/base1",
        "controlled/quant1",
        "controlled/base2",
        "controlled/quant2",
    ]
    assert value["probe_corpus"]["sha256"] == source.sha256
    first_name = json.loads(config.read_bytes())["targets"][0]["name"]
    (out / f"{first_name}.json").unlink()  # Controlled missing-target counterfactual, not a user artifact.
    resumed = run_screen(str(config), str(out), resume=True, probe_corpus=source, probe_bundle_path=str(path))
    assert reads == [True, True] and len(calls) == 8
    assert [r["action"] for r in resumed["resume_receipt"]["targets"]] == ["executed", "skipped"]
    assert all(prompts == [r["prompt"] for r in rows(6)] for _, prompts in calls)


def test_actual_local_capture_key_direct_and_retained_calibration_identity(monkeypatch, tmp_path):
    import csv

    from quantfit.safety.calibrate import build_labeling_sheet, ingest_labels
    from quantfit.safety.calibration_binding import load_bound_calibration
    from quantfit.safety.retained_labels import extract_labels, ingest_retained_labels

    source, path = local_bundle(tmp_path, n=6)
    software_arms(monkeypatch)
    report, capture = tmp_path / "report.json", tmp_path / "private.capture.jsonl"
    native.verify_safety(
        "controlled/base",
        "controlled/quant",
        probe_corpus=source,
        probe_bundle_path=str(path),
        report_path=str(report),
        capture_path=str(capture),
    )
    sheet, key = tmp_path / "private.labels.csv", tmp_path / "private.labelkey.json"
    build_labeling_sheet(str(capture), str(sheet), str(key))
    binding = json.loads(key.read_bytes())["binding"]
    assert binding["identity"]["identity_schema"] == 2
    assert binding["identity"]["probe_dataset"]["sha256"] == source.sha256
    with sheet.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, values = reader.fieldnames, list(reader)
    entries = json.loads(key.read_bytes())["ids"]
    for row in values:
        row["human_label"] = "refusal" if entries[row["id"]]["judge_refusal"] else "compliance"
    with sheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(values)
    direct_path = tmp_path / "calibration2.json"
    direct = ingest_labels(str(sheet), str(key), str(direct_path))
    assert direct["calibration_schema"] == 2 and direct["binding"] == binding
    labels, receipt, retained_path = (
        tmp_path / "private.retained.csv",
        tmp_path / "retention.json",
        tmp_path / "calibration3.json",
    )
    extract_labels(str(sheet), str(key), out_path=str(labels), receipt_path=str(receipt))
    retained = ingest_retained_labels(str(labels), str(receipt), str(key), out_path=str(retained_path))
    assert retained["calibration_schema"] == 3 and retained["binding"] == binding
    for p in (direct_path, retained_path):
        bound = load_bound_calibration(str(p))
        assert bound.identity == binding["identity"]
        native_report = DriftReport.from_json(str(report))
        bound.match_report(native_report)
        assert native_report.probe_dataset["sha256"] == source.sha256


def test_real_inspect_local_samples_task_eval_and_delayed_report(monkeypatch, tmp_path):
    from inspect_ai.model import ModelOutput

    from quantfit import inspect_task as inspect_native
    from quantfit.safety import report as report_module

    source, path = local_bundle(tmp_path, n=6)
    generated, judged = [], []

    def output(input, tools, tool_choice, config):
        generated.append(input[-1].text)
        return ModelOutput.from_content(model="mockllm/fixture", content="controlled-answer")

    def classify(values, token):
        judged.append(len(values))
        return [False] * len(values), 0.25

    def forbidden(*args, **kwargs):
        raise AssertionError("native local Inspect route must not call the Hub loader")

    monkeypatch.setattr(native, "_load_probes", forbidden)
    monkeypatch.setattr(native, "_classify_refusals", classify)
    samples = inspect_native.qsr_samples(probe_corpus=source, probe_bundle_path=str(path))
    assert len(samples) == 6
    dataset = inspect_native.qsr_dataset(probe_corpus=source, probe_bundle_path=str(path))
    assert dataset.name == f"local:sha256:{source.sha256}" and dataset.location == "private-local-probe-bundle"
    run = inspect_native.qsr_eval(
        "mockllm/base",
        "mockllm/quant",
        baseline_args={"custom_outputs": output},
        quantized_args={"custom_outputs": output},
        probe_corpus=source,
        probe_bundle_path=str(path),
        display="none",
        log_dir=str(tmp_path / "private-inspect"),
    )
    assert len(generated) == 12 and judged == [12] and len(run.outcomes) == 6
    assert run.probe_corpus == run.drift.probe_corpus == source
    assert run.log.eval.metadata["probe_dataset"] == {
        "source_kind": "local",
        "format": "quantfit-probe-bundle-v1",
        "sha256": source.sha256,
    }
    assert run.log.eval.metadata["conforms_to"] is None
    monkeypatch.setattr(
        report_module,
        "environment_fingerprint",
        lambda: {
            "python": "synthetic-not-used",
            "torch": "synthetic-not-used",
            "transformers": "synthetic-not-used",
            "cuda": None,
            "device": "cpu",
        },
    )
    baseline = inspect_native.inspect_arm("mockllm/base", "fixture-only", 1.0, revision="a" * 40)
    quant = inspect_native.inspect_arm("mockllm/quant", "fixture-only", 2.0, revision="b" * 40)
    report = run.write_report(str(tmp_path / "delayed.json"), baseline, quant, 64)
    assert DriftReport.from_json(str(report)).probe_dataset["sha256"] == source.sha256
    before = path.read_bytes()
    with pytest.raises(RuntimeError):
        run.write_report(str(path), baseline, quant, 64)
    assert path.read_bytes() == before


def test_inspect_operational_source_is_not_a_generic_dataclass_field(tmp_path):
    import copy
    import dataclasses

    from quantfit.inspect_task import QsrRun
    from quantfit.probe_bundle import _load

    source, path = local_bundle(tmp_path, n=6)
    _, held = _load(str(path), source)
    drift = native._tabulate(
        [native.Probe("u", "clear_unsafe", "unsafe"), native.Probe("s", "clear_safe", "safe")],
        [True, False],
        [True, False],
    )
    run = QsrRun(
        log="capture-class placeholder only",
        outcomes=[],
        drift=drift,
        judge_runtime_s=0.0,
        arms=("base", "quant"),
        _probe_corpus=source,
        _held_probe_bundle=held,
    )
    expected = {
        "log",
        "outcomes",
        "drift",
        "judge_runtime_s",
        "arms",
        "observed_arms",
        "observation_receipt",
        "protected_report_inputs",
    }
    assert {field.name for field in dataclasses.fields(QsrRun)} == expected
    assert set(dataclasses.asdict(run)) == expected
    assert str(path) not in json.dumps(dataclasses.asdict(run))
    for clone in (copy.copy(run), copy.deepcopy(run), dataclasses.replace(run)):
        assert clone.probe_corpus == source
        assert clone._bundle_state.path == held.path
        clone._bundle_state.check()
