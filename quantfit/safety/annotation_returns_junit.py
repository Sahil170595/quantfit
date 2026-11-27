"""Private bounded coverage projection over already validated native annotation returns."""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from quantfit.junit import _render
from quantfit.safety.annotation_chunks import MAX_PARTS, AnnotationChunksError, _valid_required_parts
from quantfit.safety.reconcile import MAX_IDS

MAX_JUNIT_BYTES = 64 * 1024
CLASS_NAME = "quantfit.annotation_returns"


@dataclass(frozen=True)
class _Coverage:
    expected_rows: tuple[int, ...]
    received_part_indices: tuple[int, ...]
    n_rows: int
    n_received_rows: int
    require_complete: bool
    manifest_sha256: str
    required_parts: tuple[int, ...] | None = None


def _require(condition: bool) -> None:
    if not condition:
        raise AnnotationChunksError("invalid_annotation_returns")


def _validate(coverage: _Coverage) -> None:
    _require(type(coverage) is _Coverage and type(coverage.require_complete) is bool)
    _require(type(coverage.expected_rows) is tuple and 1 <= len(coverage.expected_rows) <= MAX_PARTS)
    _require(not (coverage.require_complete and coverage.required_parts is not None))
    _require(_valid_required_parts(coverage.required_parts, len(coverage.expected_rows)))
    _require(type(coverage.n_rows) is int and 1 <= coverage.n_rows <= MAX_IDS)
    _require(all(type(count) is int and 1 <= count <= MAX_IDS for count in coverage.expected_rows))
    _require(sum(coverage.expected_rows) == coverage.n_rows)
    _require(
        type(coverage.received_part_indices) is tuple
        and 1 <= len(coverage.received_part_indices) <= len(coverage.expected_rows)
    )
    _require(
        all(
            type(index) is int and 1 <= index <= len(coverage.expected_rows) for index in coverage.received_part_indices
        )
    )
    _require(tuple(sorted(set(coverage.received_part_indices))) == coverage.received_part_indices)
    _require(type(coverage.n_received_rows) is int and 1 <= coverage.n_received_rows <= coverage.n_rows)
    _require(
        sum(coverage.expected_rows[index - 1] for index in coverage.received_part_indices) == coverage.n_received_rows
    )
    _require(
        type(coverage.manifest_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", coverage.manifest_sha256) is not None
    )


def _to_junit(coverage: _Coverage) -> bytes:
    """Render only safe counts/hash and original numeric indices, never private records."""
    _validate(coverage)
    n_parts = len(coverage.expected_rows)
    received = set(coverage.received_part_indices)
    n_missing = n_parts - len(received)
    required = set(range(1, n_parts + 1)) if coverage.require_complete else set(coverage.required_parts or ())
    missing_required = required - received
    unmet = bool(missing_required)
    counts = {
        "tests": str(n_parts + 1),
        "failures": "0",
        "errors": str(len(missing_required) + int(unmet)),
        "skipped": str(n_missing - len(missing_required)),
    }
    suites = ET.Element("testsuites", counts)
    suite = ET.SubElement(suites, "testsuite", {"name": CLASS_NAME, **counts})
    properties = ET.SubElement(suite, "properties")
    for name, value in (
        ("manifest_sha256", coverage.manifest_sha256),
        ("n_parts", str(n_parts)),
        ("n_received_parts", str(len(received))),
        ("n_missing_parts", str(n_missing)),
        ("n_rows", str(coverage.n_rows)),
        ("n_received_rows", str(coverage.n_received_rows)),
        ("n_missing_rows", str(coverage.n_rows - coverage.n_received_rows)),
        ("native_validation_exit_code", "0"),
        ("exit_code", "4" if unmet else "0"),
    ):
        ET.SubElement(properties, "property", {"name": name, "value": value})
    overall = ET.SubElement(suite, "testcase", {"classname": CLASS_NAME, "name": "overall"})
    if unmet:
        ET.SubElement(
            overall, "error", {"type": "IncompleteAnnotationReturns", "message": "required original parts missing"}
        )
    for index, n_rows in enumerate(coverage.expected_rows, 1):
        case = ET.SubElement(suite, "testcase", {"classname": CLASS_NAME, "name": str(index)})
        props = ET.SubElement(case, "properties")
        ET.SubElement(props, "property", {"name": "n_rows", "value": str(n_rows)})
        if index not in received:
            ET.SubElement(
                case,
                "error" if index in missing_required else "skipped",
                {"type": "MissingOriginalPart", "message": "original part not supplied"}
                if index in missing_required
                else {"message": "original part not supplied"},
            )
    raw = bytes(_render(suites), "utf-8")
    _require(len(raw) <= MAX_JUNIT_BYTES)
    return raw
