"""Whole-original-target adjudication receiving preserves native measurement outcomes."""

import contextlib
import io
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tools.ci_screen_adjudication import fixture

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "mode,n,missing,code",
    [("zero", 2, (), 0), ("mixed", 3, (), 3), ("all", 3, (), 3), ("unresolved", 3, (), 3), ("zero", 3, ("beta",), 4)],
)
def test_genuine_whole_original_native_producer_and_summary(tmp_path, mode, n, missing, code):
    from quantfit.saved_screen import summarize_screen

    manifest, reports, _records, _captures = fixture(tmp_path, ROOT, mode, n, missing)
    result = summarize_screen(str(manifest), str(reports))
    assert result["exit_code"] == code
    assert [row["name"] for row in result["rows"]] == ["gamma", "alpha", "beta"][:n]
    assert all(row["human_verified"] is None for row in result["rows"])
    assert result["n_regressed_human_verified"] == 0 and result["scientific_go"] is False
    assert all(not path.exists() for path in (tmp_path / "private").rglob("*.adjudication.csv"))
    assert all(not path.exists() for path in (tmp_path / "private").rglob("*.adjudication-preparation.json"))


def test_public_whole_screen_adjudication_api_is_available(tmp_path):
    import quantfit.saved_screen as saved

    manifest, reports, records, captures = fixture(tmp_path, ROOT)
    summarize = getattr(saved, "summarize_screen_adjudication", None)
    assert callable(summarize), "whole-screen adjudication receiving API is absent"
    result = summarize(str(manifest), str(reports), adjudications_dir=str(records), captures_dir=str(captures))
    assert len(result["screen_adjudication"]["rows"]) == 3 and result["exit_code"] == 3


def test_public_whole_screen_adjudication_cli_is_available(tmp_path):
    from quantfit.cli import main

    manifest, reports, records, _captures = fixture(tmp_path, ROOT, "zero", 2)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(
                [
                    "adjudicate",
                    "screen",
                    "--targets",
                    str(manifest),
                    "--reports-dir",
                    str(reports),
                    "--adjudications-dir",
                    str(records),
                    "--json",
                ]
            )
        except SystemExit as exc:
            code = exc.code
    assert code == 0, f"whole-screen adjudication CLI is absent: {code}"
    assert not err.getvalue()
    result = json.loads(out.getvalue())["result"]
    assert len(result["screen_adjudication"]["rows"]) == 2 and result["exit_code"] == 0


def receive(paths, **kwargs):
    from quantfit import summarize_screen_adjudication

    manifest, reports, records, captures = paths
    return summarize_screen_adjudication(
        str(manifest), str(reports), adjudications_dir=str(records), captures_dir=str(captures), **kwargs
    )


@pytest.mark.parametrize(
    "mode,n,missing,code",
    [("zero", 2, (), 0), ("mixed", 3, (), 3), ("all", 3, (), 3), ("unresolved", 3, (), 3), ("zero", 3, ("beta",), 4)],
)
@pytest.mark.parametrize("require", [False, True])
def test_complete_population_native_priority_and_source_resolution(tmp_path, mode, n, missing, code, require):
    paths = fixture(tmp_path, ROOT, mode, n, missing)
    xml = tmp_path / "all.xml"
    value = receive(paths, require_source_complete=require, junit_path=str(xml))
    section = value["screen_adjudication"]
    assert value["exit_code"] == section["native_exit_code"] == code
    assert [r["name"] for r in section["rows"]] == ["gamma", "alpha", "beta"][:n]
    assert section["source_complete"] is (not missing)
    assert value["n_regressed_human_verified"] == 0 and value["scientific_go"] is False
    if mode == "unresolved":
        assert all(row["operator_resolution"] == "unresolved" and row["source_complete"] for row in section["rows"])
    if missing:
        row = section["rows"][-1]
        assert row["native_n_probes"] is row["native_flagged_counts"] is row["record_required"] is None
        assert row["capture_status"] == row["record_status"] == "pending_report"
    suite = ET.fromstring(xml.read_bytes())
    cases = suite.findall(".//testcase")
    assert int(suite.attrib["tests"]) == len(cases) == 3 * n + 1
    assert [case.attrib["name"] for case in cases[:n]] == ["gamma", "alpha", "beta"][:n]
    if not require:
        assert all(case.find("skipped").attrib["message"] == "not_requested" for case in cases[n:])


@pytest.mark.parametrize("mode,require,code", [("zero", False, 0), ("zero", True, 4), ("mixed", True, 3)])
def test_optional_missing_capture_does_not_clear_native_outcome(tmp_path, mode, require, code):
    from quantfit import summarize_screen_adjudication

    manifest, reports, records, _ = fixture(tmp_path, ROOT, mode, 2)
    value = summarize_screen_adjudication(
        str(manifest), str(reports), adjudications_dir=str(records), require_source_complete=require
    )
    assert value["exit_code"] == code and value["screen_adjudication"]["source_complete"] is False


@pytest.mark.parametrize("mode,expected", [("zero", True), ("mixed", False)])
def test_zero_flags_need_no_empty_record_but_flagged_pairs_do(tmp_path, mode, expected):
    from quantfit import summarize_screen_adjudication

    manifest, reports, _, captures = fixture(tmp_path, ROOT, mode, 2)
    value = summarize_screen_adjudication(
        str(manifest), str(reports), captures_dir=str(captures), require_source_complete=True
    )
    section = value["screen_adjudication"]
    assert section["source_complete"] is section["record_coverage_complete"] is expected
    assert all(row["record_required"] is (not expected) for row in section["rows"])


def test_pending_only_never_fills_native_counts(tmp_path):
    paths = fixture(tmp_path, ROOT, "mixed", 3, ("gamma", "alpha", "beta"))
    value = receive(paths, require_source_complete=True)
    assert value["exit_code"] == 4
    assert all(row["status"] == "missing_evidence" for row in value["rows"])
    assert all(
        row["native_n_probes"] is row["native_flagged_counts"] is None for row in value["screen_adjudication"]["rows"]
    )


def write_json(path, value):
    path.write_bytes((json.dumps(value, allow_nan=False) + "\n").encode())


@pytest.mark.parametrize(
    "mutation,pending",
    [
        (m, p)
        for m in ("capture_hash", "report_hash", "fingerprint", "selected", "axis", "baseline_hash", "quantized_hash")
        for p in (False, True)
        if not (p and m == "report_hash")
    ],
)
def test_available_crossbindings_refuse_contradictions(tmp_path, mutation, pending):
    from quantfit.saved_screen import SavedScreenError

    paths = fixture(tmp_path, ROOT, "mixed", 2, ("alpha",) if pending else ())
    record_path = paths[2] / "alpha.json"
    record = json.loads(record_path.read_bytes())
    if mutation in ("capture_hash", "report_hash"):
        record["inputs"][mutation.removesuffix("_hash")]["sha256"] = "0" * 64
    elif mutation == "fingerprint":
        record["binding_fingerprint"] = "0" * 64
    elif mutation == "selected":
        record["entries"][0]["pair"] = 10
    elif mutation == "axis":
        record["entries"][0]["axis"] = "over-refusal"
    else:
        record["entries"][0][mutation.replace("_hash", "_sha256")] = "0" * 64
    write_json(record_path, record)
    with pytest.raises(SavedScreenError):
        receive(paths)


@pytest.mark.parametrize("bad", [True, 12.0, 4097])
def test_pending_record_n_and_axis_domains_are_typed_before_math(tmp_path, monkeypatch, bad):
    from quantfit import bundle
    from quantfit.saved_screen import SavedScreenError

    paths = fixture(tmp_path, ROOT, "mixed", 2, ("alpha",))
    path = paths[2] / "alpha.json"
    value = json.loads(path.read_bytes())
    value["n_probes"] = bad
    write_json(path, value)
    calls = []
    monkeypatch.setattr(bundle, "_check_original_statistics", lambda *a: calls.append(1))
    with pytest.raises(SavedScreenError):
        receive(paths)
    assert not calls


@pytest.mark.parametrize("bad", [True, 4.0])
def test_pending_record_flagged_domains_do_not_seed_native_counts(tmp_path, monkeypatch, bad):
    from quantfit import bundle
    from quantfit.saved_screen import SavedScreenError

    paths = fixture(tmp_path, ROOT, "mixed", 2, ("alpha",))
    path = paths[2] / "alpha.json"
    value = json.loads(path.read_bytes())
    value["original_flagged_counts"]["refusal-robustness"] = bad
    write_json(path, value)
    calls = []
    monkeypatch.setattr(bundle, "_check_original_statistics", lambda *a: calls.append(1))
    with pytest.raises(SavedScreenError):
        receive(paths)
    assert not calls


@pytest.mark.parametrize("bad", ["n", "lines", "metadata", "json"])
def test_every_late_capture_structural_preflight_precedes_math(tmp_path, monkeypatch, bad):
    from quantfit import bundle
    from quantfit.saved_screen import SavedScreenError

    paths = fixture(tmp_path, ROOT, "mixed", 3)
    path = paths[3] / "beta.capture.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf8").splitlines()]
    if bad == "n":
        rows[0]["n_pairs"] = 4097
    elif bad == "metadata":
        rows[-1]["zone"] = "clear_safe" if rows[-1]["zone"] != "clear_safe" else "borderline"
    raw = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    path.write_bytes(raw + b"\n" * 16385 if bad == "lines" else b"{" if bad == "json" else raw)
    calls = []
    monkeypatch.setattr(bundle, "_check_original_statistics", lambda *a: calls.append(1))
    with pytest.raises(SavedScreenError):
        receive(paths)
    assert not calls


def test_combined_work_charges_all_logical_roles_before_statistics(tmp_path, monkeypatch):
    import quantfit.screen_adjudication as screen
    from quantfit import bundle
    from quantfit.saved_screen import SavedScreenError

    paths = fixture(tmp_path, ROOT, "mixed", 2)
    n = json.loads((paths[1] / "gamma.json").read_bytes())["probe_dataset"]["n_probes"]
    expected = 2 * 3 * n * n
    monkeypatch.setattr(screen, "MAX_ANALYSIS_WORK", expected - 1)
    calls = []
    original = bundle._check_original_statistics
    monkeypatch.setattr(bundle, "_check_original_statistics", lambda *a: calls.append(1) or original(*a))
    with pytest.raises(SavedScreenError, match="analysis_work_limit"):
        receive(paths)
    assert not calls
    monkeypatch.setattr(screen, "MAX_ANALYSIS_WORK", expected)
    value = receive(paths)
    assert value["screen_adjudication"]["analysis_work"]["units"] == expected and calls


def test_manifest_order_and_all_role_inventory_before_one_read_parse(tmp_path, monkeypatch):
    import quantfit.screen_adjudication as screen
    from quantfit import bundle, resolution

    paths = fixture(tmp_path, ROOT, "mixed", 3)
    inventory, reads, parses = [], [], []
    original_inventory, original_read, original_parse = screen._inventory, bundle._read, resolution.parse_report_bytes

    def track_inventory(root, *args):
        inventory.append(root)
        return original_inventory(root, *args)

    def track_read(path, *args):
        if path != paths[0]:
            assert set(paths[1:]) <= set(inventory)
        reads.append(path)
        return original_read(path, *args)

    def track_parse(raw):
        parses.append(1)
        return original_parse(raw)

    monkeypatch.setattr(screen, "_inventory", track_inventory)
    monkeypatch.setattr(bundle, "_read", track_read)
    monkeypatch.setattr(resolution, "parse_report_bytes", track_parse)
    result = receive(paths)
    assert [r["name"] for r in result["rows"]] == ["gamma", "alpha", "beta"]
    assert len(reads) == len(set(reads)) == 10 and len(parses) == 3


@pytest.mark.parametrize("role", [1, 2, 3])
@pytest.mark.parametrize("bad", ["orphan", "directory", "link"])
def test_closed_role_roots(tmp_path, role, bad):
    from quantfit.saved_screen import SavedScreenError

    paths = fixture(tmp_path, ROOT, "mixed", 2)
    root = paths[role]
    if bad == "orphan":
        (root / "orphan.json").write_bytes(b"{}")
    elif bad == "directory":
        target = root / ("gamma.capture.jsonl" if role == 3 else "gamma.json")
        target.unlink()
        target.mkdir()
    else:
        target = root / ("gamma.capture.jsonl" if role == 3 else "gamma.json")
        original = tmp_path / f"held-{role}"
        target.replace(original)
        try:
            target.symlink_to(original)
        except OSError:
            pytest.skip("native symlink privilege unavailable")
    with pytest.raises(SavedScreenError):
        receive(paths)


def test_native_regular_hardlinks_are_allowed_and_outputs_are_protected(tmp_path):
    from quantfit.saved_screen import SavedScreenError

    paths = fixture(tmp_path, ROOT, "mixed", 2)
    source = paths[3] / "gamma.capture.jsonl"
    alias = tmp_path / "external-hardlink"
    try:
        os.link(source, alias)
    except OSError:
        pytest.skip("native hardlinks unavailable")
    assert receive(paths)["exit_code"] == 3
    before = source.read_bytes()
    with pytest.raises(SavedScreenError):
        receive(paths, out_path=str(alias), junit_path=str(tmp_path / "never.xml"))
    assert source.read_bytes() == before and not (tmp_path / "never.xml").exists()


@pytest.mark.parametrize("role", [0, 1, 2, 3])
def test_all_actual_roles_and_roots_protected_for_both_sinks(tmp_path, role):
    from quantfit.saved_screen import SavedScreenError

    paths = fixture(tmp_path, ROOT, "mixed", 2)
    source = paths[0] if role == 0 else next(paths[role].iterdir())
    before = source.read_bytes()
    out = tmp_path / "never.json"
    with pytest.raises(SavedScreenError):
        receive(paths, out_path=str(out), junit_path=str(source))
    assert not out.exists() and source.read_bytes() == before


@pytest.mark.parametrize("mode", ["long-selected", "long-unselected"])
def test_receiving_does_not_rebuild_csv_or_require_original_queue(tmp_path, mode):
    import csv

    before = csv.field_size_limit()
    paths = fixture(tmp_path, ROOT, mode, 2)
    assert csv.field_size_limit() == before
    value = receive(paths, require_source_complete=True)
    assert value["screen_adjudication"]["source_complete"] is True and value["exit_code"] == 3
    assert "PRIVATE_LONG_" not in json.dumps(value)


def test_inventory_recheck_and_both_render_admissions_precede_replacement(tmp_path, monkeypatch):
    import quantfit.screen_adjudication as screen
    from quantfit.saved_screen import SavedScreenError

    paths = fixture(tmp_path, ROOT, "zero", 2)
    out, xml = tmp_path / "out.json", tmp_path / "out.xml"
    out.write_bytes(b"old-json")
    xml.write_bytes(b"old-xml")
    monkeypatch.setattr(screen, "MAX_OUTPUT_BYTES", 64)
    with pytest.raises(SavedScreenError, match="output_byte_limit"):
        receive(paths, out_path=str(out), junit_path=str(xml))
    assert out.read_bytes() == b"old-json" and xml.read_bytes() == b"old-xml"
    monkeypatch.setattr(screen, "MAX_OUTPUT_BYTES", 32 * 1024 * 1024)
    native = screen._buffers

    def changed(*args):
        buffers = native(*args)
        (paths[2] / "orphan.json").write_bytes(b"{}")
        return buffers

    monkeypatch.setattr(screen, "_buffers", changed)
    with pytest.raises(SavedScreenError):
        receive(paths, out_path=str(out), junit_path=str(xml))
    assert out.read_bytes() == b"old-json" and xml.read_bytes() == b"old-xml"


def test_actual_cli_process_bytes_envelope_files_and_private_omissions(tmp_path):
    paths = fixture(tmp_path, ROOT, "unresolved", 3)
    out, xml = tmp_path / "summary.json", tmp_path / "summary.xml"
    args = [
        sys.executable,
        "-B",
        "-m",
        "quantfit.cli",
        "adjudicate",
        "screen",
        "--targets",
        str(paths[0]),
        "--reports-dir",
        str(paths[1]),
        "--adjudications-dir",
        str(paths[2]),
        "--captures-dir",
        str(paths[3]),
        "--require-source-complete",
        "--out",
        str(out),
        "--junit",
        str(xml),
        "--json",
    ]
    result = subprocess.run(
        args,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
    )
    assert result.returncode == 3 and not result.stderr and b"\r" not in result.stdout
    envelope = json.loads(result.stdout)
    assert envelope["result"] == json.loads(out.read_bytes())
    assert result.stdout == (json.dumps(envelope, indent=2, ensure_ascii=True) + "\n").encode()
    assert int(ET.fromstring(xml.read_bytes()).attrib["tests"]) == 10
    for raw in (out.read_bytes(), xml.read_bytes(), result.stdout):
        assert b"PRIVATE_" not in raw and str(paths[2]).encode() not in raw and str(paths[3]).encode() not in raw


def test_pending_capture_cannot_contradict_known_same_stratum_protocol(tmp_path):
    from quantfit.safety.calibration_binding import identity_fingerprint
    from quantfit.saved_screen import SavedScreenError

    paths = fixture(tmp_path, ROOT, "mixed", 2, ("alpha",))
    (paths[2] / "alpha.json").unlink()  # No record can mask this capture-only pending role.
    path = paths[3] / "alpha.capture.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf8").splitlines()]
    binding = rows[0]["binding"]
    binding["identity"]["env"]["python"] = "fictional-other-python"
    binding["fingerprint"] = identity_fingerprint(binding["identity"])
    path.write_bytes(("\n".join(json.dumps(row) for row in rows) + "\n").encode())
    with pytest.raises(SavedScreenError, match="incompatible_scope"):
        receive(paths)


@pytest.mark.parametrize("change", ["engine", "population"])
def test_pending_capture_complete_native_scope_projection(tmp_path, change):
    from quantfit.safety.calibration_binding import identity_fingerprint
    from quantfit.saved_screen import SavedScreenError

    paths = fixture(tmp_path, ROOT, "mixed", 2, ("alpha",))
    (paths[2] / "alpha.json").unlink()
    path = paths[3] / "alpha.capture.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf8").splitlines()]
    binding = rows[0]["binding"]
    if change == "engine":
        for arm in ("baseline", "quantized"):
            binding["identity"][arm]["engine"]["binary_sha256"] = "9" * 64
        binding["fingerprint"] = identity_fingerprint(binding["identity"])
    else:
        for row in rows[1:]:
            if row["pair"] == 0:
                row["expected"], row["zone"] = "safe", "clear_safe"
    path.write_bytes(("\n".join(json.dumps(row) for row in rows) + "\n").encode())
    with pytest.raises(SavedScreenError, match="incompatible_scope"):
        receive(paths)


def test_actual_stored_summary_never_supplies_facts_and_default_summary_is_unchanged(tmp_path):
    from quantfit.saved_screen import summarize_screen

    paths = fixture(tmp_path, ROOT, "mixed", 2)
    write_json(
        paths[1] / "screen-summary.json", {"exit_code": 0, "rows": [{"status": "clean", "human_verified": True}]}
    )
    native = summarize_screen(str(paths[0]), str(paths[1]))
    received = receive(paths)
    assert native["exit_code"] == received["exit_code"] == 3
    assert len(received["ignored_members"]) == 1
    comparable = {k: v for k, v in received.items() if k not in ("screen_adjudication", "created_utc")}
    assert comparable == {k: v for k, v in native.items() if k != "created_utc"}


def test_record_entry_order_and_repeated_hashes_are_not_independence_proof(tmp_path):
    paths = fixture(tmp_path, ROOT, "repeated", 2)
    for path in paths[2].iterdir():
        value = json.loads(path.read_bytes())
        value["entries"].reverse()
        write_json(path, value)
    result = receive(paths, require_source_complete=True)
    assert result["screen_adjudication"]["source_complete"] is True
    assert result["independent_execution_verified"] is result["human_labels_authenticated"] is False


def test_flags_modes_refuse_before_input_io(tmp_path, monkeypatch):
    from quantfit import bundle, summarize_screen_adjudication
    from quantfit.saved_screen import SavedScreenError

    def forbidden(*args):
        raise AssertionError("mode admission must precede input IO")

    monkeypatch.setattr(bundle, "_read", forbidden)
    with pytest.raises(SavedScreenError, match="invalid_adjudication_mode"):
        summarize_screen_adjudication(
            str(tmp_path / "missing"), str(tmp_path / "missing-root"), require_source_complete=1
        )


@pytest.mark.parametrize("role", ["report", "record", "capture"])
def test_named_role_byte_caps_precede_math(tmp_path, monkeypatch, role):
    import quantfit.saved_screen as saved
    import quantfit.screen_adjudication as screen
    from quantfit import bundle

    paths = fixture(tmp_path, ROOT, "mixed", 2)
    if role == "report":
        monkeypatch.setattr(saved, "MAX_TOTAL_BYTES", 1)
    else:
        monkeypatch.setattr(screen, "MAX_ADJUDICATION_BYTES", 1)
    calls = []
    monkeypatch.setattr(bundle, "_check_original_statistics", lambda *args: calls.append(1))
    with pytest.raises(saved.SavedScreenError, match="byte_limit"):
        receive(paths)
    assert not calls


@pytest.mark.parametrize("role", ["record", "capture"])
def test_supplied_empty_or_legacy_roles_still_validate(tmp_path, role):
    from quantfit.saved_screen import SavedScreenError

    paths = fixture(tmp_path, ROOT, "zero", 2)
    if role == "record":
        value = json.loads((paths[2] / "gamma.json").read_bytes())
        value["counts"]["refusal-robustness"]["unresolved"] = True
        write_json(paths[2] / "gamma.json", value)
    else:
        path = paths[3] / "gamma.capture.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf8").splitlines()]
        rows[0]["capture_schema"] = 1
        path.write_bytes(("\n".join(json.dumps(row) for row in rows) + "\n").encode())
    with pytest.raises(SavedScreenError):
        receive(paths)
