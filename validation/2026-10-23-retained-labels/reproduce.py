"""Run the native offline consumer; private fictional inputs are temporary only."""

import argparse
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, required=True, help="new aggregate JSON output")
args = parser.parse_args()
checkout = Path(__file__).resolve().parents[2]
subprocess.run([sys.executable, str(checkout / "tools/ci_retained_labels.py"), "--checkout", str(checkout), "--out", str(args.out)], check=True)
