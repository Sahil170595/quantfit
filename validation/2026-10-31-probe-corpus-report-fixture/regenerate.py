"""Record the source-preserving native report environment fixture follow-up."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

C_HEAD = "202be42594af58645ca922c5b496fb18f106fe2e"
TEST = "test_observed_whole_custom_corpus_keeps_loaded_source_and_closed_native_owners"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", required=True, type=Path)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[2]
    cases = list(ET.parse(args.junit).getroot().iter("testcase"))
    target = [c for c in cases if c.attrib["name"] == TEST]
    assert len(target) == 1 and not any(target[0].find(k) is not None for k in ("failure", "error", "skipped"))
    assert not any(c.find(k) is not None for c in cases for k in ("failure", "error"))
    prior_path = checkout / "validation/2026-10-31-probe-corpus/summary.json"
    prior = json.loads(prior_path.read_bytes())
    current = {n: hashlib.sha256((checkout / n).read_bytes()).hexdigest() for n in prior["source_hashes"]}
    changed = {n: {"B": old, "D": current[n]} for n, old in prior["source_hashes"].items() if current[n] != old}
    assert set(changed) == {"tools/ci/pyproject.toml", "tools/ci/uv.lock", "tests/test_inspect_gguf.py"}
    assert not subprocess.check_output(
        ["git", "diff", C_HEAD, "--", "quantfit", "pyproject.toml", "tools/ci"], cwd=checkout
    )
    result = {
        "candidate": "0.51.0",
        "historical_C_failed_head": C_HEAD,
        "historical_C_CI": "https://github.com/Sahil170595/quantfit/actions/runs/41225246738",
        "historical_C_unit_failures": {
            "jobs": [124607923986, 124607924010, 124607924039, 124607924041],
            "each_passed": 3650,
            "each_failed": 1,
            "each_skipped": 17,
            "missing": "torch",
        },
        "historical_C_numerical_failure": {
            "job": 124607923956,
            "passed": 3657,
            "failed": 1,
            "skipped": 14,
            "deselected": 6,
            "missing": "transformers",
        },
        "correction": "Only new software test's deterministic environment_fingerprint fixture; native report/source/server assertions retained.",
        "native_existing_pattern": "tests/test_inspect_gguf.py::test_actual_public_inspect_full_fixture_batch_closes_before_judge",
        "current_test": TEST,
        "current_test_file_sha256": hashlib.sha256((checkout / "tests/test_inspect_gguf.py").read_bytes()).hexdigest(),
        "current_selected_cases": len(cases),
        "current_passed": sum(c.find("skipped") is None for c in cases),
        "current_skipped": sum(c.find("skipped") is not None for c in cases),
        "current_JUnit_sha256": hashlib.sha256(args.junit.read_bytes()).hexdigest(),
        "fixture_counter_and_parsed_env_assertions_passed": True,
        "held_historical_B_source_hashes": len(current) - len(changed),
        "changed_historical_B_source_hashes": changed,
        "C_profile_record_held": hashlib.sha256(
            (checkout / "validation/2026-10-31-probe-corpus-unit-profile/summary.json").read_bytes()
        ).hexdigest(),
        "native_report_and_verifier_sha256": {
            n: current[n] for n in ("quantfit/safety/report.py", "quantfit/safety/verify.py")
        },
        "limits": "Synthetic environment, not physical hardware provenance. Historical B full/native remain B executions; D requires fresh hosted package/tests/browser/CodeQL.",
        "real_Hub_model_or_science_qualification": False,
    }
    Path(__file__).with_name("summary.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf8", newline="\n"
    )
    print(
        json.dumps(
            {
                "passed": result["current_passed"],
                "skipped": result["current_skipped"],
                "held_B_hashes": result["held_historical_B_source_hashes"],
                "changed_B_hashes": len(changed),
            }
        )
    )


if __name__ == "__main__":
    main()
