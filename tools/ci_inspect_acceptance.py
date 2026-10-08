"""Actual installed Inspect/HF/full-corpus/pinned-judge CPU qualification.

Identical-arm orchestration canary, not a quantization or sensitivity experiment.
Temporary Inspect logs are captures and are deleted; only aggregates are saved.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import io
import json
import platform
import time
from pathlib import Path
from unittest.mock import patch

MODEL = "hf/HuggingFaceTB/SmolLM2-135M-Instruct"
REVISION = "12fd25f77366fa6b3b4b768ec3050bf629380bac"


def main() -> None:
    import torch

    import quantfit
    from quantfit.cli import main as cli
    from quantfit.safety import verify
    from quantfit.safety.report import DriftReport

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    package = Path(quantfit.__file__).resolve().parent
    checkout_package = Path(__file__).resolve().parents[1] / "quantfit"
    assert package != checkout_package, "qualification must consume an installed candidate outside the checkout"
    assert not torch.cuda.is_available() and not torch.backends.mps.is_available(), "CPU qualification only"
    torch.set_num_threads(2)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    report_path = args.out.with_name("inspect-drift.json")
    real_judge = verify._classify_refusals
    judge_batches = []

    def measured_judge(completions, token):
        judge_batches.append(len(completions))
        return real_judge(completions, token)

    stdout = io.StringIO()
    started = time.perf_counter()
    with patch.object(verify, "_classify_refusals", measured_judge), contextlib.redirect_stdout(stdout):
        code = cli(
            [
                "inspect-run",
                "--baseline",
                MODEL,
                "--quant",
                MODEL,
                "--baseline-revision",
                REVISION,
                "--quant-revision",
                REVISION,
                "--max-new-tokens",
                "4",
                "--report",
                str(report_path),
                "--json",
            ]
        )
    envelope = json.loads(stdout.getvalue())
    assert code in (0, 4) and envelope["exit_code"] == code, envelope
    report = DriftReport.from_json(str(report_path))
    n_probes = report.probe_dataset["n_probes"]
    assert n_probes == 40 and judge_batches == [2 * n_probes], "full pinned corpus and one real judge batch required"
    assert not report.drift["regression_detected"], "identical greedy arms changed judge labels"
    for arm in (report.baseline, report.quantized):
        assert arm.revision == REVISION and arm.runtime_s > 0
        assert arm.engine["device"] == "cpu"
        assert arm.engine["generate_calls"] == n_probes
        assert arm.engine["weight_generate_host_wall_s"] > 0
        assert arm.engine["tokenizer_revision"] == REVISION
    payload = {
        "qualification_schema": 1,
        "scope": "actual installed Inspect HF identical-arm CPU orchestration; full pinned corpus and one real pinned judge batch",
        "not_established": [
            "quantization sensitivity",
            "GPU execution",
            "generation parity with verify-safety",
            "human-confirmed safety",
            "judge calibration",
        ],
        "model": MODEL,
        "revision": REVISION,
        "max_new_tokens": 4,
        "n_probes": n_probes,
        "judge_batch_sizes": judge_batches,
        "exit_code": code,
        "elapsed_s": time.perf_counter() - started,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "torch_threads": torch.get_num_threads(),
            "versions": {
                name: importlib.metadata.version(name)
                for name in ("inspect-ai", "torch", "transformers", "huggingface-hub", "datasets")
            },
        },
        "report": report_path.name,
        "package_source": {
            "scope": "installed distribution outside checkout",
            "files_sha256": {
                name: hashlib.sha256((package / name).read_bytes()).hexdigest()
                for name in ("cli.py", "inspect_task.py", "inspect_hf.py")
            },
        },
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
