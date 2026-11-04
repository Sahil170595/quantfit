"""Offline screen-resolution consumers; synthetic calibration never authenticates labels."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

AXES = {"refusal_robustness": "harmful_compliance_regressions", "over_refusal": "overrefusal_regressions"}


def binding(raw: bytes) -> dict:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def original_inputs(checkout: Path) -> tuple[bytes, dict[str, bytes]]:
    source = checkout / "validation/2026-10-18-screen-bundle/inputs"
    manifest = (source / "targets.json").read_bytes()
    reports = {
        target["name"]: (source / "reports" / f"{target['name']}.json").read_bytes()
        for target in json.loads(manifest)["targets"]
    }
    return manifest, reports


def calibration_bytes(report_raw: bytes) -> bytes:
    """Use native calibration primitives on manufactured aggregate labels, never human evidence."""
    from quantfit.resolution import parse_report_bytes
    from quantfit.safety.calibrate import _arm_block
    from quantfit.safety.calibration_binding import (
        identity_fingerprint,
        load_bound_calibration_bytes,
        measurement_identity,
    )

    report = parse_report_bytes(report_raw)
    n = report.probe_dataset["n_probes"]
    blocks = {
        arm: _arm_block(
            {
                "n": n,
                "n_unusable": 0,
                "human_refusals": refusals,
                "human_compliances": n - refusals,
                "judge_refusal_human_compliance": 0,
                "judge_compliance_human_refusal": 0,
            }
        )
        for arm, refusals in (("baseline", n // 2), ("quantized", n // 4))
    }
    identity = measurement_identity(report)
    payload = {
        "calibration_schema": 2,
        "quantfit_version": "synthetic-screen-resolution-calibration",
        "created_utc": "2026-10-18T00:00:00+00:00",
        "n_labeled": 2 * n,
        "n_unusable": 0,
        "unmeasured_arms": [],
        **blocks,
        "arm_epsilon_delta": {"delta": 0.0, "note": "Synthetic zero errors; no label study."},
        "label": "SYNTHETIC manufactured aggregate labels; no human evidence or measured judge error",
        "binding": {"identity": identity, "fingerprint": identity_fingerprint(identity)},
        "source": {
            key: hashlib.sha256(f"fictional source:{key}".encode()).hexdigest()
            for key in ("capture_sha256", "key_sha256", "sheet_sha256")
        },
    }
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    load_bound_calibration_bytes(raw, report=report)
    return raw


def stage(
    root: Path, manifest: bytes, reports: dict[str, bytes], calibrations: dict[str, bytes]
) -> tuple[Path, Path, Path]:
    root.mkdir(parents=True)
    target, native, bound = root / "targets.json", root / "reports", root / "calibrations"
    target.write_bytes(manifest)
    native.mkdir()
    bound.mkdir()
    for name, raw in reports.items():
        (native / f"{name}.json").write_bytes(raw)
    for name, raw in calibrations.items():
        (bound / f"{name}.json").write_bytes(raw)
    return target, native, bound


def invoke(
    targets: Path,
    reports: Path,
    calibrations: Path | None = None,
    *,
    out: Path | None = None,
    junit: Path | None = None,
) -> tuple[dict, str]:
    from quantfit.cli import main

    argv = ["screen-summary", "--targets", str(targets), "--reports-dir", str(reports), "--json"]
    if calibrations is not None:
        argv += ["--calibrations-dir", str(calibrations)]
    if out is not None:
        argv += ["--out", str(out)]
    if junit is not None:
        argv += ["--junit", str(junit)]
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    document = json.loads(stdout.getvalue())
    assert document["command"] == "screen-summary" and document["exit_code"] == code
    return document, stderr.getvalue()


def native_projection(summary: dict) -> dict:
    return {key: value for key, value in summary.items() if key not in {"created_utc", "conditional_resolution"}}


def expected_native(manifest: bytes, reports: dict[str, bytes]) -> dict:
    """Primitive inventory and native-axis counts; no resolution math is copied."""
    names = [row["name"] for row in json.loads(manifest)["targets"]]
    native = [json.loads(raw)["drift"] for raw in reports.values()]
    flagged = sum(any(row[axis][key] > 0 for axis, key in AXES.items()) for row in native)
    unmeasured = sum(any(row[axis]["at_risk"] == 0 for axis in AXES) for row in native)
    missing = len(names) - len(reports)
    return {
        "exit_code": 3 if flagged else 4 if missing or unmeasured else 0,
        "n_targets": len(names),
        "n_present": len(reports),
        "n_missing": missing,
        "n_flagged_targets": flagged,
        "n_unmeasured_targets": unmeasured,
    }


def junit_counts(path: Path) -> dict:
    cases = list(ET.fromstring(path.read_bytes()).iter("testcase"))
    return {
        "tests": len(cases),
        "failures": sum(case.find("failure") is not None for case in cases),
        "skipped": sum(case.find("skipped") is not None for case in cases),
        "errors": sum(case.find("error") is not None for case in cases),
    }


def check(
    document: dict, default: dict, manifest: bytes, reports: dict[str, bytes], calibrations: dict[str, bytes]
) -> dict:
    from quantfit.resolution import analyze_resolution_bytes

    expected = expected_native(manifest, reports)
    result = document["result"]
    assert document["exit_code"] == default["exit_code"] == expected["exit_code"]
    assert native_projection(result) == native_projection(default["result"])
    assert "conditional_resolution" not in default["result"]
    assert result["control_evidence_verified"] is result["human_labels_authenticated"] is False
    assert result["sensitivity_established"] is result["scientific_go"] is False
    block = result["conditional_resolution"]
    assert block["screen_resolution_schema_version"] == 1 and block["kind"] == "quantfit.screen-resolution"
    assert block["assumptions_verified"] is block["human_labels_authenticated"] is block["scientific_go"] is False
    assert block["source_authentication"] == "unverified" and block["scope"]
    assert block["limits"] == {
        "calibration_bytes": 2097152,
        "total_calibration_bytes": 67108864,
        "max_targets": 256,
        "max_analysis_probes": 4096,
        "max_analysis_work_units": 16777216,
    }
    targets = json.loads(manifest)["targets"]
    counts = dict.fromkeys(
        ("n_analyzed", "n_calibration_missing", "n_pending_report_missing", "n_report_and_calibration_missing"), 0
    )
    assert [row["name"] for row in block["rows"]] == [target["name"] for target in targets]
    work = 0
    for row, target in zip(block["rows"], targets, strict=True):
        name = target["name"]
        report, calibration = reports.get(name), calibrations.get(name)
        status = (
            "analyzed"
            if report is not None and calibration is not None
            else "calibration_missing"
            if report is not None
            else "pending_report_missing"
            if calibration is not None
            else "report_and_calibration_missing"
        )
        counts[f"n_{status}"] += 1
        assert row["status"] == status
        assert row["native_report_sha256"] == (binding(report)["sha256"] if report is not None else None)
        assert row["calibration"] == {
            "member": f"{name}.json",
            "status": "present" if calibration is not None else "missing",
            **(binding(calibration) if calibration is not None else {"sha256": None, "size_bytes": None}),
        }
        assert row["binding_fingerprint"] == (
            json.loads(calibration)["binding"]["fingerprint"] if calibration is not None else None
        )
        if status == "analyzed":
            _, analysis = analyze_resolution_bytes(report, calibration)
            assert native_projection(row["analysis"]) == native_projection(analysis)
            assert row["analysis"]["human_confirmation_verified"] is row["analysis"]["assumptions_verified"] is False
            work += json.loads(report)["probe_dataset"]["n_probes"] ** 2
        else:
            assert row["analysis"] is None
    assert block["coverage"] == {
        "n_targets": len(targets),
        **counts,
        "complete": counts["n_analyzed"] == len(targets),
    }
    assert block["analysis_work_units"] == work
    return {
        **expected,
        **counts,
        "analysis_work_units": work,
        "native_reports": [{"name": name, **binding(raw)} for name, raw in reports.items()],
        "calibrations": [{"name": name, **binding(raw)} for name, raw in calibrations.items()],
        "assumptions_verified": False,
        "scientific_go": False,
    }


def accept_cpu(report_path: Path, out_root: Path) -> dict:
    """Annotate one existing real CPU receipt with an EMPTY calibration directory."""
    original = report_path.read_bytes()
    native = json.loads(original)
    assert native["env"]["device"] == "cpu" and native["decode"]["max_new_tokens"] == 64
    target = {
        "name": "existing-cold-native",
        "stratum": "gguf",
        "baseline": native["baseline"]["model"],
        "quant": native["quantized"]["model"],
    }
    raw_manifest = (
        json.dumps(
            {"schema_version": 1, "name": "existing native CPU screen resolution", "targets": [target]}, indent=2
        )
        + "\n"
    ).encode()
    manifest, reports, calibrations = stage(out_root, raw_manifest, {target["name"]: original}, {})
    with contextlib.ExitStack() as stack:
        traps = [
            stack.enter_context(
                patch(name, side_effect=AssertionError("resolution annotation attempted inference or assets"))
            )
            for name in (
                "quantfit.safety.verify.verify_safety",
                "quantfit.safety.gguf_arm.resolve_pair",
                "huggingface_hub.hf_hub_download",
            )
        ]
        before, after = out_root / "native.xml", out_root / "annotated.xml"
        default, _ = invoke(manifest, reports, junit=before)
        annotated, _ = invoke(manifest, reports, calibrations, out=out_root / "annotated.json", junit=after)
        compact = check(annotated, default, raw_manifest, {target["name"]: original}, {})
        assert before.read_bytes() == after.read_bytes()
        assert compact["n_calibration_missing"] == 1 and compact["analysis_work_units"] == 0
        for trap in traps:
            trap.assert_not_called()
    assert report_path.read_bytes() == original
    return {
        "kind": "existing native CPU receipt; empty calibration annotation",
        "additional_native_calls": 0,
        **compact,
        "junit": junit_counts(after),
    }
