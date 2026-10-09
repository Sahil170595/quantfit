"""Actual offline CLI/portable consumers and synthetic legacy-contract equivalence."""

import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def write(path, value):
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def command(args, expected):
    proc = subprocess.run([sys.executable, "-m", "quantfit.cli", *args, "--json"], cwd=ROOT,
                          capture_output=True, text=True, check=False)
    assert proc.returncode == expected, proc.stdout + proc.stderr
    envelope = json.loads(proc.stdout)
    return {"argv": [sys.executable, "-m", "quantfit.cli", *args, "--json"],
            "exit_code": proc.returncode, "result": envelope["result"]}


def main():
    invocations = []
    phi4 = ROOT / "validation/2026-10-09-phi4-public-candidate/producer/run-1/report.json"
    synthetic = ROOT / "validation/2026-10-08-calibration-aware-outputs"
    for label, source, calibration, expected in (
        ("phi4", phi4, None, 0),
        ("bound", synthetic / "drift.json", synthetic / "calibration.json", 5),
    ):
        case = OUT / label
        case.mkdir(exist_ok=True)
        raw = source.read_bytes()
        copied, gate, junit = case / "report.json", case / "gate.json", case / "gate.xml"
        args = ["gate", "--from-report", str(source), "--tier", "smoke", "--report", str(copied),
                "--out", str(gate), "--junit", str(junit)]
        if calibration:
            args += ["--calibration-report", str(calibration)]
            (case / "calibration.json").write_bytes(calibration.read_bytes())
        invocations.append(command(args, expected))
        assert source.read_bytes() == copied.read_bytes() == raw
        decision = invocations[-1]["result"]
        assert decision["source_evidence"]["report_sha256"] == hashlib.sha256(raw).hexdigest()
        if label == "phi4":
            assert decision["ungated_axis_regressed"] and decision["over_refusal"]["flips"] == 2
            assert decision["drift"]["refusal_robustness"]["harmful_compliance_regressions"] == 0
        else:
            assert decision["drift"] is None and decision["eps"]["actual_run_matched"] is True
            assert decision["eps"]["assumptions_verified"] is decision["eps"]["measured"] is False
        bundle = case / "created-bundle"
        args = ["bundle", "create", "--report", str(copied), "--gate", str(gate), "--out", str(bundle)]
        if calibration:
            args += ["--calibration-report", str(case / "calibration.json")]
        invocations.append(command(args, 0))
        relocated = case / "relocated-bundle"
        bundle.rename(relocated)
        invocations.append(command(["bundle", "verify", "--bundle", str(relocated)], 0))
        assert invocations[-1]["result"]["integrity_verified"] is True
    # Execute the actual base implementation in memory, with only its native
    # measurement call replaced by actual tabulation objects (explicitly synthetic).
    old_raw = subprocess.check_output(["git", "show", "95c8e5f:quantfit/gate.py"], cwd=ROOT)
    old = types.ModuleType("quantfit_previous_gate")
    sys.modules[old.__name__] = old
    exec(compile(old_raw, "95c8e5f:quantfit/gate.py", "exec"), old.__dict__)
    from quantfit.gate import run_gate
    from quantfit.safety.verify import SafetyDrift

    legacy = []
    for risk, flips, epsilon in ((12, 0, None), (12, 1, None), (0, 0, None), (1, 0, None), (12, 0, 0.02)):
        drift = SafetyDrift(n=40, unsafe_n=12, unsafe_baseline_refused=risk,
                            unsafe_quant_refused=risk-flips, harmful_compliance_regressions=flips,
                            safe_n=28, safe_baseline_refused=0, safe_quant_refused=2, overrefusal_regressions=2,
                            by_zone={"clear_unsafe":{"n":12,"baseline_refused":risk,"quant_refused":risk-flips},
                                     "clear_safe":{"n":28,"baseline_refused":0,"quant_refused":2}})
        options = {"tier": "smoke", "eps_upper": epsilon, "eps_source": None if epsilon is None else "synthetic operator assumption"}
        with patch("quantfit.safety.verify.verify_safety", return_value=drift):
            before, after = old.run_gate("base", "quant", **options), run_gate("base", "quant", **options)
        before.pop("created_utc")
        after.pop("created_utc")
        assert before == after
        legacy.append({"at_risk":risk, "flagged_flips":flips, "operator_upper":epsilon,
                       "exit_code":after["exit_code"], "all_other_fields_exact":True})
    write(OUT / "functional.json", {"source_head_observed":SOURCE,
          "base_gate_blob_sha256":hashlib.sha256(old_raw).hexdigest(), "invocations":invocations,
          "legacy_comparison_ignored_fields":["created_utc"], "synthetic_legacy_cases":legacy,
          "limits":["Offline source checkout execution, not installed wheel or hosted qualification.",
                    "Phi4 source is a preserved earlier measurement, not a new model run.",
                    "Calibration and legacy cases are synthetic; no human label authentication, sensitivity or scientific GO."]})
    print("6 actual offline CLI commands; two relocated bundles; five exact synthetic legacy comparisons")


if __name__ == "__main__":
    main()
