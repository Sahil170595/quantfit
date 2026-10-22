"""Offline screen-bundle CLI consumers; source, installed and real CPU proof stay distinct."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch


def binding(raw: bytes) -> dict:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def committed_inputs(checkout: Path) -> tuple[bytes, dict[str, bytes]]:
    """Read the literal 0.32 synthetic originals, including their original line endings."""
    source = checkout / "validation/2026-10-18-screen-resume/inputs"
    manifest = (source / "manifest.json").read_bytes()
    reports = {
        target["name"]: (source / "reports" / f"{target['name']}.json").read_bytes()
        for target in json.loads(manifest)["targets"]
    }
    assert binding(manifest) == {
        "sha256": "60a61566f4d18c6f87619bdcf7cea4ba36e26ca64be824da4cd4e05f7e58937c",
        "size_bytes": 803,
    }
    return manifest, reports


def stage(root: Path, manifest: bytes, reports: dict[str, bytes], *, summary: bytes | None = None) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    path, directory = root / "targets.json", root / "reports"
    path.write_bytes(manifest)
    directory.mkdir()
    for name, raw in reports.items():
        (directory / f"{name}.json").write_bytes(raw)
    if summary is not None:
        (directory / "screen-summary.json").write_bytes(summary)
    return path, directory


def invoke(argv: list[str]) -> tuple[dict, str]:
    """Run actual parser, dispatch and JSON emission; never filter stdout notices."""
    from quantfit.cli import main

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(["bundle", *argv, "--json"])
    result = json.loads(stdout.getvalue())
    assert result["exit_code"] == code
    assert result["command"] == (f"bundle {argv[0]}" if code == 0 else "bundle")
    return result, stderr.getvalue()


def create(manifest: Path, reports: Path, out: Path) -> dict:
    return invoke(["screen-create", "--targets", str(manifest), "--reports-dir", str(reports), "--out", str(out)])[0]


def verify(bundle: Path) -> dict:
    return invoke(["screen-verify", "--bundle", str(bundle)])[0]


def expected_counts(manifest: bytes, reports: dict[str, bytes]) -> dict:
    """Read primitive native at-risk and flip counts, without copying receiver statistics."""
    targets = json.loads(manifest)["targets"]
    axes = {}
    for stratum in sorted({t["stratum"] for t in targets}):
        native = [
            json.loads(reports[t["name"]])["drift"] for t in targets if t["stratum"] == stratum and t["name"] in reports
        ]
        axes[stratum] = {}
        for axis, flips in (
            ("refusal_robustness", "harmful_compliance_regressions"),
            ("over_refusal", "overrefusal_regressions"),
        ):
            axes[stratum][axis] = {
                "n_measured": sum(row[axis]["at_risk"] > 0 for row in native),
                "n_regressed": sum(row[axis][flips] > 0 for row in native),
                "n_regressed_human_verified": 0,
            }
    flagged = any(a["n_regressed"] for group in axes.values() for a in group.values())
    unmeasured = any(
        row["drift"][a]["at_risk"] == 0
        for raw in reports.values()
        for row in [json.loads(raw)]
        for a in ("refusal_robustness", "over_refusal")
    )
    return {
        "exit_code": 3 if flagged else 4 if len(reports) < len(targets) or unmeasured else 0,
        "coverage": {
            "n_targets": len(targets),
            "n_present": len(reports),
            "n_missing": len(targets) - len(reports),
            "complete": len(reports) == len(targets),
        },
        "axes": axes,
    }


def check(
    document: dict, bundle: Path, manifest: bytes, reports: dict[str, bytes], *, summary: bytes | None = None
) -> dict:
    from quantfit.screen import CONDITIONALITY_LABEL, RESOLUTION_LABEL

    assert document["exit_code"] == 0
    result = document["result"]
    assert result["bundle_schema_version"] == 1
    assert result["kind"] == "quantfit.screen-bundle-verification" and result["status"] == "verified_content"
    assert (
        result["exit_code"] == 0
        and result["source_authentication"] == "unverified"
        and result["scientific_go"] is False
    )
    assert isinstance(result["scope"], str) and result["scope"]
    assert result["limits"] == {
        "transport_bytes": 64 * 1024 * 1024,
        "outer_manifest_bytes": 256 * 1024,
        "targets_bytes": 1024 * 1024,
        "report_bytes": 8 * 1024 * 1024,
        "max_targets": 256,
    }
    outer_raw = (bundle / "manifest.json").read_bytes()
    outer = json.loads(outer_raw)
    assert result["manifest_sha256"] == binding(outer_raw)["sha256"] and result["bundle_manifest"] == outer
    assert set(outer) == {"bundle_schema_version", "kind", "targets", "reports", "producer_summary"}
    assert outer["bundle_schema_version"] == 1 and outer["kind"] == "quantfit.screen-bundle"
    assert outer["targets"] == {"path": "targets.json", **binding(manifest)}
    assert (bundle / "targets.json").read_bytes() == manifest
    expected_files = {"manifest.json", "targets.json"}
    targets = json.loads(manifest)["targets"]
    assert len(outer["reports"]) == len(targets)
    for row, target in zip(outer["reports"], targets, strict=True):
        name = target["name"]
        relative = f"reports/{name}.json"
        expected = {
            "name": name,
            "path": relative,
            "status": "present" if name in reports else "missing",
            "sha256": None,
            "size_bytes": None,
        }
        if name in reports:
            expected.update(binding(reports[name]))
            assert (bundle / relative).read_bytes() == reports[name]
            expected_files.add(relative)
        assert row == expected
    producer = {
        "path": "reports/screen-summary.json",
        "status": "present" if summary is not None else "absent",
        "sha256": None,
        "size_bytes": None,
    }
    if summary is not None:
        producer.update(binding(summary))
        assert (bundle / "reports/screen-summary.json").read_bytes() == summary
        expected_files.add("reports/screen-summary.json")
    assert outer["producer_summary"] == producer
    assert (bundle / "reports").is_dir()
    actual_files = {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()}
    assert actual_files == expected_files
    total = sum((bundle / name).stat().st_size for name in actual_files)
    assert result["transport_bytes"] == total
    expected = expected_counts(manifest, reports)
    receiving = result["receiving_summary"]
    assert receiving["exit_code"] == expected["exit_code"] and receiving["coverage"] == expected["coverage"]
    assert receiving["manifest"] == {
        "name": json.loads(manifest)["name"],
        "path": "targets.json",
        **binding(manifest),
        "n_targets": len(targets),
    }
    assert receiving["reports_dir"] == "reports" and isinstance(receiving["scope"], str) and receiving["scope"]
    assert receiving["ignored_members"] == (
        [{"member": "screen-summary.json", **binding(summary)}] if summary is not None else []
    )
    assert receiving["control_evidence_verified"] is receiving["human_labels_authenticated"] is False
    assert receiving["independent_execution_verified"] is receiving["scientific_go"] is False
    for row, target in zip(receiving["report_bindings"], targets, strict=True):
        name = target["name"]
        assert row["name"] == name and row["member"] == f"{name}.json"
        assert row["status"] == ("validated" if name in reports else "missing_evidence")
        assert row["producer_quantfit_version"] == (
            json.loads(reports[name])["quantfit_version"] if name in reports else None
        )
        assert {key: row[key] for key in ("sha256", "size_bytes")} == (
            binding(reports[name]) if name in reports else {"sha256": None, "size_bytes": None}
        )
    for stratum, group in expected["axes"].items():
        for axis, counts in group.items():
            received = receiving["by_stratum"][stratum][axis]
            assert {key: received[key] for key in counts} == counts
            assert (
                received["conditionality"] == CONDITIONALITY_LABEL and received["resolution_caveat"] == RESOLUTION_LABEL
            )
    assert all(row["human_verified"] is None for row in receiving["rows"])
    return {
        "content_exit_code": 0,
        "receiving_exit_code": expected["exit_code"],
        "coverage": expected["coverage"],
        "axes": expected["axes"],
        "manifest_sha256": result["manifest_sha256"],
        "targets": binding(manifest),
        "transport_bytes": total,
        "n_native_members": len(reports),
        "n_ignored_summary_members": int(summary is not None),
        "source_authentication": "unverified",
        "scientific_go": False,
    }


def accept_cpu(report_path: Path, out_root: Path) -> dict:
    """Create, relocate and verify one already-produced cold native report offline."""
    original = report_path.read_bytes()
    native = json.loads(original)
    assert native["env"]["device"] == "cpu" and native["decode"]["max_new_tokens"] == 64
    target = {
        "name": "existing-cold-native",
        "stratum": "gguf",
        "baseline": native["baseline"]["model"],
        "quant": native["quantized"]["model"],
    }
    manifest_raw = (
        json.dumps(
            {"schema_version": 1, "name": "existing native CPU screen bundle", "targets": [target]},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    out_root.mkdir(parents=True)
    source = out_root / "source"
    manifest, reports = stage(source, manifest_raw, {target["name"]: original})
    bundle, moved = out_root / "bundle", out_root / "relocated-bundle"
    with contextlib.ExitStack() as stack:
        traps = [
            stack.enter_context(patch(target, side_effect=AssertionError("bundle attempted new inference or assets")))
            for target in (
                "quantfit.safety.verify.verify_safety",
                "quantfit.safety.gguf_arm.resolve_pair",
                "huggingface_hub.hf_hub_download",
            )
        ]
        created = create(manifest, reports, bundle)
        before = check(created, bundle, manifest_raw, {target["name"]: original})
        bundle.rename(moved)
        source.rename(out_root / "producer-unavailable")
        verified = verify(moved)
        after = check(verified, moved, manifest_raw, {target["name"]: original})
        for trap in traps:
            trap.assert_not_called()
    assert before == after and report_path.read_bytes() == original
    return {"kind": "existing native CPU receipt; offline screen bundle", "additional_native_calls": 0, **after}
