"""Optional per-target resolution is conditional analysis, never a native gate change."""

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
from test_calibration_binding import calibration_fixture
from test_saved_screen import corpus

from quantfit.bundle import _report
from quantfit.junit import screen_to_junit
from quantfit.saved_screen import SavedScreenError, summarize_screen


def inputs(tmp_path, entries=None, *, missing_reports=(), missing_calibrations=()):
    entries = entries or [("g0", "gguf", 0, 0, None)]
    manifest, reports = corpus(tmp_path, entries)
    calibrations = tmp_path / "calibrations"
    calibrations.mkdir()
    for name, *_ in entries:
        payload = calibration_fixture(_report((reports / f"{name}.json").read_bytes()))
        if name not in missing_calibrations:
            (calibrations / f"{name}.json").write_text(json.dumps(payload, indent=3) + "\n", encoding="utf-8")
        if name in missing_reports:
            (reports / f"{name}.json").unlink()
    return manifest, reports, calibrations


def summary(manifest, reports, calibrations, **kwargs):
    return summarize_screen(str(manifest), str(reports), calibrations_dir=str(calibrations), **kwargs)


def trap_analysis(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(args)
        pytest.fail("analysis began before all-target preflight")

    monkeypatch.setattr("quantfit.resolution.analyze_resolution_bytes", forbidden)
    return calls


@pytest.mark.parametrize("danger,unmeasured,code", [(0, None, 0), (1, None, 3), (0, "danger", 4)])
def test_optional_analysis_matches_authoritative_bytes_and_preserves_native_summary(tmp_path, danger, unmeasured, code):
    from quantfit.resolution import analyze_resolution_bytes

    manifest, reports, calibrations = inputs(tmp_path, [("g0", "gguf", danger, 0, unmeasured)])
    before = {path: path.read_bytes() for path in (manifest, reports / "g0.json", calibrations / "g0.json")}
    native = summarize_screen(str(manifest), str(reports))
    result = summary(manifest, reports, calibrations)
    assert result["exit_code"] == native["exit_code"] == code
    assert screen_to_junit(result) == screen_to_junit(native)
    base = {key: value for key, value in result.items() if key != "conditional_resolution"}
    base["created_utc"] = native["created_utc"]
    assert base == native
    extension = result["conditional_resolution"]
    row = extension["rows"][0]
    _, direct = analyze_resolution_bytes(before[reports / "g0.json"], before[calibrations / "g0.json"])
    observed = copy.deepcopy(row["analysis"])
    observed["created_utc"] = direct["created_utc"]
    assert observed == direct and row["status"] == "analyzed"
    assert row["native_report_sha256"] == hashlib.sha256(before[reports / "g0.json"]).hexdigest()
    assert row["calibration"] == {
        "member": "g0.json",
        "status": "present",
        "sha256": hashlib.sha256(before[calibrations / "g0.json"]).hexdigest(),
        "size_bytes": len(before[calibrations / "g0.json"]),
    }
    assert extension["analysis_work_units"] == 40**2 and extension["coverage"]["complete"] is True
    assert extension["assumptions_verified"] is False and extension["scientific_go"] is False
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize(
    "report_missing,cal_missing,status",
    [
        (False, True, "calibration_missing"),
        (True, False, "pending_report_missing"),
        (True, True, "report_and_calibration_missing"),
    ],
)
def test_optional_missing_evidence_is_explicit_and_never_analyzed(
    tmp_path, monkeypatch, report_missing, cal_missing, status
):
    manifest, reports, calibrations = inputs(
        tmp_path, missing_reports=("g0",) if report_missing else (), missing_calibrations=("g0",) if cal_missing else ()
    )
    calls = trap_analysis(monkeypatch)
    native = summarize_screen(str(manifest), str(reports))
    result = summary(manifest, reports, calibrations)
    row = result["conditional_resolution"]["rows"][0]
    assert row["status"] == status and row["analysis"] is None and not calls
    assert row["native_report_sha256"] == native["report_bindings"][0]["sha256"]
    assert result["exit_code"] == native["exit_code"] and screen_to_junit(result) == screen_to_junit(native)
    assert result["conditional_resolution"]["analysis_work_units"] == 0
    if not cal_missing:
        assert len(row["binding_fingerprint"]) == 64
    else:
        assert row["calibration"]["sha256"] is None and row["calibration"]["size_bytes"] is None


@pytest.mark.parametrize("mutation", ["truncated", "private", "duplicate", "scope"])
def test_late_bad_calibration_refuses_before_earlier_analysis_or_output_mutation(tmp_path, monkeypatch, mutation):
    from quantfit.safety.calibration_binding import identity_fingerprint

    manifest, reports, calibrations = inputs(tmp_path, [("first", "gguf", 0, 0, None), ("last", "gguf", 0, 0, None)])
    last = calibrations / "last.json"
    if mutation == "truncated":
        last.write_bytes(b'{"PRIVATE provider diagnostics"')
    elif mutation == "duplicate":
        last.write_bytes(b'{"calibration_schema":2,"calibration_schema":2}')
    else:
        payload = json.loads(last.read_bytes())
        if mutation == "private":
            payload["provider_response"] = "PRIVATE completion"
        else:
            payload["binding"]["identity"]["decode"]["max_new_tokens"] = 65
            payload["binding"]["fingerprint"] = identity_fingerprint(payload["binding"]["identity"])
        last.write_text(json.dumps(payload), encoding="utf-8")
    out, xml = tmp_path / "out.json", tmp_path / "out.xml"
    out.write_bytes(b"previous json")
    xml.write_bytes(b"previous xml")
    original = last.read_bytes()
    calls = trap_analysis(monkeypatch)
    with pytest.raises(SavedScreenError) as error:
        summary(manifest, reports, calibrations, out_path=str(out), junit_path=str(xml))
    assert "PRIVATE" not in str(error.value)
    assert not calls and out.read_bytes() == b"previous json" and xml.read_bytes() == b"previous xml"
    assert last.read_bytes() == original


@pytest.mark.parametrize("mutation", ["model", "backend", "device", "baseline_dtype"])
def test_pending_calibration_known_target_mismatch_refuses_without_analysis(tmp_path, monkeypatch, mutation):
    from quantfit.safety.calibration_binding import identity_fingerprint

    manifest, reports, calibrations = inputs(tmp_path, missing_reports=("g0",))
    path = calibrations / "g0.json"
    payload = json.loads(path.read_bytes())
    identity = payload["binding"]["identity"]
    if mutation == "model":
        identity["baseline"]["model"] = "hf:synthetic/other/other-base.gguf"
    elif mutation == "backend":
        for arm in ("baseline", "quantized"):
            identity[arm]["engine"] = {"name": "transformers", "version": "5.17.0", "device": "cpu"}
    elif mutation == "device":
        identity["baseline"]["engine"]["device"] = "cuda"
    else:
        identity["baseline"]["resolved_dtype"] = "Q4_K_M"
    payload["binding"]["fingerprint"] = identity_fingerprint(identity)
    path.write_text(json.dumps(payload), encoding="utf-8")
    if mutation == "baseline_dtype":
        from quantfit.safety.calibration_binding import load_bound_calibration_bytes

        assert load_bound_calibration_bytes(path.read_bytes()).identity["baseline"]["resolved_dtype"] == "Q4_K_M"
    calls = trap_analysis(monkeypatch)
    with pytest.raises(SavedScreenError):
        summary(manifest, reports, calibrations)
    assert not calls


@pytest.mark.parametrize("sink", ["calibration", "manifest", "native", "inside_calibrations", "outputs", "hardlink"])
def test_optional_output_aliases_refuse_before_analysis(tmp_path, monkeypatch, sink):
    manifest, reports, calibrations = inputs(tmp_path)
    out = {
        "calibration": calibrations / "g0.json",
        "manifest": manifest,
        "native": reports / "g0.json",
        "inside_calibrations": calibrations / "new.json",
        "outputs": tmp_path / "same",
        "hardlink": tmp_path / "alias",
    }[sink]
    if sink == "hardlink":
        os.link(calibrations / "g0.json", out)
    before = {path: path.read_bytes() for path in (manifest, reports / "g0.json", calibrations / "g0.json")}
    calls = trap_analysis(monkeypatch)
    with pytest.raises(SavedScreenError):
        summary(manifest, reports, calibrations, out_path=str(out), junit_path=str(out) if sink == "outputs" else None)
    assert not calls and all(path.read_bytes() == raw for path, raw in before.items())


def replace_population(reports, calibrations, name, n):
    from quantfit.safety.verify import SafetyDrift

    path = reports / f"{name}.json"
    payload = json.loads(path.read_bytes())
    payload["probe_dataset"]["n_probes"] = n
    payload["drift"] = SafetyDrift(
        n,
        1,
        1,
        1,
        0,
        n - 1,
        0,
        0,
        0,
        {
            "clear_unsafe": {"n": 1, "baseline_refused": 1, "quant_refused": 1},
            "clear_safe": {"n": n - 1, "baseline_refused": 0, "quant_refused": 0},
            "borderline": {"n": 0, "baseline_refused": 0, "quant_refused": 0},
        },
    ).to_dict()
    path.write_text(json.dumps(payload), encoding="utf-8")
    from quantfit.resolution import parse_report_bytes

    (calibrations / f"{name}.json").write_text(
        json.dumps(calibration_fixture(parse_report_bytes(path.read_bytes()))), encoding="utf-8"
    )


def test_analysis_work_boundary_is_checked_for_all_targets_before_math(tmp_path, monkeypatch):
    from quantfit import screen_resolution as receiving

    manifest, reports, calibrations = inputs(tmp_path, [("first", "gguf", 0, 0, None), ("last", "gguf", 0, 0, None)])
    monkeypatch.setattr(receiving, "MAX_ANALYSIS_WORK_UNITS", 2 * 40**2 - 1)
    calls = trap_analysis(monkeypatch)
    with pytest.raises(SavedScreenError, match="resolution_work_limit"):
        summary(manifest, reports, calibrations)
    assert not calls
    monkeypatch.undo()
    monkeypatch.setattr(receiving, "MAX_ANALYSIS_WORK_UNITS", 2 * 40**2)
    result = summary(manifest, reports, calibrations)
    assert result["conditional_resolution"]["analysis_work_units"] == 2 * 40**2


def test_actual_report_probe_cap_refuses_before_any_analysis(tmp_path, monkeypatch):
    manifest, reports, calibrations = inputs(tmp_path)
    replace_population(reports, calibrations, "g0", 4097)
    calls = trap_analysis(monkeypatch)
    with pytest.raises(SavedScreenError):
        summary(manifest, reports, calibrations)
    assert not calls


@pytest.mark.parametrize("calibration_missing", [True, False])
def test_native_boundary_and_larger_pending_scope_add_no_analysis_work(tmp_path, monkeypatch, calibration_missing):
    manifest, reports, calibrations = inputs(tmp_path)
    replace_population(reports, calibrations, "g0", 4096 if calibration_missing else 4097)
    if calibration_missing:
        (calibrations / "g0.json").unlink()
    else:
        (reports / "g0.json").unlink()
    calls = trap_analysis(monkeypatch)
    native = summarize_screen(str(manifest), str(reports))
    result = summary(manifest, reports, calibrations)
    assert not calls and result["conditional_resolution"]["analysis_work_units"] == 0
    assert result["exit_code"] == native["exit_code"]


def test_two_actual_maximum_reports_exceed_total_work_before_first_analysis(tmp_path, monkeypatch):
    manifest, reports, calibrations = inputs(tmp_path, [("first", "gguf", 0, 0, None), ("last", "gguf", 0, 0, None)])
    for name in ("first", "last"):
        replace_population(reports, calibrations, name, 4096)
    calls = trap_analysis(monkeypatch)
    with pytest.raises(SavedScreenError, match="resolution_work_limit"):
        summary(manifest, reports, calibrations)
    assert not calls


@pytest.mark.parametrize("bound", ["file", "total"])
def test_calibration_byte_limits_refuse_before_analysis(tmp_path, monkeypatch, bound):
    from quantfit import screen_resolution as receiving

    manifest, reports, calibrations = inputs(tmp_path, [("first", "gguf", 0, 0, None), ("last", "gguf", 0, 0, None)])
    sizes = [(calibrations / f"{name}.json").stat().st_size for name in ("first", "last")]
    if bound == "file":
        monkeypatch.setattr(receiving, "MAX_CALIBRATION_BYTES", min(sizes) - 1)
    else:
        monkeypatch.setattr(receiving, "MAX_TOTAL_CALIBRATION_BYTES", sum(sizes) - 1)
    calls = trap_analysis(monkeypatch)
    with pytest.raises(SavedScreenError):
        summary(manifest, reports, calibrations)
    assert not calls


def test_partial_coverage_statuses_are_mutually_exclusive_and_native_flags_unchanged(tmp_path):
    manifest, reports, calibrations = inputs(
        tmp_path,
        [("a", "gguf", 0, 0, None), ("b", "gguf", 1, 0, None), ("c", "gguf", 0, 0, None), ("d", "gguf", 0, 0, None)],
        missing_reports=("c", "d"),
        missing_calibrations=("b", "d"),
    )
    result = summary(manifest, reports, calibrations)
    extension = result["conditional_resolution"]
    assert [row["status"] for row in extension["rows"]] == [
        "analyzed",
        "calibration_missing",
        "pending_report_missing",
        "report_and_calibration_missing",
    ]
    assert extension["coverage"] == {
        "n_targets": 4,
        "n_analyzed": 1,
        "n_calibration_missing": 1,
        "n_pending_report_missing": 1,
        "n_report_and_calibration_missing": 1,
        "complete": False,
    }
    assert extension["analysis_work_units"] == 40**2 and result["exit_code"] == 3


def test_held_inputs_remain_pure_after_source_files_are_removed(tmp_path, monkeypatch):
    import shutil

    from quantfit import saved_screen as saved
    from quantfit import screen_resolution as receiving

    manifest, reports, calibrations = inputs(tmp_path)
    native = saved._hold_screen_inputs(str(manifest), str(reports))
    held = receiving._hold_calibrations(calibrations, frozenset({"g0.json"}))
    manifest.unlink()
    shutil.rmtree(reports)
    shutil.rmtree(calibrations)
    monkeypatch.setattr(saved, "_read", lambda *args: pytest.fail("held bytes reopened"))
    monkeypatch.setattr(receiving, "_read", lambda *args: pytest.fail("held bytes reopened"))
    monkeypatch.setattr(Path, "read_bytes", lambda *args: pytest.fail("held bytes reopened"))
    monkeypatch.setattr(os, "scandir", lambda *args: pytest.fail("held inventory rescanned"))
    result = receiving._summarize_inputs(native, held)
    assert result["conditional_resolution"]["rows"][0]["status"] == "analyzed"


def test_publication_never_rereads_manifest_native_or_calibration_bytes(tmp_path, monkeypatch):
    from quantfit import saved_screen as saved
    from quantfit import screen_resolution as receiving

    manifest, reports, calibrations = inputs(tmp_path)
    read = saved._read
    calls = []

    def once(path, limit):
        assert path not in calls
        calls.append(path)
        return read(path, limit)

    monkeypatch.setattr(saved, "_read", once)
    monkeypatch.setattr(receiving, "_read", once)
    out, xml = tmp_path / "receiving.json", tmp_path / "receiving.xml"
    result = summary(manifest, reports, calibrations, out_path=str(out), junit_path=str(xml))
    assert set(calls) == {manifest, reports / "g0.json", calibrations / "g0.json"}
    assert json.loads(out.read_bytes()) == result and xml.read_text() == screen_to_junit(result)


@pytest.mark.parametrize("names", [("unexpected.json",), ("g0.json", "g0.json")])
def test_calibration_inventory_stops_and_closes_on_first_unknown_or_duplicate(tmp_path, monkeypatch, names):
    from types import SimpleNamespace

    from quantfit import screen_resolution as receiving

    _, _, calibrations = inputs(tmp_path)
    seen, closed = [], []

    class Scan:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append(True)

        def __iter__(self):
            for name in names:
                seen.append(name)
                yield SimpleNamespace(name=name)
            pytest.fail("unsafe inventory continued after the first refusal")

    monkeypatch.setattr(os, "scandir", lambda root: Scan())
    monkeypatch.setattr(Path, "iterdir", lambda *args: pytest.fail("materialized directory inventory"))
    with pytest.raises(SavedScreenError, match="unsupported_calibration_member"):
        receiving._inventory(calibrations, frozenset({"g0.json"}))
    assert seen == list(names) and closed == [True]


@pytest.mark.parametrize("kind", ["foreign", "directory", "unreadable", "symlink"])
def test_unsafe_calibration_inventory_refuses_before_analysis(tmp_path, monkeypatch, kind):
    from quantfit import screen_resolution as receiving

    manifest, reports, calibrations = inputs(tmp_path)
    path = calibrations / "g0.json"
    if kind == "foreign":
        (calibrations / "foreign.json").write_bytes(b"PRIVATE")
    elif kind == "directory":
        path.unlink()
        path.mkdir()
    elif kind == "unreadable":
        original = receiving._read

        def unreadable(path, limit):
            if path.parent == calibrations:
                raise PermissionError("PRIVATE provider diagnostics")
            return original(path, limit)

        monkeypatch.setattr(receiving, "_read", unreadable)
    else:
        path.unlink()
        try:
            path.symlink_to(reports / "g0.json")
        except OSError:
            pytest.skip("host does not permit symbolic link creation")
    calls = trap_analysis(monkeypatch)
    with pytest.raises(SavedScreenError) as error:
        summary(manifest, reports, calibrations)
    assert not calls and "PRIVATE" not in str(error.value)


def test_malformed_orphan_is_refused_not_retained_as_pending(tmp_path, monkeypatch):
    manifest, reports, calibrations = inputs(tmp_path, missing_reports=("g0",))
    (calibrations / "g0.json").write_bytes(b'{"calibration_schema":2,"response":"PRIVATE"}')
    calls = trap_analysis(monkeypatch)
    with pytest.raises(SavedScreenError) as error:
        summary(manifest, reports, calibrations)
    assert not calls and "PRIVATE" not in str(error.value)


def test_exact_calibration_byte_budgets_admit_originals(tmp_path, monkeypatch):
    from quantfit import screen_resolution as receiving

    manifest, reports, calibrations = inputs(tmp_path, [("a", "gguf", 0, 0, None), ("b", "gguf", 0, 0, None)])
    sizes = [(calibrations / f"{name}.json").stat().st_size for name in ("a", "b")]
    monkeypatch.setattr(receiving, "MAX_CALIBRATION_BYTES", max(sizes))
    monkeypatch.setattr(receiving, "MAX_TOTAL_CALIBRATION_BYTES", sum(sizes))
    result = summary(manifest, reports, calibrations)
    assert result["conditional_resolution"]["coverage"]["n_analyzed"] == 2


@pytest.mark.parametrize("mutation", ["foreign", "alias", "interrupt"])
def test_publication_rechecks_inventory_and_aliases_without_reopening_inputs(tmp_path, monkeypatch, mutation):
    from quantfit import screen_resolution as receiving

    manifest, reports, calibrations = inputs(tmp_path)
    out, xml = tmp_path / "summary.json", tmp_path / "summary.xml"
    out.write_bytes(b"old summary")
    xml.write_bytes(b"old junit")
    raw_cal = (calibrations / "g0.json").read_bytes()
    analyze = receiving.resolution.analyze_resolution_bytes

    def analyze_then_mutate(*args):
        result = analyze(*args)
        if mutation == "foreign":
            (calibrations / "foreign.json").write_bytes(b"PRIVATE foreign")
        elif mutation == "alias":
            xml.unlink()
            os.link(calibrations / "g0.json", xml)
        else:
            raise KeyboardInterrupt("PRIVATE")
        return result

    monkeypatch.setattr(receiving.resolution, "analyze_resolution_bytes", analyze_then_mutate)
    with pytest.raises(SavedScreenError) as error:
        summary(manifest, reports, calibrations, out_path=str(out), junit_path=str(xml))
    assert "PRIVATE" not in str(error.value) and out.read_bytes() == b"old summary"
    assert xml.read_bytes() == (raw_cal if mutation == "alias" else b"old junit")
    assert (calibrations / "g0.json").read_bytes() == raw_cal
    assert not list(tmp_path.glob(".reproduce-*"))


@pytest.mark.parametrize("junit_alias", [True, False])
def test_junit_input_alias_or_missing_output_parent_refuses_before_analysis(tmp_path, monkeypatch, junit_alias):
    manifest, reports, calibrations = inputs(tmp_path)
    calls = trap_analysis(monkeypatch)
    kwargs = (
        {"junit_path": str(calibrations / "g0.json")}
        if junit_alias
        else {"out_path": str(tmp_path / "missing" / "summary.json")}
    )
    with pytest.raises(SavedScreenError):
        summary(manifest, reports, calibrations, **kwargs)
    assert not calls
