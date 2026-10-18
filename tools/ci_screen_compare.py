"""Actual offline screen-comparison consumers; native counts are the expected-value oracle."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

AXES = ("refusal_robustness", "over_refusal")
FLIPS = {"refusal_robustness": "harmful_compliance_regressions", "over_refusal": "overrefusal_regressions"}


def binding(raw: bytes) -> dict:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def original_inputs(checkout: Path) -> tuple[bytes, dict[str, bytes]]:
    root = checkout / "validation/2026-10-18-screen-bundle/inputs"
    manifest = (root / "targets.json").read_bytes()
    reports = {
        t["name"]: (root / "reports" / f"{t['name']}.json").read_bytes() for t in json.loads(manifest)["targets"]
    }
    return manifest, reports


def observation(raw: bytes, *, dangerous: int = 0, over: int = 0, measured: bool = True) -> bytes:
    """Fictional changed observation; preserve all declared arm identities and native arithmetic."""
    from quantfit.safety.verify import SafetyDrift

    report = copy.deepcopy(json.loads(raw))
    unsafe, safe_base = (12, 0) if measured else (0, 28)
    report["drift"] = SafetyDrift(
        40,
        12,
        unsafe,
        unsafe - dangerous,
        dangerous,
        28,
        safe_base,
        safe_base + over,
        over,
        {
            "clear_unsafe": {"n": 12, "baseline_refused": unsafe, "quant_refused": unsafe - dangerous},
            "clear_safe": {
                "n": 12,
                "baseline_refused": 12 if safe_base else 0,
                "quant_refused": 12 if safe_base else over,
            },
            "borderline": {
                "n": 16,
                "baseline_refused": 16 if safe_base else 0,
                "quant_refused": 16 if safe_base else 0,
            },
        },
    ).to_dict()
    report["quantfit_version"] = "synthetic-screen-comparison-observation"
    return (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()


def make_bundle(root: Path, manifest: bytes, reports: dict[str, bytes]) -> Path:
    from quantfit.screen_bundle import create_screen_bundle

    root.mkdir(parents=True)
    producer = root / "producer"
    producer.mkdir()
    targets = producer / "targets.json"
    targets.write_bytes(manifest)
    directory = producer / "reports"
    directory.mkdir()
    for name, raw in reports.items():
        (directory / f"{name}.json").write_bytes(raw)
    bundle = root / "bundle"
    result = create_screen_bundle(str(targets), str(directory), str(bundle))
    assert result["status"] == "verified_content" and result["exit_code"] == 0
    return bundle


def invoke(reference: Path, candidate: Path, *, out: Path | None = None, junit: Path | None = None) -> tuple[dict, str]:
    from quantfit.cli import main

    argv = ["screen-compare", "--reference-bundle", str(reference), "--candidate-bundle", str(candidate), "--json"]
    if out is not None:
        argv += ["--out", str(out)]
    if junit is not None:
        argv += ["--junit", str(junit)]
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    document = json.loads(stdout.getvalue())
    assert document["command"] == "screen-compare" and document["exit_code"] == code
    return document, stderr.getvalue()


def native_axis(raw: bytes | None, axis: str) -> dict:
    if raw is None:
        return {
            "present": False,
            "measured": False,
            "flagged": False,
            "flips": None,
            "at_risk": None,
            "flip_rate_wilson95": None,
            "mde_at_80pct_power": None,
        }
    value = json.loads(raw)["drift"][axis]
    return {
        "present": True,
        "measured": value["at_risk"] > 0,
        "flagged": value[FLIPS[axis]] > 0,
        "flips": value[FLIPS[axis]],
        "at_risk": value["at_risk"],
        "flip_rate_wilson95": value["flip_rate_wilson95"],
        "mde_at_80pct_power": value["mde_at_80pct_power"],
    }


def check(
    document: dict,
    reference: Path,
    candidate: Path,
    manifest: bytes,
    reports: dict[str, dict[str, bytes]],
    *,
    code: int,
) -> dict:
    assert document["exit_code"] == code
    result = document["result"]
    assert result["screen_comparison_schema_version"] == 1 and result["kind"] == "quantfit.screen-comparison"
    assert result["exit_code"] == code and result["source_authentication"] == "unverified"
    for key in (
        "independent_execution_verified",
        "weights_authenticated",
        "physical_hosts_authenticated",
        "human_labels_authenticated",
        "sensitivity_established",
        "scientific_go",
    ):
        assert result[key] is False
    assert result["limits"] == {
        "bundle_transport_bytes": 67108864,
        "combined_logical_transport_bytes": 134217728,
        "max_targets": 256,
    }
    for side, bundle in (("reference", reference), ("candidate", candidate)):
        total = sum(p.stat().st_size for p in bundle.rglob("*") if p.is_file())
        assert result["inputs"][side] == {
            "bundle_manifest_sha256": binding((bundle / "manifest.json").read_bytes())["sha256"],
            "targets_sha256": binding(manifest)["sha256"],
            "transport_bytes": total,
        }
        summary = result["screens"][side]
        assert summary["manifest"]["sha256"] == binding(manifest)["sha256"] and summary["manifest"][
            "size_bytes"
        ] == len(manifest)
        assert (
            summary["control_evidence_verified"]
            is summary["independent_execution_verified"]
            is summary["scientific_go"]
            is False
        )
    targets = json.loads(manifest)["targets"]
    assert [row["name"] for row in result["rows"]] == [target["name"] for target in targets]
    counts = {"n_targets": len(targets), "n_matched_axes": 0, "n_identical_report_pairs": 0}
    for side in ("reference", "candidate"):
        counts[f"n_flagged_axes_{side}"] = 0
        counts[f"n_unmeasured_axes_{side}"] = 0
        counts[f"n_missing_reports_{side}"] = len(targets) - len(reports[side])
    for row, target in zip(result["rows"], targets, strict=True):
        name = row["name"]
        assert row["stratum"] == target["stratum"] and row["identity"]["same_weights_established"] is False
        left, right = reports["reference"].get(name), reports["candidate"].get(name)
        identical = left == right if left is not None and right is not None else None
        assert row["identical_report_bytes"] is identical
        counts["n_identical_report_pairs"] += identical is True
        for side in ("reference", "candidate"):
            raw = reports[side].get(name)
            entry = row["bindings"][side]
            assert {key: entry[key] for key in ("sha256", "size_bytes")} == (
                binding(raw) if raw is not None else {"sha256": None, "size_bytes": None}
            )
        for axis in AXES:
            value = row["axes"][axis]
            for side in ("reference", "candidate"):
                expected = native_axis(reports[side].get(name), axis)
                assert value[side] == expected
                counts[f"n_flagged_axes_{side}"] += expected["flagged"]
                counts[f"n_unmeasured_axes_{side}"] += expected["present"] and not expected["measured"]
            if value["status"] == "matched":
                before, after = value["reference"]["flagged"], value["candidate"]["flagged"]
                transition = (
                    ("persisting_flag" if before else "newly_flagged")
                    if after
                    else ("apparent_clearance" if before else "no_flag")
                )
                assert (
                    value["transition"] == transition
                    and value["comparison_basis"] == "declared_target_and_compatible_protocol"
                )
                counts["n_matched_axes"] += 1
            else:
                assert value["transition"] is value["comparison_basis"] is None
    return {
        "exit_code": code,
        **counts,
        "inputs": result["inputs"],
        "scientific_go": False,
        "independent_execution_verified": False,
    }


def check_junit(path: Path, document: dict) -> dict:
    result = document["result"]
    cases = {case.get("name"): case for case in ET.fromstring(path.read_bytes()).iter("testcase")}
    assert len(cases) == 2 * len(result["rows"]) + 1
    failures = skipped = 0
    for row in result["rows"]:
        for axis in AXES:
            value = row["axes"][axis]
            case = cases[f"{row['name']}.{axis}"]
            flagged = value["reference"]["flagged"] or value["candidate"]["flagged"]
            unavailable = value["status"] != "matched"
            assert (case.find("failure") is not None) == flagged
            assert (case.find("skipped") is not None) == (unavailable and not flagged)
            assert case.find("error") is None
            failures += flagged
            skipped += unavailable and not flagged
    overall = cases["overall"]
    assert (overall.find("failure") is not None) == (result["exit_code"] == 3)
    assert (overall.find("skipped") is not None) == (result["exit_code"] == 4)
    return {
        "tests": len(cases),
        "failures": failures + (result["exit_code"] == 3),
        "skipped": skipped + (result["exit_code"] == 4),
        "errors": 0,
    }


def accept_cpu(bundle_path: Path, report_path: Path, out_root: Path) -> dict:
    """Compare the existing relocated CPU bundle to itself; no new native execution."""
    original = report_path.read_bytes()
    native = json.loads(original)
    manifest = (bundle_path / "targets.json").read_bytes()
    target = json.loads(manifest)["targets"][0]
    assert len(json.loads(manifest)["targets"]) == 1 and native["env"]["device"] == "cpu"
    reports = {target["name"]: original}
    code = (
        3
        if any(native_axis(original, axis)["flagged"] for axis in AXES)
        else 4
        if any(not native_axis(original, axis)["measured"] for axis in AXES)
        else 0
    )
    out_root.mkdir(parents=True)
    out, junit = out_root / "comparison.json", out_root / "comparison.xml"
    with contextlib.ExitStack() as stack:
        traps = [
            stack.enter_context(patch(name, side_effect=AssertionError("comparison attempted inference or assets")))
            for name in (
                "quantfit.safety.verify.verify_safety",
                "quantfit.safety.gguf_arm.resolve_pair",
                "huggingface_hub.hf_hub_download",
            )
        ]
        document, _ = invoke(bundle_path, bundle_path, out=out, junit=junit)
        compact = check(
            document, bundle_path, bundle_path, manifest, {"reference": reports, "candidate": reports}, code=code
        )
        assert json.loads(out.read_bytes()) == document["result"]
        xml = check_junit(junit, document)
        for trap in traps:
            trap.assert_not_called()
    assert report_path.read_bytes() == original
    return {
        "kind": "existing native CPU bundle compared to itself",
        "additional_native_calls": 0,
        **compact,
        "junit": xml,
    }
