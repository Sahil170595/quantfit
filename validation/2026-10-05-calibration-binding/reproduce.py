"""Reproduce aggregate functional fixtures; no real models, human labels or study."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_bound_calibration_pipeline import _large_synthetic_run, synthetic_roundtrip

from quantfit import __version__
from quantfit.gate import run_gate
from quantfit.safety.calibration_binding import CalibrationBindingError, load_bound_calibration


def write(name: str, payload: dict) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="quantfit-binding-fixture-") as temporary:
        tmp = Path(temporary)
        with pytest.MonkeyPatch.context() as patch:
            payload, calibration, drift, *_ = synthetic_roundtrip(tmp, patch)
            bound = load_bound_calibration(str(calibration))
            decision = run_gate("base", "quant", tier="smoke", calibration_report=str(calibration))
            assert decision["exit_code"] == 5
            assert not decision["eps"]["actual_run_matched"]
            assert not decision["eps"]["measured"]
            for source, name in ((calibration, "calibration.json"), (drift, "drift.json")):
                shutil.copyfile(source, OUT / name)
            write("gate.json", decision)
            # A second derivation from denominators documents which arm controls each bound.
            from quantfit.safety.verify import wilson_interval

            assert bound.eps_baseline_upper == max(wilson_interval(0, 20)[1], wilson_interval(0, 20)[1])
            assert bound.eps_quant_upper == max(wilson_interval(0, 10)[1], wilson_interval(0, 30)[1])

        cli = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantfit.cli",
                "gate",
                "--baseline",
                "base",
                "--quant",
                "quant",
                "--tier",
                "smoke",
                "--calibration-report",
                str(OUT / "calibration.json"),
                "--json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert cli.returncode == 5, cli.stderr
        envelope = json.loads(cli.stdout)
        assert envelope["exit_code"] == 5 and not envelope["result"]["eps"]["actual_run_matched"]
        assert envelope["result"]["eps"]["source_sha256"] == bound.source_sha256
        write("cli-envelope.json", envelope)

        wide = tmp / "widened-fixture"
        wide.mkdir()
        with pytest.MonkeyPatch.context() as patch:
            calibration, calls = _large_synthetic_run(wide, patch)
            observed = wide / "drift.json"
            matched = run_gate("base", "quant", tier="smoke", calibration_report=calibration, report_path=str(observed))
            assert len(calls) == 1 and matched["eps"]["actual_run_matched"] and matched["exit_code"] == 0
            assert not matched["eps"]["measured"]
            for source, name in (
                (Path(calibration), "widened-fixture-calibration.json"),
                (observed, "widened-fixture-drift.json"),
            ):
                shutil.copyfile(source, OUT / name)
            write("widened-fixture-gate.json", matched)

        with pytest.MonkeyPatch.context() as patch:
            calibration, calls = _large_synthetic_run(wide, patch, mismatch=True)
            try:
                run_gate("base", "quant", tier="smoke", calibration_report=calibration)
            except CalibrationBindingError as error:
                mismatch = str(error)
            else:
                raise AssertionError("changed observed weights must be refused")
            assert len(calls) == 1

    sources = (
        "quantfit/safety/calibration_binding.py",
        "quantfit/safety/calibrated_gate.py",
        "quantfit/safety/calibrate.py",
        "quantfit/safety/verify.py",
        "quantfit/gate.py",
        "quantfit/cli.py",
        "tests/test_calibration_binding.py",
        "tests/test_bound_calibration_pipeline.py",
        "validation/2026-10-05-calibration-binding/reproduce.py",
    )
    write(
        "receipt.json",
        {
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": "synthetic functional evidence, no human adjudication",
            "command": "tools/ci/.venv/Scripts/python.exe validation/2026-10-05-calibration-binding/reproduce.py",
            "actual_runtime": {
                "quantfit_source_version": __version__,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "machine": platform.machine(),
                "packages": {
                    name: importlib.metadata.version(name)
                    for name in ("torch", "transformers", "pytest", "ruff", "datasets")
                },
            },
            "fixture_scope_is_observed_runtime": False,
            "source_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sources},
            "roundtrip": {
                "n_labeled": payload["n_labeled"],
                "eps_baseline_upper": bound.eps_baseline_upper,
                "eps_quant_upper": bound.eps_quant_upper,
                "fingerprint": bound.fingerprint,
                "gate_exit": decision["exit_code"],
                "cli_process_exit": cli.returncode,
                "binding_status": decision["eps"]["binding_status"],
            },
            "post_run_fixture": {
                "n_probes": 2000,
                "expected_unsafe": 1500,
                "gate_exit": matched["exit_code"],
                "actual_run_matched": matched["eps"]["actual_run_matched"],
                "changed_weights_refusal": mismatch,
            },
            "limits": [
                "All generation, judge outputs and labels are manufactured test data; no real models ran.",
                "Placeholder immutable arm revisions and fixture versions are synthetic, not checked upstream assets.",
                "The widened corpus is monkeypatched in this script only; shipped corpus and QSR v0 do not change.",
                "Matching scope and hashes cannot authenticate label truth, independence or sensitivity.",
                "No calibration study, GPU qualification, sensitivity control or research GO is established.",
                "Raw capture, labeling sheet and key exist only in an automatically removed temporary directory.",
            ],
        },
    )


if __name__ == "__main__":
    main()
