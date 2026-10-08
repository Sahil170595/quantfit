"""Synthetic aggregate evidence only: no labels, calibration study or GO is claimed."""

import copy
import json
from dataclasses import replace

import pytest

from quantfit.safety.calibration_binding import (
    CalibrationBindingError,
    engine_causal_identity,
    identity_fingerprint,
    load_bound_calibration,
    measurement_identity,
)
from quantfit.safety.report import ArmRun, DriftReport
from quantfit.safety.verify import (
    DECODE_CHAT_TEMPLATE_POLICY,
    JUDGE_INPUT_CONTRACT,
    JUDGE_MODEL_ID,
    JUDGE_REVISION,
    PROBE_DATASET_ID,
    PROBE_DATASET_REVISION,
    PROBE_SPLIT,
)


def report_fixture(n=40):
    return DriftReport(
        schema_version=2,
        quantfit_version="fixture",
        created_utc="2026-10-05T00:00:00+00:00",
        judge={"id": JUDGE_MODEL_ID, "revision": JUDGE_REVISION, "input_contract": JUDGE_INPUT_CONTRACT},
        probe_dataset={"id": PROBE_DATASET_ID, "revision": PROBE_DATASET_REVISION, "split": PROBE_SPLIT, "n_probes": n},
        decode={"max_new_tokens": 64, "do_sample": False, "chat_template": DECODE_CHAT_TEMPLATE_POLICY},
        env={"python": "3.13.1", "torch": "2.13.0+cpu", "transformers": "5.17.0", "cuda": None, "device": "cpu"},
        baseline=ArmRun(
            "base", "a" * 40, "torch.float32", 2.0, {"name": "transformers", "version": "5.17.0", "device": "cpu"}, None
        ),
        quantized=ArmRun(
            "quant",
            "b" * 40,
            "torch.float32",
            1.0,
            {"name": "transformers", "version": "5.17.0", "device": "cpu"},
            None,
        ),
        judge_runtime_s=0.5,
        drift={},
    )


def calibration_fixture(report):
    from quantfit.safety.calibrate import _arm_block

    n = report.probe_dataset["n_probes"]
    blocks = {}
    for arm, refusals in (("baseline", n // 2), ("quantized", n // 4)):
        blocks[arm] = _arm_block(
            {
                "n": n,
                "n_unusable": 0,
                "human_refusals": refusals,
                "human_compliances": n - refusals,
                "judge_refusal_human_compliance": 0,
                "judge_compliance_human_refusal": 0,
            }
        )
    identity = measurement_identity(report)
    return {
        "calibration_schema": 2,
        "quantfit_version": "fixture",
        "created_utc": report.created_utc,
        "n_labeled": 2 * n,
        "n_unusable": 0,
        "unmeasured_arms": [],
        **blocks,
        "arm_epsilon_delta": {"delta": 0.0, "note": "synthetic"},
        "label": "SYNTHETIC, not human evidence",
        "binding": {"identity": identity, "fingerprint": identity_fingerprint(identity)},
        "source": {key: "0" * 64 for key in ("capture_sha256", "key_sha256", "sheet_sha256")},
    }


def write_calibration(tmp_path, payload):
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_identity_omits_run_outputs_and_cache_hit_but_retains_actual_weights():
    report = report_fixture()
    cached = replace(
        report,
        created_utc="later",
        judge_runtime_s=9.0,
        baseline=replace(
            report.baseline, runtime_s=10.0, engine={**report.baseline.engine, "baseline_cache": {"key": "hit"}}
        ),
    )
    assert measurement_identity(cached) == measurement_identity(report)
    assert measurement_identity(
        replace(report, baseline=replace(report.baseline, revision="c" * 40))
    ) != measurement_identity(report)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: replace(r, baseline=replace(r.baseline, revision="main")),
        lambda r: replace(r, quantized=replace(r.quantized, revision=None)),
        lambda r: replace(r, judge={**r.judge, "revision": "main"}),
        lambda r: replace(r, probe_dataset={**r.probe_dataset, "n_probes": True}),
        lambda r: replace(r, decode={**r.decode, "do_sample": True}),
        lambda r: replace(r, decode={**r.decode, "greedy": True, "do_sample": "false"}),
        lambda r: replace(r, decode={**r.decode, "greedy": True, "do_sample": 1}),
        lambda r: replace(r, decode={**r.decode, "greedy": 1}),
        lambda r: replace(r, env={**r.env, "torch": ""}),
    ],
)
def test_incomplete_or_non_greedy_identity_is_refused(change):
    with pytest.raises(CalibrationBindingError):
        measurement_identity(change(report_fixture()))


def test_separate_uppers_source_hash_and_matching_scope(tmp_path):
    report = report_fixture()
    path = write_calibration(tmp_path, calibration_fixture(report))
    bound = load_bound_calibration(path, report=report)
    assert bound.eps_baseline_upper < bound.eps_quant_upper
    assert len(bound.source_sha256) == 64
    assert bound.source_sha256 in bound.eps_source
    with pytest.raises(CalibrationBindingError, match="scope"):
        bound.match_report(replace(report, decode={**report.decode, "max_new_tokens": 65}))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(calibration_schema=1),
        lambda p: p.update(binding=None),
        lambda p: p["binding"].update(fingerprint="0" * 64),
        lambda p: p["baseline"].update(mde_epsilon_upper=0.001),
        lambda p: p["baseline"].update(n=True),
        lambda p: p["baseline"].update(n_unusable=-1),
        lambda p: p["baseline"]["directional"]["false_refusal"].update(epsilon_wilson95=[0.0, float("nan")]),
        lambda p: p["baseline"].update(human_refusals=0),
        lambda p: p.update(n_labeled=79),
        lambda p: p.update(n_unusable=1),
        lambda p: p["source"].update(capture_sha256=None),
        lambda p: p.update(label=""),
        lambda p: p["arm_epsilon_delta"].update(note=float("nan")),
        lambda p: p["quantized"]["direction"].update(judge_compliance_human_refusal=99),
    ],
)
def test_tampered_or_unbound_calibration_is_refused(tmp_path, mutation):
    payload = calibration_fixture(report_fixture())
    mutation(payload)
    with pytest.raises(CalibrationBindingError):
        load_bound_calibration(write_calibration(tmp_path, payload))


def test_fingerprint_uses_canonical_json_and_refuses_nonfinite():
    identity = measurement_identity(report_fixture())
    assert identity_fingerprint(identity) == identity_fingerprint(dict(reversed(list(identity.items()))))
    broken = copy.deepcopy(identity)
    broken["env"]["cuda"] = float("inf")
    with pytest.raises(CalibrationBindingError):
        identity_fingerprint(broken)


def test_duplicate_json_fields_are_not_silently_overwritten(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"calibration_schema": 1, "calibration_schema": 2}', encoding="utf-8")
    with pytest.raises(CalibrationBindingError, match="duplicate"):
        load_bound_calibration(str(path))


def test_aggregate_read_is_bounded_and_overflow_literal_refused_anywhere(tmp_path):
    from quantfit.safety.calibration_binding import MAX_CALIBRATION_BYTES

    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * (MAX_CALIBRATION_BYTES + 1))
    with pytest.raises(CalibrationBindingError, match="2 MiB"):
        load_bound_calibration(str(path))
    path.write_text('{"arbitrary_nested_metadata": {"overflow": 1e999}}', encoding="utf-8")
    with pytest.raises(CalibrationBindingError, match="numeric literal"):
        load_bound_calibration(str(path))


def test_complete_arm_with_no_refusals_cannot_bound_false_compliance(tmp_path):
    from quantfit.safety.calibrate import _arm_block

    payload = calibration_fixture(report_fixture())
    payload["baseline"] = _arm_block(
        {
            "n": 40,
            "n_unusable": 0,
            "human_refusals": 0,
            "human_compliances": 40,
            "judge_refusal_human_compliance": 0,
            "judge_compliance_human_refusal": 0,
        }
    )
    with pytest.raises(CalibrationBindingError, match="unmeasured error direction"):
        load_bound_calibration(write_calibration(tmp_path, payload))


@pytest.mark.parametrize("arm", ["baseline", "quantized"])
def test_gguf_engine_identity_requires_observed_backend_pins(arm):
    report = report_fixture()
    gguf = replace(
        getattr(report, arm),
        revision=None,
        artifact_sha256="e" * 64,
        resolved_dtype="Q4_K_M",
        engine={"name": "llama.cpp", "binary_sha256": "f" * 64, "threads": 8},
    )
    identity = measurement_identity(replace(report, **{arm: gguf}))
    assert identity[arm]["artifact_sha256"] == "e" * 64
    with pytest.raises(CalibrationBindingError, match="binary_sha256"):
        measurement_identity(replace(report, **{arm: replace(gguf, engine={"name": "llama.cpp", "threads": 8})}))


def inspect_engine(repo="org/model", revision="a" * 40, n=40):
    """Synthetic fields follow the observed Inspect HF contract, not operator aliases."""
    return {
        "name": "inspect_ai:hf",
        "inspect_ai_version": "0.3.269",
        "torch_version": "2.13.0+cpu",
        "transformers_version": "5.17.0",
        "device": "cpu",
        "source_repo": repo,
        "config_commit_hash": revision,
        "snapshot_manifest_sha256": "c" * 64,
        "tokenizer_revision": revision,
        "tokenizer_template_sha256": "d" * 64,
        "quantization_config_sha256": None,
        "quantization_method": None,
        "max_samples": 1,
        "do_sample": False,
        "model_args": {"do_sample": False},
        "generate_calls": n,
        "weight_generate_host_wall_s": 1.0,
        "runtime_scope": "synthetic observed call wall time",
        "weight_runtime_scope": "synthetic weight generate wall time",
        "revision_observation": "synthetic immutable snapshot observation",
    }


def inspect_report_fixture():
    report = report_fixture()
    return replace(
        report,
        baseline=replace(report.baseline, model="hf/org/base", engine=inspect_engine("org/base")),
        quantized=replace(report.quantized, model="hf/org/quant", engine=inspect_engine("org/quant", "b" * 40)),
    )


def test_observed_inspect_identity_omits_outputs_and_round_trips_stored_scope(tmp_path):
    report = inspect_report_fixture()
    changed = replace(
        report,
        baseline=replace(
            report.baseline,
            runtime_s=10.0,
            engine={**report.baseline.engine, "weight_generate_host_wall_s": 9.0, "runtime_scope": "later timing note"},
        ),
    )
    assert measurement_identity(report) == measurement_identity(changed)
    engine = measurement_identity(report)["baseline"]["engine"]
    assert "generate_calls" not in engine and "weight_generate_host_wall_s" not in engine
    assert engine_causal_identity(engine, observed=False) == engine
    load_bound_calibration(write_calibration(tmp_path, calibration_fixture(report)), report=changed)
    causal_change = replace(
        report,
        baseline=replace(report.baseline, engine={**report.baseline.engine, "tokenizer_template_sha256": "e" * 64}),
    )
    assert measurement_identity(causal_change) != measurement_identity(report)


@pytest.mark.parametrize(
    "change",
    [
        lambda e: e.update(generate_calls=39),
        lambda e: e.update(generate_calls=True),
        lambda e: e.pop("weight_generate_host_wall_s"),
        lambda e: e.update(weight_generate_host_wall_s=float("inf")),
        lambda e: e.update(provider="operator-alias"),
        lambda e: e.update(do_sample=0),
        lambda e: e.update(model_args={"do_sample": 0}),
        lambda e: e.update(max_samples=True),
        lambda e: e.update(tokenizer_revision="b" * 40),
        lambda e: e.update(config_commit_hash="b" * 40),
        lambda e: e.update(source_repo="another/model"),
    ],
)
def test_observed_inspect_metadata_refuses_incomplete_or_contradictory_facts(change):
    report = inspect_report_fixture()
    change(report.baseline.engine)
    with pytest.raises(CalibrationBindingError):
        measurement_identity(report)


def test_nullable_observed_config_commit_is_preserved_without_invention():
    report = inspect_report_fixture()
    report.baseline.engine["config_commit_hash"] = None
    assert measurement_identity(report)["baseline"]["engine"]["config_commit_hash"] is None
