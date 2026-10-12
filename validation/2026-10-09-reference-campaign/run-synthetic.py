"""Actual aggregate/T0 assessment of explicit edited historical fixtures; no models."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tests"))
from test_reference_campaign import assess, reports  # noqa: E402

head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
cases = {}
for name, settings in (("null", {}), ("unconfirmed-flags", {"flips": 1}), ("axis-limited", {"unsafe": 0})):
    folder = OUT / "synthetic" / name
    folder.mkdir(parents=True)
    paths = reports(folder, **settings)
    value = assess(paths)
    (folder / "assessment.json").write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())
    cases[name] = {"native_exits_from_synthetic_counts": value["native_exits"],
                   "t0_protocol_pass": value["t0"]["protocol_pass"],
                   "full_report_repeatability": value["full_report_repeatability"]["pass"],
                   "eligible_axes_before_publication": value["eligible_axes_before_publication"],
                   "registry_admission": value["registry_admission"], "reference_registered": False}
record = {"source_head_observed": head, "scope": "Actual offline analysis over edited historical synthetic aggregates",
          "inputs": "tests/test_reference_campaign.py:reports; edits hardware, CPU controls and drift. No actual new native run.",
          "cases": cases, "native_requests": 0, "models_loaded": 0, "human_adjudication": False,
          "scientific_go": False, "human_labels_authenticated": False,
          "limitations": ["Fixture identity/counts/engine/hardware are declared, not measured on current models.",
                          "Successful T0 and pre-publication eligibility do not authenticate independent execution or public bytes."]}
(OUT / "synthetic-run.json").write_bytes((json.dumps(record, indent=2, sort_keys=True) + "\n").encode())
print(json.dumps({"source": head, "cases": cases, "models_loaded": 0}))
