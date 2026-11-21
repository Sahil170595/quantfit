"""Closed pure JUnit projection of original native assessment criteria; no new policy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

from quantfit.bundle_archive_kinds import MAX_REPLAY_CANONICAL_BYTES
from quantfit.junit import _render
from quantfit.resolution import MAX_REPORT_BYTES

MAX_JUNIT_BYTES = 64 * 1024
CLASS_NAME = "quantfit.references.assess"
CAVEAT = (
    "Saved aggregate criteria only. Reference registration, producer locations, weights, physical hosts, "
    "human labels, independent execution, sensitivity and scientific GO remain unverified."
)
_FLAGS = (
    "reference_registered",
    "registry_admission_verified",
    "producer_locations_verified",
    "human_labels_authenticated",
    "weight_sizes_authenticated",
    "weights_authenticated",
    "binary_authenticated",
    "physical_hosts_authenticated",
    "independent_execution_verified",
    "sensitivity_established",
    "scientific_go",
)
_CORE_KEYS = frozenset(
    (
        "receiving_assessment_schema_version",
        "quantfit_version",
        "spec_version",
        "target_sha256",
        "target",
        "pair",
        "baseline_cap_bytes",
        "source_reports",
        "native_exits",
        "t0",
        "full_report_repeatability",
        "axes_by_run",
        "excluded_axes",
        "measured_axes",
        "eligible_axes_before_publication",
        "criteria",
        "blocking_reasons",
        "unknown_reasons",
        "outcome",
        "exit_code",
        *_FLAGS,
        "scope",
    )
)
_RECEIVING_KEYS = frozenset(
    ("bundle_path", "manifest", "original_t0", "original_t0_sha256", "receiving_t0", "report_bindings")
)


def _rules() -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]:
    rows: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
        ("supported_spec", (), ("unsupported_spec",)),
        ("supported_profile", (), ("unsupported_profile",)),
        ("baseline_declared_cap", ("baseline_declared_size_over_cap",), ("baseline_size_unestablished",)),
        ("quantized_size_declared", (), ("quantized_size_unestablished",)),
    ]
    facts = (("reported_target_facts_mismatch",), ("target_facts_unestablished",))
    for index in range(1, 4):
        for arm in ("baseline", "quantized"):
            for field in ("model", "revision", "resolved_dtype", "artifact_sha256"):
                rows.append((f"run-{index}.arms.{arm}.{field}", *facts))
            for field in ("name", "device", "binary_sha256", "threads", "offload_device", "n_gpu_layers", "op_offload"):
                rows.append((f"run-{index}.{arm}.engine.{field}", *facts))
        rows.append((f"run-{index}.native_profile", ("reported_native_profile_mismatch",), ()))
        for group, fields in (
            ("judge", ("id", "revision", "input_contract")),
            ("probe_dataset", ("id", "revision", "split", "n_probes")),
            ("decode", ("max_new_tokens", "do_sample", "chat_template")),
        ):
            for field in fields:
                rows.append((f"run-{index}.{group}.{field}", *facts))
    rows.extend(
        (
            ("native_t0", ("t0_operational_refusal", "t0_disagreement"), ()),
            ("full_report_repeatability", ("full_report_repeatability_failed",), ()),
            ("no_fresh_flags", ("fresh_flags_without_human_adjudication",), ()),
            ("measured_axis", (), ("no_measured_axis",)),
        )
    )
    return tuple(rows)


_RULES = _rules()
CANONICAL_CRITERIA = tuple(row[0] for row in _RULES)
_REASONS = frozenset(reason for _, false, unknown in _RULES for reason in (*false, *unknown))
_MESSAGES = {
    "unsupported_spec": "native target spec is unsupported",
    "unsupported_profile": "native target profile is unsupported",
    "baseline_declared_size_over_cap": "declared baseline size exceeds the native cap",
    "baseline_size_unestablished": "baseline size is unestablished",
    "quantized_size_unestablished": "quantized size is unestablished",
    "reported_target_facts_mismatch": "reported facts differ from the target declaration",
    "target_facts_unestablished": "target facts are unestablished",
    "reported_native_profile_mismatch": "reported native profile does not match",
    "t0_operational_refusal": "native T0 was operationally refused",
    "t0_disagreement": "native T0 disagrees",
    "full_report_repeatability_failed": "native full report repeatability failed",
    "fresh_flags_without_human_adjudication": "fresh native flags remain unconfirmed",
    "no_measured_axis": "no native measured axis is established",
}


class ReferenceAssessmentJUnitError(RuntimeError):
    """Categorical invalid projection or requested XML cap; never producer diagnostics."""

    def __init__(self) -> None:
        super().__init__("invalid_reference_assessment_junit")


@dataclass(frozen=True)
class _Criterion:
    name: str
    state: bool | None
    reason: str | None


@dataclass(frozen=True)
class _Snapshot:
    code: int
    criteria: tuple[_Criterion, ...]
    properties: tuple[tuple[str, str], ...]


def _require(condition: bool) -> None:
    if not condition:
        raise ReferenceAssessmentJUnitError()


def _object(value: object, keys: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ReferenceAssessmentJUnitError()
    return dict(value)


def _digest(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ReferenceAssessmentJUnitError()
    return value


def _reasons(value: object) -> frozenset[str]:
    if type(value) is not list or len(value) > len(_REASONS):
        raise ReferenceAssessmentJUnitError()
    reasons: set[str] = set()
    for reason in value:
        if type(reason) is not str or reason not in _REASONS or reason in reasons:
            raise ReferenceAssessmentJUnitError()
        reasons.add(reason)
    return frozenset(reasons)


def _snapshot(assessment: dict[str, object]) -> _Snapshot:
    receiving = _CORE_KEYS | _RECEIVING_KEYS
    if type(assessment) is not dict or set(assessment) not in (_CORE_KEYS, receiving, receiving | {"replay_archive"}):
        raise ReferenceAssessmentJUnitError()
    _require(
        type(assessment["receiving_assessment_schema_version"]) is int
        and assessment["receiving_assessment_schema_version"] == 1
    )
    code = assessment["exit_code"]
    if type(code) is not int or code not in (0, 3, 4):
        raise ReferenceAssessmentJUnitError()
    _require(
        assessment["outcome"] == {0: "ready_for_publication_review", 3: "blocked", 4: "unestablished"}[code]
        and type(assessment["outcome"]) is str
    )
    _require(all(assessment[flag] is False for flag in _FLAGS))
    source = _object(assessment["criteria"], frozenset(CANONICAL_CRITERIA))
    rows = []
    for name, false, unknown in _RULES:
        item = _object(source[name], frozenset(("pass", "reason")))
        value, reason = item["pass"], item["reason"]
        state: bool | None
        if value is True:
            state = True
            _require(reason is None)
        elif value is False:
            state = False
            _require(type(reason) is str and reason in false)
        elif value is None:
            state = None
            _require(type(reason) is str and reason in unknown)
        else:
            raise ReferenceAssessmentJUnitError()
        rows.append(_Criterion(name, state, reason))
    # Projection consistency only: never infer a verdict from native_exits or redo statistics.
    expected = 3 if any(row.state is False for row in rows) else 4 if any(row.state is None for row in rows) else 0
    _require(code == expected)
    _require(_reasons(assessment["blocking_reasons"]) == frozenset(row.reason for row in rows if row.state is False))
    _require(_reasons(assessment["unknown_reasons"]) == frozenset(row.reason for row in rows if row.state is None))
    exits = assessment["native_exits"]
    _require(type(exits) is list and len(exits) == 3 and all(type(item) is int and item in (0, 3, 4) for item in exits))
    properties = [
        ("criteria_total", str(len(rows))),
        ("criteria_true", str(sum(row.state is True for row in rows))),
        ("criteria_false", str(sum(row.state is False for row in rows))),
        ("criteria_unestablished", str(sum(row.state is None for row in rows))),
        ("exit_code", str(code)),
        ("target_sha256", _digest(assessment["target_sha256"])),
    ]
    reports = assessment["source_reports"]
    if type(reports) is not list or len(reports) != 3:
        raise ReferenceAssessmentJUnitError()
    for index, value in enumerate(reports, 1):
        report = _object(value, frozenset(("path", "sha256", "size_bytes")))
        size = report["size_bytes"]
        _require(type(size) is int and 0 < size <= MAX_REPORT_BYTES)
        properties.extend(
            ((f"report_{index}_sha256", _digest(report["sha256"])), (f"report_{index}_size_bytes", str(size)))
        )
    if _RECEIVING_KEYS <= set(assessment):
        properties.append(("original_t0_sha256", _digest(assessment["original_t0_sha256"])))
    if "replay_archive" in assessment:
        archive = _object(assessment["replay_archive"], frozenset(("sha256", "size_bytes")))
        size = archive["size_bytes"]
        _require(type(size) is int and 0 < size <= MAX_REPLAY_CANONICAL_BYTES)
        properties.extend(
            (("replay_archive_sha256", _digest(archive["sha256"])), ("replay_archive_size_bytes", str(size)))
        )
    return _Snapshot(code, tuple(rows), tuple(properties))


def assessment_to_junit(assessment: dict[str, object]) -> str:
    """Project an admitted core/receiving assessment in canonical order without native calls or mutation."""
    snapshot = _snapshot(assessment)  # No raw assessment data is accessed after this immutable boundary.
    failures = sum(row.state is False for row in snapshot.criteria) + int(snapshot.code == 3)
    errors = sum(row.state is None for row in snapshot.criteria) + int(snapshot.code == 4)
    counts = {
        "tests": str(len(snapshot.criteria) + 1),
        "failures": str(failures),
        "errors": str(errors),
        "skipped": "0",
    }
    suites = ET.Element("testsuites", counts)
    suite = ET.SubElement(suites, "testsuite", {"name": CLASS_NAME, **counts})
    properties = ET.SubElement(suite, "properties")
    for name, value in snapshot.properties:
        ET.SubElement(properties, "property", {"name": name, "value": value})
    overall = ET.SubElement(suite, "testcase", {"classname": CLASS_NAME, "name": "overall"})
    if snapshot.code:
        ET.SubElement(
            overall,
            "failure" if snapshot.code == 3 else "error",
            {
                "type": "NativeAssessmentBlocked" if snapshot.code == 3 else "NativeAssessmentUnestablished",
                "message": "native assessment is blocked"
                if snapshot.code == 3
                else "native assessment is unestablished",
            },
        )
    for row in snapshot.criteria:
        case = ET.SubElement(suite, "testcase", {"classname": CLASS_NAME, "name": row.name})
        if row.state is not True:
            assert row.reason is not None
            ET.SubElement(
                case,
                "failure" if row.state is False else "error",
                {
                    "type": "NativeCriterionFalse" if row.state is False else "NativeCriterionUnestablished",
                    "message": _MESSAGES[row.reason],
                },
            )
    ET.SubElement(suite, "system-out").text = CAVEAT
    rendered = _render(suites)
    if not isinstance(rendered, str) or len(rendered.encode("utf-8")) > MAX_JUNIT_BYTES:
        raise ReferenceAssessmentJUnitError()
    return rendered
