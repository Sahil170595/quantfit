"""Actual WSL/POSIX orchestration; synthetic aggregates, no models or raw output."""

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quantfit.cold_run import cold_run  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-head", required=True, help="Windows Git observation, supplied explicitly")
    args = parser.parse_args()
    output = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("cold_test", ROOT / "tests/test_cold_run.py")
    test = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test)
    cases = []
    modes = ("regression", "null", "unmeasured", "disagreement", "operational", "timeout",
             "different-binary", "different-threads", "quantized-baseline")
    for mode in modes:
        with tempfile.TemporaryDirectory(prefix="quantfit-synthetic-shim-") as name, pytest.MonkeyPatch.context() as patch:
            test.synthetic_children(Path(name), patch, mode)
            destination = output / mode
            argv = [sys.executable, "-m", "quantfit.cli", "cold-run", "--baseline", "b.gguf",
                    "--quant", "q.gguf", "--out", str(destination), "--timeout-seconds",
                    "1" if mode == "timeout" else "10", "--json"]
            done = subprocess.run(argv, capture_output=True, text=True, check=False)
            payload = json.loads(done.stdout)
            (output / f"{mode}-cli.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            expected = 3 if mode == "disagreement" else 2 if mode in {
                "operational", "timeout", "different-binary", "different-threads", "quantized-baseline"
            } else 0
            assert done.returncode == expected, (mode, done.returncode)
            assert payload["exit_code"] == expected
            result = payload["result"]
            assert len(result["runs"]) == 3
            assert len({run["pid"] for run in result["runs"]}) == 3
            assert all(r["cleanup"]["direct_child_reaped"] and r["cleanup"]["no_live_group_members_observed"]
                       for r in result["runs"])
            assert result["scientific_go"] is False and result["independent_execution_verified"] is False
            cases.append({"case": mode, "argv": argv, "actual_exit": done.returncode,
                          "native_exits": [r["native_exit_code"] for r in result["runs"]],
                          "status": result["status"], "t0_protocol_pass": result["t0"]["protocol_pass"] if result["t0"] else None,
                          "fresh_pid_count": len({r["pid"] for r in result["runs"]}),
                          "raw_stdout_from_children_retained": False, "shim_removed": True})
    proof = {
        "kind": "synthetic functional actual POSIX process/session/CLI acceptance, not model execution",
        "source_head": args.source_head,
        "source_head_observation": "supplied by Windows git rev-parse HEAD; WSL did not read worktree Git metadata",
        "source_hashes": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in (
            "quantfit/cold_run.py", "quantfit/safety/gguf_arm.py", "quantfit/safety/verify.py", "quantfit/cli.py",
            "tests/test_cold_run.py", "tools/ci_installed.py")},
        "python": platform.python_version(), "pytest": pytest.__version__, "platform": platform.platform(),
        "psutil": __import__("psutil").__version__, "cases": cases,
        "limitations": ["No model, Hub download or llama-server executable ran.",
                        "Arm bytes/revisions/statistics are fixture declarations, not authenticated observations.",
                        "Direct children were waited/reaped. Grandchild reaping is not established.",
                        "No human adjudication, sensitivity, GPU, crosshardware or independent reproduction claim.",
                        "Hosted installed model/T0 campaign remains pending."],
    }
    (output / "functional-proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"actual_cases": len(cases), "exit_codes": [c["actual_exit"] for c in cases]}))


if __name__ == "__main__":
    main()
