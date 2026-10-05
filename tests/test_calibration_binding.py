"""Synthetic aggregate evidence only: no labels, calibration study or GO is claimed."""

import copy
import json
from dataclasses import replace

import pytest

from quantfit.safety.calibration_binding import (
    CalibrationBindingError,
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
