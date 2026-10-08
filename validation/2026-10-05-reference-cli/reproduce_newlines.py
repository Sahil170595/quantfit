"""Check raw newline bytes through an installed CLI outside its source checkout."""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent
installed = sys.argv[1]
records = []
with tempfile.TemporaryDirectory(prefix="quantfit-reference-newlines-") as name:
    sandbox = Path(name)
    for ending, label in [(b"\n", "LF"), (b"\r\n", "CRLF")]:
        original = b'{"fixture_only":true,"count":1}' + ending
        target = sandbox / "report.json"
        target.write_bytes(original)
        registry = json.loads((root / "synthetic-registry.json").read_text(encoding="utf-8"))
        registry["reports"][0]["report_sha256"] = hashlib.sha256(original).hexdigest()
        regpath = sandbox / "registry.json"
        regpath.write_text(json.dumps(registry), encoding="utf-8")
        args = [
            installed,
            "-m",
            "quantfit.cli",
            "references",
            "verify",
            "--registry",
            str(regpath),
            "--slug",
            "fixture",
            "--report",
            str(target),
            "--json",
        ]
        for match, expected in [(True, 0), (False, 3)]:
            if not match:
                target.write_bytes(original.replace(ending, b"\r\n" if ending == b"\n" else b"\n"))
            result = subprocess.run(args, cwd=sandbox, capture_output=True, text=True, check=False)
            assert result.returncode == expected, (result.stdout, result.stderr)
            actual = json.loads(result.stdout)["result"]
            assert actual["expected_sha256"] == hashlib.sha256(original).hexdigest()
            assert actual["actual_sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
            assert actual["matches"] == match and actual["publication_verified"] is False
            records.append(
                {
                    "declared_ending": label,
                    "match_expected": match,
                    "exit_code": result.returncode,
                    "expected_sha256": actual["expected_sha256"],
                    "actual_sha256": actual["actual_sha256"],
                }
            )
(root / "newline-cases.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
print("Four installed exact-byte cases passed; no publication authenticated.")
