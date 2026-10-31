"""CLI envelope/exit/capture tests, with synthetic run results explicitly isolated."""

import json
import os
import types

import pytest

from quantfit.cli import main

SHA = "a" * 40
ARGS = [
    "inspect-run",
    "--baseline",
    "hf/example/base",
    "--quant",
    "hf/example/quant",
    "--baseline-revision",
    SHA,
    "--quant-revision",
    SHA,
    "--json",
]


@pytest.fixture
def observed_population(monkeypatch):
    import datasets

    from quantfit.safety import verify

    state = {"builds": 0, "yielded": 0, "EOF": 0}

    def generate():
        for i in range(40):
            state["yielded"] += 1
            yield {"prompt": f"controlled runner row {i}", "zone": "clear_safe", "expected": "safe"}
        state["EOF"] += 1

    class Builder:
        hash = verify.PROBE_DATASET_REVISION

        def as_streaming_dataset(self, split):
            assert split == verify.PROBE_SPLIT
            return datasets.IterableDataset.from_generator(generate)

    def builder(path, *, revision, token):
        assert path == "hf://datasets/" + verify.PROBE_DATASET_ID
        assert revision == verify.PROBE_DATASET_REVISION and token is None
        state["builds"] += 1
        return Builder()

    monkeypatch.setattr(datasets, "load_dataset_builder", builder)
    return state


@pytest.mark.parametrize("args", [["inspect-run", "--json"], ARGS[:5] + ["--json"]])
def test_missing_inputs_clean_exit_two(args, capsys):
    assert main(args) == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["command"] == "inspect-run" and payload["exit_code"] == 2
    assert "Traceback" not in captured.out + captured.err


@pytest.mark.parametrize(
    "regression,axes,expected", [(False, [], 0), (True, [], 3), (False, ["dangerous"], 4), (True, ["dangerous"], 3)]
)
def test_exit_precedence_and_json_isolation(monkeypatch, capsys, tmp_path, regression, axes, expected):
    import quantfit.inspect_task as task

    received = []
    report_calls = []

    def fake_run(*args, **kwargs):
        received.append(kwargs)
        print("synthetic provider progress")
        drift = types.SimpleNamespace(
            regression_detected=regression, unmeasurable_axes=axes, summary=lambda: "fixture verdict"
        )
        return types.SimpleNamespace(
            drift=drift, observed_arms=("fixture-base", "fixture-quant"), write_report=lambda *a: report_calls.append(a)
        )

    monkeypatch.setattr(task, "qsr_eval", fake_run)
    report = tmp_path / "nested" / "drift.json"
    assert main(ARGS + ["--report", str(report)]) == expected
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["exit_code"] == expected
    assert "synthetic provider progress" in captured.err
    assert received[0]["max_samples"] == 1 and received[0]["display"] == "none"
    assert received[0]["hf_revisions"] == (SHA, SHA)
    assert not __import__("pathlib").Path(received[0]["log_dir"]).exists()
    assert report_calls == [(str(report), "fixture-base", "fixture-quant", 64)]


def test_observation_failure_is_not_a_verdict(monkeypatch, capsys):
    import quantfit.inspect_task as task

    monkeypatch.setattr(task, "qsr_eval", lambda *a, **k: types.SimpleNamespace(observed_arms=None))
    assert main(ARGS) == 2
    assert "actual loaded" in json.loads(capsys.readouterr().out)["error"]["message"]


def test_gguf_local_pin_slots_forward_without_invented_revisions(monkeypatch, capsys):
    import quantfit.inspect_task as task

    received = []

    def failed(*a, **kw):
        received.append(kw)
        raise RuntimeError("synthetic refusal before model loading")

    monkeypatch.setattr(task, "qsr_eval", failed)
    assert (
        main(["inspect-run", "--baseline", "quantfit_gguf/base.gguf", "--quant", "quantfit_gguf/quant.gguf", "--json"])
        == 2
    )
    assert received[0]["gguf_revisions"] == (None, None) and "hf_revisions" not in received[0]
    assert not __import__("pathlib").Path(received[0]["log_dir"]).exists()
    assert json.loads(capsys.readouterr().out)["exit_code"] == 2


@pytest.mark.parametrize("alias", ["direct", "relative", "hardlink", "symlink"])
def test_gguf_report_alias_refuses_before_contact(monkeypatch, capsys, tmp_path, alias):
    import quantfit.inspect_task as task

    base, quant = tmp_path / "base.gguf", tmp_path / "quant.gguf"
    base.write_bytes(b"synthetic immutable weights")
    quant.write_bytes(b"synthetic quant weights")
    out = base
    if alias == "relative":
        monkeypatch.chdir(tmp_path)
        out = __import__("pathlib").Path("base.gguf")
    elif alias == "hardlink":
        out = tmp_path / "alias.json"
        os.link(base, out)
    elif alias == "symlink":
        out = tmp_path / "alias.json"
        try:
            out.symlink_to(base)
        except OSError:
            pytest.skip("Symlink privilege unavailable; hosted Linux exercises report alias")
    monkeypatch.setattr(task, "qsr_eval", lambda *a, **kw: pytest.fail("model contact forbidden for aliased report"))
    assert (
        main(
            [
                "inspect-run",
                "--baseline",
                f"quantfit_gguf/{base}",
                "--quant",
                f"quantfit_gguf/{quant}",
                "--report",
                str(out),
                "--json",
            ]
        )
        == 2
    )
    assert "overwrite" in json.loads(capsys.readouterr().out)["error"]["message"]
    assert base.read_bytes() == b"synthetic immutable weights" and quant.read_bytes() == b"synthetic quant weights"


def test_explicit_log_dir_gets_capture_warning(monkeypatch, capsys, tmp_path):
    import quantfit.inspect_task as task

    def failed(*a, **k):
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(task, "qsr_eval", failed)
    assert main(ARGS + ["--log-dir", str(tmp_path / "logs")]) == 2
    captured = capsys.readouterr()
    assert "never commit" in captured.err
    assert json.loads(captured.out)["exit_code"] == 2


def test_observed_mode_refuses_parallel_samples_before_loading(monkeypatch):
    import quantfit.inspect_task as task

    monkeypatch.setattr(task, "_inspect_api", lambda: {"get_model": lambda *a, **k: pytest.fail("load forbidden")})
    with pytest.raises(RuntimeError, match="max_samples=1"):
        task.qsr_eval("hf/example/base", "hf/example/quant", hf_revisions=(SHA, SHA), max_samples=2)


def test_observed_mode_does_not_admit_source_override(monkeypatch):
    import quantfit.inspect_task as task

    monkeypatch.setattr(task, "_inspect_api", dict)
    with pytest.raises(RuntimeError, match="model_path"):
        task.qsr_eval(
            "hf/example/base", "hf/example/quant", hf_revisions=(SHA, SHA), baseline_args={"model_path": "/forged"}
        )


def test_observed_runner_failure_releases_process_lock(monkeypatch, observed_population):
    import quantfit.inspect_hf as hf
    import quantfit.inspect_task as task

    def failure(*a, **k):
        assert observed_population["yielded"] == 40 * observed_population["builds"]
        assert observed_population["EOF"] == observed_population["builds"]
        raise RuntimeError("fixture load failed")

    monkeypatch.setattr(task, "_inspect_api", lambda: {"get_model": object()})
    monkeypatch.setattr(hf, "HfRunObserver", failure)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="fixture load failed"):
            task.qsr_eval("hf/example/base", "hf/example/quant", hf_revisions=(SHA, SHA))
        assert not hf.RUN_LOCK.locked()
    assert observed_population == {"builds": 2, "yielded": 80, "EOF": 2}


def test_observed_runner_defaults_to_serial_and_restores_after_eval_failure(monkeypatch, observed_population):
    import quantfit.inspect_hf as hf
    import quantfit.inspect_task as task
    from quantfit.safety import verify

    closed = []
    received = []
    sentinel = types.SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(task, "_inspect_api", lambda: {"get_model": object()})
    monkeypatch.setattr(hf, "HfRunObserver", lambda *a, **k: sentinel)

    def prepared(*args):
        source, probes, observer = args[-3:]
        assert source == verify.ProbeCorpus(verify.PROBE_DATASET_ID, verify.PROBE_DATASET_REVISION, verify.PROBE_SPLIT)
        assert len(probes) == 40 and all(type(p) is verify.Probe for p in probes)
        assert observer is sentinel
        assert observed_population == {"builds": 1, "yielded": 40, "EOF": 1}
        received.append((source, probes))
        return types.SimpleNamespace(dataset=probes)

    monkeypatch.setattr(task, "_registry", lambda: {"prepared_task": prepared})

    def evaluate(api, built, passthrough, *args, probe_corpus):
        assert passthrough["max_samples"] == 1
        assert args[-1] is sentinel
        assert probe_corpus is received[0][0] and built.dataset is received[0][1]
        raise RuntimeError("fixture eval failed")

    monkeypatch.setattr(task, "_eval_task", evaluate)
    with pytest.raises(RuntimeError, match="fixture eval failed"):
        task.qsr_eval("hf/example/base", "hf/example/quant", hf_revisions=(SHA, SHA))
    assert closed == [True] and not hf.RUN_LOCK.locked()
    assert len(received) == 1


def test_concurrent_observed_evaluation_fails_before_load(monkeypatch, observed_population):
    import quantfit.inspect_hf as hf
    import quantfit.inspect_task as task

    monkeypatch.setattr(task, "_inspect_api", dict)
    with hf.RUN_LOCK, pytest.raises(RuntimeError, match="concurrent"):
        task.qsr_eval("hf/example/base", "hf/example/quant", hf_revisions=(SHA, SHA))
    assert observed_population == {"builds": 1, "yielded": 40, "EOF": 1}
