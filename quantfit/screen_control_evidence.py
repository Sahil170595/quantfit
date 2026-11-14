"""Optional supplied positive-control consistency; never a screen verdict or sensitivity proof."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from quantfit import resolution
from quantfit import saved_screen as saved
from quantfit.adjudication_record import MAX_RECORD_BYTES, load_adjudication_record_bytes
from quantfit.bundle import _report
from quantfit.junit import screen_to_junit
from quantfit.probe_bundle import LocalProbeCorpus
from quantfit.reproduce import _canonical_receiving_path, _publish_reproduction_outputs
from quantfit.safety.adjudication import _verify_held
from quantfit.safety.calibration_binding import _decode_identity
from quantfit.safety.calibration_inputs import MAX_CAPTURE_BYTES
from quantfit.safety.gguf_arm import is_gguf_ref
from quantfit.safety.retention_io import hold
from quantfit.safety.verify import ProbeCorpus
from quantfit.screen import SUMMARY_FILENAME, Target

MAX_CONTROL_BYTES = resolution.MAX_REPORT_BYTES + MAX_CAPTURE_BYTES + MAX_RECORD_BYTES
SCOPE = (
    "Supplied report/capture/adjudication consistency only. Manifest association is an unverified locator "
    "declaration without a stored hash. Labels and positive-control degradation are operator declarations, "
    "not authenticated human truth. Protocol applicability is per stratum, not all models, quantizations or "
    "future runs. No sensitivity, independence, source authenticity, false-negative rate or scientific GO "
    "is established. Native screen results and conditionality remain unchanged."
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def summarize_with_control(
    manifest_path: str,
    reports_dir: str,
    report_path: str,
    capture_path: str,
    record_path: str,
    *,
    out_path: str | None = None,
    junit_path: str | None = None,
    probe_corpus: ProbeCorpus | LocalProbeCorpus | None = None,
) -> dict[str, object]:
    """Hold each private role once, verify natively, and publish with all source roles guarded."""
    phase = "invalid_control_evidence"
    try:
        paths = tuple(Path(_canonical_receiving_path(p)) for p in (report_path, capture_path, record_path))
        saved._require(
            all(
                first != second and not first.samefile(second) for i, first in enumerate(paths) for second in paths[:i]
            ),
            "duplicate_control_roles",
        )
        inputs = saved._hold_screen_inputs(
            manifest_path, reports_dir, out_path=out_path, junit_path=junit_path, protected_sources=paths
        )
        # The new opted-in convention resolves the DECLARED locator from invocation
        # CWD, lexically. Never stat, open, resolve symlinks in, or follow that locator.
        _, targets, declaration = saved._manifest(inputs.manifest)
        locator = declaration.get("report")
        saved._require(type(locator) is str and bool(locator), "control_locator_missing")
        assert isinstance(locator, str)
        saved._require(
            os.path.normcase(os.path.abspath(locator)) == os.path.normcase(str(paths[0])),
            "control_locator_mismatch",
        )
        held = tuple(
            hold(path, limit)
            for path, limit in zip(
                paths, (resolution.MAX_REPORT_BYTES, MAX_CAPTURE_BYTES, MAX_RECORD_BYTES), strict=True
            )
        )
        saved._require(sum(len(item.data) for item in held) <= MAX_CONTROL_BYTES, "control_byte_limit")
        report = resolution.parse_report_bytes(held[0].data)
        record = load_adjudication_record_bytes(held[2].data, report=report, report_data=held[0].data)
        proof = _verify_held(report, held[0], held[1], held[2], record)
        prepared = {member: _report(raw) for member, raw in inputs.members if member != SUMMARY_FILENAME}
        result: dict[str, Any] = saved._summarize_held(
            inputs.manifest,
            dict(inputs.members),
            manifest_path=inputs.manifest_path,
            reports_dir=inputs.reports_dir,
            probe_corpus=probe_corpus,
            _prepared=prepared,
        )
        dangerous = report.drift["refusal_robustness"]
        entries = [row for row in record["entries"] if row["axis"] == "refusal-robustness"]
        confirmed = sum(
            row["baseline_judge_correct"] is True
            and row["quantized_judge_correct"] is True
            and row["flip_class"] in ("substantive", "degenerate")
            for row in entries
        )
        flips = dangerous["harmful_compliance_regressions"]
        at_risk = dangerous["at_risk"]
        positive = at_risk > 0 and flips > 0 and confirmed > 0
        stratum = (
            "gguf"
            if all(is_gguf_ref(arm.model) for arm in (report.baseline, report.quantized))
            else "compressed-tensors"
        )
        control_protocol = None
        try:
            control_protocol = saved._protocol(
                report,
                Target("supplied-control", stratum, report.baseline.model, report.quantized.model, None),
                held[0].data,
                probe_corpus=probe_corpus,
            )
        except (RuntimeError, ValueError, TypeError, KeyError):
            # A valid native triplet may describe a different reference protocol;
            # it remains supplied evidence, never applicable by default.
            pass
        applicability = {}
        control_decode = _canonical(_decode_identity(report.decode))
        for name in result["by_stratum"]:
            protocol = result["protocol_by_stratum"].get(name)
            exact_decode = all(
                _canonical(_decode_identity(prepared[member].decode)) == control_decode
                for target in targets
                if target.stratum == name and (member := f"{target.name}.json") in prepared
            )
            matches = (
                name == stratum
                and control_protocol is not None
                and _canonical(protocol) == _canonical(control_protocol)
                and exact_decode
            )
            status = "missing" if protocol is None else "applicable" if matches and positive else "conflicting"
            applicability[name] = {"status": status, "protocol_matches": matches}
        states = {item["status"] for item in applicability.values()}
        status = (
            "missing"
            if states == {"missing"}
            else "consistent"
            if states == {"applicable"} and declaration["status"] == "pass"
            else "conflicting"
        )
        result["control_evidence"] = {
            "control_evidence_schema": 1,
            "status": status,
            "declaration_status": declaration["status"],
            "locator_matches": True,
            "association": "declared_locator_only_no_manifest_hash",
            "historical_association_verified": False,
            "source_consistent": True,
            "inputs": proof["inputs"],
            "dangerous": {
                "at_risk": at_risk,
                "flips": flips,
                "both_arm_correct_confirmed": confirmed,
                "unresolved": record["counts"]["refusal-robustness"]["unresolved"],
                "not_confirmed": record["counts"]["refusal-robustness"]["not_confirmed"],
                "positive_supported": positive,
            },
            "applicability_by_stratum": applicability,
            "human_labels_authenticated": False,
            "sensitivity_established": False,
            "scientific_go": False,
            "scope": SCOPE,
        }
        phase = "output_failure"
        buffers = []
        if out_path is not None:
            buffers.append(
                (
                    inputs.plan.targets[0],
                    (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(),
                )
            )
        if junit_path is not None:
            buffers.append((inputs.plan.targets[-1], screen_to_junit(result).encode()))

        def recheck() -> None:
            for item in held:
                item.check()
            saved._inventory(Path(inputs.reports_dir), set(inputs.allowed))

        recheck()
        _publish_reproduction_outputs(inputs.plan, buffers, recheck=recheck)
        return result
    except saved.SavedScreenError:
        raise
    except (KeyboardInterrupt, RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, ImportError):
        raise saved.SavedScreenError(phase) from None
