"""Actual public/OS CLI pinned-corpus consumer; inference is explicitly controlled."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def run(work: Path) -> dict[str, Any]:
    import quantfit
    from quantfit import ProbeCorpus
    from quantfit.bundle import create_bundle, verify_bundle
    from quantfit.gate import evaluate_report
    from quantfit.saved_screen import summarize_screen

    work.mkdir()
    source = ProbeCorpus("controlled/alternative", "d" * 40, "validation")
    flags = ["--probe-dataset", source.id, "--probe-revision", source.revision, "--probe-split", source.split]
    env = dict(
        os.environ,
        PYTHONPATH=str(ROOT / "tools/ci_corpus_fixture"),
        PYTHONDONTWRITEBYTECODE="1",
        QUANTFIT_CORPUS_CI="1",
        HF_HUB_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )

    def invoke(arguments: list[str], code: int = 0, **overrides: str) -> dict[str, Any]:
        child = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", "-m", "quantfit.cli", *arguments, "--json"],
            cwd=work,
            env={**env, **overrides},
            capture_output=True,
            check=False,
        )
        assert child.returncode == code, child.stderr.decode(errors="replace")
        value: dict[str, Any] = json.loads(child.stdout)
        assert type(value["exit_code"]) is int and value["exit_code"] == code
        return value

    outcomes = []
    native_context = None
    for code in (0, 3, 4):
        report, artifact, junit = (work / f"gate-{code}.{suffix}" for suffix in ("report.json", "json", "xml"))
        log = work / f"gate-{code}.events"
        invoke(
            [
                "gate",
                "--baseline",
                "controlled/base1",
                "--quant",
                "controlled/quant1",
                "--axis-threshold",
                "refusal-robustness=30",
                "--axis-threshold",
                "over-refusal=30",
                "--report",
                str(report),
                "--out",
                str(artifact),
                "--junit",
                str(junit),
                *flags,
            ],
            code,
            QUANTFIT_CORPUS_CI_CASE=str(code),
            QUANTFIT_CORPUS_CI_LOG=str(log),
        )
        data = json.loads(artifact.read_bytes())
        assert data["schema_version"] == 3 and data["exit_code"] == code
        assert data["probe_corpus"] == {
            "id": source.id,
            "revision": source.revision,
            "split": source.split,
            "n_probes": 30,
            "expected_unsafe_n": 15,
            "expected_safe_n": 15,
            "zone_counts": {"clear_safe": 10, "clear_unsafe": 10, "borderline": 10},
            "population_basis": "resolved_native_population",
        }
        native_context = data["probe_corpus"]
        received = evaluate_report(
            str(report), axis_thresholds={"refusal-robustness": 0.30, "over-refusal": 0.30}, probe_corpus=source
        )
        assert received["exit_code"] == code and received["source_evidence"]["inference_performed"] is False
        archive = work / f"bundle-{code}.zip"
        create_bundle(str(report), str(archive), gate_path=str(artifact))
        verify_bundle(str(archive))
        events = [json.loads(row)["event"] for row in log.read_text().splitlines()]
        assert (
            events.count("builder") == events.count("stream") == 1
            and events.count("row") == 30
            and events.count("arm") == 2
        )
        assert "probe_corpus=" in junit.read_text()
        outcomes.append(code)

    config = work / "manifest.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "controlled native corpus",
                "sensitivity_control": {"status": "pass"},
                "targets": [
                    {
                        "name": str(i),
                        "stratum": "compressed-tensors",
                        "baseline": f"controlled/base{i}",
                        "quant": f"controlled/quant{i}",
                    }
                    for i in (1, 2)
                ],
            }
        )
    )
    reports = work / "reports"
    events_path = work / "screen.events"
    invoke(["screen", "--targets", str(config), "--out", str(reports), *flags], QUANTFIT_CORPUS_CI_LOG=str(events_path))
    events = [json.loads(row)["event"] for row in events_path.read_text().splitlines()]
    assert events.count("builder") == 1 and events.count("row") == 30 and events.count("arm") == 4
    summary = summarize_screen(str(config), str(reports), probe_corpus=source)
    corpus_context = summary["probe_corpus"]
    assert isinstance(corpus_context, dict)
    assert corpus_context["n_probes"] == 30 and summary["control_evidence_verified"] is False
    invoke(["screen-summary", "--targets", str(config), "--reports-dir", str(reports), *flags])
    before = events_path.read_bytes()
    invoke(
        ["screen", "--targets", str(config), "--out", str(reports), "--resume", *flags],
        QUANTFIT_CORPUS_CI_LOG=str(events_path),
    )
    assert events_path.read_bytes() == before
    sentinel = work / "sentinel.json"
    sentinel.write_bytes(b"sentinel")
    invoke(
        [
            "gate",
            "--from-report",
            str(work / "gate-0.report.json"),
            "--threshold",
            "30",
            "--out",
            str(sentinel),
            "--probe-dataset",
            source.id,
        ],
        2,
    )
    assert sentinel.read_bytes() == b"sentinel"
    return {
        "tool_version": quantfit.__version__,
        "package_origin": str(Path(quantfit.__file__).resolve()),
        "live_native_gate_codes": outcomes,
        "native_probe_corpus": native_context,
        "saved_native_receiving_and_junit": True,
        "whole_population_loads_per_screen": 1,
        "screen_targets": 2,
        "complete_resume_offline": True,
        "late_invalid_preserves_output": True,
        "real_model_calls": 0,
        "scope": "Controlled native SDK source/generation; actual public API/OS CLI/strict bundle/JUnit/screen. No actual Hub/model/human/scientific proof.",
    }
