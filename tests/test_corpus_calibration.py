"""Conditional native binding and cache/capture identity, not calibration evidence."""

import json

import pytest
from test_calibration_binding import calibration_fixture, write_calibration
from test_corpus_gate import alternative, native_runtime
from test_probe_corpus import rows

from quantfit import gate
from quantfit.safety import verify as v
from quantfit.safety.calibration_binding import identity_fingerprint
from quantfit.safety.report import ArmRun, DriftReport

pytest_plugins = ["test_probe_corpus"]


def bound_input(sdk, monkeypatch, tmp_path, n=1000):
    source = alternative(sdk)
    sdk["rows"] = rows(n)
    calls = native_runtime(monkeypatch)
    path = tmp_path / "original.json"
    v.verify_safety("controlled/base", "controlled/quant", probe_corpus=source, report_path=str(path))
    report = DriftReport.from_json(str(path))
    payload = calibration_fixture(report)
    calls.clear()
    sdk["loads"].clear()
    return source, calls, payload


@pytest.mark.parametrize("kind", ["source", "count", "actual_revision", "valid"])
def test_native_bound_scope_phases_and_actual_resolved_fingerprint(sdk, monkeypatch, tmp_path, kind):
    source, calls, payload = bound_input(sdk, monkeypatch, tmp_path)
    identity = payload["binding"]["identity"]
    if kind == "source":
        identity["probe_dataset"]["split"] = "other"
    elif kind == "count":
        # The calibration is internally valid for1000, but resolution now yields30.
        sdk["rows"] = rows(30)
    elif kind == "actual_revision":
        identity["baseline"]["revision"] = "e" * 40
    payload["binding"]["fingerprint"] = identity_fingerprint(identity)
    calibration = write_calibration(tmp_path, payload)
    artifact = tmp_path / "decision.json"
    report = tmp_path / "published.json"
    artifact.write_bytes(b"held")
    if kind == "valid":
        result = gate.run_gate(
            "controlled/base",
            "controlled/quant",
            threshold=0.3,
            probe_corpus=source,
            calibration_report=calibration,
            out_path=str(artifact),
            report_path=str(report),
        )
        assert result["exit_code"] == 0 and result["eps"]["actual_run_matched"] is True
        assert result["eps"]["measured"] is False and result["eps"]["assumptions_verified"] is False
        assert len(calls) == 2 and report.exists()
    else:
        with pytest.raises(RuntimeError):
            gate.run_gate(
                "controlled/base",
                "controlled/quant",
                threshold=0.3,
                probe_corpus=source,
                calibration_report=calibration,
                out_path=str(artifact),
                report_path=str(report),
            )
        assert artifact.read_bytes() == b"held" and not report.exists()
        assert len(calls) == (2 if kind == "actual_revision" else 0)
        assert len(sdk["loads"]) == (0 if kind == "source" else 1)


def gguf_runtime(monkeypatch):
    from pathlib import Path

    from quantfit.safety import gguf_arm
    from quantfit.safety import report as report_module

    calls = []
    engine = {
        "name": "llama.cpp",
        "binary_sha256": "e" * 64,
        "source": "controlled-no-binary",
        "threads": 1,
        "device": "cpu",
        **gguf_arm.CPU_OFFLOAD_CONTROLS,
    }

    def resolve(baseline, quant, token, **options):
        return tuple(
            gguf_arm.ResolvedGguf(ref, Path("unused"), None, sha * 64, "controlled", dtype, True, None)
            for ref, sha, dtype in [(baseline, "c", "F16"), (quant, "d", "Q4_K_M")]
        )

    def identity(arm):
        return {
            "model": arm.ref,
            "revision": arm.revision,
            "resolved_dtype": arm.file_type,
            "engine": dict(engine),
            "artifact_sha256": arm.sha256,
        }

    def generate(arm, prompts, max_new_tokens, **options):
        calls.append((arm.ref, list(prompts)))
        return ["refused" if i % 2 == 0 else "answered" for i in range(len(prompts))], ArmRun(
            runtime_s=0.0, **identity(arm)
        )

    monkeypatch.setattr(gguf_arm, "resolve_pair", resolve)
    monkeypatch.setattr(gguf_arm, "arm_identity", identity)
    monkeypatch.setattr(gguf_arm, "generate_completions", generate)
    monkeypatch.setattr(v, "_classify_refusals", lambda values, token: ([x == "refused" for x in values], 0.0))
    monkeypatch.setattr(
        report_module,
        "environment_fingerprint",
        lambda: {
            "python": "synthetic-not-used",
            "torch": "synthetic-not-used",
            "transformers": "synthetic-not-used",
            "cuda": None,
            "device": "cpu",
        },
    )
    return calls


@pytest.mark.parametrize("change", ["revision", "split"])
def test_native_gguf_cache_uses_whole_held_source_and_capture_identity(sdk, monkeypatch, tmp_path, change):
    from quantfit.safety import cache

    source = alternative(sdk)
    sdk["rows"] = rows(30)
    calls = gguf_runtime(monkeypatch)
    root = tmp_path / "private-cache"
    report = tmp_path / "report.json"
    first = gate.run_gate(
        "base.gguf",
        "quant.gguf",
        threshold=0.3,
        probe_corpus=source,
        baseline_cache_dir=str(root),
        report_path=str(report),
    )
    assert first["exit_code"] == 0 and len(calls) == 2
    gate.run_gate(
        "base.gguf",
        "quant.gguf",
        threshold=0.3,
        probe_corpus=source,
        baseline_cache_dir=str(root),
        report_path=str(report),
    )
    assert len(calls) == 3  # onlyquant generation; native cache servesbaseline
    changed = v.ProbeCorpus(
        source.id, "f" * 40 if change == "revision" else source.revision, "test" if change == "split" else source.split
    )
    sdk["hash"] = changed.revision
    capture = tmp_path / "private.capture.jsonl"
    v.verify_safety(
        "base.gguf",
        "quant.gguf",
        probe_corpus=changed,
        baseline_cache_dir=str(root),
        report_path=str(report),
        capture_path=str(capture),
    )
    assert len(calls) == 5 and len(list(root.glob(cache.CACHE_ENTRY_GLOB))) == 2
    header = json.loads(capture.read_text().splitlines()[0])
    assert header["binding"]["identity"]["probe_dataset"] == {
        "id": changed.id,
        "revision": changed.revision,
        "split": changed.split,
        "n_probes": 30,
    }


def test_whole_screen_source_is_common_across_both_native_strata(sdk, monkeypatch, tmp_path):
    from quantfit.saved_screen import summarize_screen
    from quantfit.screen import run_screen

    source = alternative(sdk)
    native_runtime(monkeypatch)
    gguf_runtime(monkeypatch)
    path, out = tmp_path / "manifest.json", tmp_path / "reports"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "both strata",
                "targets": [
                    {
                        "name": "hf",
                        "stratum": "compressed-tensors",
                        "baseline": "controlled/base",
                        "quant": "controlled/quant",
                    },
                    {"name": "cpu", "stratum": "gguf", "baseline": "base.gguf", "quant": "quant.gguf"},
                ],
            }
        )
    )
    result = run_screen(str(path), str(out), probe_corpus=source)
    assert len(sdk["loads"]) == 1 and len(result["rows"]) == 2
    assert set(result["by_stratum"]) == {"gguf", "compressed-tensors"}
    saved = summarize_screen(str(path), str(out), probe_corpus=source)
    assert saved["probe_corpus"]["n_probes"] == 6


def test_saved_custom_screen_calibration_and_variants_keep_explicit_source(sdk, monkeypatch, tmp_path):
    from test_corpus_gate import manifest

    from quantfit.saved_screen import summarize_screen
    from quantfit.screen import run_screen

    source = alternative(sdk)
    sdk["rows"] = rows(30)
    native_runtime(monkeypatch)
    config, out, calibrations = tmp_path / "manifest.json", tmp_path / "reports", tmp_path / "calibrations"
    manifest(config)
    run_screen(str(config), str(out), probe_corpus=source)
    calibrations.mkdir()
    for name in ("first", "last"):
        report = DriftReport.from_json(str(out / f"{name}.json"))
        (calibrations / f"{name}.json").write_text(json.dumps(calibration_fixture(report)))

    def forbidden(*a, **k):
        pytest.fail("offline calibrated screen attempted source/model loading")

    monkeypatch.setattr(v, "_prepare_probes", forbidden)
    result = summarize_screen(str(config), str(out), probe_corpus=source, calibrations_dir=str(calibrations))
    assert result["probe_corpus"]["n_probes"] == 30
    assert result["conditional_resolution"]["coverage"]["n_analyzed"] == 2
    variants = summarize_screen(
        str(config),
        str(out),
        probe_corpus=source,
        calibration_variants={"provided": str(calibrations), "missing": None},
    )
    assert variants["probe_corpus"] == result["probe_corpus"]
    assert variants["calibration_choice_sensitivity"]["coverage"]["analyzed"] == 2
