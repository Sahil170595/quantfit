"""Run fictional paired acceptance with private fixture material in an owned tempdir."""

import argparse
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, required=True, help="new aggregate JSON output")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
subprocess.run(
    [sys.executable, str(root / "tools/ci_calibration_paired.py"), "--checkout", str(root), "--out", str(args.out)],
    check=True,
)
