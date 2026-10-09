"""Actual installed wheel entrypoint + pinned GGUF/full40/one real80-label judge.

Raw outputs stay in temporary Inspect memory/logs; only validated aggregates ship.
This is execution qualification, not sensitivity/adjudication/reproduction parity.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import io
import json
import platform
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from ci_cpu_acceptance import MODEL, REVISION, gguf_pair


def main() -> None:
    import torch

    import quantfit
    from quantfit.cli import main as cli
    from quantfit.safety import verify
    from quantfit.safety.report import DriftReport

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    package = Path(quantfit.__file__).resolve().parent
    assert not package.is_relative_to(checkout), "installed candidate must be outside checkout"
    assert not torch.cuda.is_available() and not torch.backends.mps.is_available()
    torch.set_num_threads(2)
    entries = [e for e in importlib.metadata.distribution("quantfit").entry_points if e.group == "inspect_ai"]
    assert [(e.name, e.value) for e in entries] == [("quantfit", "quantfit._inspect_registry")]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    report_path = args.out.with_name("inspect-gguf-drift.json")
    batches = []
    real_judge = verify._classify_refusals

    def measured_judge(outputs, token):
        batches.append(len(outputs))
        return real_judge(outputs, token)

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="quantfit-inspect-gguf-model-") as name:
        baseline, quant, conversion = gguf_pair(Path(name))
        # No direct provider-module import/register: resolve the advertised name
        # using actual installed package entrypoint discovery first.
        from inspect_ai.model import get_model

        model = get_model(f"quantfit_gguf/{baseline}", memoize=False)
        assert type(model.api).__module__ == "quantfit.inspect_gguf"
        model.api.close()  # construction resolved bytes; no server/model generation yet
        argv = [
            "inspect-run",
            "--baseline",
            f"quantfit_gguf/{baseline}",
            "--quant",
            f"quantfit_gguf/{quant}",
            "--max-new-tokens",
            "64",
            "--report",
            str(report_path),
            "--json",
        ]
        output = io.StringIO()
        with patch.object(verify, "_classify_refusals", measured_judge), contextlib.redirect_stdout(output):
            code = cli(argv)
        envelope = json.loads(output.getvalue())
        assert code in (0, 3, 4) and envelope["exit_code"] == code, envelope
        report = DriftReport.from_json(str(report_path))
        assert report.probe_dataset["n_probes"] == 40 and report.decode["max_new_tokens"] == 64
        assert report.decode["greedy"] is True and batches == [80]
        facts = envelope["result"]["observation_receipt"]
        assert facts["calls"] == facts["request_calls"] == [40, 40]
        assert facts["closed_before_judge"] and facts["resident_model_servers"] == 2
        assert facts["observed_available_ram_bytes"] >= facts["required_ram_estimate_bytes"]
        processes = facts["native_processes"]
        assert len({p["pid"] for p in processes}) == 2
        assert all(
            p["cleanup"]["direct_child_reaped"] and p["cleanup"]["no_live_group_members_observed"] for p in processes
        )
        from quantfit.safety import gguf_arm

        for arm, path in ((report.baseline, baseline), (report.quantized, quant)):
            assert arm.artifact_sha256 == gguf_arm._sha256(path) and arm.revision is None
            assert arm.engine["name"] == "inspect_ai:quantfit_gguf" and arm.engine["device"] == "cpu"
            assert all(arm.engine[k] == v for k, v in gguf_arm.CPU_OFFLOAD_CONTROLS.items())
            assert arm.engine["served_model_verified"] and arm.engine["generate_calls"] == 40
        from quantfit.bundle import _report

        _report(report_path.read_bytes())

    hashes = {}
    for relative in (
        "cli.py",
        "inspect_task.py",
        "inspect_gguf.py",
        "_inspect_registry.py",
        "safety/gguf_arm.py",
        "safety/verify.py",
        "cold_run.py",
        "safety/calibration_binding.py",
        "bundle.py",
    ):
        raw = (package / relative).read_bytes()
        canonical = subprocess.run(
            ["git", "show", f"HEAD:quantfit/{relative}"], cwd=checkout, capture_output=True, check=True
        ).stdout
        assert raw == canonical, "installed candidate module bytes differ from Gitblob"
        hashes[relative] = hashlib.sha256(raw).hexdigest()
    receipt = {
        "scope": "actual installed public Inspect extension, pinned converted GGUF pair, full40/real80judge",
        "source_model": MODEL,
        "source_revision": REVISION,
        "conversion": conversion,
        "max_new_tokens": 64,
        "n_probes": 40,
        "judge_batch_sizes": batches,
        "actual_exit": code,
        "observation": facts,
        "report": report_path.name,
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "source_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=checkout, capture_output=True, text=True, check=True
        ).stdout.strip(),
        "installed_origin": str(package),
        "installed_source_git_blob_sha256": hashes,
        "python": platform.python_version(),
        "elapsed_s": time.monotonic() - started,
        "versions": {n: importlib.metadata.version(n) for n in ("quantfit", "inspect-ai", "httpx", "gguf", "torch")},
        "scientific_go": False,
        "human_labels_authenticated": False,
        "limitations": [
            "Two model servers resident; RAM admission is an estimate, not peak RSS evidence.",
            "No native-generation parity, sensitivity, T0, GPU/crosshardware or independent reproduction.",
            "Observed judge flags are not human-confirmed labels; QSRv1 remains unfrozen.",
        ],
    }
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
