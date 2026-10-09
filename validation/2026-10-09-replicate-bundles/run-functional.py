"""Actual offline commands; historical aggregates and a labelled synthetic disagreement."""

import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path

from quantfit.reproduce import within_hardware_identical
from quantfit.safety.verify import SafetyDrift

ROOT = Path(__file__).resolve().parents[2]
RECORD = Path(__file__).resolve().parent
SOURCE = ROOT / "validation/2026-10-09-phi4-public-candidate/producer"
BASE = "ef03db2ebf02eef6f356b3ccb66b9e1d08a801fd"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    old_raw = subprocess.check_output(["git", "show", f"{BASE}:quantfit/reproduce.py"], cwd=ROOT)
    old = types.ModuleType("quantfit._replay_original_reproduce")
    sys.modules[old.__name__] = old
    exec(compile(old_raw, "original-ef03-reproduce.py", "exec"), old.__dict__)
    commands, cases = [], []
    for name in ("historical-phi4", "synthetic-disagreement"):
        parent = RECORD / name
        parent.mkdir()
        inputs = parent / "disposable-producer"
        inputs.mkdir()
        reports = [inputs / f"run-{i}.json" for i in range(1, 4)]
        held = [(SOURCE / f"run-{i}/report.json").read_bytes() for i in range(1, 4)]
        synthetic = name.startswith("synthetic")
        if synthetic:
            data = json.loads(held[2])
            data["drift"] = SafetyDrift(
                n=40, unsafe_n=12, unsafe_baseline_refused=12, unsafe_quant_refused=12,
                harmful_compliance_regressions=0, safe_n=28, safe_baseline_refused=8,
                safe_quant_refused=9, overrefusal_regressions=1, by_zone=data["drift"]["by_zone"],
            ).to_dict()
            held[2] = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
        for path, raw in zip(reports, held, strict=True):
            path.write_bytes(raw)
        native = within_hardware_identical(reports)
        assert native == old.within_hardware_identical(reports)
        t0 = inputs / "t0.json"
        held_t0 = ((json.dumps(native, indent=2) + "\n").encode() if synthetic
                   else (SOURCE / "native-t0.json").read_bytes())
        t0.write_bytes(held_t0)
        bundle = parent / "bundle"
        create = [sys.executable, "-m", "quantfit.cli", "bundle", "replay-create", "--reports", *map(str, reports),
                  "--t0", str(t0), "--out", str(bundle), "--json"]
        for phase, argv in (("create", create),):
            done = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
            assert done.returncode == 0, done.stdout + done.stderr
            result = json.loads(done.stdout)["result"]
            commands.append({"argv": argv, "exit_code": done.returncode, "phase": phase,
                             "integrity_verified": result["integrity_verified"],
                             "protocol_pass": result["original_t0"]["protocol_pass"]})
        for path in [*reports, t0]:
            path.unlink()
        inputs.rmdir()
        relocated = parent / "relocated"
        bundle.rename(relocated)
        argv = [sys.executable, "-m", "quantfit.cli", "bundle", "replay-verify", "--bundle", str(relocated), "--json"]
        done = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
        assert done.returncode == 0, done.stdout + done.stderr
        result = json.loads(done.stdout)["result"]
        assert result["original_t0"]["protocol_pass"] is (not synthetic)
        assert result["receiving_t0"]["protocol_pass"] is (not synthetic)
        assert result["scientific_claims_verified"] is result["producer_locations_verified"] is False
        assert (relocated / "t0.json").read_bytes() == held_t0
        for i, raw in enumerate(held, 1):
            assert (relocated / f"report-{i}.json").read_bytes() == raw
        (parent / "receiving-check.json").write_bytes((json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
        commands.append({"argv": argv, "exit_code": done.returncode, "phase": "verify",
                         "integrity_verified": result["integrity_verified"],
                         "protocol_pass": result["receiving_t0"]["protocol_pass"]})
        cases.append({"case": name, "synthetic": synthetic, "producer_copies_removed": True,
                      "original_t0_sha256": sha(held_t0), "report_sha256": [sha(raw) for raw in held],
                      "original_bytes_unchanged": True, "native_old_dictionary_equal": True,
                      "t0_protocol_pass": not synthetic})
    (RECORD / "functional.json").write_bytes((json.dumps({
        "source_head_observed": head, "base_native_head": BASE, "base_native_blob_sha256": sha(old_raw),
        "cases": cases, "invocations": commands,
        "scope": "Actual source CLI only, no new inference; prior Phi4 measurement and synthetic disagreement.",
    }, indent=2, sort_keys=True) + "\n").encode())
    print("4 actual offline commands; two relocated original-byte handoffs; two exact legacy native T0 comparisons")


if __name__ == "__main__":
    main()
