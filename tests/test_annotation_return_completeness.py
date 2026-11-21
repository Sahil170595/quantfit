"""Native return validation gates original part coverage without publishing labels."""

import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest
from test_annotation_chunks import fill, prepare, read_rows, write_rows

from quantfit.safety import annotation_chunks as chunks


def inspect(source, roles, **kwargs):
    sheet, key, manifest, parts, _ = source
    return chunks.validate_annotation_returns(
        str(sheet), str(key), str(manifest), tuple((index, str(parts[index - 1])) for index in roles), **kwargs
    )


def command(source, roles, out):
    sheet, key, manifest, parts, _ = source
    argv = [
        sys.executable,
        "-B",
        "-m",
        "quantfit.cli",
        "calibrate",
        "chunks",
        "validate",
        "--sheet",
        str(sheet),
        "--key",
        str(key),
        "--manifest",
        str(manifest),
        "--out",
        str(out),
    ]
    for index in roles:
        argv += ["--part", f"{index}={parts[index - 1]}"]
    return argv


def test_required_partial_retains_native_census_and_all_original_xml_cases(tmp_path):
    source = prepare(tmp_path)
    fill(source[3])
    out, xml = tmp_path / "inspection.json", tmp_path / "inspection.xml"
    result = inspect(source, [4, 2], require_complete=True, out_path=str(out), junit_path=str(xml))
    assert result["annotation_returns_schema"] == 2
    assert result["completeness_requirement"] == {
        "requirement_schema": 1,
        "require_complete": True,
        "native_validation_exit_code": 0,
        "exit_code": 4,
    }
    assert result["received_part_indices"] == [2, 4] and result["missing_part_indices"] == [1, 3]
    assert result["n_received_rows"] == 8 and result["n_missing_rows"] == 10
    assert json.loads(out.read_bytes()) == result
    cases = list(ET.fromstring(xml.read_bytes()).iter("testcase"))
    assert [c.get("name") for c in cases] == ["overall", "1", "2", "3", "4"]
    assert [c.get("name") for c in cases if c.find("error") is not None] == ["overall", "1", "3"]


def test_false_with_junit_leaves_legacy_json_exact_and_missing_cases_skipped(tmp_path):
    source = prepare(tmp_path)
    fill(source[3])
    original = inspect(source, [4, 2])
    out, xml = tmp_path / "false.json", tmp_path / "false.xml"
    result = inspect(source, [4, 2], require_complete=False, out_path=str(out), junit_path=str(xml))
    assert result == original and out.read_bytes() == chunks._encode(original)
    assert result["annotation_returns_schema"] == 1 and "completeness_requirement" not in result
    cases = list(ET.fromstring(xml.read_bytes()).iter("testcase"))
    assert [c.get("name") for c in cases if c.find("skipped") is not None] == ["1", "3"]
    assert not any(c.find("error") is not None for c in cases)


def test_actual_os_cli_publishes_valid_partial_receipt_and_xml_before_exit_four(tmp_path):
    source = prepare(tmp_path)
    fill(source[3])
    out, xml = tmp_path / "cli.json", tmp_path / "cli.xml"
    process = subprocess.run(
        [*command(source, [2], out), "--require-complete", "--junit", str(xml), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    assert process.returncode == 4 and not process.stderr
    document = json.loads(process.stdout)
    assert document["exit_code"] == document["result"]["completeness_requirement"]["exit_code"] == 4
    assert document["result"] == json.loads(out.read_bytes()) and xml.exists()


def test_policy_exact_bool_admitted_before_any_private_io(monkeypatch):
    monkeypatch.setattr(chunks, "_held", lambda *a, **k: pytest.fail("invalid policy reached private IO"))
    with pytest.raises(chunks.AnnotationChunksError, match="^invalid_annotation_returns$"):
        chunks.validate_annotation_returns("PRIVATE", "PRIVATE", "PRIVATE", ((1, "PRIVATE"),), require_complete=1)


def test_late_bad_part_outranks_missing_required_coverage_without_any_output(tmp_path):
    source = prepare(tmp_path)
    fill(source[3])
    rows = read_rows(source[3][-1])
    rows[-1][2] = "PRIVATE_BAD_LABEL"
    write_rows(source[3][-1], rows)
    out, xml = tmp_path / "refused.json", tmp_path / "refused.xml"
    with pytest.raises(chunks.AnnotationChunksError, match="^invalid_annotation_returns$"):
        inspect(source, [1, 4], require_complete=True, out_path=str(out), junit_path=str(xml))
    assert not out.exists() and not xml.exists()


@pytest.fixture(autouse=True)
def receiving_only(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("return inspection attempted collection, ingestion, model or Hub execution")

    monkeypatch.setattr(chunks, "collect_annotation_chunks", forbidden)
    monkeypatch.setattr("quantfit.safety.calibrate.ingest_labels", forbidden)
    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)


@pytest.mark.parametrize(
    "mode,required,code",
    [
        ("partial", False, 0),
        ("partial", True, 4),
        ("complete", True, 0),
        ("reverse", True, 0),
        ("all_unusable", True, 0),
    ],
)
def test_actual_os_cli_native_modes_retain_coverage_and_originals(tmp_path, mode, required, code):
    source = prepare(tmp_path)
    fill(source[3], "unusable" if mode == "all_unusable" else "refusal")
    roles = [2] if mode == "partial" else [4, 3, 2, 1] if mode == "reverse" else [1, 2, 3, 4]
    inputs = [source[0], source[1], source[2], *source[3]]
    before = [p.read_bytes() for p in inputs]
    out, xml = tmp_path / "cli.json", tmp_path / "cli.xml"
    process = subprocess.run(
        [*command(source, roles, out), *(["--require-complete"] if required else []), "--junit", str(xml), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
        cwd=tmp_path,
    )
    assert process.returncode == code and not process.stderr
    result = json.loads(process.stdout)["result"]
    assert json.loads(out.read_bytes()) == result and len(list(ET.fromstring(xml.read_bytes()).iter("testcase"))) == 5
    assert result["complete"] is (mode != "partial") and [p.read_bytes() for p in inputs] == before
    if required:
        assert result["completeness_requirement"]["exit_code"] == code
    else:
        assert "completeness_requirement" not in result and result["annotation_returns_schema"] == 1


@pytest.mark.parametrize("policy", [None, 0, 1, "true", [], {}, object()])
def test_every_non_bool_policy_refuses_before_holds(monkeypatch, policy):
    monkeypatch.setattr(chunks, "_held", lambda *a, **k: pytest.fail("invalid policy reached holds"))
    with pytest.raises(chunks.AnnotationChunksError):
        chunks.validate_annotation_returns("PRIVATE", "PRIVATE", "PRIVATE", ((1, "PRIVATE"),), require_complete=policy)


@pytest.mark.parametrize("fault", ["empty", "duplicate", "bool", "float", "zero", "too_many", "not_tuple"])
def test_required_mode_keeps_exact_original_index_admission_before_holds(monkeypatch, fault):
    monkeypatch.setattr(chunks, "_held", lambda *a, **k: pytest.fail("invalid index reached holds"))
    roles = {
        "empty": (),
        "duplicate": ((1, "a"), (1, "b")),
        "bool": ((True, "a"),),
        "float": ((1.0, "a"),),
        "zero": ((0, "a"),),
        "too_many": tuple((i, "a") for i in range(1, 130)),
        "not_tuple": [(1, "a")],
    }[fault]
    with pytest.raises(chunks.AnnotationChunksError):
        chunks.validate_annotation_returns("PRIVATE", "PRIVATE", "PRIVATE", roles, require_complete=True)


@pytest.mark.parametrize("stored", ["0.17.3", "0.61.0"])
def test_stored_producer_manifest_is_reconstructed_with_its_original_version(tmp_path, stored):
    source = prepare(tmp_path)
    fill(source[3])
    manifest = json.loads(source[2].read_bytes())
    manifest["quantfit_version"] = stored
    source[2].write_bytes(chunks._encode(manifest))
    before = source[2].read_bytes()
    result = inspect(source, [4, 3, 2, 1], require_complete=True, junit_path=str(tmp_path / "stored.xml"))
    assert result["complete"] and result["completeness_requirement"]["exit_code"] == 0
    assert source[2].read_bytes() == before


def test_all_roles_held_once_sinks_admitted_before_private_parsing_and_single_publish(tmp_path, monkeypatch):
    source = prepare(tmp_path)
    fill(source[3])
    hold = Mock(wraps=chunks.hold)
    admit = chunks.admit_outputs
    read = chunks.calibrate._read_sheet
    joined = Mock(wraps=chunks.calibrate._join)
    published = Mock(wraps=chunks.publish)
    admitted = []
    out, xml = tmp_path / "held.json", tmp_path / "held.xml"

    def admission(paths, inputs):
        assert len(hold.call_args_list) == 5 and paths == (str(out), str(xml))
        targets = admit(paths, inputs)
        admitted.append(True)
        return targets

    def parsed(*args, **kwargs):
        assert admitted, "CSV parsing preceded sink admission"
        return read(*args, **kwargs)

    monkeypatch.setattr(chunks, "hold", hold)
    monkeypatch.setattr(chunks, "admit_outputs", admission)
    monkeypatch.setattr(chunks.calibrate, "_read_sheet", parsed)
    monkeypatch.setattr(chunks.calibrate, "_join", joined)
    monkeypatch.setattr(chunks, "publish", published)
    result = inspect(source, [4, 2], require_complete=True, out_path=str(out), junit_path=str(xml))
    paths = [call.args[0] for call in hold.call_args_list]
    assert len(paths) == len(set(paths)) == 5 and joined.call_count == 2 and published.call_count == 1
    assert len(published.call_args.args[0]) == 2 and result["completeness_requirement"]["exit_code"] == 4


@pytest.mark.parametrize("sink", ["json", "xml"])
@pytest.mark.parametrize("alias", ["sheet", "key", "manifest", "part", "mutual", "existing", "directory"])
def test_both_sink_roles_admit_after_holds_before_csv_and_preserve_sources(tmp_path, monkeypatch, sink, alias):
    source = prepare(tmp_path)
    fill(source[3])
    foreign = tmp_path / "existing"
    foreign.write_bytes(b"foreign operator work")
    roles = {
        "sheet": source[0],
        "key": source[1],
        "manifest": source[2],
        "part": source[3][0],
        "existing": foreign,
        "directory": tmp_path,
        "mutual": tmp_path / "same",
    }
    out, xml = tmp_path / "result.json", tmp_path / "result.xml"
    if alias == "mutual":
        out = xml = roles[alias]
    elif sink == "json":
        out = roles[alias]
    else:
        xml = roles[alias]
    held = Mock(wraps=chunks.hold)
    monkeypatch.setattr(chunks, "hold", held)
    monkeypatch.setattr(chunks, "_preparation", lambda *a, **k: pytest.fail("unsafe sink reached CSV preparation"))
    inputs = [source[0], source[1], source[2], source[3][0], foreign]
    before = [p.read_bytes() for p in inputs]
    with pytest.raises(chunks.AnnotationChunksError):
        inspect(source, [1], require_complete=True, out_path=str(out), junit_path=str(xml))
    assert held.call_count == 4 and [p.read_bytes() for p in inputs] == before
    assert not (tmp_path / "result.json").exists() and not (tmp_path / "result.xml").exists()


def test_requested_xml_cap_refuses_before_either_output_but_json_only_never_renders(tmp_path, monkeypatch):
    from quantfit.safety import annotation_returns_junit as junit

    source = prepare(tmp_path)
    fill(source[3])
    monkeypatch.setattr(junit, "MAX_JUNIT_BYTES", 1)
    out, xml = tmp_path / "bounded.json", tmp_path / "bounded.xml"
    with pytest.raises(chunks.AnnotationChunksError):
        inspect(source, [1], require_complete=True, out_path=str(out), junit_path=str(xml))
    assert not out.exists() and not xml.exists()
    trap = Mock(side_effect=AssertionError("JSON-only inspection rendered XML"))
    monkeypatch.setattr(junit, "_to_junit", trap)
    result = inspect(source, [1], require_complete=True, out_path=str(out))
    assert result["completeness_requirement"]["exit_code"] == 4 and out.exists()
    trap.assert_not_called()


@pytest.mark.parametrize("policy", [False, True])
def test_xml_and_json_are_private_count_hash_only_and_deterministic(tmp_path, policy):
    source = prepare(tmp_path)
    fill(source[3])
    manifest = json.loads(source[2].read_bytes())
    manifest["annotator_declared"] = {"role": "named_second", "name": "PRIVATE_RATER_CANARY"}
    source[2].write_bytes(chunks._encode(manifest))
    first, second = tmp_path / "first.xml", tmp_path / "second.xml"
    result = inspect(source, [4, 2], require_complete=policy, junit_path=str(first))
    reverse = inspect(source, [2, 4], require_complete=policy, junit_path=str(second))
    assert result == reverse and first.read_bytes() == second.read_bytes()
    public = json.dumps(result) + first.read_text(encoding="utf-8")
    key = json.loads(source[1].read_bytes())
    assert "PRIVATE_" not in public and key["salt"] not in public and str(tmp_path) not in public
    assert all(ident not in public for ident in key["ids"])
    root = ET.fromstring(first.read_bytes())
    assert all(c.get("classname") == "quantfit.annotation_returns" for c in root.iter("testcase"))
    assert all(
        p.get("name") == "manifest_sha256" or p.get("value").isascii() and p.get("value").isdecimal()
        for p in root.iter("property")
    )


@pytest.mark.parametrize(
    "fault",
    [
        "rows_list",
        "empty",
        "too_many",
        "bool_row",
        "zero_row",
        "huge_row",
        "row_census",
        "received_list",
        "received_empty",
        "duplicate",
        "reversed",
        "foreign_index",
        "bool_index",
        "received_census",
        "bool_census",
        "policy",
        "hash",
        "foreign_type",
    ],
)
def test_forged_or_contradictory_private_projection_refuses_before_xml(monkeypatch, fault):
    from quantfit.safety import annotation_returns_junit as junit

    projection = junit._Coverage((5, 5, 5, 3), (2, 4), 18, 8, True, "a" * 64)
    values = {
        "rows_list": {"expected_rows": [5, 5, 5, 3]},
        "empty": {"expected_rows": ()},
        "too_many": {"expected_rows": (1,) * 129, "n_rows": 129},
        "bool_row": {"expected_rows": (True, 5, 5, 3)},
        "zero_row": {"expected_rows": (0, 5, 5, 3)},
        "huge_row": {"expected_rows": (10**1000, 5, 5, 3)},
        "row_census": {"n_rows": 17},
        "received_list": {"received_part_indices": [2, 4]},
        "received_empty": {"received_part_indices": ()},
        "duplicate": {"received_part_indices": (2, 2)},
        "reversed": {"received_part_indices": (4, 2)},
        "foreign_index": {"received_part_indices": (2, 5)},
        "bool_index": {"received_part_indices": (True, 4)},
        "received_census": {"n_received_rows": 7},
        "bool_census": {"n_received_rows": True},
        "policy": {"require_complete": 1},
        "hash": {"manifest_sha256": "PRIVATE"},
    }
    projection = {} if fault == "foreign_type" else replace(projection, **values[fault])
    trap = lambda *a, **k: pytest.fail("invalid projection reached XML construction")
    monkeypatch.setattr(junit, "ET", SimpleNamespace(Element=trap, SubElement=trap))
    with pytest.raises(chunks.AnnotationChunksError, match="^invalid_annotation_returns$"):
        junit._to_junit(projection)


def test_real_native_maximum_128_parts_has_129_ordered_cases_and_all_unusable_is_valid(tmp_path):
    from test_annotation_chunks import ROOT

    spec = importlib.util.spec_from_file_location(
        "large_native_return_fixture", ROOT / "tools/ci_label_reconciliation.py"
    )
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    sheet, _, key, _ = helper.fixture(tmp_path / "private", ROOT, n=64, mode="agreement")
    rows = read_rows(sheet)
    for row in rows[1:]:
        row[2] = ""
    write_rows(sheet, rows, bom=True)
    directory = tmp_path / "parts"
    directory.mkdir()
    chunks.prepare_annotation_chunks(str(sheet), str(key), out_dir=str(directory), rows_per_part=1)
    parts = sorted(directory.glob("part-*.labels.csv"))
    fill(parts, "unusable")
    source = (sheet, key, directory / "annotation.chunkmanifest.json", parts, None)
    xml = tmp_path / "maximum.xml"
    result = inspect(source, list(reversed(range(1, 129))), require_complete=True, junit_path=str(xml))
    assert (
        result["n_rows"] == result["n_received_rows"] == result["n_parts"] == 128
        and result["completeness_requirement"]["exit_code"] == 0
    )
    cases = list(ET.fromstring(xml.read_bytes()).iter("testcase"))
    assert [c.get("name") for c in cases] == ["overall", *[str(i) for i in range(1, 129)]] and len(
        xml.read_bytes()
    ) <= 64 * 1024
    assert not any(c.find("skipped") is not None or c.find("error") is not None for c in cases)


@pytest.mark.parametrize("timing", ["during_staging", "after_checkpoint"])
def test_native_source_stamp_checkpoint_and_held_snapshot_are_preserved(tmp_path, monkeypatch, timing):
    from quantfit.safety import retention_io

    source = prepare(tmp_path)
    fill(source[3])
    original = source[3][0].read_bytes()
    out, xml = tmp_path / "snapshot.json", tmp_path / "snapshot.xml"
    native_stage, native_open = retention_io.tempfile.mkstemp, retention_io.os.open
    changed = []

    def mutate():
        if not changed:
            source[3][0].write_bytes(original + b"\n")
            changed.append(True)

    def stage(*args, **kwargs):
        value = native_stage(*args, **kwargs)
        if timing == "during_staging":
            mutate()
        return value

    def opened(path, flags, *args, **kwargs):
        if timing == "after_checkpoint" and Path(path) == out and flags & os.O_EXCL:
            mutate()
        return native_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(retention_io.tempfile, "mkstemp", stage)
    monkeypatch.setattr(retention_io.os, "open", opened)
    if timing == "during_staging":
        with pytest.raises(chunks.AnnotationChunksError):
            inspect(source, [1], require_complete=True, out_path=str(out), junit_path=str(xml))
        assert not out.exists() and not xml.exists()
    else:
        result = inspect(source, [1], require_complete=True, out_path=str(out), junit_path=str(xml))
        assert result["completeness_requirement"]["exit_code"] == 4 and out.exists() and xml.exists()
        import hashlib

        assert result["parts"][0]["filled_sheet"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert changed and not list(tmp_path.glob(".quantfit-retain-*"))


@pytest.mark.parametrize("fault", ["second_write", "existing_second", "ancestor_substitution"])
def test_late_publication_failure_preserves_first_and_foreign_outputs(tmp_path, monkeypatch, fault):
    from quantfit.safety import retention_io

    source = prepare(tmp_path)
    fill(source[3])
    parent = tmp_path / "xml-parent"
    parent.mkdir()
    out, xml = tmp_path / "first.json", parent / "second.xml"
    native_open, native_sync = retention_io.os.open, retention_io.os.fsync
    first_fd = []
    changed = []

    def opened(path, flags, *args, **kwargs):
        if Path(path) == xml and flags & os.O_EXCL:
            assert json.loads(out.read_bytes())["completeness_requirement"]["exit_code"] == 4
            if fault == "existing_second":
                xml.write_bytes(b"foreign XML operator work")
            if fault == "second_write":
                raise OSError("PRIVATE second output fault")
        fd = native_open(path, flags, *args, **kwargs)
        if Path(path) == out and flags & os.O_EXCL:
            first_fd.append(fd)
        return fd

    def sync(fd):
        native_sync(fd)
        if fault == "ancestor_substitution" and first_fd and fd == first_fd[0] and not changed:
            parent.rename(tmp_path / "moved-xml-parent")
            parent.mkdir()
            (parent / "foreign").write_bytes(b"preserve")
            changed.append(True)

    monkeypatch.setattr(retention_io.os, "open", opened)
    monkeypatch.setattr(retention_io.os, "fsync", sync)
    with pytest.raises(chunks.AnnotationChunksError, match="^invalid_annotation_returns$"):
        inspect(source, [1], require_complete=True, out_path=str(out), junit_path=str(xml))
    assert out.exists() and json.loads(out.read_bytes())["completeness_requirement"]["exit_code"] == 4
    if fault == "existing_second":
        assert xml.read_bytes() == b"foreign XML operator work"
    elif fault == "ancestor_substitution":
        assert (parent / "foreign").read_bytes() == b"preserve" and (tmp_path / "moved-xml-parent").is_dir()
    else:
        assert not xml.exists()


def test_without_outputs_native_held_check_still_overrides_valid_missing_requirement(tmp_path, monkeypatch):
    source = prepare(tmp_path)
    fill(source[3])
    native = chunks.calibrate._join

    def changed(*args, **kwargs):
        result = native(*args, **kwargs)
        source[3][0].write_bytes(source[3][0].read_bytes() + b"\n")
        return result

    monkeypatch.setattr(chunks.calibrate, "_join", changed)
    monkeypatch.setattr(chunks, "publish", lambda *a, **k: pytest.fail("no-output validation published"))
    with pytest.raises(chunks.AnnotationChunksError):
        inspect(source, [1], require_complete=True)


def test_actual_os_cli_late_xml_failure_exits_two_and_preserves_first_required_four_receipt(tmp_path):
    source = prepare(tmp_path)
    fill(source[3])
    out, xml = tmp_path / "first.json", tmp_path / "second.xml"
    program = """
import os, sys
from pathlib import Path
from quantfit.safety import retention_io
from quantfit.cli import main
xml = Path(sys.argv[1])
native = retention_io.os.open
def opened(path, flags, *args, **kwargs):
    if Path(path) == xml and flags & os.O_EXCL:
        raise OSError('PRIVATE late XML write failure')
    return native(path, flags, *args, **kwargs)
retention_io.os.open = opened
raise SystemExit(main(sys.argv[2:]))
"""
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            program,
            str(xml),
            *command(source, [1], out)[4:],
            "--require-complete",
            "--junit",
            str(xml),
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
        cwd=tmp_path,
    )
    assert process.returncode == 2 and not process.stderr
    document = json.loads(process.stdout)
    assert document["result"] is None and document["error"]["message"] == "invalid_annotation_returns"
    assert json.loads(out.read_bytes())["completeness_requirement"]["exit_code"] == 4 and not xml.exists()
    assert "PRIVATE" not in process.stdout and not list(tmp_path.glob(".quantfit-retain-*"))
