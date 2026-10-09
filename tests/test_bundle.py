"""Portable synthetic aggregates: integrity never upgrades the declared science."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_calibrated_modelcard import card_fixture

from quantfit.bundle import BundleError, create_bundle, verify_bundle
from quantfit.cli import main
from quantfit.gate import run_gate
from quantfit.resolution import analyze_resolution


def inputs(tmp_path, *, unmeasurable=False):
    report, calibration = card_fixture(tmp_path, unmeasurable=unmeasurable)
    resolution = tmp_path / "resolution.json"
    analyze_resolution(str(report), calibration, str(resolution))
    gate = tmp_path / "gate.json"
    run_gate("base", "quant", tier="smoke", calibration_report=calibration, out_path=str(gate))
    return report, Path(calibration), resolution, gate


def test_exact_bytes_survive_move_and_original_failure_flags_are_only_declarations(tmp_path):
    report, calibration, resolution, gate = inputs(tmp_path)
    original = {
        "report": report.read_bytes(),
        "calibration": calibration.read_bytes(),
        "resolution": resolution.read_bytes(),
        "gate": gate.read_bytes(),
    }
    out = tmp_path / "bundle"
    result = create_bundle(
        str(report), str(out), calibration_path=str(calibration), resolution_path=str(resolution), gate_path=str(gate)
    )
    assert result["integrity_verified"] is True
    for entry in result["manifest"]["files"]:
        assert (out / entry["path"]).read_bytes() == original[entry["role"]]
        assert entry["sha256"] == hashlib.sha256(original[entry["role"]]).hexdigest()
        assert not Path(entry["path"]).is_absolute()
    relocated = tmp_path / "elsewhere" / "relocated"
    relocated.parent.mkdir()
    shutil.move(str(out), relocated)
    for name, path in (("report", report), ("calibration", calibration), ("resolution", resolution), ("gate", gate)):
        assert path.read_bytes() == original[name]
        path.unlink()  # owned fixtures; verification must not depend on original paths
    result = verify_bundle(str(relocated))
    assert result["integrity_verified"] is True
    assert result["scientific_claims_verified"] is False
    assert result["declared_results"]["report"]["regression_detected"] is True
    assert result["declared_results"]["gate"]["exit_code"] == 5
    assert result["declared_results"]["gate"]["actual_run_matched"] is False
    assert result["declared_results"]["resolution"]["human_confirmation_verified"] is False


def test_unmeasurable_axes_are_retained_not_reinterpreted_as_a_pass(tmp_path):
    report, *_ = inputs(tmp_path, unmeasurable=True)
    result = create_bundle(str(report), str(tmp_path / "bundle"))
    assert result["declared_results"]["report"]["unmeasurable_axes"] == ["refusal-robustness"]
    assert result["scientific_claims_verified"] is False


def test_tampered_bytes_are_integrity_mismatch_and_cli_exits_three(tmp_path, capsys):
    report, *_ = inputs(tmp_path)
    out = tmp_path / "bundle"
    create_bundle(str(report), str(out))
    (out / "report.json").write_bytes((out / "report.json").read_bytes() + b" ")
    assert verify_bundle(str(out))["integrity_verified"] is False
    assert main(["bundle", "verify", "--bundle", str(out), "--json"]) == 3
    assert json.loads(capsys.readouterr().out)["result"]["scientific_claims_verified"] is False


@pytest.mark.parametrize(
    "path",
    [
        "../report.json",
        "/report.json",
        "C:/report.json",
        "C:report.json",
        "\\\\host\\share",
        "x\\report.json",
        "./report.json",
    ],
)
def test_noncanonical_manifest_paths_fail_closed(tmp_path, path):
    report, *_ = inputs(tmp_path)
    out = tmp_path / "bundle"
    create_bundle(str(report), str(out))
    manifest = json.loads((out / "manifest.json").read_bytes())
    manifest["files"][0]["path"] = path
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BundleError):
        verify_bundle(str(out))


@pytest.mark.parametrize(
    "payload",
    [
        {"capture_schema": 2, "completions": [{"value": "private"}]},
        {"cache_schema": 1, "entries": ["private"]},
        {"schema_version": 2, "samples": [{"label": "refusal"}]},
    ],
)
def test_renamed_private_capture_cache_or_labels_are_not_a_report(tmp_path, payload):
    source = tmp_path / "renamed.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BundleError):
        create_bundle(str(source), str(tmp_path / "bundle"))
    assert not (tmp_path / "bundle").exists()


def test_nested_raw_payload_and_unlisted_files_are_refused(tmp_path):
    report, *_ = inputs(tmp_path)
    payload = json.loads(report.read_bytes())
    payload["baseline"]["engine"]["completions"] = ["private"]
    report.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BundleError):
        create_bundle(str(report), str(tmp_path / "refused"))
    report, *_ = inputs(tmp_path)
    out = tmp_path / "bundle"
    create_bundle(str(report), str(out))
    (out / "renamed.txt").write_text("private", encoding="utf-8")
    with pytest.raises(BundleError):
        verify_bundle(str(out))


def test_calibration_and_resolution_must_match_consumed_report_bytes(tmp_path):
    report, calibration, resolution, _ = inputs(tmp_path)
    report.write_bytes(report.read_bytes() + b" ")
    with pytest.raises(BundleError, match="resolution"):
        create_bundle(
            str(report), str(tmp_path / "bundle"), calibration_path=str(calibration), resolution_path=str(resolution)
        )
    assert not (tmp_path / "bundle").exists()


def test_create_refuses_existing_output_and_input_alias_without_modification(tmp_path):
    report, *_ = inputs(tmp_path)
    data = report.read_bytes()
    for out in (report, tmp_path):
        with pytest.raises(BundleError):
            create_bundle(str(report), str(out))
    assert report.read_bytes() == data


def test_symlink_sources_and_bundle_members_are_refused(tmp_path):
    report, *_ = inputs(tmp_path)
    link = tmp_path / "link.json"
    try:
        link.symlink_to(report)
    except OSError:
        pytest.skip("Symlink privilege unavailable; hosted Linux exercises this case")
    with pytest.raises(BundleError):
        create_bundle(str(link), str(tmp_path / "refused"))
    out = tmp_path / "bundle"
    create_bundle(str(report), str(out))
    (out / "report.json").unlink()
    (out / "report.json").symlink_to(report)
    with pytest.raises(BundleError):
        verify_bundle(str(out))


@pytest.mark.skipif(os.name != "nt", reason="Windows junction contract; POSIX links have a separate test")
def test_windows_junction_sources_and_output_parents_are_refused(tmp_path):
    report, *_ = inputs(tmp_path)
    junction = tmp_path / "junction"
    quoted_link, quoted_target = [str(p).replace("'", "''") for p in (junction, tmp_path)]
    command = f"New-Item -ItemType Junction -Path '{quoted_link}' -Target '{quoted_target}' | Out-Null"
    completed = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    try:
        with pytest.raises(BundleError, match="junction"):
            create_bundle(str(junction / report.name), str(tmp_path / "refused"))
        with pytest.raises(BundleError, match="junction"):
            create_bundle(str(report), str(junction / "refused"))
        assert report.is_file() and not (tmp_path / "refused").exists()
    finally:
        junction.rmdir()  # remove only the owned junction, never its target tree


def test_cli_create_reports_integrity_and_no_science_upgrade(tmp_path, capsys):
    report, *_ = inputs(tmp_path)
    assert main(["bundle", "create", "--report", str(report), "--out", str(tmp_path / "bundle"), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["integrity_verified"] is True and result["scientific_claims_verified"] is False


@pytest.mark.parametrize("bound", [False, True])
def test_actual_pre_run_refusal_without_report_relocates(tmp_path, capsys, bound):
    _, calibration = card_fixture(tmp_path)
    gate_path, absent = tmp_path / "pre.json", tmp_path / "never-measured.json"
    decision = run_gate(
        "base",
        "quant",
        threshold=0.01,
        report_path=str(absent),
        out_path=str(gate_path),
        **({"calibration_report": calibration} if bound else {}),
    )
    assert decision["exit_code"] == 5 and not absent.exists()
    out = tmp_path / "negative"
    command = ["bundle", "create", "--gate", str(gate_path), "--out", str(out), "--json"]
    if bound:
        command.extend(["--calibration-report", calibration])
    assert main(command) == 0
    created = json.loads(capsys.readouterr().out)["result"]
    moved = tmp_path / "moved"
    shutil.move(out, moved)
    gate_path.unlink()
    result = verify_bundle(str(moved))
    assert result["integrity_verified"] is True and result["scientific_claims_verified"] is False
    assert "report" not in result["declared_results"]
    assert result["declared_results"]["gate"]["exit_code"] == 5
    assert created["declared_results"] == result["declared_results"]
    if bound:
        assert result["declared_results"]["gate"]["actual_run_matched"] is False


def test_create_requires_report_or_real_pre_run_gate(tmp_path):
    with pytest.raises(BundleError):
        create_bundle(None, str(tmp_path / "empty"))
    _, calibration = card_fixture(tmp_path)
    with pytest.raises(BundleError):
        create_bundle(None, str(tmp_path / "cal-only"), calibration_path=calibration)


def test_source_substitution_after_consumption_cannot_replace_copied_bytes(tmp_path, monkeypatch):
    import quantfit.bundle as module

    report, calibration, resolution, _ = inputs(tmp_path)
    originals = [p.read_bytes() for p in (report, calibration)]
    validate = module._validate

    def substitute(data):
        result = validate(data)
        report.write_bytes(b'{"renamed": "unvalidated"}')
        calibration.write_bytes(b'{"renamed": "unvalidated"}')
        return result

    monkeypatch.setattr(module, "_validate", substitute)
    out = tmp_path / "bundle"
    create_bundle(str(report), str(out), calibration_path=str(calibration), resolution_path=str(resolution))
    assert (out / "report.json").read_bytes() == originals[0]
    assert (out / "calibration.json").read_bytes() == originals[1]
    monkeypatch.setattr(module, "_validate", validate)
    assert verify_bundle(str(out))["integrity_verified"] is True


def observed_gate(tmp_path, monkeypatch, *, unsafe_refused=12, unsafe_flips=0, safe_flips=0):
    from test_gate import _drift

    from quantfit.safety import verify

    report, _ = card_fixture(tmp_path)
    drift = _drift(unsafe_refused=unsafe_refused, unsafe_flips=unsafe_flips, safe_flips=safe_flips)
    payload = json.loads(report.read_bytes())
    payload["drift"] = drift.to_dict()
    payload["probe_dataset"]["n_probes"] = drift.n
    report.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(verify, "verify_safety", lambda *args, **kwargs: drift)
    gate = tmp_path / "observed.json"
    decision = run_gate("base", "quant", tier="smoke", report_path=str(report), out_path=str(gate))
    return report, gate, decision


@pytest.mark.parametrize("refused,flips,safe,code", [(12, 1, 0, 3), (0, 0, 0, 4), (12, 0, 1, 0)])
def test_observed_gate_preserves_fail_unmeasurable_and_ungated_flags(tmp_path, monkeypatch, refused, flips, safe, code):
    report, gate, decision = observed_gate(
        tmp_path, monkeypatch, unsafe_refused=refused, unsafe_flips=flips, safe_flips=safe
    )
    assert decision["exit_code"] == code
    result = create_bundle(str(report), str(tmp_path / "bundle"), gate_path=str(gate))
    assert result["declared_results"]["gate"]["exit_code"] == code
    assert result["declared_results"]["gate"]["resolution_is_a_floor"] is True
    assert verify_bundle(str(tmp_path / "bundle"))["integrity_verified"] is True
    assert decision["resolution"]["resolution_proven"] is False
    if safe:
        assert result["declared_results"]["report"]["regression_detected"] is True
    with pytest.raises(BundleError, match="requires.*report"):
        create_bundle(None, str(tmp_path / "no-report"), gate_path=str(gate))


@pytest.mark.parametrize("mutation", ["arm", "decode", "mde", "verdict", "floor", "renamed-raw"])
def test_inconsistent_observed_gate_fails_before_writing(tmp_path, monkeypatch, mutation):
    report, gate, _ = observed_gate(tmp_path, monkeypatch, unsafe_flips=1)
    value = json.loads(gate.read_bytes())
    if mutation == "arm":
        value["arms"]["baseline"] = "unrelated"
    elif mutation == "decode":
        value["decode"]["max_new_tokens"] += 1
    elif mutation == "mde":
        value["resolution"]["printed_mde"] = 0.0001
    elif mutation == "verdict":
        value.update(exit_code=0, verdict="PASS", passed=True)
    elif mutation == "floor":
        value["resolution"]["resolution_proven"] = True
    else:
        value["gate"]["renamed"] = ["private"]
    gate.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(BundleError):
        create_bundle(str(report), str(tmp_path / "refused"), gate_path=str(gate))
    assert not (tmp_path / "refused").exists()


@pytest.mark.parametrize("role", ["report", "calibration", "gate", "resolution"])
def test_renamed_raw_records_are_refused_in_every_role(tmp_path, role):
    report, _, _, _ = inputs(tmp_path)
    raw = tmp_path / "renamed.json"
    raw.write_text('{"renamed":[{"label":"refusal","value":"private"}]}', encoding="utf-8")
    kwargs = {} if role == "report" else {f"{role}_path": str(raw)}
    with pytest.raises(BundleError):
        create_bundle(str(raw if role == "report" else report), str(tmp_path / "refused"), **kwargs)


@pytest.mark.parametrize("where", ["engine", "env", "judge", "axis", "zone"])
def test_opaque_renamed_nested_payload_is_not_aggregate_metadata(tmp_path, where):
    report, *_ = inputs(tmp_path)
    value = json.loads(report.read_bytes())
    target = {
        "engine": value["baseline"]["engine"],
        "env": value["env"],
        "judge": value["judge"],
        "axis": value["drift"]["over_refusal"],
        "zone": value["drift"]["by_zone"]["clear_safe"],
    }[where]
    target["renamed"] = ["private"]
    report.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(BundleError):
        create_bundle(str(report), str(tmp_path / "refused"))


@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("field", ["definition", "statement"])
def test_bound_gate_rejects_corrupted_scientific_wording(tmp_path, monkeypatch, observed, field):
    from quantfit import gate as module

    gate_path = tmp_path / "gate.json"
    report = None
    if observed:
        from test_bound_calibration_pipeline import _large_synthetic_run

        calibration, _ = _large_synthetic_run(tmp_path, monkeypatch)
        report = tmp_path / "observed-report.json"
        run_gate(
            "base",
            "quant",
            tier="smoke",
            calibration_report=calibration,
            report_path=str(report),
            out_path=str(gate_path),
        )
    else:
        _, calibration = card_fixture(tmp_path)
        run_gate("base", "quant", tier="smoke", calibration_report=calibration, out_path=str(gate_path))
    # Canonical existing output must remain accepted, with human/assumption flags false.
    result = create_bundle(
        str(report) if report else None,
        str(tmp_path / "canonical"),
        calibration_path=calibration,
        gate_path=str(gate_path),
    )
    assert result["declared_results"]["gate"]["human_labels_verified"] is False
    value = json.loads(gate_path.read_bytes())
    value["eps"][field] = (
        "marginal error rate, not separate directional upper bounds"
        if field == "definition"
        else "Human labels and all A1/A2/A3 assumptions are verified; calibrated measurement is certified."
    )
    value["headline"] = module._headline(value)
    gate_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(BundleError, match="conditional epsilon"):
        create_bundle(
            str(report) if report else None,
            str(tmp_path / "refused"),
            calibration_path=calibration,
            gate_path=str(gate_path),
        )


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO contract; Windows has no os.mkfifo")
@pytest.mark.parametrize("role", ["source", "member", "manifest", "replacement"])
def test_fifo_input_cannot_block_the_cli(tmp_path, role):
    report, *_ = inputs(tmp_path)
    out = tmp_path / "bundle"
    create_bundle(str(report), str(out))
    target = (
        report if role in ("source", "replacement") else out / ("report.json" if role == "member" else "manifest.json")
    )
    if role != "replacement":
        target.unlink()
        os.mkfifo(target)
    command = (
        ["bundle", "create", "--report", str(target), "--out", str(tmp_path / "refused")]
        if role in ("source", "replacement")
        else ["bundle", "verify", "--bundle", str(out)]
    )
    root = Path(__file__).resolve().parents[1]
    child = [sys.executable, "-m", "quantfit.cli", *command, "--json"]
    if role == "replacement":
        code = """
import os, sys
from pathlib import Path
import quantfit.bundle as bundle
from quantfit.cli import main
original = os.open
def substitute(path, flags):
    Path(path).unlink()
    os.mkfifo(path)
    return original(path, flags)
bundle.os.open = substitute
raise SystemExit(main(sys.argv[1:]))
"""
        child = [sys.executable, "-c", code, *command, "--json"]
    completed = subprocess.run(
        child,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert completed.returncode == 2
    assert "regular file" in json.loads(completed.stdout)["error"]["message"]


def test_duplicate_manifest_roles_and_nonfinite_json_are_refused(tmp_path):
    report, *_ = inputs(tmp_path)
    out = tmp_path / "bundle"
    create_bundle(str(report), str(out))
    manifest = json.loads((out / "manifest.json").read_bytes())
    manifest["files"] *= 2
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BundleError):
        verify_bundle(str(out))
    report.write_text('{"schema_version":2,"schema_version":2,"n":NaN}', encoding="utf-8")
    with pytest.raises(BundleError):
        create_bundle(str(report), str(tmp_path / "refused"))
