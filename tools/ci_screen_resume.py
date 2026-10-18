"""Offline strict-resume consumers; synthetic aggregates are protocol fixtures only."""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET


def binding(raw: bytes) -> dict:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def synthetic_fixture(prototype: Path) -> tuple[dict, dict[str, bytes]]:
    """Construct schema-v2 aggregates with explicitly fictional weight/engine identities."""
    from quantfit.safety.verify import DECODE_CHAT_TEMPLATE_POLICY, SafetyDrift

    template = json.loads(prototype.read_bytes())
    targets, reports = [], {}
    for name, unsafe, safe_base, dangerous in (
        ("clean", 12, 0, 0),
        ("flagged", 12, 0, 1),
        ("unmeasured", 0, 28, 0),
    ):
        report = copy.deepcopy(template)
        target = {
            "name": name,
            "stratum": "gguf",
            "baseline": f"hf:synthetic/{name}/{name}-base.gguf",
            "quant": f"hf:synthetic/{name}/{name}-quant.gguf",
        }
        targets.append(target)
        for arm, key in (("baseline", "baseline"), ("quantized", "quant")):
            identity = f"fictional protocol fixture:{name}:{arm}".encode()
            report[arm].update(
                model=target[key],
                revision=hashlib.sha1(identity).hexdigest(),
                artifact_sha256=hashlib.sha256(identity).hexdigest(),
                runtime_s=0.0,
                engine={
                    "name": "llama.cpp",
                    "device": "cpu",
                    "threads": 2,
                    "binary_sha256": hashlib.sha256(b"fictional executable; never run").hexdigest(),
                    "source": "synthetic protocol fixture; no executable or model run",
                },
            )
        report.update(
            quantfit_version="synthetic-bounded-aggregate-fixture",
            created_utc="2026-10-18T00:00:00+00:00",
            judge_runtime_s=0.0,
            env={
                "python": "synthetic",
                "torch": "synthetic",
                "transformers": "synthetic",
                "cuda": None,
                "device": "cpu",
            },
            decode={"do_sample": False, "max_new_tokens": 64, "chat_template": DECODE_CHAT_TEMPLATE_POLICY},
        )
        report["drift"] = SafetyDrift(
            40,
            12,
            unsafe,
            unsafe - dangerous,
            dangerous,
            28,
            safe_base,
            safe_base,
            0,
            {
                "clear_unsafe": {"n": 12, "baseline_refused": unsafe, "quant_refused": unsafe - dangerous},
                "clear_safe": {
                    "n": 12,
                    "baseline_refused": 12 if safe_base else 0,
                    "quant_refused": 12 if safe_base else 0,
                },
                "borderline": {
                    "n": 16,
                    "baseline_refused": 16 if safe_base else 0,
                    "quant_refused": 16 if safe_base else 0,
                },
            },
        ).to_dict()
        reports[name] = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
    return {
        "schema_version": 1,
        "name": "synthetic strict-resume protocol fixture; no measurements",
        "targets": targets,
        "sensitivity_control": {"status": "pass", "human_verifier": "declaration only; not authenticated"},
    }, reports


def write_fixture(
    root: Path, manifest: dict, reports: dict[str, bytes], *, missing: tuple[str, ...] = ()
) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    manifest_path, out = root / "manifest.json", root / "reports"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out.mkdir()
    for name, raw in reports.items():
        if name not in missing:
            (out / f"{name}.json").write_bytes(raw)
    return manifest_path, out


def invoke(manifest: Path, out: Path, *, junit: Path | None = None) -> tuple[dict, str]:
    """Execute the real parser/dispatch/JSON emission, without filtering progress lines."""
    from quantfit.cli import main

    argv = ["screen", "--targets", str(manifest), "--out", str(out), "--resume", "--max-new-tokens", "64", "--json"]
    if junit is not None:
        argv.extend(["--junit", str(junit)])
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    document = json.loads(stdout.getvalue())
    assert code == document["exit_code"] and document["command"] == "screen"
    return document, stderr.getvalue()


def native_counts(reports: list[dict]) -> dict:
    """Read primitive native counts, independently of the screen reducer."""
    axes = {}
    for axis, flips in (
        ("refusal_robustness", "harmful_compliance_regressions"),
        ("over_refusal", "overrefusal_regressions"),
    ):
        axes[axis] = {
            "n_measured": sum(r["drift"][axis]["at_risk"] > 0 for r in reports),
            "n_regressed": sum(r["drift"][axis][flips] > 0 for r in reports),
            "n_regressed_human_verified": 0,
        }
    regression = any(a["n_regressed"] for a in axes.values())
    unmeasured = any(r["drift"][a]["at_risk"] == 0 for r in reports for a in axes)
    return {"exit_code": 3 if regression else 4 if unmeasured else 0, "n_targets": len(reports), "axes": axes}


def check(
    document: dict, manifest: Path, out: Path, originals: dict[str, bytes], *, executed: tuple[str, ...] = ()
) -> dict:
    from quantfit.screen import CONDITIONALITY_LABEL, RESOLUTION_LABEL

    expected = native_counts([json.loads(raw) for raw in originals.values()])
    assert document["exit_code"] == expected["exit_code"]
    result, count = document["result"], len(originals)
    receipt = result["resume_receipt"]
    assert receipt["schema_version"] == 1 and receipt["kind"] == "quantfit.screen-resume"
    assert receipt["exit_code"] == expected["exit_code"]
    assert receipt["manifest"] == binding(manifest.read_bytes())
    assert receipt["n_executed"] == len(executed) and receipt["n_skipped"] == count - len(executed)
    assert receipt["n_operational_errors"] == 0 and len(receipt["targets"]) == count
    assert receipt["initial_missing"] == list(executed)
    assert receipt["control_evidence_verified"] is receipt["independent_execution_verified"] is False
    assert receipt["limits"] == {
        "manifest_bytes": 1048576,
        "report_bytes": 8388608,
        "total_report_bytes": 67108864,
        "max_targets": 256,
    }
    declared = json.loads(manifest.read_bytes())["targets"]
    for row, target in zip(receipt["targets"], declared, strict=True):
        name, raw = target["name"], originals[target["name"]]
        assert {k: row[k] for k in ("name", "stratum", "baseline", "quant")} == target
        native = json.loads(raw)["drift"]
        expected_status = (
            "regression"
            if native["regression_detected"]
            else "unmeasurable"
            if native["unmeasurable_axes"]
            else "no_regression"
        )
        assert row["member"] == f"{name}.json" and row["status"] == expected_status
        assert row["action"] == ("executed" if name in executed else "skipped")
        assert {k: row[k] for k in ("sha256", "size_bytes")} == binding(raw)
        assert row["producer_quantfit_version"] == json.loads(raw)["quantfit_version"]
        assert (out / f"{name}.json").read_bytes() == raw
    assert len(result["rows"]) == count and result["all_targets_attempted"] is True
    assert all(row.get("human_verified") is None for row in result["rows"])
    for axis, values in expected["axes"].items():
        aggregate = result["by_stratum"]["gguf"][axis]
        assert {k: aggregate[k] for k in values} == values
        assert aggregate["conditionality"] == CONDITIONALITY_LABEL
        assert aggregate["resolution_caveat"] == RESOLUTION_LABEL
    return {
        **expected,
        "n_skipped": receipt["n_skipped"],
        "n_executed": receipt["n_executed"],
        "n_operational_errors": 0,
        "manifest": receipt["manifest"],
        "reports": [
            {"name": row["name"], "action": row["action"], **binding(originals[row["name"]])}
            for row in receipt["targets"]
        ],
        "control_evidence_verified": False,
        "independent_execution_verified": False,
    }


def check_junit(path: Path, originals: dict[str, bytes]) -> dict:
    cases = list(ET.fromstring(path.read_bytes()).iter("testcase"))
    assert len(cases) == len(originals)
    failures = skipped = 0
    for case in cases:
        native = json.loads(originals[case.get("name")])["drift"]
        flagged = any(
            native[a][k] > 0
            for a, k in (
                ("refusal_robustness", "harmful_compliance_regressions"),
                ("over_refusal", "overrefusal_regressions"),
            )
        )
        unmeasured = any(native[a]["at_risk"] == 0 for a in ("refusal_robustness", "over_refusal"))
        assert (case.find("failure") is not None) == flagged
        assert (case.find("skipped") is not None) == (unmeasured and not flagged)
        assert case.find("error") is None
        failures += flagged
        skipped += unmeasured and not flagged
    return {"tests": len(cases), "failures": failures, "skipped": skipped, "errors": 0}


def accept_cpu(report_path: Path, out_root: Path) -> dict:
    """Reuse one real cold-run receipt; the trap forbids any additional native run."""
    original = report_path.read_bytes()
    native = json.loads(original)
    assert native["env"]["device"] == "cpu" and native["decode"]["max_new_tokens"] == 64
    target = {
        "name": "existing-cold-native",
        "stratum": "gguf",
        "baseline": native["baseline"]["model"],
        "quant": native["quantized"]["model"],
    }
    manifest, out = write_fixture(
        out_root,
        {"schema_version": 1, "name": "existing native CPU receipt", "targets": [target]},
        {target["name"]: original},
    )
    with patch(
        "quantfit.safety.verify.verify_safety", side_effect=AssertionError("resume attempted a new native run")
    ) as execution:
        document, _ = invoke(manifest, out)
    execution.assert_not_called()
    result = check(document, manifest, out, {target["name"]: original})
    assert report_path.read_bytes() == original
    return {"kind": "existing native CPU receipt; offline strict resume", "additional_native_calls": 0, **result}
