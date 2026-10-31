"""Whole original-target saved screens with held adjudication-source consistency.

No inference, CSV reconstruction, original queue/key lookup or human authentication.
The work policy charges n*n for EACH present logical report, record and capture;
it is not a runtime/operation-count/heap guarantee. Individual role limits do not
imply that a multi-role population fits the combined policy.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any, cast

from quantfit import bundle, resolution
from quantfit import saved_screen as saved
from quantfit.adjudication_record import MAX_RECORD_BYTES, _flagged, _record_report_match, _record_structure
from quantfit.junit import screen_to_junit
from quantfit.reproduce import (
    CANONICAL_CHAT_TEMPLATE_POLICIES,
    _canonical_receiving_path,
    _publish_reproduction_outputs,
    _ReproductionOutputs,
    _validate_reproduction_outputs,
)
from quantfit.safety.adjudication import _capture_selection, _match_selected_record
from quantfit.safety.calibration_binding import _same_numbers, identity_fingerprint, measurement_identity
from quantfit.safety.calibration_inputs import _SEPARATORS, MAX_CAPTURE_BYTES, MAX_CAPTURE_RECORDS, _capture
from quantfit.safety.gguf_arm import is_gguf_ref
from quantfit.safety.report import DriftReport
from quantfit.safety.retained_labels import _binding, _json
from quantfit.safety.verify import Probe, _tabulate
from quantfit.screen import SUMMARY_FILENAME, Target

MAX_ADJUDICATION_BYTES = 64 * 1024 * 1024
MAX_ANALYSIS_WORK = resolution.MAX_PROBES**2
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
SCOPE = (
    "Held supplied-source consistency over every original manifest target. Operator declarations are "
    "unauthenticated; unresolved declarations may be source-complete. Missing reports retain null native "
    "counts. Native flags, statistical rules, control declarations, sensitivity and scientific GO are "
    "unchanged. Original preparation and review queues are unverified declarations. No fresh inference, "
    "independence, weight/host authentication or human truth is established."
)


def _inventory(root: Path, allowed: set[str], cap: int) -> dict[str, tuple[int, int, int, int]]:
    bundle._no_links(root)
    saved._require(root.is_dir(), "invalid_source_directory")
    result: dict[str, tuple[int, int, int, int]] = {}
    with os.scandir(root) as scan:
        for entry in scan:
            saved._require(entry.name in allowed and len(result) < len(allowed), "unsupported_directory_member")
            path = root / entry.name
            bundle._no_links(path)
            info = path.lstat()
            saved._require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= cap, "invalid_source_member")
            # Regular hardlinks are native saved-screen inputs, not blanket-refused.
            result[entry.name] = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    return result


def _capture_count(raw: bytes) -> int:
    """Bound native recognized records and exact header n before its range reader."""
    text = raw.decode("utf-8")
    records, last = 0, 0
    for match in _SEPARATORS.finditer(text):
        records += 1
        last = match.end()
        saved._require(records <= MAX_CAPTURE_RECORDS, "invalid_capture")
    records += int(last < len(text))
    saved._require(0 < records <= MAX_CAPTURE_RECORDS, "invalid_capture")
    first = next(line for line in text.splitlines() if line.strip())
    value = _json(first.encode("utf-8"))
    n = value.get("n_pairs")
    saved._require(type(n) is int and 0 < n <= resolution.MAX_PROBES, "invalid_capture")
    return cast(int, n)


def _capture_protocol(header: dict[str, Any], target: Target, n: int) -> dict[str, Any]:
    saved._require(header["capture_schema"] == 2 and header["binding"] is not None, "invalid_capture")
    identity = header["binding"]["identity"]
    saved._require(
        header["baseline"] == target.baseline == identity["baseline"]["model"]
        and header["quant"] == target.quant == identity["quantized"]["model"]
        and identity["probe_dataset"]["n_probes"] == n,
        "capture_target_mismatch",
    )
    saved._require(
        all(is_gguf_ref(ref) == (target.stratum == "gguf") for ref in (target.baseline, target.quant)),
        "incompatible_scope",
    )
    decode = identity["decode"]
    return saved._protocol_fields(
        identity["judge"],
        identity["probe_dataset"],
        decode,
        identity["env"],
        identity["baseline"],
        identity["quantized"],
        target,
        chat_canonical=isinstance(decode.get("chat_template"), str)
        and decode["chat_template"].strip() in CANONICAL_CHAT_TEMPLATE_POLICIES,
        greedy=decode.get("greedy"),
        observed=False,
    )


def _encode(value: dict[str, Any], remaining: int, *, sort_keys: bool = False) -> bytes:
    data = bytearray()
    for piece in json.JSONEncoder(indent=2, ensure_ascii=True, allow_nan=False, sort_keys=sort_keys).iterencode(value):
        raw = piece.encode("utf-8")
        saved._require(len(data) + len(raw) + 1 <= remaining, "output_byte_limit")
        data.extend(raw)
    data.extend(b"\n")
    return bytes(data)


def _buffers(result: dict[str, Any], junit: bool) -> tuple[bytes, bytes, bytes | None]:
    from quantfit.cli import _json_document

    plain = _encode(result, MAX_OUTPUT_BYTES, sort_keys=True)
    envelope = _encode(_json_document("adjudicate screen", result["exit_code"], result), MAX_OUTPUT_BYTES - len(plain))
    xml = screen_to_junit(result).encode("utf-8") if junit else None
    saved._require(
        len(plain) + len(envelope) + (len(xml) if xml is not None else 0) <= MAX_OUTPUT_BYTES, "output_byte_limit"
    )
    return plain, envelope, xml


def append_junit_cases(suite: ET.Element, section: dict[str, Any]) -> None:
    required = section["require_source_complete"]
    for row in section["rows"]:
        for criterion, good, not_required in (
            ("capture_source", row["capture_status"] == "source_matched", False),
            ("record_source", row["record_status"] == "source_matched", row["record_required"] is False),
        ):
            case = ET.SubElement(
                suite, "testcase", {"name": f"{row['name']}:{criterion}", "classname": "quantfit.screen-adjudication"}
            )
            if not required or not_required:
                ET.SubElement(case, "skipped", {"message": "not_requested" if not required else "not_required"})
            elif not good:
                ET.SubElement(case, "error", {"type": "SourceUnavailable", "message": "source_incomplete"})
    case = ET.SubElement(
        suite, "testcase", {"name": "source_completeness", "classname": "quantfit.screen-adjudication"}
    )
    if not required:
        ET.SubElement(case, "skipped", {"message": "not_requested"})
    elif not section["source_complete"]:
        ET.SubElement(case, "error", {"type": "SourceUnavailable", "message": "source_incomplete"})


def _receive(
    manifest_path: str,
    reports_dir: str,
    *,
    adjudications_dir: str | None = None,
    captures_dir: str | None = None,
    require_source_complete: bool = False,
    out_path: str | None = None,
    junit_path: str | None = None,
) -> tuple[dict[str, Any], bytes]:
    saved._require(type(require_source_complete) is bool, "invalid_adjudication_mode")
    phase = "unsafe_output"
    try:
        manifest = Path(_canonical_receiving_path(manifest_path))
        roots = {"report": Path(_canonical_receiving_path(reports_dir))}
        if adjudications_dir is not None:
            roots["record"] = Path(_canonical_receiving_path(adjudications_dir))
        if captures_dir is not None:
            roots["capture"] = Path(_canonical_receiving_path(captures_dir))
        outputs = tuple(Path(_canonical_receiving_path(p)) for p in (out_path, junit_path) if p is not None)
        _validate_reproduction_outputs(_ReproductionOutputs((manifest,), tuple(roots.values()), outputs))
        phase = "invalid_manifest"
        manifest_raw = bundle._read(manifest, saved.MAX_MANIFEST_BYTES)
        manifest_stat = manifest.stat()
        _, targets, _ = saved._manifest(manifest_raw)
        names = {
            "report": {f"{t.name}.json" for t in targets} | {SUMMARY_FILENAME},
            "record": {f"{t.name}.json" for t in targets},
            "capture": {f"{t.name}.capture.jsonl" for t in targets},
        }
        caps = {"report": saved.MAX_REPORT_BYTES, "record": MAX_RECORD_BYTES, "capture": MAX_CAPTURE_BYTES}
        sources = (manifest, *[root / name for role, root in roots.items() for name in sorted(names[role])])
        plan = _ReproductionOutputs(sources, tuple(roots.values()), outputs)
        _validate_reproduction_outputs(plan)
        phase = "invalid_adjudication_sources"
        # Inventory ALL roles before holding ANY measurement-role files.
        inventories = {role: _inventory(root, names[role], caps[role]) for role, root in roots.items()}
        saved._require(sum(v[2] for v in inventories["report"].values()) <= saved.MAX_TOTAL_BYTES, "report_byte_limit")
        saved._require(
            sum(v[2] for role, inv in inventories.items() if role != "report" for v in inv.values())
            <= MAX_ADJUDICATION_BYTES,
            "adjudication_byte_limit",
        )
        held: dict[str, dict[str, bytes]] = {}
        report_remaining, additional_remaining = saved.MAX_TOTAL_BYTES, MAX_ADJUDICATION_BYTES
        for role, root in roots.items():
            held[role] = {}
            for name in sorted(inventories[role]):
                remaining = report_remaining if role == "report" else additional_remaining
                saved._require(remaining > 0, "source_byte_limit")
                raw = bundle._read(root / name, min(caps[role], remaining))
                saved._require(len(raw) <= remaining, "source_byte_limit")
                held[role][name] = raw
                if role == "report":
                    report_remaining -= len(raw)
                else:
                    additional_remaining -= len(raw)

        def recheck() -> None:
            _validate_reproduction_outputs(plan)
            saved._require(manifest.stat() == manifest_stat, "source_inventory_changed")
            saved._require(
                all(_inventory(root, names[role], caps[role]) == inventories[role] for role, root in roots.items()),
                "source_inventory_changed",
            )

        recheck()
        parsed: dict[str, DriftReport] = {}
        records: dict[str, dict[str, Any]] = {}
        selections: dict[
            str, tuple[dict[int, tuple[str, dict[str, Any], dict[str, Any]]], list[Probe], list[bool], list[bool]]
        ] = {}
        work = 0
        scopes: dict[str, dict[str, Any]] = {}
        hashes: set[str] = set()
        pairs: set[tuple[object, ...]] = set()
        if SUMMARY_FILENAME in held["report"]:
            bundle._json(held["report"][SUMMARY_FILENAME])
        # All structural, scope, available byte/fingerprint and selected digest
        # checks precede native statistics. No fake report/held-file adapters.
        for target in targets:
            report_raw = held["report"].get(f"{target.name}.json")
            record_raw = held.get("record", {}).get(f"{target.name}.json")
            capture_raw = held.get("capture", {}).get(f"{target.name}.capture.jsonl")
            if report_raw is not None:
                bundle._json(report_raw)
                report = resolution.parse_report_bytes(report_raw)
                resolution._axes(report)
                n = report.drift["n_probes"]
                bundle._report_shape(report)
                protocol = saved._protocol(report, target, report_raw)
                saved._require(target.stratum not in scopes or scopes[target.stratum] == protocol, "incompatible_scope")
                scopes[target.stratum] = protocol
                sha = hashlib.sha256(report_raw).hexdigest()
                tokens = saved._pair_tokens(report, target.stratum)
                saved._require(sha not in hashes and not pairs.intersection(tokens), "duplicate_evidence")
                hashes.add(sha)
                pairs.update(tokens)
                parsed[f"{target.name}.json"] = report
                work += n * n
            if record_raw is not None:
                record = _record_structure(record_raw)
                records[target.name] = record
                work += record["n_probes"] ** 2
                if report_raw is not None:
                    _record_report_match(record, parsed[f"{target.name}.json"], report_raw)
            if capture_raw is not None:
                n = _capture_count(capture_raw)
                header, captured = _capture(capture_raw, n)
                capture_protocol = _capture_protocol(header, target, n)
                selected = _capture_selection(n, captured)
                # These are structural metadata counts, not inferred report
                # statistics or native counts for an unavailable report.
                expected = Counter(probe.expected for probe in selected[1])
                zones = Counter(probe.zone for probe in selected[1])
                capture_protocol["input_population"] = {
                    "expected_unsafe_n": expected["unsafe"],
                    "expected_safe_n": expected["safe"],
                    "by_zone": dict(zones),
                }
                saved._require(
                    target.stratum not in scopes or scopes[target.stratum] == capture_protocol, "incompatible_scope"
                )
                scopes[target.stratum] = capture_protocol
                selections[target.name] = selected
                work += n * n
                if report_raw is not None:
                    identity = measurement_identity(parsed[f"{target.name}.json"])
                    saved._require(
                        header["binding"]["identity"] == identity
                        and header["binding"]["fingerprint"] == identity_fingerprint(identity),
                        "capture_report_mismatch",
                    )
                if record_raw is not None:
                    record = records[target.name]
                    saved._require(
                        record["n_probes"] == n and record["binding_fingerprint"] == header["binding"]["fingerprint"],
                        "capture_record_mismatch",
                    )
                    _same_numbers(record["inputs"]["capture"], _binding(capture_raw), "actual capture")
                    _match_selected_record(selected[0], record)
        saved._require(work <= MAX_ANALYSIS_WORK, "analysis_work_limit")

        result = saved._summarize_held(
            manifest_raw,
            held["report"],
            manifest_path=str(manifest),
            reports_dir=str(roots["report"]),
            _prepared=parsed,
        )
        source_rows = []
        for target in targets:
            row_report = parsed.get(f"{target.name}.json")
            row_record = records.get(target.name)
            row_selected = selections.get(target.name)
            if row_report is not None and row_selected is not None:
                _same_numbers(row_report.drift, _tabulate(*row_selected[1:]).to_dict(), "actual capture tabulation")
            flags = None if row_report is None else _flagged(row_report)
            record_required = None if flags is None else sum(flags.values()) > 0
            capture_status = (
                "missing" if row_selected is None else "pending_report" if row_report is None else "source_matched"
            )
            record_status = (
                "missing"
                if row_record is None
                else "pending_report"
                if row_report is None
                else "report_matched_capture_missing"
                if row_selected is None
                else "source_matched"
            )
            source_complete = capture_status == "source_matched" and (
                record_required is False or record_status == "source_matched"
            )
            bindings = {}
            for role, suffix in (("report", ".json"), ("record", ".json"), ("capture", ".capture.jsonl")):
                role_raw = held.get(role, {}).get(target.name + suffix)
                bindings[role] = None if role_raw is None else _binding(role_raw)
            source_rows.append(
                {
                    "name": target.name,
                    "inputs": bindings,
                    "native_n_probes": None if row_report is None else row_report.probe_dataset["n_probes"],
                    "native_flagged_counts": flags,
                    "record_required": record_required,
                    "record_coverage_complete": row_report is not None
                    and (record_required is False or row_record is not None),
                    "capture_status": capture_status,
                    "record_status": record_status,
                    "source_complete": source_complete,
                    "declared_n_probes": None if row_record is None else row_record["n_probes"],
                    "declared_counts": None if row_record is None else row_record["counts"],
                    "operator_resolution": (
                        "unresolved" if any(v["unresolved"] for v in row_record["counts"].values()) else "resolved"
                    )
                    if row_record is not None
                    else "not_required"
                    if record_required is False
                    else "unknown"
                    if row_report is None
                    else "missing",
                }
            )
        complete = all(row["source_complete"] for row in source_rows)
        result["screen_adjudication"] = {
            "schema_version": 1,
            "rows": source_rows,
            "source_complete": complete,
            "require_source_complete": require_source_complete,
            "record_coverage_complete": all(row["record_coverage_complete"] for row in source_rows),
            "native_exit_code": result["exit_code"],
            "native_outcome": result["outcome"],
            "analysis_work": {
                "policy": "sum_of_each_present_logical_role_n_squared",
                "units": work,
                "limit": MAX_ANALYSIS_WORK,
                "runtime_bound": False,
            },
            "human_labels_authenticated": False,
            "original_queue_verified": False,
            "original_preparation_verified": False,
            "source_authenticity_verified": False,
            "scientific_go": False,
            "scope": SCOPE,
        }
        if require_source_complete and not complete and result["exit_code"] == 0:
            result["exit_code"], result["outcome"] = 4, "incomplete_adjudication_sources"
        phase = "unsafe_output"
        plain, envelope, xml = _buffers(result, junit_path is not None)
        buffers: list[tuple[Path, bytes]] = []
        if out_path is not None:
            buffers.append((outputs[0], plain))
        if junit_path is not None:
            assert xml is not None
            buffers.append((outputs[-1], xml))
        recheck()
        if outputs:
            _publish_reproduction_outputs(plan, buffers, recheck=recheck)
        return result, envelope
    except saved.SavedScreenError:
        raise
    except (
        KeyboardInterrupt,
        RuntimeError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        RecursionError,
        ImportError,
    ):
        raise saved.SavedScreenError(phase) from None


def summarize_screen_adjudication(
    manifest_path: str,
    reports_dir: str,
    *,
    adjudications_dir: str | None = None,
    captures_dir: str | None = None,
    require_source_complete: bool = False,
    out_path: str | None = None,
    junit_path: str | None = None,
) -> dict[str, Any]:
    """Hold once and preserve native 3>4>0; opt-in can only change native 0 to 4.

    Role encoded caps: manifest1MiB, reports8MiB each/64MiB combined, records4MiB
    and captures16MiB each/64MiB additional combined. All roles are structurally
    prepared before native statistics and the shared sum(n*n)<=4096**2 policy.
    Bare JSON + exact CLI JSON envelope + requested JUnit share32MiB. Every
    requested complete buffer is admitted before per-file atomic replacement;
    this is not a multi-file transaction or a hostile-filesystem guarantee.
    """
    return _receive(
        manifest_path,
        reports_dir,
        adjudications_dir=adjudications_dir,
        captures_dir=captures_dir,
        require_source_complete=require_source_complete,
        out_path=out_path,
        junit_path=junit_path,
    )[0]
