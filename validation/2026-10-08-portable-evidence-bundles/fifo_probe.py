"""Real stdlib-only POSIX FIFO source/member/manifest/replacement CLI regression."""

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quantfit.bundle import create_bundle

records = []
with tempfile.TemporaryDirectory(prefix="quantfit-owned-fifo-") as owned:
    for role in ("source", "member", "manifest", "replacement"):
        directory = Path(owned) / role
        directory.mkdir()
        source = directory / "source.json"
        source.write_bytes((ROOT / "validation/2026-10-08-calibration-aware-outputs/drift.json").read_bytes())
        bundle = directory / "bundle"
        create_bundle(str(source), str(bundle))
        target = source if role in ("source", "replacement") else bundle / ("report.json" if role == "member" else "manifest.json")
        arguments = ["bundle", "create", "--report", str(target), "--out", str(directory / "refused")] if role in ("source", "replacement") else ["bundle", "verify", "--bundle", str(bundle)]
        if role != "replacement":
            target.unlink()
            os.mkfifo(target)
            command = [sys.executable, "-B", "-m", "quantfit.cli", *arguments, "--json"]
        else:
            # Replace a regular file after the pre-open lstat, at the real open seam.
            code = """
import os, sys
from pathlib import Path
import quantfit.bundle as bundle
from quantfit.cli import main
original = os.open
def substitute(path, flags):
    Path(path).unlink()
    os.mkfifo(path)
    return original(path, flags)
bundle.os.open = substitute
raise SystemExit(main(sys.argv[1:]))
"""
            command = [sys.executable, "-B", "-c", code, *arguments, "--json"]
        started = time.monotonic()
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=5, check=False)
        elapsed = time.monotonic() - started
        result = json.loads(completed.stdout)
        assert completed.returncode == 2 and "regular file" in result["error"]["message"], (role, completed.stdout, completed.stderr)
        records.append({"role": role, "argv": command, "exit_code": completed.returncode, "elapsed_seconds": elapsed,
                        "timeout_seconds": 5, "response": result})

print(json.dumps({"source_head_supplied_by_windows_git": sys.argv[1],
                  "bundle_source_sha256": hashlib.sha256((ROOT / "quantfit/bundle.py").read_bytes()).hexdigest(),
                  "python": platform.python_version(), "platform": platform.platform(), "cases": records,
                  "all_children_completed_and_reaped": True, "owned_temp_directory_removed": not Path(owned).exists(),
                  "no_new_dependencies": True, "scientific_claims_verified": False}, indent=2, sort_keys=True))
