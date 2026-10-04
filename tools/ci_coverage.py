"""Enforce measured branch-coverage floors on scientific decision modules."""

import json
import sys
from pathlib import Path

# Baselines are recorded in validation/2026-10-04-hosted-ci/README.md.
FLOORS = {"quantfit/safety/mde.py": 95, "quantfit/gate.py": 90, "quantfit/safety/report.py": 90}

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
files = {name.replace("\\", "/"): value for name, value in data["files"].items()}
failed = False
for file, floor in FLOORS.items():
    summary = files[file]["summary"]
    if not summary.get("num_branches"):
        raise SystemExit(f"branch measurement absent for {file}")
    percentage = 100 * summary["covered_branches"] / summary["num_branches"]
    print(f"{file}: branch coverage {percentage:.2f}% (floor {floor}%)")
    failed |= percentage < floor
total = data["totals"]
for key, floor in (("percent_covered", 88), ("percent_branches_covered", 85)):
    print(f"total {key}: {total[key]:.2f}% (floor {floor}%)")
    failed |= total[key] < floor
raise SystemExit(int(failed))
