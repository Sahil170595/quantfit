"""Bound-calibration bridge: preflight scope is not an observed actual-run match."""

from __future__ import annotations

import tempfile
from pathlib import Path

from quantfit.safety.calibration_binding import CalibrationBindingError, load_bound_calibration

EPS_MODE_BOUND = "bound_calibration_report"
ASSUMPTIONS = {
    "A1": "Directional calibration bounds apply within the realized at-risk population; global labeled rates do not verify this.",
    "A2": "Judge errors are independent across arms conditional on true labels; correlated error is bias no sample size fixes.",
    "A3": "At least half the observed at-risk set is truly at risk (pi >= 1/2); binding does not establish this.",
}
ASSUMPTIONS_STATEMENT = (
    "At-risk applicability (A1), arm-conditional independence (A2), and majority-real at-risk probes (A3) "
    "remain unverified; resolution is conditional on them."
)


def prepare_calibration(path, baseline, quant, max_new_tokens, n_probes):
    from quantfit.safety import verify as sv
    from quantfit.safety.mde import EPS_DEFINITION

    bound = load_bound_calibration(path)
    expected = {
        "judge": {"id": sv.JUDGE_MODEL_ID, "revision": sv.JUDGE_REVISION, "input_contract": sv.JUDGE_INPUT_CONTRACT},
        "probe_dataset": {
            "id": sv.PROBE_DATASET_ID,
            "revision": sv.PROBE_DATASET_REVISION,
            "split": sv.PROBE_SPLIT,
            "n_probes": n_probes,
        },
    }
    if any(bound.identity[key] != value for key, value in expected.items()):
        raise CalibrationBindingError("calibration scope does not match the requested pinned judge/corpus")
    if bound.identity["baseline"]["model"] != baseline or bound.identity["quantized"]["model"] != quant:
        raise CalibrationBindingError("calibration scope does not match requested arm names")
    decode = bound.identity["decode"]
    if decode != {"max_new_tokens": max_new_tokens, "greedy": True, "chat_template": sv.DECODE_CHAT_TEMPLATE_POLICY}:
        raise CalibrationBindingError("calibration scope does not match the requested decode protocol")
    eps = {
        "upper": None,  # no single operator epsilon: the two directional bounds stay separate
        "baseline_upper": bound.eps_baseline_upper,
        "quantized_upper": bound.eps_quant_upper,
        "source": bound.eps_source,
        "source_sha256": bound.source_sha256,
        "scope_fingerprint": bound.fingerprint,
        "binding_status": "scope_validated_actual_run_unobserved",
        "actual_run_matched": False,
        "measured": False,  # a matched file cannot authenticate a labeler's truth
        "assumptions_verified": False,
        "assumptions": dict(ASSUMPTIONS),
        "definition": EPS_DEFINITION,
        "mode": EPS_MODE_BOUND,
        "resolution_is_a_floor": False,
        "statement": "Calibration scope and aggregate arithmetic validated; actual arm weights/environment not yet "
        "observed. Binding never authenticates human labels, sensitivity, or a GO. " + ASSUMPTIONS_STATEMENT,
    }
    return bound, eps


def verify_bound_run(bound, eps, baseline, quant, *, token, max_new_tokens, report_path, baseline_cache_dir):
    from quantfit.safety.report import DriftReport
    from quantfit.safety.verify import verify_safety

    # A temporary aggregate report gives the gate the SAME resolved provenance as
    # the capture producer, without loading twice or changing the public return type.
    with tempfile.TemporaryDirectory(prefix="quantfit-calibrated-run-") as temporary:
        observed_path = report_path or str(Path(temporary) / "drift.json")
        drift = verify_safety(
            baseline,
            quant,
            token=token,
            max_new_tokens=max_new_tokens,
            report_path=observed_path,
            baseline_cache_dir=baseline_cache_dir,
        )
        observed = DriftReport.from_json(observed_path)
        bound.match_report(observed)
        if observed.drift != drift.to_dict():
            raise CalibrationBindingError("actual report counts do not match the run being gated")
    eps["binding_status"] = "actual_run_matched"
    eps["actual_run_matched"] = True
    eps["statement"] = (
        "Calibration scope matched the actual resolved run and aggregate arithmetic was checked. "
        "Label truth and sensitivity remain unverified; no GO is inferred. " + ASSUMPTIONS_STATEMENT
    )
    return drift
