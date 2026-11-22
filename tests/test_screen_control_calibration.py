"""Existing calibration and supplied-control evidence compose without new verdicts."""

import hashlib
import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest
from test_calibration_binding import calibration_fixture
from test_screen_control_evidence import case, command, options

from quantfit.bundle import _report
from quantfit.junit import screen_to_junit
from quantfit.saved_screen import SavedScreenError, summarize_screen


@pytest.fixture(autouse=True)
def receiving_only(monkeypatch):
    from quantfit import resolution, saved_screen

    def forbidden(*args, **kwargs):
        pytest.fail("combined receiving attempted model, judge or Hub execution")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    monkeypatch.setattr(saved_screen, "datetime", Clock)
    monkeypatch.setattr(resolution, "datetime", Clock)


def calibrated(root, **kwargs):
    paths = case(root, **kwargs)
    directory = root / "calibrations"
    directory.mkdir()
    for report in paths[1].iterdir():
        data = calibration_fixture(_report(report.read_bytes()))
        (directory / report.name).write_text(json.dumps(data), encoding="utf-8")
    return (*paths, directory)


def combined(paths, scalar=None, **kwargs):
    return summarize_screen(
        str(paths[0]),
        str(paths[1]),
        **options(paths),
        calibrations_dir=str(paths[5]),
        required_conditional_resolution_pp=scalar,
        **kwargs,
    )


class Clock:
    @staticmethod
    def now(*args):
        return datetime(2026, 11, 15, 3, tzinfo=timezone.utc)


def test_real_composition_equals_original_control_and_calibration_projections(tmp_path, monkeypatch):
    from quantfit import resolution, saved_screen

    monkeypatch.setattr(saved_screen, "datetime", Clock)
    monkeypatch.setattr(resolution, "datetime", Clock)
    paths = calibrated(tmp_path / "composition")
    control = summarize_screen(str(paths[0]), str(paths[1]), **options(paths))
    calibration = summarize_screen(str(paths[0]), str(paths[1]), calibrations_dir=str(paths[5]))
    result = combined(paths)
    assert result["control_evidence"] == control["control_evidence"]
    assert result["conditional_resolution"] == calibration["conditional_resolution"]
    assert result["exit_code"] == control["exit_code"] == calibration["exit_code"] == 3
    assert {key: value for key, value in result.items() if key != "control_evidence"} == calibration
    assert screen_to_junit(result) == screen_to_junit(calibration)


def test_scalar_qualification_and_junit_ignore_control_annotation_state(tmp_path):
    paths = calibrated(tmp_path / "unresolved", labels="unresolved")
    calibration = summarize_screen(
        str(paths[0]),
        str(paths[1]),
        calibrations_dir=str(paths[5]),
        required_conditional_resolution_pp=100,
    )
    result = combined(paths, 100)
    assert result["control_evidence"]["status"] == "conflicting"
    assert not result["control_evidence"]["dangerous"]["positive_supported"]
    assert result["exit_code"] == calibration["exit_code"] == 3
    assert result["conditional_resolution_requirement"] == calibration["conditional_resolution_requirement"]
    assert screen_to_junit(result) == screen_to_junit(calibration)


def test_actual_os_cli_composition_publishes_complete_native_json_and_junit(tmp_path):
    paths = calibrated(tmp_path / "cli")
    out, xml = tmp_path / "receiving.json", tmp_path / "receiving.xml"
    result = subprocess.run(
        [
            *command(paths),
            "--calibrations-dir",
            str(paths[5]),
            "--require-conditional-resolution",
            "100",
            "--out",
            str(out),
            "--junit",
            str(xml),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    assert result.returncode == 3, result.stderr
    document = json.loads(result.stdout)
    assert document["result"] == json.loads(out.read_bytes())
    summary = document["result"]
    assert summary["control_evidence"]["status"] == "consistent"
    assert "conditional_resolution" in summary and "conditional_resolution_requirement" in summary
    assert xml.read_text(encoding="utf-8") == screen_to_junit(summary)
    assert len(list(ET.fromstring(xml.read_bytes()).iter("testcase"))) == 4


def test_variants_remain_refused_before_io_even_with_full_control_roles(monkeypatch):
    monkeypatch.setattr(
        "quantfit.saved_screen._hold_screen_inputs", lambda *a, **k: pytest.fail("unsupported variants reached IO")
    )
    with pytest.raises(SavedScreenError):
        summarize_screen(
            "PRIVATE",
            "PRIVATE",
            calibration_variants={"declared": None},
            control_report="PRIVATE-r",
            control_capture="PRIVATE-c",
            control_adjudication="PRIVATE-a",
        )


def qualified(root, **kwargs):
    control = case(root / "control")
    checkout = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "combined_resolution_fixture", checkout / "tools/ci_screen_requirement.py"
    )
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    manifest, reports, calibrations = helper.fixture(checkout, root / "screen", **kwargs)
    data = json.loads(manifest.read_bytes())
    data["sensitivity_control"] = {"status": "pass", "report": str(control[2]), "human_verifier": "declared"}
    manifest.write_text(json.dumps(data), encoding="utf-8")
    return manifest, reports, *control[2:], calibrations


@pytest.mark.parametrize(
    "scenario,ceiling,expected,settings",
    [
        ("qualified", 40, 0, {}),
        ("coarse", 30, 5, {}),
        ("saturated", 100, 5, {"n": 40}),
        ("missing", 40, 4, {"missing": ("clean",)}),
        ("flags", 1, 3, {"flagged": True}),
        ("unmeasured", 1, 4, {"unmeasured": True}),
    ],
)
def test_combination_keeps_exact_native_scalar_priority_and_junit(tmp_path, scenario, ceiling, expected, settings):
    paths = qualified(tmp_path / scenario, **settings)
    calibration = summarize_screen(
        str(paths[0]), str(paths[1]), calibrations_dir=str(paths[5]), required_conditional_resolution_pp=ceiling
    )
    result = combined(paths, ceiling)
    assert result["exit_code"] == calibration["exit_code"] == expected
    assert result["conditional_resolution"] == calibration["conditional_resolution"]
    assert result["conditional_resolution_requirement"] == calibration["conditional_resolution_requirement"]
    assert screen_to_junit(result) == screen_to_junit(calibration)
    assert result["control_evidence"]["status"] == "conflicting"
    assert not any(result[key] for key in ("scientific_go", "human_labels_authenticated", "sensitivity_established"))


def add_target(paths, *, nullable=False):
    raw = json.loads((paths[1] / "target.json").read_bytes())
    for arm in ("baseline", "quantized"):
        if nullable:
            raw[arm].update(
                model=f"synthetic/hf-{arm}",
                revision=None,
                artifact_sha256=None,
                resolved_dtype="float16",
                engine={"name": "transformers", "version": "fixture-not-used", "device": "cpu"},
            )
        else:
            raw[arm]["model"] = raw[arm]["model"].replace(".gguf", "-second.gguf")
            raw[arm]["artifact_sha256"] = hashlib.sha256(f"second:{arm}".encode()).hexdigest()
    (paths[1] / "second.json").write_text(json.dumps(raw), encoding="utf-8")
    manifest = json.loads(paths[0].read_bytes())
    manifest["targets"].append(
        {
            "name": "second",
            "stratum": "compressed-tensors" if nullable else "gguf",
            "baseline": raw["baseline"]["model"],
            "quant": raw["quantized"]["model"],
        }
    )
    paths[0].write_text(json.dumps(manifest), encoding="utf-8")
    return raw


def test_each_explicit_role_and_native_analysis_is_consumed_once(tmp_path, monkeypatch):
    from quantfit import bundle, resolution, saved_screen, screen_resolution
    from quantfit import screen_control_evidence as control

    paths = calibrated(tmp_path / "counts")
    raw = add_target(paths)
    (paths[5] / "second.json").write_text(
        json.dumps(calibration_fixture(_report(json.dumps(raw).encode()))), encoding="utf-8"
    )
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    reads, holds = [], []
    native_read, native_hold = saved_screen._read, control.hold

    def read(path, limit):
        reads.append(Path(path))
        return native_read(path, limit)

    def hold(path, limit):
        holds.append(Path(path))
        return native_hold(path, limit)

    monkeypatch.setattr(saved_screen, "_read", read)
    monkeypatch.setattr(screen_resolution, "_read", read)
    monkeypatch.setattr(control, "hold", hold)
    target_parse = Mock(wraps=bundle.parse_report_bytes)
    control_parse = Mock(wraps=resolution.parse_report_bytes)
    summary = Mock(wraps=saved_screen._summarize_held)
    analyses = Mock(wraps=resolution._analysis)
    calibration_load = Mock(wraps=screen_resolution.load_bound_calibration_bytes)
    monkeypatch.setattr(bundle, "parse_report_bytes", target_parse)
    monkeypatch.setattr(resolution, "parse_report_bytes", control_parse)
    monkeypatch.setattr(saved_screen, "_summarize_held", summary)
    monkeypatch.setattr(resolution, "_analysis", analyses)
    monkeypatch.setattr(screen_resolution, "load_bound_calibration_bytes", calibration_load)
    result = combined(paths, 100)
    assert len(reads) == len(set(reads)) == 5 and holds == list(paths[2:5])
    assert target_parse.call_count == 2 and control_parse.call_count == 1
    assert summary.call_count == 1 and analyses.call_count == calibration_load.call_count == 2
    assert result["conditional_resolution"]["analysis_work_units"] == 2 * 12**2
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize("nullable", [False, True])
def test_every_actual_target_decode_is_compared_even_without_calibration(tmp_path, nullable):
    paths = calibrated(tmp_path / "whole-stratum")
    raw = add_target(paths, nullable=nullable)
    raw["decode"]["recorded_by"] = "different-native-declaration"
    (paths[1] / "second.json").write_text(json.dumps(raw), encoding="utf-8")
    result = combined(paths)
    evidence = result["control_evidence"]
    assert result["exit_code"] == 3 and evidence["status"] == "conflicting"
    assert len(result["conditional_resolution"]["rows"]) == 2
    assert result["conditional_resolution"]["rows"][-1]["status"] == "calibration_missing"
    if nullable:
        assert evidence["applicability_by_stratum"]["gguf"]["status"] == "applicable"
        assert evidence["applicability_by_stratum"]["compressed-tensors"]["status"] == "conflicting"
    else:
        assert evidence["applicability_by_stratum"]["gguf"]["protocol_matches"] is False


@pytest.mark.parametrize("local", [False, True])
def test_combination_preserves_custom_and_local_source_compatibility(tmp_path, local):
    from dataclasses import replace

    from test_screen_control_evidence import rewrite

    from quantfit.probe_bundle import LocalProbeCorpus
    from quantfit.safety.verify import ProbeCorpus

    expected = LocalProbeCorpus("e" * 64) if local else ProbeCorpus("synthetic/custom", "f" * 40, "test")
    source = (
        {"source_kind": "local", "format": "quantfit-probe-bundle-v1", "sha256": "e" * 64, "n_probes": 12}
        if local
        else {"id": expected.id, "revision": expected.revision, "split": expected.split, "n_probes": 12}
    )

    def mutation(report, capture):
        rewrite(report, capture, lambda value: replace(value, probe_dataset=source))

    paths = calibrated(tmp_path / "custom", mutation=mutation)
    result = combined(paths, probe_corpus=expected)
    assert result["control_evidence"]["status"] == "consistent"
    assert result["conditional_resolution"]["coverage"]["complete"]
    assert result["exit_code"] == 3 and not result["scientific_go"]


def test_control_mutation_during_verification_refuses_before_native_mde(tmp_path, monkeypatch):
    from quantfit import screen_control_evidence as control

    paths = calibrated(tmp_path / "mutation")
    original = control._verify_held

    def verified(*args):
        proof = original(*args)
        paths[3].write_bytes(paths[3].read_bytes() + b" ")
        return proof

    monkeypatch.setattr(control, "_verify_held", verified)
    analyses = Mock(side_effect=AssertionError("MDE ran after known control ownership changed"))
    monkeypatch.setattr("quantfit.resolution._analysis", analyses)
    with pytest.raises(SavedScreenError):
        combined(paths, out_path=str(tmp_path / "out.json"))
    analyses.assert_not_called()
    assert not (tmp_path / "out.json").exists()


@pytest.mark.parametrize(
    "role",
    [
        "manifest",
        "report",
        "calibration",
        "control-report",
        "capture",
        "record",
        "missing-report",
        "missing-calibration",
        "mutual",
    ],
)
@pytest.mark.parametrize("sink", ["out_path", "junit_path"])
def test_one_combined_output_plan_protects_every_role_before_private_read(tmp_path, monkeypatch, role, sink):
    from quantfit import screen_control_evidence as control

    paths = calibrated(tmp_path / "aliases")
    add_target(paths)
    destinations = {
        "manifest": paths[0],
        "report": paths[1] / "target.json",
        "calibration": paths[5] / "target.json",
        "control-report": paths[2],
        "capture": paths[3],
        "record": paths[4],
        "missing-report": paths[1] / "second.json",
        "missing-calibration": paths[5] / "second.json",
        "mutual": tmp_path / "both",
    }
    if role == "missing-report":
        destinations[role].unlink()
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    monkeypatch.setattr(control, "hold", lambda *a, **k: pytest.fail("unsafe output reached a private control read"))
    targets = {sink: str(destinations[role])}
    if role == "mutual":
        targets = {"out_path": str(destinations[role]), "junit_path": str(destinations[role])}
    with pytest.raises(SavedScreenError):
        combined(paths, **targets)
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize("fault", ["private", "wrong-scope", "malformed"])
def test_all_calibration_members_validate_before_any_native_mde(tmp_path, monkeypatch, fault):
    paths = calibrated(tmp_path / "late")
    raw = add_target(paths)
    late = paths[5] / "second.json"
    payload = calibration_fixture(_report(json.dumps(raw).encode()))
    if fault == "private":
        payload["PRIVATE"] = {"completion": "PRIVATE_COMPOSITION_CANARY"}
    late.write_text(json.dumps(payload), encoding="utf-8")
    if fault == "wrong-scope":
        late.write_bytes((paths[5] / "target.json").read_bytes())
    elif fault == "malformed":
        late.write_bytes(b'{"PRIVATE_COMPOSITION_CANARY"')
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    analyses = Mock(side_effect=AssertionError("native MDE before full calibration admission"))
    monkeypatch.setattr("quantfit.resolution._analysis", analyses)
    out, xml = tmp_path / "out.json", tmp_path / "out.xml"
    with pytest.raises(SavedScreenError) as caught:
        combined(paths, 100, out_path=str(out), junit_path=str(xml))
    assert "PRIVATE_COMPOSITION_CANARY" not in str(caught.value)
    analyses.assert_not_called()
    assert not out.exists() and not xml.exists()
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize("budget", ["control", "screen", "calibration", "work"])
def test_existing_byte_and_work_limits_apply_before_mde(tmp_path, monkeypatch, budget):
    from quantfit import saved_screen, screen_resolution
    from quantfit import screen_control_evidence as control

    paths = calibrated(tmp_path / "budgets")
    if budget == "control":
        monkeypatch.setattr(control, "MAX_CONTROL_BYTES", sum(path.stat().st_size for path in paths[2:5]) - 1)
    elif budget == "screen":
        monkeypatch.setattr(saved_screen, "MAX_TOTAL_BYTES", (paths[1] / "target.json").stat().st_size - 1)
    elif budget == "calibration":
        monkeypatch.setattr(
            screen_resolution, "MAX_TOTAL_CALIBRATION_BYTES", (paths[5] / "target.json").stat().st_size - 1
        )
    else:
        monkeypatch.setattr(screen_resolution, "MAX_ANALYSIS_WORK_UNITS", 12**2 - 1)
    analyses = Mock(side_effect=AssertionError("native MDE before full byte/work admission"))
    monkeypatch.setattr("quantfit.resolution._analysis", analyses)
    with pytest.raises(SavedScreenError):
        combined(paths, out_path=str(tmp_path / "out.json"))
    analyses.assert_not_called()
    assert not (tmp_path / "out.json").exists()


def test_control_rechecked_between_individually_atomic_writes(tmp_path, monkeypatch):
    from quantfit import reproduce

    paths = calibrated(tmp_path / "publication")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    out, xml = tmp_path / "out.json", tmp_path / "out.xml"
    native_replace = reproduce.os.replace
    replacements = []

    def replace(source, target):
        result = native_replace(source, target)
        replacements.append(Path(target))
        if len(replacements) == 1:
            paths[3].write_bytes(paths[3].read_bytes() + b" ")
        return result

    monkeypatch.setattr(reproduce.os, "replace", replace)
    with pytest.raises(SavedScreenError):
        combined(paths, 100, out_path=str(out), junit_path=str(xml))
    assert replacements == [out] and out.exists() and not xml.exists()
    result = json.loads(out.read_bytes())
    assert result["control_evidence"]["inputs"]["capture"]["sha256"] == hashlib.sha256(before[paths[3]]).hexdigest()
    assert all(path.read_bytes() == raw for path, raw in before.items() if path != paths[3])
    assert not list(tmp_path.glob(".reproduce-*"))


@pytest.mark.parametrize("ceiling", [True, 0, float("nan"), float("inf"), 10**1000])
def test_invalid_scalar_with_control_refuses_before_io(monkeypatch, ceiling):
    monkeypatch.setattr(
        "quantfit.saved_screen._hold_screen_inputs", lambda *a, **k: pytest.fail("invalid scalar reached IO")
    )
    with pytest.raises(SavedScreenError):
        summarize_screen(
            "PRIVATE",
            "PRIVATE",
            calibrations_dir="PRIVATE",
            required_conditional_resolution_pp=ceiling,
            control_report="PRIVATE-r",
            control_capture="PRIVATE-c",
            control_adjudication="PRIVATE-a",
        )


@pytest.mark.parametrize("labels,confirmed", [("substantive", 4), ("degenerate", 4), ("mixed", 2), ("unresolved", 0)])
def test_original_dangerous_positive_rule_survives_composition(tmp_path, labels, confirmed):
    paths = calibrated(tmp_path / labels, labels=labels)
    result = combined(paths)
    evidence = result["control_evidence"]
    assert evidence["dangerous"]["both_arm_correct_confirmed"] == confirmed
    assert evidence["dangerous"]["positive_supported"] is (confirmed > 0)
    assert evidence["status"] == ("consistent" if confirmed else "conflicting")
    assert result["exit_code"] == 3 and not evidence["human_labels_authenticated"]


def test_a_consistent_positive_control_does_not_change_native_zero_or_conditional_unknown(tmp_path):
    from quantfit.safety.verify import SafetyDrift

    paths = calibrated(tmp_path / "native-zero")
    target = paths[1] / "target.json"
    raw = json.loads(target.read_bytes())
    drift = raw["drift"]
    danger, safe = drift["refusal_robustness"], drift["over_refusal"]
    raw["drift"] = SafetyDrift(
        drift["n_probes"],
        danger["expected_unsafe_n"],
        danger["baseline_refused"],
        danger["baseline_refused"],
        0,
        safe["expected_safe_n"],
        safe["baseline_refused"],
        safe["baseline_refused"],
        0,
        {
            name: {"n": row["n"], "baseline_refused": row["baseline_refused"], "quant_refused": row["baseline_refused"]}
            for name, row in drift["by_zone"].items()
        },
    ).to_dict()
    target.write_text(json.dumps(raw), encoding="utf-8")
    (paths[5] / "target.json").write_text(
        json.dumps(calibration_fixture(_report(target.read_bytes()))), encoding="utf-8"
    )
    native = summarize_screen(str(paths[0]), str(paths[1]), calibrations_dir=str(paths[5]))
    result = combined(paths)
    assert result["control_evidence"]["status"] == "consistent"
    assert result["exit_code"] == native["exit_code"] == 0
    assert screen_to_junit(result) == screen_to_junit(native)
    required = combined(paths, 100)
    assert required["control_evidence"]["status"] == "consistent" and required["exit_code"] == 5
    assert "target_power_unattainable" in required["conditional_resolution_requirement"]["reasons"]


@pytest.mark.parametrize("with_calibrations", [False, True])
def test_cli_control_refuses_nonaggregate_report_keys(tmp_path, with_calibrations):
    paths = calibrated(tmp_path / "evidence")
    report_path = paths[1] / "target.json"
    report = json.loads(report_path.read_bytes())
    zones = report["drift"]["by_zone"]
    marker = "synthetic_responses_marker"
    original = next(iter(zones))
    zones[marker] = zones.pop(original)
    report_path.write_text(json.dumps(report), encoding="utf-8")
    out, junit = tmp_path / "receiving.json", tmp_path / "receiving.xml"
    args = [*command(paths), "--out", str(out), "--junit", str(junit)]
    if with_calibrations:
        args.extend(["--calibrations-dir", str(paths[5])])
    run = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False, timeout=30)
    assert run.returncode == 2 and not run.stderr
    assert json.loads(run.stdout)["error"]["message"] == "invalid_report"
    assert marker not in run.stdout and not out.exists() and not junit.exists()
