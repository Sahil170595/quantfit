"""Opted source gate profile; native policy math over one held population."""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from quantfit import gate
from quantfit import probe_population as population
from quantfit.probe_bundle import LocalProbeCorpus, _pin
from quantfit.safety.verify import ProbeCorpus, _corpus

SCOPE = (
    "Explicit pinned corpus and native census, not authenticated remote completeness or curation. "
    "Historical default-distribution judge accuracy/epsilon and sensitivity do not transfer. "
    "Conditional assumptions and human truth remain unverified; no scientific GO."
)
HISTORICAL_SCOPE = (
    "Historical default-distribution qualification: any legacy measured-epsilon/accuracy or n<=34 figures below "
    "describe that past default-distribution calibration, not a measured bound for this supplied population. "
)


def scoped_epsilon(eps: dict[str, Any]) -> dict[str, Any]:
    """Qualify legacy prose only; the native numeric bounds/calculus are unchanged."""
    if eps["mode"] == gate.EPS_MODE_FLOOR:
        return {**eps, "statement": HISTORICAL_SCOPE + gate._eps(None, None)["statement"]}
    return dict(eps)


def _policy(
    threshold: float | None, tier: str | None, axis_thresholds: Mapping[str, float] | None
) -> dict[str, float] | None:
    if axis_thresholds is not None:
        from quantfit.axis_gate import admit_thresholds

        return admit_thresholds(axis_thresholds, threshold, tier)
    gate._declared(threshold, tier)
    return None


def decision(
    *,
    baseline: str,
    quant: str,
    threshold: float | None,
    tier: str | None,
    axis_thresholds: Mapping[str, float] | None,
    eps: dict[str, Any],
    max_new_tokens: int,
    report_path: str | None,
    drift: dict[str, Any] | None,
    context: dict[str, Any],
    report_sha256: str | None = None,
) -> dict[str, Any]:
    context = population.admit_context(context)
    eps = scoped_epsilon(eps)
    options: dict[str, Any]
    if axis_thresholds is not None:
        from quantfit.axis_gate import decision as axis_decision

        value = axis_decision(
            baseline=baseline,
            quant=quant,
            policy=axis_thresholds,
            eps=eps,
            max_new_tokens=max_new_tokens,
            report_path=report_path,
            drift=drift,
            report_sha256=report_sha256,
            _population=context,
        )
        kind = 2
    else:
        effect, tier_row, declared = gate._declared(threshold, tier)
        n = context["expected_unsafe_n"]
        block = gate._block(eps, n)
        pre = gate._resolution(gate.STAGE_PRE_RUN, effect, block, eps, n)
        if not pre["not_refused"]:
            message = (
                f"REFUSED before loading any model or judge: native best-case n={n} for the "
                f"declared {gate._pp(effect)} effect cannot resolve this policy on "
                f"{_pin(context, include_split=True)}; none was started."
            )
            options = {
                "block": block,
                "resolution": pre,
                "verdict": gate.VERDICT_UNRESOLVABLE,
                "exit_code": 5,
                "message": message,
                "passed": None,
                "drift": None,
                "over_refusal": None,
            }
        else:
            gate._require(drift is not None, "native observed corpus decision requires its run")
            assert drift is not None
            options = gate._observed_policy(drift, effect, eps, declared, _population=context)
        source = (
            None
            if report_sha256 is None
            else {
                "kind": "saved_report",
                "report_sha256": report_sha256,
                "evaluation_phase": "policy_preflight" if options["drift"] is None else "observed_counts",
                "inference_performed": False,
            }
        )
        value = gate._decision(
            baseline=baseline,
            quant=quant,
            threshold=effect,
            tier=tier_row,
            declared_as=declared,
            eps=eps,
            max_new_tokens=max_new_tokens,
            report_path=report_path,
            source_evidence=source,
            **options,
        )
        value["corpus_composition"] = {
            "expected_unsafe_n_pinned": n,
            "expected_safe_n_pinned": context["expected_safe_n"],
            "expected_unsafe_n_observed": None
            if options["drift"] is None
            else options["drift"]["refusal_robustness"]["expected_unsafe_n"],
            "matches_pin": None if options["drift"] is None else True,
        }
        kind = 1
    value["schema_version"] = 3
    value["decision_schema_version"] = kind
    value["probe_corpus"] = context
    value["notes"].append(SCOPE)
    value["notes"] = [
        HISTORICAL_SCOPE + note if "0.196" in note or "n <= 34" in note else note for note in value["notes"]
    ]
    if value["floor_mode_caveats"] is not None:
        value["floor_mode_caveats"]["resolution"] = HISTORICAL_SCOPE + value["floor_mode_caveats"]["resolution"]
    value["message"] = value["message"].replace("this curated set", "this supplied population")
    value["headline"] = gate._headline(value) if kind == 1 else value["message"]
    if value["resolution_is_a_floor"]:
        value["headline"] = HISTORICAL_SCOPE + value["headline"]
    return value


def _local_model_inputs(refs: Sequence[str | None]) -> tuple[Path, ...]:
    """Protect explicitly supplied local GGUF identities, not opaque saved labels.

    Native local model reading follows symlinks. Keep the original serving ref
    untouched and use its resolved path only for output-role/alias protection.
    Remote hf: refs and their unobserved cache files are outside this role.
    """
    from quantfit.safety.gguf_arm import HF_REF_PREFIX, is_gguf_ref

    return tuple(
        Path(ref).resolve()
        for ref in refs
        if ref is not None and is_gguf_ref(ref) and not ref.startswith(HF_REF_PREFIX)
    )


def _admit_publication_paths(
    inputs: Sequence[str | Path | None], outputs: Sequence[str | Path | None], *, cache_dir: str | None = None
) -> None:
    from quantfit.reproduce import _ReproductionOutputs, _validate_reproduction_outputs

    gate.validate_replay_outputs(inputs, outputs)
    _validate_reproduction_outputs(
        _ReproductionOutputs(
            tuple(Path(p) for p in inputs if p is not None),
            (),
            tuple(Path(p) for p in outputs if p is not None),
        )
    )
    if cache_dir is not None:
        root = Path(cache_dir)
        gate._require(
            all(not p.exists() or p.is_dir() for p in (root, *root.parents)),
            "baseline cache requires a directory with directory parents",
        )


def run_corpus_gate(
    baseline: str,
    quant: str,
    *,
    probe_corpus: ProbeCorpus | LocalProbeCorpus,
    probe_bundle_path: str | None = None,
    _publication_outputs: tuple[str, ...] = (),
    threshold: float | None = None,
    tier: str | None = None,
    axis_thresholds: Mapping[str, float] | None = None,
    eps_upper: float | None = None,
    eps_source: str | None = None,
    token: str | None = None,
    max_new_tokens: int = 64,
    report_path: str | None = None,
    out_path: str | None = None,
    baseline_cache_dir: str | None = None,
    calibration_report: str | None = None,
) -> dict[str, Any]:
    from quantfit.axis_gate import preflight
    from quantfit.bundle import _report
    from quantfit.safety import verify
    from quantfit.safety.calibrated_gate import OBSERVED_STATEMENT, calibration_epsilon
    from quantfit.safety.calibration_binding import _same_numbers

    try:
        source = _corpus(probe_corpus)
        policy = _policy(threshold, tier, axis_thresholds)
        baseline, quant = gate._text(baseline, "baseline"), gate._text(quant, "quant")
        gate._require(type(max_new_tokens) is int and max_new_tokens > 0, "invalid max_new_tokens")
        model_inputs = _local_model_inputs((baseline, quant))
        _admit_publication_paths(
            [calibration_report, probe_bundle_path, *model_inputs],
            [report_path, out_path, *_publication_outputs],
            cache_dir=baseline_cache_dir,
        )
        verify._admit_verify_options(
            baseline, quant, probe_corpus=source, baseline_cache_dir=baseline_cache_dir, max_new_tokens=max_new_tokens
        )
        bound = None
        if calibration_report is not None:
            gate._require(eps_upper is None and eps_source is None, "mutually exclusive calibration/epsilon")
            bound = population.preflight_calibration(calibration_report, source, baseline, quant, max_new_tokens)
            eps = calibration_epsilon(bound)
        else:
            eps = gate._eps(eps_upper, eps_source)
        held = population.prepare(token, source, probe_bundle_path=probe_bundle_path)
        if held.held_file is not None:
            from dataclasses import replace

            held = replace(
                held,
                publication_inputs=tuple(str(p) for p in (calibration_report, *model_inputs) if p is not None),
                publication_outputs=tuple(
                    str(p) for p in (report_path, out_path, *_publication_outputs) if p is not None
                ),
            )
        context = population.context(held)
        if bound is not None:
            _same_numbers(
                bound.identity["probe_dataset"]["n_probes"], context["n_probes"], "resolved calibration population"
            )
        if policy is None:
            effect = gate._declared(threshold, tier)[0]
            n = context["expected_unsafe_n"]
            allowed = gate._resolution(gate.STAGE_PRE_RUN, effect, gate._block(eps, n), eps, n)["not_refused"]
        else:
            allowed = all(r["resolution"]["not_refused"] for r in preflight(policy, eps, _population=context).values())
        drift = None
        raw = None
        if allowed:
            with tempfile.TemporaryDirectory(prefix="quantfit-corpus-gate-") as temporary:
                path = Path(temporary) / "observed.json"
                observed = verify.verify_safety(
                    baseline,
                    quant,
                    token=token,
                    max_new_tokens=max_new_tokens,
                    report_path=str(path),
                    baseline_cache_dir=baseline_cache_dir,
                    probe_corpus=source,
                    _prepared_population=held,
                )
                raw = path.read_bytes()
                report = _report(raw)
                population.match_report(report, context)
                _same_numbers(report.drift, observed.to_dict(), "actual held native run")
                if bound is not None:
                    bound.match_report(report)
                    eps.update(
                        binding_status="actual_run_matched", actual_run_matched=True, statement=OBSERVED_STATEMENT
                    )
                drift = observed.to_dict()
        value = decision(
            baseline=baseline,
            quant=quant,
            threshold=threshold,
            tier=tier,
            axis_thresholds=policy,
            eps=eps,
            max_new_tokens=max_new_tokens,
            report_path=report_path,
            drift=drift,
            context=context,
        )
        if held.held_file is not None:
            held.held_file.check()
        _admit_publication_paths(
            [calibration_report, probe_bundle_path, *model_inputs],
            [report_path, out_path, *_publication_outputs],
            cache_dir=baseline_cache_dir,
        )
        if raw is not None and report_path is not None:
            Path(report_path).write_bytes(raw)
        if out_path is not None:
            gate._write(out_path, value)
        return value
    except (RuntimeError, OSError) as exc:
        if isinstance(exc, gate.GateError):
            raise
        raise gate.GateError(str(exc)) from exc


def evaluate_corpus_report(
    source_path: str,
    *,
    probe_corpus: ProbeCorpus | LocalProbeCorpus,
    threshold: float | None = None,
    tier: str | None = None,
    axis_thresholds: Mapping[str, float] | None = None,
    eps_upper: float | None = None,
    eps_source: str | None = None,
    calibration_report: str | None = None,
    report_path_out: str | None = None,
    out_path: str | None = None,
) -> dict[str, Any]:
    from quantfit.bundle import _json, _read, _report
    from quantfit.modelcard import _check_original_statistics
    from quantfit.resolution import MAX_REPORT_BYTES
    from quantfit.safety.calibrated_gate import calibration_epsilon
    from quantfit.safety.calibration_binding import MAX_CALIBRATION_BYTES, load_bound_calibration_bytes

    try:
        source = _corpus(probe_corpus)
        policy = _policy(threshold, tier, axis_thresholds)
        _admit_publication_paths([source_path, calibration_report], [report_path_out, out_path])
        raw = _read(Path(source_path), MAX_REPORT_BYTES)
        _json(raw)
        report = _report(raw)
        _check_original_statistics(report)
        context = population.report_context(report, source)
        decode = report.decode
        max_tokens = decode.get("max_new_tokens")
        gate._require(
            type(max_tokens) is int
            and max_tokens > 0
            and decode.get("do_sample", not decode.get("greedy", False)) is False
            and decode.get("greedy", True) is True
            and type(decode.get("temperature", 0)) in (int, float)
            and decode.get("temperature", 0) == 0,
            "saved gate requires recorded greedy decode",
        )
        if calibration_report is not None:
            gate._require(eps_upper is None and eps_source is None, "mutually exclusive calibration/epsilon")
            cal = _read(Path(calibration_report), MAX_CALIBRATION_BYTES)
            _json(cal)
            eps = calibration_epsilon(load_bound_calibration_bytes(cal, report=report), saved_report=True)
        else:
            eps = gate._eps(eps_upper, eps_source)
        value = decision(
            baseline=report.baseline.model,
            quant=report.quantized.model,
            threshold=threshold,
            tier=tier,
            axis_thresholds=policy,
            eps=eps,
            max_new_tokens=max_tokens,
            report_path=report_path_out or source_path,
            drift=report.drift,
            context=context,
            report_sha256=hashlib.sha256(raw).hexdigest(),
        )
        _admit_publication_paths([source_path, calibration_report], [report_path_out, out_path])
        if report_path_out is not None:
            Path(report_path_out).write_bytes(raw)
        if out_path is not None:
            gate._write(out_path, value)
        return value
    except (RuntimeError, OSError) as exc:
        if isinstance(exc, gate.GateError):
            raise
        raise gate.GateError(str(exc)) from exc
