"""Held judge reruns and offline comparison through the native calibration paths."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("held_judge_fixture", ROOT / "tools/ci_calibration_judges.py")
assert SPEC and SPEC.loader
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


@pytest.fixture
def original(tmp_path):
    return FIXTURE.fixture(tmp_path / "source", ROOT, "a", native_report=True)


def paths(source):
    return tuple(str(source[role]) for role in ("report", "capture", "key"))


def observe(source, out):
    from quantfit.safety.calibration_judges import observe_calibration_judge

    return observe_calibration_judge(*paths(source), out_path=str(out))


def compare(source, observed, out, *, retained=False, pin=None):
    from quantfit.safety.calibration_judges import compare_observed_judge

    modes = (
        {"retained_labels_path": str(source["retained"]), "retention_receipt_path": str(source["receipt"])}
        if retained
        else {"sheet_path": str(source["sheet"])}
    )
    return compare_observed_judge(
        *paths(source),
        str(observed),
        observation_sha256=pin or hashlib.sha256(observed.read_bytes()).hexdigest(),
        out_path=str(out),
        **modes,
    )


def test_native_original_positive(original):
    from quantfit.resolution import parse_report_bytes
    from quantfit.safety.calibration_inputs import load_calibration_inputs

    report = parse_report_bytes(original["report"].read_bytes())
    held = load_calibration_inputs(str(original["capture"]), str(original["key"]), sheet_path=str(original["sheet"]))
    assert report.drift["n_probes"] == held.n_pairs == 8
    assert len(held.rows) == 16 and held.binding_fingerprint is not None


@pytest.mark.parametrize("retained", [False, True])
def test_observe_and_compare_keeps_the_whole_native_population(original, tmp_path, monkeypatch, retained):
    from quantfit.safety import verify

    calls = []
    flags = [*FIXTURE.JUDGES["b"][0], *FIXTURE.JUDGES["b"][1]]

    def judge(text, token):
        calls.append(text)
        return flags, 0.25

    monkeypatch.setattr(verify, "_classify_refusals", judge)
    monkeypatch.setattr(verify, "_generate_completions", lambda *_: pytest.fail("generation during judge rerun"))
    monkeypatch.setattr(verify, "_load_probes", lambda *_: pytest.fail("probe load during judge rerun"))
    observed = tmp_path / "private.judge-observation.json"
    before = {role: file.read_bytes() for role, file in original.items()}
    receipt = observe(original, observed)
    assert calls == [[f"{FIXTURE.MARKER} {arm} {i % 2}" for arm in ("baseline", "quantized") for i in range(8)]]
    raw = observed.read_bytes()
    record = json.loads(raw)
    assert receipt["observation"] == {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
    assert record["flags"] == flags and record["arm_order"] == ["baseline", "quantized"]
    assert record["fresh_judge"] == {
        "id": verify.JUDGE_MODEL_ID,
        "revision": verify.JUDGE_REVISION,
        "input_contract": verify.JUDGE_INPUT_CONTRACT,
    }
    assert record["runtime_s"] == 0.25 and record["n_pairs"] == 8
    assert FIXTURE.MARKER not in raw.decode()
    assert "flags" not in receipt
    monkeypatch.setattr(verify, "_classify_refusals", lambda *_: pytest.fail("offline compare contacted classifier"))
    out = tmp_path / "comparison.json"
    result = compare(original, observed, out, retained=retained)
    assert result == json.loads(out.read_bytes())
    assert result["n_pairs"] == 8 and result["n_rows_per_judge"] == 16
    assert result["same_judge_pin"] is False and result["gate_eligible"] is False
    assert result["truth_coverage"] == {
        "denominator_pairs": 8,
        "both_usable": 3,
        "baseline_only": 2,
        "quantized_only": 2,
        "neither_usable": 1,
    }
    assert result["per_arm"]["baseline"]["judge_a_by_judge_b"] == [[2, 2], [2, 2]]
    assert result["per_arm"]["baseline"]["error_a_by_error_b"] == [[1, 1], [2, 1]]
    assert result["per_arm"]["quantized"]["error_a_by_error_b"] == [[2, 1], [2, 0]]
    for group in result["native_per_judge"].values():
        for block in group["arms"].values():
            assert block["n"] == 5
    for private in (FIXTURE.MARKER, *map(str, original.values()), str(observed), str(out)):
        assert private not in out.read_text(encoding="utf-8")
    assert before == {role: file.read_bytes() for role, file in original.items()}


@pytest.mark.parametrize("change", ["capture_text", "valid_other_drift", "output_alias", "existing_output"])
def test_originals_and_output_are_admitted_before_judge(original, tmp_path, monkeypatch, change):
    from dataclasses import replace

    from quantfit.resolution import parse_report_bytes
    from quantfit.safety import verify
    from quantfit.safety.calibration_judges import CalibrationJudgesError

    out = tmp_path / "new.judge-observation.json"
    if change == "capture_text":
        data = original["capture"].read_bytes()
        original["capture"].write_bytes(data.replace(FIXTURE.MARKER.encode(), b"changed private bytes", 1))
    elif change == "valid_other_drift":
        report = parse_report_bytes(original["report"].read_bytes())
        probes = [verify.Probe("", "borderline", "safe" if i % 2 else "unsafe") for i in range(8)]
        alternate = verify._tabulate(probes, [True] * 8, [False] * 8).to_dict()
        replace(report, drift=alternate).to_json(str(original["report"]))
    elif change == "output_alias":
        out = original["key"]
    else:
        out.write_bytes(b"KEEP EXISTING")
    snapshots = {p: p.read_bytes() for p in (*original.values(), out) if p.exists()}
    monkeypatch.setattr(verify, "_classify_refusals", lambda *_: pytest.fail("judge before admission"))
    with pytest.raises(CalibrationJudgesError, match="^invalid_calibration_judges$") as error:
        observe(original, out)
    assert error.value.__cause__ is None
    assert all(p.read_bytes() == data for p, data in snapshots.items())
    assert out.exists() == (out in snapshots)


@pytest.mark.parametrize(
    ("flags", "runtime"),
    [
        ([False] * 15, 0),
        ([0] * 16, 0),
        ((False,) * 16, 0),
        ([False] * 16, False),
        ([False] * 16, -1),
        ([False] * 16, float("inf")),
    ],
)
def test_judge_output_is_exact_bool_vector_and_finite_nonnegative_runtime(
    original, tmp_path, monkeypatch, flags, runtime
):
    from quantfit.safety import verify
    from quantfit.safety.calibration_judges import CalibrationJudgesError

    monkeypatch.setattr(verify, "_classify_refusals", lambda *_: (flags, runtime))
    out = tmp_path / "bad.judge-observation.json"
    with pytest.raises(CalibrationJudgesError, match="^invalid_calibration_judges$"):
        observe(original, out)
    assert not out.exists()


@pytest.mark.parametrize("ambiguous", [False, True])
def test_pinned_native_classifier_receives_completion_only_and_refuses_ambiguous_head(
    original, tmp_path, monkeypatch, ambiguous
):
    import contextlib
    import sys

    from quantfit.safety import verify
    from quantfit.safety.calibration_judges import CalibrationJudgesError

    loads, tokenized = [], []
    config = SimpleNamespace(id2label={0: "refusal", 1: "refused"} if ambiguous else {0: "refusal", 1: "compliance"})

    class Tensor(dict):
        def to(self, device):
            assert device == "cpu"
            return self

    def tokenizer(text, **options):
        tokenized.append(text)
        assert options == {"return_tensors": "pt", "truncation": True, "max_length": 512}
        return Tensor(index=int(text.rsplit(" ", 1)[-1]))

    class Model:
        def to(self, device):
            assert device == "cpu"
            return self

        def eval(self):
            return None

        def __call__(self, *, index):
            return SimpleNamespace(logits=SimpleNamespace(argmax=lambda **_: SimpleNamespace(item=lambda: index)))

    model = Model()
    model.config = config

    def loader(kind, value):
        def load(name, **options):
            loads.append((kind, name, options))
            return value

        return SimpleNamespace(from_pretrained=load)

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoTokenizer=loader("tokenizer", tokenizer), AutoModelForSequenceClassification=loader("model", model)
        ),
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(no_grad=contextlib.nullcontext))
    monkeypatch.setattr(verify, "pick_device", lambda: "cpu")
    monkeypatch.setattr(verify, "free_gpu", lambda _: None)
    out = tmp_path / "native.judge-observation.json"
    if ambiguous:
        with pytest.raises(CalibrationJudgesError, match="^invalid_calibration_judges$") as error:
            observe(original, out)
        assert error.value.__cause__ is None and not out.exists() and tokenized == []
    else:
        observe(original, out)
        assert tokenized == [f"{FIXTURE.MARKER} {arm} {i % 2}" for arm in ("baseline", "quantized") for i in range(8)]
        assert json.loads(out.read_bytes())["flags"] == [True, False] * 8
    assert loads == [
        (kind, verify.JUDGE_MODEL_ID, {"revision": verify.JUDGE_REVISION, "token": None})
        for kind in ("tokenizer", "model")
    ]


@pytest.mark.parametrize(
    "change",
    [
        "pin",
        "source_bytes",
        "bool_schema",
        "flag_count",
        "flag_type",
        "fresh_pin",
        "order",
        "ordered_cells",
        "extra",
        "duplicate",
        "runtime",
    ],
)
def test_offline_receiver_refuses_pin_and_typed_bindings(original, tmp_path, monkeypatch, change):
    from quantfit.safety import verify
    from quantfit.safety.calibration_judges import CalibrationJudgesError

    monkeypatch.setattr(verify, "_classify_refusals", lambda *_: ([False] * 16, 0))
    obs = tmp_path / "observed.judge-observation.json"
    receipt = observe(original, obs)
    value = json.loads(obs.read_bytes())
    if change == "source_bytes":
        original["report"].write_bytes(original["report"].read_bytes() + b"\n")
    elif change == "bool_schema":
        value["judge_observation_schema"] = True
    elif change == "flag_count":
        value["flags"].pop()
    elif change == "flag_type":
        value["flags"][0] = 0
    elif change == "fresh_pin":
        value["fresh_judge"]["revision"] = "0" * 40
    elif change == "order":
        value["arm_order"].reverse()
    elif change == "ordered_cells":
        value["ordered_cells_sha256"] = "0" * 64
    elif change == "extra":
        value["surplus"] = True
    elif change == "runtime":
        value["runtime_s"] = True
    encoded = json.dumps(value).encode()
    if change == "duplicate":
        encoded = b'{"n_pairs":8,' + encoded[1:]
    obs.write_bytes(encoded)
    monkeypatch.setattr(verify, "_classify_refusals", lambda *_: pytest.fail("receiver ran classifier"))
    out = tmp_path / "not-written.json"
    pin = receipt["observation"]["sha256"] if change == "pin" else None
    with pytest.raises(CalibrationJudgesError, match="^invalid_calibration_judges$"):
        compare(original, obs, out, pin=pin)
    assert not out.exists()


def test_local_identity_same_pin_and_all_unusable_remain_descriptive(tmp_path, monkeypatch):
    from quantfit.safety import verify

    side = FIXTURE.fixture(
        tmp_path / "local",
        ROOT,
        "b",
        native_report=True,
        local_source=True,
        pinned_judge=True,
        base_truth=("unusable",) * 8,
        quant_truth=("unusable",) * 8,
    )
    flags = [*FIXTURE.JUDGES["b"][0], *FIXTURE.JUDGES["b"][1]]

    def classify(text, token):
        assert text == [f"{FIXTURE.MARKER} {arm} {i % 2}" for arm in ("baseline", "quantized") for i in range(8)]
        return flags, 0.0

    monkeypatch.setattr(verify, "_classify_refusals", classify)
    obs = tmp_path / "local.judge-observation.json"
    observe(side, obs)
    result = compare(side, obs, tmp_path / "local-aggregate.json", retained=True)
    assert result["same_judge_pin"] is True
    assert result["original_measurement_fingerprint"] == json.loads(side["key"].read_bytes())["binding"]["fingerprint"]
    assert result["truth_coverage"]["neither_usable"] == 8
    for arm, table in result["per_arm"].items():
        assert table["whole_n"] == table["unusable_truth_n"] == 8 and table["flag_disagreements"] == 0
        assert table["error_a_by_error_b"] == [[0, 0], [0, 0]]
        for group in result["native_per_judge"].values():
            block = group["arms"][arm]
            assert block["n"] == 0 and block["epsilon"] is None and block["epsilon_wilson95"] == [0, 1]


def test_installed_selected_consumer_uses_real_os_cli(tmp_path):
    spec = importlib.util.spec_from_file_location("judge_observation_consumer", ROOT / "tools/ci_judge_observation.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    result = helper.run(ROOT, tmp_path / "cli")
    assert [case["exit_code"] for case in result["real_os_cli"]] == [0, 0, 0, 2, 2]
    assert result["classifier_calls"] == 1 and result["package_origin_matched_parent"] is True


def test_external_classifier_exception_is_private_and_leaves_no_output(original, tmp_path, monkeypatch):
    from quantfit.safety import verify
    from quantfit.safety.calibration_judges import CalibrationJudgesError

    class LoaderFailure(Exception):
        pass

    def fail(*args):
        raise LoaderFailure(FIXTURE.MARKER)

    monkeypatch.setattr(verify, "_classify_refusals", fail)
    out = tmp_path / "no-observation.judge-observation.json"
    with pytest.raises(CalibrationJudgesError, match="^invalid_calibration_judges$") as error:
        observe(original, out)
    assert error.value.__cause__ is None and error.value.__suppress_context__
    assert not out.exists()


def test_late_truth_failure_is_rejected_before_statistics(original, tmp_path, monkeypatch):
    from quantfit.safety import calibration_judges, verify

    monkeypatch.setattr(verify, "_classify_refusals", lambda *_: ([False] * 16, 0))
    obs = tmp_path / "valid.judge-observation.json"
    observe(original, obs)
    with original["sheet"].open("ab") as stream:
        stream.write(b"extra,PRIVATE_UNRECOGNIZED,unusable\n")
    monkeypatch.setattr(
        calibration_judges, "_group", lambda *_: pytest.fail("statistics before complete truth admission")
    )
    out = tmp_path / "not-aggregated.json"
    with pytest.raises(calibration_judges.CalibrationJudgesError, match="^invalid_calibration_judges$"):
        compare(original, obs, out)
    assert not out.exists()
