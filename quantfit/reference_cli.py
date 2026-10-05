"""Offline access to declared reference registries and exact artifact-byte checks."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, fields
from pathlib import Path

from quantfit import refreports

MAX_REGISTRY_BYTES = 1024 * 1024
_COMMIT = re.compile(r"[0-9a-f]{40}")
_ENTRY_FIELDS = {field.name for field in fields(refreports.ReferenceReport)}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise refreports.RefReportError(f"duplicate registry key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise refreports.RefReportError(f"nonfinite registry value: {value}")


def _registry(path: str | None) -> tuple[tuple, dict]:
    source = {
        "official_registry": path is None,
        "registry_source": "bundled" if path is None else str(path),
        "registry_sha256": None,
        "publication_verified": False,
        "scope": "Offline declared-registry and exact-byte checks; no measurement or publication verification.",
    }
    if path is None:
        return refreports.REGISTRY, source
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(MAX_REGISTRY_BYTES + 1)
        if len(raw) > MAX_REGISTRY_BYTES:
            raise refreports.RefReportError("reference registry exceeds 1 MiB")
        data = json.loads(raw, object_pairs_hook=_object, parse_constant=_constant)
        if not isinstance(data, dict) or set(data) != {"refreport_schema_version", "reports"}:
            raise refreports.RefReportError("registry requires exactly refreport_schema_version and reports")
        if (
            type(data["refreport_schema_version"]) is not int
            or data["refreport_schema_version"] != refreports.REFREPORT_SCHEMA_VERSION
        ):
            raise refreports.RefReportError("unsupported reference registry schema")
        if not isinstance(data["reports"], list):
            raise refreports.RefReportError("registry reports must be an array")
        entries = []
        for row in data["reports"]:
            if not isinstance(row, dict) or set(row) != _ENTRY_FIELDS:
                raise refreports.RefReportError("each reference entry must contain exactly the ReferenceReport fields")
            if any(not isinstance(value, str) for key, value in row.items() if key != "hf_revision"):
                raise refreports.RefReportError("reference entry fields must be strings")
            revision = row["hf_revision"]
            if revision is not None and (not isinstance(revision, str) or not _COMMIT.fullmatch(revision)):
                raise refreports.RefReportError("hf_revision must be an immutable lowercase 40-hex commit or null")
            entries.append(refreports.ReferenceReport(**row))
        registry = refreports.validate_registry(entries)
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        raise refreports.RefReportError(f"unreadable reference registry {path}: {exc}") from exc
    source["registry_sha256"] = hashlib.sha256(raw).hexdigest()
    return registry, source


def list_references(registry_path: str | None = None) -> dict:
    """List declared entries with spec validity and immutable URLs, without fetching."""
    registry, source = _registry(registry_path)
    result = refreports.registry_validity(registry=registry)
    for entry, record in zip(registry, result["reports"]):
        record["declared_spec_validity"] = record.pop("verdict")
        record.pop("still_citable_at_its_own_spec_version")
        record["publication_verified"] = False
        record["citable"] = False
        record["reason"] = (
            f"Declared spec {entry.spec_version} compared with current spec {result['current_spec_version']}; "
            "this does not verify the declared run, publication or citation provenance."
        )
        record["rule"] = "Spec-version comparison of declarations only; no authenticity or publication verification."
        record["entry"] = asdict(entry)
        record["hf_url"] = refreports.hf_url(entry) if entry.hf_revision else None
    result["rule"] = "Spec-version comparison of declarations only; no authenticity or publication verification."
    return {**result, **source}


def verify_reference(slug: str, report_path: str, registry_path: str | None = None) -> dict:
    """Compare bytes with the selected declared entry; a mismatch is a result."""
    registry, source = _registry(registry_path)
    entry = refreports.find(slug, registry)
    result = refreports.verify_published(entry, report_path)
    result["declared_reference_citable"] = result["citable"]
    result["citable"] = False
    status = "MATCH" if result["matches"] else "MISMATCH"
    result["statement"] = (
        f"{status}: file SHA256 {result['actual_sha256']}; declared registry SHA256 {result['expected_sha256']}. "
        "This is an exact-byte comparison against a declaration. Publication, measurement validity and "
        "citation provenance are not authenticated."
    )
    return {**result, **source}
