"""Actual public Inspect/CLI execution over explicit synthetic files/server/judge.

No model, native executable, actual HTTP, dataset download or human labels here.
The test fixture observes real Inspect calls while replacing the native server.
"""

import contextlib
import argparse
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import platform
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def write(name, value):
    (OUT / name).write_bytes((json.dumps(value, indent=2, allow_nan=False) + "\n").encode())


def load_test(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command(argv, expected):
    from quantfit.cli import main

    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
        code = main(argv)
    result = json.loads(output.getvalue())
    assert code == expected == result["exit_code"], result
    return {"argv": argv, "actual_exit": code, "envelope": result}


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    OUT = parser.parse_args().out.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    from quantfit.safety import report as report_module
    from quantfit.safety import verify
    from quantfit.safety.report import DriftReport

    observed_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                                   check=True).stdout.strip()
    tests = load_test("test_inspect_gguf")
    cal_tests = load_test("test_calibration_binding")
    batches, fixtures = [], []
    report_path = OUT / "synthetic-drift.json"
    with tempfile.TemporaryDirectory(prefix="quantfit-inspect-synthetic-") as name, pytest.MonkeyPatch.context() as patch:
        ext, _, arms, servers, binary = tests.fixture.__wrapped__(patch, Path(name))
        patch.setattr(ext.ga, "_binary_source", lambda path: "synthetic fixture binary; never provisioned or executed")
        probes = [verify.Probe(f"synthetic {i}", "clear_unsafe" if i < 20 else "clear_safe",
                               "unsafe" if i < 20 else "safe") for i in range(40)]
        patch.setattr(verify, "_load_probes", lambda token: probes)

        def judge(outputs, token):
            assert len(outputs) == 80 and len(servers) == 2 and all(s.closed for s in servers)
            batches.append(len(outputs))
            return [True] * 20 + [False] * 20 + [False] * 4 + [True] * 16 + [False] * 20, 0.0

        patch.setattr(verify, "_classify_refusals", judge)
        patch.setattr(report_module, "environment_fingerprint", lambda: {
            "python": platform.python_version(), "torch": "not installed; synthetic fixture",
            "transformers": "not installed; synthetic fixture", "cuda": None, "device": "cpu",
        })
        run = command(["inspect-run", "--baseline", f"quantfit_gguf/{arms[0].path}", "--quant",
                       f"quantfit_gguf/{arms[1].path}", "--report", str(report_path), "--json"], 3)
        write("synthetic-cli.json", run)
        assert batches == [80] and run["envelope"]["result"]["observation_receipt"]["calls"] == [40, 40]
        for arm in arms:
            fixtures.append({"name": arm.name, "actual_file_bytes": arm.path.stat().st_size,
                             "actual_file_sha256": hashlib.sha256(arm.path.read_bytes()).hexdigest()})
        fixtures.append({"name": "synthetic binary NOT executed", "actual_file_bytes": binary.stat().st_size,
                         "actual_file_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()})
    report = DriftReport.from_json(str(report_path))
    assert report.decode["max_new_tokens"] == 64 and report.probe_dataset["n_probes"] == 40
    calibration = OUT / "synthetic-calibration.json"
    write(calibration.name, cal_tests.calibration_fixture(report))
    resolution = OUT / "synthetic-resolution.json"
    write("resolution-cli.json", command(["resolution", "--report", str(report_path), "--calibration-report",
                                         str(calibration), "--out", str(resolution), "--json"], 0))
    bundle = OUT / "synthetic-bundle"
    write("bundle-create-cli.json", command(["bundle", "create", "--report", str(report_path),
                                            "--calibration-report", str(calibration), "--resolution",
                                            str(resolution), "--out", str(bundle), "--json"], 0))
    write("bundle-verify-cli.json", command(["bundle", "verify", "--bundle", str(bundle), "--json"], 0))
    write("synthetic-run.json", {
        "source_head_observed": observed_head,
        "scope": "actual public Inspect SDK and quantfit CLI over synthetic files/server/judge, no native model proof",
        "fixture_dependencies": ["tests/test_inspect_gguf.py:fixture", "tests/test_calibration_binding.py:calibration_fixture"],
        "declared_not_observed": ["native served metadata", "CPU inference", "available RAM", "GGUF dtype/architecture",
                                  "native process cleanup", "protocol dataset membership", "judge classifications"],
        "actual_public_sdk_calls": [40, 40], "actual_judge_fixture_batch_sizes": batches,
        "native_requests": 0, "models_loaded": 0, "real_judge_loaded": False,
        "fixtures": fixtures, "artifact_report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "omitted_token_flag_default": 64, "negative_cli_exit": 3,
        "scientific_go": False, "human_labels_authenticated": False, "assumptions_verified": False,
        "sdk_version": importlib.metadata.version("inspect-ai"), "default_private_log_dir_removed": True,
        "limitations": ["Synthetic binding is not human labels or calibrated sensitivity.",
                        "No GPU/crosshardware, native-generation parity, T0 or independent reproduction.",
                        "Actual installed wheel/model/real judge/POSIX qualification remains hosted-only pending."],
    })


if __name__ == "__main__":
    main()
