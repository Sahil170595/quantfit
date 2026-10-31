"""Controlled pinned-source API/module-entrypoint consumer; no Hub or inference."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import runpy
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


def _guard(checkout: Path, installed: bool) -> int:
    import quantfit

    package = Path(quantfit.__file__).resolve().parent
    if installed:
        assert not package.is_relative_to(checkout.resolve())
    count = 0
    for name, module in tuple(sys.modules.items()):
        if name == "quantfit" or name.startswith("quantfit."):
            origin = getattr(module, "__file__", None)
            assert origin and Path(origin).resolve().is_relative_to(package)
            count += 1
    return count


def _child(root: Path, interface: str, case: str, checkout: Path, installed: bool) -> None:
    from contextlib import ExitStack
    from unittest.mock import patch

    from quantfit.safety import report as report_mod
    from quantfit.safety import verify as native
    from quantfit.safety.report import ArmRun

    datasets = importlib.import_module("datasets")
    _guard(checkout, installed)
    source = native.ProbeCorpus(
        "controlled/corpus" if case not in {"default", "explicit", "revision", "split"} else native.PROBE_DATASET_ID,
        "d" * 40
        if case in {"custom", "revision", "capture-only", "one-axis", "regression"}
        else native.PROBE_DATASET_REVISION,
        "validation" if case == "split" else native.PROBE_SPLIT,
    )
    count = 4 if case == "one-axis" else 40
    rows = [
        {
            "prompt": f"  controlled Ω value {i}\r\n" if i % 5 else "repeated controlled value",
            "zone": ["clear_safe", "clear_unsafe", "borderline"][i % 3],
            "expected": "safe" if case == "one-axis" or i % 2 else "unsafe",
        }
        for i in range(count)
    ]
    calls: dict[str, Any] = {"factory": 0, "stream": 0, "iterations": 0, "arm_calls": 0, "judge": 0}

    class Builder:
        hash = source.revision

        def as_streaming_dataset(self, split: str) -> Any:
            assert split == source.split
            calls["stream"] += 1

            def generate() -> Any:
                calls["iterations"] += 1
                yield from rows

            return datasets.IterableDataset.from_generator(generate)

    def builder(path: str, **kwargs: Any) -> Builder:
        assert path == "hf://datasets/" + source.id and kwargs == {"revision": source.revision, "token": None}
        calls["factory"] += 1
        return Builder()

    def generation(model: str, prompts: list[str], maximum: int, token: str | None) -> Any:
        assert prompts == [row["prompt"] for row in rows]
        calls["arm_calls"] += 1
        values = ["refused" if row["expected"] == "unsafe" else "answered" for row in rows]
        if case == "regression" and calls["arm_calls"] == 2:
            values[0] = "answered"
        return values, ArmRun(
            model,
            ("a" if calls["arm_calls"] == 1 else "b") * 40,
            "torch.float32",
            1.0,
            {"name": "transformers", "version": "5.12.1", "device": "cpu"},
            None,
        )

    def judge(values: list[str], token: str | None) -> Any:
        calls["judge"] += 1
        assert len(values) == 2 * count
        return [value == "refused" for value in values], 0.25

    def no_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network forbidden in controlled corpus fixture")

    report, capture = root / "report.json", root / "private.capture.jsonl"
    options: dict[str, Any] = {"capture_path": str(capture)}
    if case != "capture-only":
        options["report_path"] = str(report)
    if case != "default":
        options["probe_corpus"] = source
    expected_exit = 4 if case == "one-axis" else 3 if case == "regression" else 0
    with ExitStack() as stack:
        for obj, name, value in [
            (datasets, "load_dataset_builder", builder),
            (native, "_generate_completions", generation),
            (native, "_classify_refusals", judge),
            (socket, "create_connection", no_network),
            (socket.socket, "connect", no_network),
            (
                report_mod,
                "environment_fingerprint",
                lambda: {
                    "python": "3.12.13",
                    "torch": "2.13.0+cpu",
                    "transformers": "5.12.1",
                    "cuda": None,
                    "device": "cpu",
                },
            ),
        ]:
            stack.enter_context(patch.object(obj, name, value))
        if interface == "api":
            drift = native.verify_safety("controlled/base", "controlled/quant", **options)
            actual_exit = 3 if drift.regression_detected else 4 if drift.unmeasurable_axes else 0
            assert actual_exit == expected_exit
        else:
            sys.argv = [
                "quantfit",
                "verify-safety",
                "--baseline",
                "controlled/base",
                "--quant",
                "controlled/quant",
                "--capture",
                str(capture),
                "--json",
            ]
            if case != "capture-only":
                sys.argv += ["--report", str(report)]
            if case != "default":
                sys.argv += [
                    "--probe-dataset",
                    source.id,
                    "--probe-revision",
                    source.revision,
                    "--probe-split",
                    source.split,
                ]
            try:
                runpy.run_module("quantfit.cli", run_name="__main__")
            except SystemExit as exit_result:
                assert exit_result.code == expected_exit
    assert calls == {"factory": 1, "stream": 1, "iterations": 1, "arm_calls": 2, "judge": 1}
    source_data = {"id": source.id, "revision": source.revision, "split": source.split, "n_probes": count}
    header = json.loads(capture.read_bytes().splitlines()[0])
    assert header["binding"]["identity"]["probe_dataset"] == source_data
    if case != "capture-only":
        from quantfit.modelcard import model_card_fragment
        from quantfit.safety.calibration_binding import CalibrationBindingError, load_bound_calibration
        from quantfit.safety.report import DriftReport

        actual = DriftReport.from_json(str(report))
        assert actual.probe_dataset == source_data
        spec = importlib.util.spec_from_file_location(
            "corpus_native_calibration", checkout / "tools/ci_screen_resolution.py"
        )
        assert spec and spec.loader
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        calibration = root / "calibration.json"
        calibration.write_bytes(helper.calibration_bytes(report.read_bytes()))
        bound = load_bound_calibration(str(calibration), report=actual)
        bound.match_report(actual)
        from dataclasses import replace

        try:
            bound.match_report(replace(actual, probe_dataset={**actual.probe_dataset, "revision": "e" * 40}))
        except CalibrationBindingError:
            pass
        else:
            raise AssertionError("source mismatch must refuse bound calibration")
        for calibrated in (False, True):
            card = model_card_fragment(str(report), **({"calibration_report": str(calibration)} if calibrated else {}))
            if not native._canonical_source(source):
                assert "supplied noncanonical" in card and "n <= 34" not in card and "At the n above" not in card
        if case == "regression":
            from quantfit.safety.adjudication import apply_adjudication, prepare_adjudication

            spec = importlib.util.spec_from_file_location("corpus_private_fill", checkout / "tools/ci_adjudication.py")
            assert spec and spec.loader
            fill_helper = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fill_helper)
            queue, preparation, record = root / "private.csv", root / "preparation.json", root / "adjudication.json"
            prepared = prepare_adjudication(
                str(report), str(capture), review_path=str(queue), receipt_path=str(preparation)
            )
            assert prepared["n_selected"] == 1
            fill_helper.filled(queue)  # Explicit fictional labels, no human review.
            apply_adjudication(str(report), str(capture), str(queue), str(preparation), out_path=str(record))
            for calibrated in (False, True):
                card = model_card_fragment(
                    str(report),
                    adjudication_record=str(record),
                    adjudication_capture=str(capture),
                    **({"calibration_report": str(calibration)} if calibrated else {}),
                )
                assert "supplied noncanonical" in card and "n <= 34" not in card and "At the n above" not in card
    (root / "result.json").write_text(
        json.dumps(
            {
                "interface": interface,
                "case": case,
                "count": count,
                "native_exit": expected_exit,
                "calls": calls,
                "source_exact": True,
                "capture_only": case == "capture-only",
                "custom_capture_backed_adjudication_cards": case == "regression",
                "loaded_modules_guarded": _guard(checkout, installed),
            }
        )
        + "\n"
    )


def run(checkout: Path, root: Path, *, installed: bool = False) -> dict[str, Any]:
    records = []
    for interface in ("api", "cli"):
        for case in ("default", "explicit", "custom", "revision", "split", "capture-only", "one-axis", "regression"):
            local = root / f"{interface}-{case}"
            local.mkdir(parents=True)
            argv = [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                str(Path(__file__).resolve()),
                "--child",
                interface,
                "--case",
                case,
                "--root",
                str(local),
                "--checkout",
                str(checkout),
            ]
            if installed:
                argv += ["--installed"]
            env = {
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUTF8": "1",
                "HF_HUB_OFFLINE": "1",
                "HF_DATASETS_OFFLINE": "1",
            }
            env.pop("PYTHONPATH", None)
            result = subprocess.run(
                argv, cwd=local, env=env, stdin=subprocess.DEVNULL, capture_output=True, check=False
            )
            (local / "child.stdout").write_bytes(result.stdout)
            (local / "child.stderr").write_bytes(result.stderr)
            assert result.returncode == 0, (
                "controlled corpus child failed; private output retained only by owning test capture"
            )
            if interface == "cli":
                envelope = json.loads(result.stdout)
                assert envelope["exit_code"] == (4 if case == "one-axis" else 3 if case == "regression" else 0)
                if case not in {"default", "explicit"}:
                    assert envelope["result"]["probe_scope"].startswith("supplied noncanonical")
            records.append(json.loads((local / "result.json").read_bytes()))
    adverse = []
    for label, flags in (
        ("partial-id", ["--probe-dataset", "controlled/corpus"]),
        ("partial-revision", ["--probe-revision", "d" * 40]),
        ("partial-split", ["--probe-split", "train"]),
        ("bucket", ["--probe-dataset", "buckets/fixture", "--probe-revision", "d" * 40, "--probe-split", "train"]),
        ("moving-pin", ["--probe-dataset", "controlled/corpus", "--probe-revision", "main", "--probe-split", "train"]),
        (
            "split-union",
            ["--probe-dataset", "controlled/corpus", "--probe-revision", "d" * 40, "--probe-split", "train+test"],
        ),
        (
            "split-slice",
            ["--probe-dataset", "controlled/corpus", "--probe-revision", "d" * 40, "--probe-split", "train[:40]"],
        ),
        (
            "demo-conflict",
            ["--demo", "--probe-dataset", "controlled/corpus", "--probe-revision", "d" * 40, "--probe-split", "train"],
        ),
    ):
        result = subprocess.run(
            [sys.executable, "-B", "-m", "quantfit.cli", "verify-safety", *flags, "--json"],
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 2 and result.stdout and not result.stderr
        envelope = json.loads(result.stdout)
        assert "invalid_probe_corpus" in envelope["error"]["message"]
        adverse.append({"case": label, "exit_code": 2, "pre_IO_source_refusal": True})
    return {
        "positive_cases": len(records),
        "cases": records,
        "actual_source_load_once": True,
        "adverse_cases": len(adverse),
        "adverse": adverse,
        "bound_source_mismatch_controls": sum(not case["capture_only"] for case in records),
        "boundary": "controlled SDK factory/generation/judge; actual API and OS module entrypoint/Inspect-tested separately; no real corpus/model qualification",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", choices=["api", "cli"], required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    _child(args.root, args.child, args.case, args.checkout, args.installed)


if __name__ == "__main__":
    main()
