"""CLI envelope/exit/capture tests, with synthetic run results explicitly isolated."""

import json
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


def test_observed_runner_failure_releases_process_lock(monkeypatch):
    import quantfit.inspect_hf as hf
    import quantfit.inspect_task as task

    def failure(*a, **k):
        raise RuntimeError("fixture load failed")

    monkeypatch.setattr(task, "_inspect_api", lambda: {"get_model": object()})
    monkeypatch.setattr(hf, "HfRunObserver", failure)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="fixture load failed"):
            task.qsr_eval("hf/example/base", "hf/example/quant", hf_revisions=(SHA, SHA))
        assert not hf.RUN_LOCK.locked()


def test_observed_runner_defaults_to_serial_and_restores_after_eval_failure(monkeypatch):
    import quantfit.inspect_hf as hf
    import quantfit.inspect_task as task

    closed = []
    sentinel = types.SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(task, "_inspect_api", lambda: {"get_model": object()})
    monkeypatch.setattr(hf, "HfRunObserver", lambda *a, **k: sentinel)
    monkeypatch.setattr(task, "_registry", lambda: {"task": lambda *a, **k: types.SimpleNamespace(dataset=[1])})

    def evaluate(api, built, passthrough, *args):
        assert passthrough["max_samples"] == 1
        assert args[-1] is sentinel
        raise RuntimeError("fixture eval failed")

    monkeypatch.setattr(task, "_eval_task", evaluate)
    with pytest.raises(RuntimeError, match="fixture eval failed"):
        task.qsr_eval("hf/example/base", "hf/example/quant", hf_revisions=(SHA, SHA))
    assert closed == [True] and not hf.RUN_LOCK.locked()


def test_concurrent_observed_evaluation_fails_before_load(monkeypatch):
    import quantfit.inspect_hf as hf
    import quantfit.inspect_task as task

    monkeypatch.setattr(task, "_inspect_api", dict)
    with hf.RUN_LOCK, pytest.raises(RuntimeError, match="concurrent"):
        task.qsr_eval("hf/example/base", "hf/example/quant", hf_revisions=(SHA, SHA))
