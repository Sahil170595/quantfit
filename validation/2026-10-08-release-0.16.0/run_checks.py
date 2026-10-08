"""Record local candidate checks without model downloads or captures."""

import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(__file__).resolve().parents[2]
output = Path(__file__).resolve().parent
scripts = root / "tools/ci/.venv/Scripts"
commands = [
    [str(scripts / "ruff.exe"), "check", "quantfit", "tests", "tools"],
    [
        str(scripts / "ruff.exe"),
        "format",
        "--check",
        "quantfit",
        "tests",
        *[str(p.relative_to(root)) for p in sorted((root / "tools").glob("ci_*.py"))],
        "tools/ci_gate_fixture",
    ],
    [str(scripts / "mypy.exe"), "--strict", "quantfit/spec.py", "quantfit/engines/base.py"],
    [str(scripts / "quantfit.exe"), "audit"],
    [
        sys.executable,
        "-m",
        "pytest",
        "tests",
        "-q",
        "--ignore=tests/test_numerical_properties.py",
        f"--junitxml={output / 'unit.xml'}",
    ],
]
results = []
for command in commands:
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    results.append(
        {"command": command, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    )
    print(f"{Path(command[0]).name} {command[1]}: exit {completed.returncode}", flush=True)
tree = ET.parse(output / "unit.xml")
cases = tree.findall(".//testcase")
summary = {
    "tests": len(cases),
    "skipped": sum(c.find("skipped") is not None for c in cases),
    "failures": sum(c.find("failure") is not None for c in cases),
    "errors": sum(c.find("error") is not None for c in cases),
}
record = {
    "python": sys.version,
    "platform": platform.platform(),
    "commands": results,
    "junit_independent_count": summary,
}
(output / "checks.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary))
raise SystemExit(any(r["exit_code"] for r in results))
