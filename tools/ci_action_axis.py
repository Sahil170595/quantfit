"""Saved-count fixtures for the real reference action; no inference or assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from xml.etree import ElementTree as ET

from ci_axis_gate import native_report


def prepare(root: Path, code: int) -> None:
    counts = {0: {"unsafe_flips": 1}, 2: {}, 3: {"safe_flips": 1}, 4: {"safe_refused": 28}, 5: {}}[code]
    root.mkdir(parents=True, exist_ok=False)
    source = root / "source.json"
    native_report(**counts).to_json(str(source))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (root / "source.sha256").write_text(digest, encoding="ascii")
    print(json.dumps({"fixture": "synthetic native counts", "expected_exit": code, "source_sha256": digest}))


def check(root: Path, code: int) -> None:
    source = root / "source.json"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == (root / "source.sha256").read_text(encoding="ascii")
    assert os.environ["ACTION_OUTCOME"] == ("success" if code == 0 else "failure")
    assert os.environ["ACTION_CODE"] == str(code)
    for key in ("ACTION_MDE", "ACTION_PROVEN", "ACTION_UNGATED"):
        assert os.environ[key] == "unknown", (key, os.environ[key])
    projected = json.loads(os.environ["ACTION_AXIS_RESULTS"])
    if code == 2:
        assert projected is None and os.environ["ACTION_VERDICT"] == "unknown"
        assert all(not (root / name).exists() for name in ("gate.json", "drift.json", "junit.xml"))
    else:
        from quantfit.bundle import create_bundle, verify_bundle

        decision = json.loads((root / "gate.json").read_bytes())
        assert decision["schema_version"] == 2 and decision["exit_code"] == code
        assert decision["verdict"] == os.environ["ACTION_VERDICT"]
        native = decision["axis_results"]["over-refusal"]
        resolution = native["resolution"]
        assert projected == {
            "over-refusal": {
                "exit_code": native["exit_code"],
                "verdict": native["verdict"],
                "observed": native["observed"],
                "threshold_pp": native["threshold"] * 100,
                "printed_mde_pp": None if resolution["printed_mde"] is None else resolution["printed_mde"] * 100,
                "resolution_status": resolution["verdict"],
                "resolution_proven": resolution["resolution_proven"],
                **{key: native[key] for key in ("n_at_risk", "flagged_flips", "detection_threshold_flips")},
            }
        }
        assert decision["source_evidence"]["report_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert decision["source_evidence"]["inference_performed"] is False
        xml = ET.parse(root / "junit.xml")
        assert len(xml.findall(".//testcase")) == 4
        assert bool(xml.findall(".//failure")) == (code != 0)
        if code == 0:
            assert decision["diagnostic_axes"]["refusal-robustness"]["flagged_flips"] == 1
        if code == 3:
            assert native["flagged_flips"] == 1 and xml.findall(".//failure[@type='NativeDetection']")
        if code == 4:
            assert native["n_at_risk"] == 0 and xml.findall(".//skipped")
            assert xml.findall(".//failure[@type='SelectedAxisUnmeasurable']")
        if code == 5:
            assert decision["drift"] is None and decision["resolution"]["stage"] == "pre_run"
            assert xml.findall(".//failure[@type='ThresholdUnresolvable']")
        bundle = root / "received"
        create_bundle(str(source), str(bundle), gate_path=str(root / "gate.json"))
        assert verify_bundle(str(bundle))["declared_results"]["gate"]["exit_code"] == code
    print(json.dumps({"saved_axis_action_exit": code, "source_held": True, "native_json_junit_checked": True}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "check"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--code", type=int, choices=(0, 2, 3, 4, 5), required=True)
    args = parser.parse_args()
    if args.operation == "prepare":
        prepare(args.root, args.code)
    else:
        check(args.root, args.code)


if __name__ == "__main__":
    main()
