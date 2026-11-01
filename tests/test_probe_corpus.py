"""Pinned corpus software controls; no Hub/model/judge inference."""

import dataclasses
import json
import subprocess
import sys

import pytest

from quantfit.safety import verify as v


def rows(n=40):
    return [
        {
            "prompt": f"  controlled corpus row {i}\r\n" if i % 5 else "same controlled row",
            "zone": ["clear_safe", "clear_unsafe", "borderline"][i % 3],
            "expected": "unsafe" if i % 2 == 0 else "safe",
        }
        for i in range(n)
    ]


@pytest.fixture
def sdk(monkeypatch):
    import datasets

    state = {"rows": rows(), "loads": [], "streams": 0, "hash": v.PROBE_DATASET_REVISION}

    def dataset():
        return datasets.Dataset.from_list(state["rows"])

    def old(path, **kwargs):
        state["loads"].append((path, kwargs))
        return dataset()

    class Builder:
        @property
        def hash(self):
            return state["hash"]

        def as_streaming_dataset(self, split):
            state["streams"] += 1
            state["split"] = split

            def generate():
                state["iterations"] = state.get("iterations", 0) + 1
                for row in state["rows"]:
                    state["yielded"] = state.get("yielded", 0) + 1
                    yield row
                if state.get("EOF_error"):
                    raise RuntimeError("controlled private EOF failure")

            return datasets.IterableDataset.from_generator(generate)

    def builder(path, **kwargs):
        state["loads"].append((path, kwargs))
        return Builder()

    monkeypatch.setattr(datasets, "load_dataset", old)
    monkeypatch.setattr(datasets, "load_dataset_builder", builder)
    return state


def test_native_default_full_order_is_positive_before_new_source(sdk):
    got = v._load_probes(None)
    assert [dataclasses.asdict(p) for p in got] == rows()
    assert got[0].prompt == got[5].prompt
    assert got[1].prompt.startswith("  ") and got[1].prompt.endswith("\r\n")


def test_public_probe_corpus_admits_full_alternative(sdk):
    import quantfit

    corpus = quantfit.ProbeCorpus("controlled/alternative", "d" * 40, "validation")
    sdk["hash"] = corpus.revision
    got = v._load_probes(None, probe_corpus=corpus)
    assert [dataclasses.asdict(p) for p in got] == rows()
    assert sdk["loads"] == [("hf://datasets/controlled/alternative", {"revision": "d" * 40, "token": None})]
    assert sdk["streams"] == 1 and sdk["split"] == "validation"


def test_actual_os_cli_source_mode_is_a_native_json_refusal():
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "quantfit.cli",
            "verify-safety",
            "--demo",
            "--probe-dataset",
            "controlled/alternative",
            "--json",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout, "new source mode must be handled by the native command, not argparse unknown-option"
    envelope = json.loads(result.stdout)
    assert envelope["command"] == "verify-safety" and envelope["exit_code"] == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "json"),
        ("id", "buckets/fixture"),
        ("id", "https://controlled/repo"),
        ("id", "../fixture"),
        ("id", False),
        ("revision", "main"),
        ("revision", "A" * 40),
        ("revision", None),
        ("split", "all"),
        ("split", "train+test"),
        ("split", "train[:40]"),
        ("split", " train"),
        ("split", "x" * 65),
        ("split", False),
    ],
)
def test_source_options_refuse_before_any_sdk_factory(sdk, field, value):
    options = {"id": "controlled/corpus", "revision": "a" * 40, "split": "train", field: value}
    with pytest.raises(RuntimeError, match="invalid_probe_corpus"):
        v.ProbeCorpus(**options)
    assert not sdk["loads"]


@pytest.mark.parametrize("actual_hash", [None, "auto", "b" * 40, 17, True])
def test_exact_resolved_builder_pin_precedes_streaming(sdk, actual_hash):
    sdk["hash"] = actual_hash
    with pytest.raises(RuntimeError, match="invalid_probe_corpus_population"):
        v._load_probes(None)
    assert sdk["streams"] == 0


ROUTES = ["direct_hf", "direct_gguf", "task", "inspect_unobserved", "inspect_hf", "inspect_gguf"]
BAD_POPULATIONS = [
    "zero",
    "count",
    "missing",
    "bool",
    "numeric",
    "none",
    "zone",
    "expected",
    "surrogate",
    "prompt",
    "aggregate",
    "EOF",
]


def invalid_population(sdk, case):
    sdk["rows"] = rows(2)
    changes = {
        "missing": ("expected", None),
        "bool": ("prompt", False),
        "numeric": ("prompt", 42),
        "none": ("zone", None),
        "zone": ("zone", "invalid"),
        "expected": ("expected", "invalid"),
        "surrogate": ("prompt", "\ud800"),
        "prompt": ("prompt", "x" * 65537),
    }
    if case in changes:
        field, value = changes[case]
        if case == "missing":
            sdk["rows"][-1].pop(field)
        else:
            sdk["rows"][-1][field] = value
    elif case == "zero":
        sdk["rows"] = []
    elif case == "count":
        sdk["rows"] = rows(4097)
    elif case == "aggregate":
        sdk["rows"] = [{"prompt": "x" * 65536, "zone": "clear_safe", "expected": "safe"}] * 129
    elif case == "EOF":
        sdk["EOF_error"] = True


def invoke_route(route, source):
    from quantfit import inspect_task as it

    if route.startswith("direct"):
        if route == "direct_hf":
            return v.verify_safety("controlled/base", "controlled/quant", probe_corpus=source)
        return v.verify_safety(
            "hf:controlled/base/base-f16.gguf",
            "hf:controlled/quant/quant-q4.gguf",
            baseline_revision="a" * 40,
            quant_revision="b" * 40,
            probe_corpus=source,
        )
    if route == "task":
        return it.qsr_paired_diff("hf/controlled/base", "hf/controlled/quant", probe_corpus=source)
    if route == "inspect_gguf":
        return it.qsr_eval(
            "quantfit_gguf/hf:controlled/base/base-f16.gguf",
            "quantfit_gguf/hf:controlled/quant/quant-q4.gguf",
            gguf_revisions=("a" * 40, "b" * 40),
            probe_corpus=source,
        )
    return it.qsr_eval(
        "hf/controlled/base",
        "hf/controlled/quant",
        probe_corpus=source,
        **({"hf_revisions": ("a" * 40, "b" * 40)} if route == "inspect_hf" else {}),
    )


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("case", BAD_POPULATIONS)
def test_whole_population_refusal_precedes_every_model_observer_and_judge(sdk, monkeypatch, route, case):
    from quantfit import inspect_gguf, inspect_hf
    from quantfit import inspect_task as it
    from quantfit.safety import gguf_arm

    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("model/observer must not be constructed for an invalid population")

    monkeypatch.setattr(v, "_generate_completions", forbidden)
    monkeypatch.setattr(v, "_classify_refusals", forbidden)
    monkeypatch.setattr(gguf_arm, "resolve_pair", forbidden)
    monkeypatch.setattr(it, "qsr_arm", forbidden)
    monkeypatch.setattr(inspect_hf, "HfRunObserver", forbidden)
    monkeypatch.setattr(inspect_gguf, "GgufRunObserver", forbidden)
    invalid_population(sdk, case)
    source = v.ProbeCorpus("controlled/alternative", sdk["hash"], "validation")
    with pytest.raises(RuntimeError, match="invalid_probe_corpus_population"):
        invoke_route(route, source)
    assert calls == [] and len(sdk["loads"]) == 1 and sdk.get("iterations", 0) <= 1


def test_exact_utf8_and_aggregate_profiles_keep_every_row(sdk):
    sdk["rows"] = [{"prompt": "é" * 32768, "zone": "clear_safe", "expected": "unsafe"}]
    assert v._load_probes(None)[0].prompt == sdk["rows"][0]["prompt"]
    full = {"prompt": "x" * 65536, "zone": "clear_safe", "expected": "safe"}
    charge = 65536 + len("clear_safe") + len("safe")
    remainder = v.MAX_PROBE_SELECTED_BYTES - 127 * charge - len("clear_safe") - len("safe")
    sdk["rows"] = [full] * 127 + [{**full, "prompt": "x" * remainder}]
    assert (
        sum(len(p.prompt.encode()) + len(p.zone) + len(p.expected) for p in v._load_probes(None))
        == v.MAX_PROBE_SELECTED_BYTES
    )
    sdk["rows"][-1]["prompt"] += "x"
    with pytest.raises(RuntimeError, match="invalid_probe_corpus_population"):
        v._load_probes(None)


def test_exact_native_4096_population_is_not_truncated(sdk):
    sdk["rows"] = rows(4096)
    actual = v._load_probes(None)
    assert len(actual) == sdk["yielded"] == 4096 and actual[-1].prompt == sdk["rows"][-1]["prompt"]


def test_actual_source_carrier_preserves_default_abi_and_copy_replace():
    import copy

    native = v._tabulate(
        [v.Probe("u", "clear_unsafe", "unsafe"), v.Probe("s", "clear_safe", "safe")], [True, False], [True, False]
    )
    custom = dataclasses.replace(native, _probe_corpus=v.ProbeCorpus("controlled/alternative", "a" * 40, "test"))
    assert dataclasses.asdict(native) == dataclasses.asdict(custom) and native.to_dict() == custom.to_dict()
    assert "curated probes" in native.summary() and "supplied noncanonical probes" in custom.summary()
    for actual in [copy.copy(custom), copy.deepcopy(custom), dataclasses.replace(custom)]:
        assert actual.probe_corpus == custom.probe_corpus and actual.summary() == custom.summary()


def test_custom_forty_cannot_enter_reference_execution_before_io(sdk, monkeypatch):
    from quantfit.safety import gguf_arm

    calls = []
    monkeypatch.setattr(gguf_arm, "resolve_pair", lambda *a, **k: calls.append(True))
    with pytest.raises(RuntimeError, match="execution_recipe_mismatch"):
        v.verify_safety(
            "b.gguf",
            "q.gguf",
            _execution_guard=lambda *a: None,
            probe_corpus=v.ProbeCorpus(v.PROBE_DATASET_ID, "d" * 40, v.PROBE_SPLIT),
        )
    assert not sdk["loads"] and not calls


def software_arms(monkeypatch):
    from quantfit.safety import report
    from quantfit.safety.report import ArmRun

    arms = [
        ArmRun(
            "controlled/base",
            "a" * 40,
            "torch.float32",
            1.0,
            {"name": "transformers", "version": "5.12.1", "device": "cpu"},
            None,
        ),
        ArmRun(
            "controlled/quant",
            "b" * 40,
            "torch.float32",
            2.0,
            {"name": "transformers", "version": "5.12.1", "device": "cpu"},
            None,
        ),
    ]
    calls = []

    def generate(model, prompts, max_new_tokens, token):
        calls.append(list(prompts))
        return ["refused" if i % 2 == 0 else "answered" for i in range(len(prompts))], arms[len(calls) - 1]

    monkeypatch.setattr(v, "_generate_completions", generate)
    monkeypatch.setattr(v, "_classify_refusals", lambda values, token: ([x == "refused" for x in values], 0.25))
    monkeypatch.setattr(
        report,
        "environment_fingerprint",
        lambda: {"python": "3.12.13", "torch": "2.13.0+cpu", "transformers": "5.12.1", "cuda": None, "device": "cpu"},
    )
    return calls


@pytest.mark.parametrize(
    "id,revision,split",
    [
        ("controlled/alternative", "d" * 40, "validation"),
        (v.PROBE_DATASET_ID, "d" * 40, v.PROBE_SPLIT),
        (v.PROBE_DATASET_ID, v.PROBE_DATASET_REVISION, "validation"),
    ],
)
@pytest.mark.parametrize("save_report", [True, False])
def test_native_actual_source_report_capture_only_summary_and_card(
    sdk, monkeypatch, tmp_path, id, revision, split, save_report
):
    from quantfit.modelcard import model_card_fragment
    from quantfit.safety.calibration_binding import identity_fingerprint, measurement_identity
    from quantfit.safety.report import DriftReport

    calls = software_arms(monkeypatch)
    source = v.ProbeCorpus(id, revision, split)
    sdk["hash"] = revision
    path = tmp_path / "report.json"
    capture = tmp_path / "private.capture.jsonl"
    drift = v.verify_safety(
        "controlled/base",
        "controlled/quant",
        probe_corpus=source,
        report_path=str(path) if save_report else None,
        capture_path=str(capture),
    )
    actual = {"id": id, "revision": revision, "split": split, "n_probes": 40}
    assert len(sdk["loads"]) == 1 and sdk["iterations"] == 1 and len(calls) == 2
    assert all(prompts == [r["prompt"] for r in rows()] for prompts in calls)
    assert "supplied noncanonical" in drift.summary() and "curated probes" not in drift.summary()
    header = json.loads(capture.read_text().splitlines()[0])
    assert header["binding"]["identity"]["probe_dataset"] == actual
    if save_report:
        report = DriftReport.from_json(str(path))
        assert report.probe_dataset == actual
        assert header["binding"] == {
            "identity": measurement_identity(report),
            "fingerprint": identity_fingerprint(measurement_identity(report)),
        }
        card = model_card_fragment(str(path))
        assert "supplied noncanonical" in card and "curated probes" not in card
        assert "At the n above" not in card and "n <= 34" not in card
        assert "historical default-distribution" in report.judge["card_xstest_accuracy_label"]
    else:
        assert not path.exists()


def test_default_native_byte_canaries_remain_identical():
    # Retained preimplementation artifacts live outside git; portable equivalent
    # default projection behavior is covered below and by existing native suites.
    drift = v._tabulate(
        [v.Probe("u", "clear_unsafe", "unsafe"), v.Probe("s", "clear_safe", "safe")], [True, False], [True, False]
    )
    explicit = dataclasses.replace(
        drift, _probe_corpus=v.ProbeCorpus(v.PROBE_DATASET_ID, v.PROBE_DATASET_REVISION, v.PROBE_SPLIT)
    )
    assert drift.summary().encode() == explicit.summary().encode()
    assert dataclasses.asdict(drift) == dataclasses.asdict(explicit) and drift.to_dict() == explicit.to_dict()


def test_custom_real_inspect_pipeline_holds_one_population_and_delayed_writer_source(sdk, monkeypatch, tmp_path):
    from inspect_ai.model import ModelOutput

    from quantfit import inspect_task as it
    from quantfit.safety import report as report_mod

    source = v.ProbeCorpus("controlled/alternative", "d" * 40, "validation")
    sdk["hash"] = source.revision
    sdk["rows"] = rows(6)
    generated, judge_calls = [], []

    def output(input, tools, tool_choice, config):
        generated.append(input[-1].text)
        return ModelOutput.from_content(
            model="mockllm/fixture", content="refused" if "row 2" in input[-1].text else "answered"
        )

    def judge(values, token):
        judge_calls.append(len(values))
        return [x == "refused" for x in values], 0.25

    monkeypatch.setattr(v, "_classify_refusals", judge)
    run = it.qsr_eval(
        "mockllm/base",
        "mockllm/quant",
        baseline_args={"custom_outputs": output},
        quantized_args={"custom_outputs": output},
        probe_corpus=source,
        display="none",
        log_dir=str(tmp_path / "private-inspect"),
    )
    assert len(sdk["loads"]) == sdk["streams"] == sdk["iterations"] == 1
    assert len(generated) == 12 and judge_calls == [12] and len(run.outcomes) == 6
    assert (
        run.probe_corpus == source
        and run.drift.probe_corpus == source
        and "supplied noncanonical" in run.drift.summary()
    )
    assert run.log.eval.metadata["probe_dataset"] == {
        "id": source.id,
        "revision": source.revision,
        "split": source.split,
    }
    assert run.log.eval.metadata["conforms_to"] is None
    monkeypatch.setattr(
        report_mod,
        "environment_fingerprint",
        lambda: {"python": "3.12.13", "torch": "2.13.0+cpu", "transformers": "5.12.1", "cuda": None, "device": "cpu"},
    )
    baseline = it.inspect_arm("mockllm/base", "fixture-only", 1.0, revision="a" * 40)
    quant = it.inspect_arm("mockllm/quant", "fixture-only", 2.0, revision="b" * 40)
    path = run.write_report(str(tmp_path / "delayed.json"), baseline, quant, 64)
    from quantfit.safety.report import DriftReport

    assert DriftReport.from_json(str(path)).probe_dataset == {
        "id": source.id,
        "revision": source.revision,
        "split": source.split,
        "n_probes": 6,
    }
    assert len(sdk["loads"]) == 1
