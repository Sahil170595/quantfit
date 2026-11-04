"""Run fictional offline receiving requirements; no model or human calibration study."""

import argparse
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, required=True, help="new aggregate record path")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
subprocess.run(
    [sys.executable, str(root / "tools/ci_screen_requirement.py"), "--checkout", str(root), "--out", str(args.out)],
    check=True,
)
