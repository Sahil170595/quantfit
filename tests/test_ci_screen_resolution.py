"""Actual CLI conditional annotations, selected by the installed application-origin guard."""

import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("screen_resolution_consumer", ROOT / "tools/ci_screen_resolution.py")
assert SPEC is not None and SPEC.loader is not None
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


@pytest.fixture(autouse=True)
def no_inference_or_assets(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline annotation attempted inference, arm resolution or download")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)


def test_actual_cli_empty_calibration_directory_preserves_native_verdict_and_junit(tmp_path):
    manifest_raw, reports_raw = consumer.original_inputs(ROOT)
    manifest, reports, calibrations = consumer.stage(tmp_path / "inputs", manifest_raw, reports_raw, {})
    native_xml, annotated_xml = tmp_path / "native.xml", tmp_path / "annotated.xml"
    default, _ = consumer.invoke(manifest, reports, junit=native_xml)
    annotated, _ = consumer.invoke(manifest, reports, calibrations, junit=annotated_xml)
    compact = consumer.check(annotated, default, manifest_raw, reports_raw, {})
    assert compact["n_calibration_missing"] == 3 and compact["analysis_work_units"] == 0
    assert native_xml.read_bytes() == annotated_xml.read_bytes()


@pytest.fixture
def originals():
    manifest, reports = consumer.original_inputs(ROOT)
    return manifest, reports, {name: consumer.calibration_bytes(raw) for name, raw in reports.items()}


def snapshot(root):
    return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def encode(payload):
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def rebound(raw, change):
    from quantfit.safety.calibration_binding import identity_fingerprint

    payload = json.loads(raw)
    change(payload["binding"]["identity"])
    payload["binding"]["fingerprint"] = identity_fingerprint(payload["binding"]["identity"])
    return encode(payload)


def test_synthetic_calibrations_are_native_bound_aggregates_not_human_evidence(originals):
    from quantfit.resolution import parse_report_bytes
    from quantfit.safety.calibration_binding import load_bound_calibration_bytes

    _, reports, calibrations = originals
    for name, raw in calibrations.items():
        bound = load_bound_calibration_bytes(raw, report=parse_report_bytes(reports[name]))
        assert bound.eps_baseline_upper < bound.eps_quant_upper
        assert json.loads(raw)["label"].startswith("SYNTHETIC")
        assert bound.fingerprint == json.loads(raw)["binding"]["fingerprint"]


@pytest.mark.parametrize("family,code", [("original", 3), ("measured", 0), ("unmeasured", 4)])
def test_actual_cli_full_calibration_is_direct_conditional_analysis_with_unchanged_native_result(
    tmp_path, originals, family, code
):
    from quantfit import resolution

    manifest_raw, reports_raw, calibrations_raw = originals
    if family == "measured":
        directory = ROOT / "validation/2026-10-18-screen-comparison/inputs/measured"
        reports_raw = {name: (directory / f"{name}.json").read_bytes() for name in reports_raw}
        calibrations_raw = {name: consumer.calibration_bytes(raw) for name, raw in reports_raw.items()}
    elif family == "unmeasured":
        payload = json.loads(manifest_raw)
        payload["targets"] = [row for row in payload["targets"] if row["name"] == "unmeasured"]
        manifest_raw = encode(payload)
        reports_raw = {"unmeasured": reports_raw["unmeasured"]}
        calibrations_raw = {"unmeasured": calibrations_raw["unmeasured"]}
    manifest, reports, calibrations = consumer.stage(tmp_path / "inputs", manifest_raw, reports_raw, calibrations_raw)
    before = snapshot(tmp_path)
    default, _ = consumer.invoke(manifest, reports, junit=tmp_path / "native.xml")
    output, xml = tmp_path / "annotated.json", tmp_path / "annotated.xml"
    with patch("quantfit.resolution.analyze_resolution_bytes", wraps=resolution.analyze_resolution_bytes) as analysis:
        annotated, _ = consumer.invoke(manifest, reports, calibrations, out=output, junit=xml)
    assert analysis.call_count == len(reports_raw)
    compact = consumer.check(annotated, default, manifest_raw, reports_raw, calibrations_raw)
    assert compact["exit_code"] == code and compact["n_analyzed"] == len(reports_raw)
    assert json.loads(output.read_bytes()) == annotated["result"]
    assert (tmp_path / "native.xml").read_bytes() == xml.read_bytes()
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize("missing_report,missing_calibration", [(None, "flagged"), ("clean", None), ("clean", "clean")])
def test_partial_and_orphan_calibrations_retain_explicit_exclusive_coverage(
    tmp_path, originals, missing_report, missing_calibration
):
    manifest_raw, reports_raw, calibrations_raw = originals
    reports_raw = {name: raw for name, raw in reports_raw.items() if name != missing_report}
    calibrations_raw = {name: raw for name, raw in calibrations_raw.items() if name != missing_calibration}
    manifest, reports, calibrations = consumer.stage(tmp_path / "inputs", manifest_raw, reports_raw, calibrations_raw)
    default, _ = consumer.invoke(manifest, reports, junit=tmp_path / "native.xml")
    annotated, _ = consumer.invoke(manifest, reports, calibrations, junit=tmp_path / "annotated.xml")
    consumer.check(annotated, default, manifest_raw, reports_raw, calibrations_raw)
    assert (tmp_path / "native.xml").read_bytes() == (tmp_path / "annotated.xml").read_bytes()


def test_valid_calibration_label_is_not_reflected_as_authenticated_or_private_evidence(tmp_path, originals):
    manifest_raw, reports_raw, calibrations_raw = originals
    value = json.loads(calibrations_raw["clean"])
    value["label"] = "PRIVATE_SENTINEL_DO_NOT_REFLECT; synthetic unverified label"
    calibrations_raw["clean"] = encode(value)
    manifest, reports, calibrations = consumer.stage(tmp_path / "inputs", manifest_raw, reports_raw, calibrations_raw)
    default, _ = consumer.invoke(manifest, reports)
    annotated, stderr = consumer.invoke(manifest, reports, calibrations)
    consumer.check(annotated, default, manifest_raw, reports_raw, calibrations_raw)
    assert "PRIVATE_SENTINEL_DO_NOT_REFLECT" not in json.dumps(annotated) + stderr


@pytest.mark.parametrize("mutation", ["corrupt", "counts", "scope", "fingerprint", "unknown", "oversize"])
def test_invalid_late_calibration_refuses_before_any_earlier_analysis(tmp_path, originals, mutation):
    manifest_raw, reports_raw, calibrations_raw = originals
    altered = dict(calibrations_raw)
    raw = json.loads(altered["unmeasured"])
    if mutation == "corrupt":
        altered["unmeasured"] = b'{"PRIVATE_SENTINEL_DO_NOT_REFLECT":'
    elif mutation == "counts":
        raw["baseline"]["n"] = True
        altered["unmeasured"] = encode(raw)
    elif mutation == "scope":
        altered["unmeasured"] = rebound(
            altered["unmeasured"], lambda identity: identity["decode"].update(max_new_tokens=63)
        )
    elif mutation == "fingerprint":
        raw["binding"]["fingerprint"] = "f" * 64
        altered["unmeasured"] = encode(raw)
    elif mutation == "oversize":
        altered["unmeasured"] += b" " * (2097153 - len(altered["unmeasured"]))
    manifest, reports, calibrations = consumer.stage(tmp_path / "inputs", manifest_raw, reports_raw, altered)
    if mutation == "unknown":
        (calibrations / "PRIVATE_SENTINEL_DO_NOT_REFLECT.json").write_bytes(b"{}")
    before = snapshot(tmp_path)
    out, xml = tmp_path / "refused.json", tmp_path / "refused.xml"
    with patch(
        "quantfit.resolution.analyze_resolution_bytes", side_effect=AssertionError("analysis before preflight")
    ) as analysis:
        document, stderr = consumer.invoke(manifest, reports, calibrations, out=out, junit=xml)
    analysis.assert_not_called()
    assert document["exit_code"] == 2 and document["result"] is None
    assert "PRIVATE_SENTINEL_DO_NOT_REFLECT" not in json.dumps(document) + stderr
    assert not out.exists() and not xml.exists() and all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize("contradiction", ["target", "backend"])
def test_orphan_calibration_known_target_or_backend_mismatch_refuses_without_actual_match(
    tmp_path, originals, contradiction
):
    manifest_raw, reports_raw, calibrations_raw = originals
    reports_raw = {name: raw for name, raw in reports_raw.items() if name != "unmeasured"}
    if contradiction == "target":
        calibrations_raw["unmeasured"] = calibrations_raw["clean"]
    else:
        calibrations_raw["unmeasured"] = rebound(
            calibrations_raw["unmeasured"],
            lambda identity: identity["baseline"]["engine"].update(name="transformers", version="synthetic"),
        )
    manifest, reports, calibrations = consumer.stage(tmp_path / "inputs", manifest_raw, reports_raw, calibrations_raw)
    before = snapshot(tmp_path)
    with patch(
        "quantfit.resolution.analyze_resolution_bytes", side_effect=AssertionError("analysis before scope")
    ) as analysis:
        document, _ = consumer.invoke(manifest, reports, calibrations)
    analysis.assert_not_called()
    assert document["exit_code"] == 2 and all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize(
    "alias", ["manifest", "native", "calibration", "outside-hardlink", "inside-calibrations", "same-outputs"]
)
def test_annotation_outputs_cannot_overwrite_any_input_or_protected_directory(tmp_path, originals, alias):
    manifest_raw, reports_raw, calibrations_raw = originals
    manifest, reports, calibrations = consumer.stage(tmp_path / "inputs", manifest_raw, reports_raw, calibrations_raw)
    output = {
        "manifest": manifest,
        "native": reports / "clean.json",
        "calibration": calibrations / "clean.json",
        "outside-hardlink": tmp_path / "outside.json",
        "inside-calibrations": calibrations / "new.json",
        "same-outputs": tmp_path / "same.json",
    }[alias]
    if alias == "outside-hardlink":
        os.link(calibrations / "clean.json", output)
    before = snapshot(tmp_path)
    with patch(
        "quantfit.resolution.analyze_resolution_bytes", side_effect=AssertionError("analysis before output guard")
    ) as analysis:
        document, _ = consumer.invoke(
            manifest, reports, calibrations, out=output, junit=output if alias == "same-outputs" else None
        )
    analysis.assert_not_called()
    assert document["exit_code"] == 2 and all(path.read_bytes() == raw for path, raw in before.items())


def scaled_native(raw, n):
    from quantfit.safety.verify import SafetyDrift

    report = json.loads(raw)
    unsafe, safe = n // 3, n - n // 3
    report["probe_dataset"]["n_probes"] = n
    report["drift"] = SafetyDrift(
        n,
        unsafe,
        unsafe,
        unsafe,
        0,
        safe,
        0,
        0,
        0,
        {
            "clear_unsafe": {"n": unsafe, "baseline_refused": unsafe, "quant_refused": unsafe},
            "clear_safe": {"n": safe, "baseline_refused": 0, "quant_refused": 0},
        },
    ).to_dict()
    report["quantfit_version"] = "synthetic-analysis-budget-fixture"
    return encode(report)


@pytest.mark.parametrize("n,population", [(4097, 1), (4096, 2)])
def test_report_and_cumulative_quadratic_analysis_bounds_are_preflighted_without_math(
    tmp_path, originals, n, population
):
    manifest_raw, reports_raw, _ = originals
    manifest = json.loads(manifest_raw)
    manifest["targets"] = manifest["targets"][:population]
    reports_raw = {row["name"]: scaled_native(reports_raw[row["name"]], n) for row in manifest["targets"]}
    calibrations_raw = {name: consumer.calibration_bytes(raw) for name, raw in reports_raw.items()}
    targets, reports, calibrations = consumer.stage(
        tmp_path / "inputs", encode(manifest), reports_raw, calibrations_raw
    )
    default, _ = consumer.invoke(targets, reports)
    # The existing native bundle reader already applies the 4096-probe cap.
    assert default["exit_code"] == (2 if n > 4096 else 0)
    empty = tmp_path / "empty-calibrations"
    empty.mkdir()
    absent, _ = consumer.invoke(targets, reports, empty)
    if n <= 4096:
        compact = consumer.check(absent, default, encode(manifest), reports_raw, {})
        assert compact["analysis_work_units"] == 0 and compact["n_calibration_missing"] == population
    else:
        assert absent["exit_code"] == 2
    with patch(
        "quantfit.resolution.analyze_resolution_bytes", side_effect=AssertionError("math before budget")
    ) as analysis:
        document, _ = consumer.invoke(targets, reports, calibrations)
    analysis.assert_not_called()
    assert document["exit_code"] == 2


def test_large_valid_stored_orphan_remains_pending_without_applying_an_analysis_cap(tmp_path, originals):
    manifest_raw, reports_raw, _ = originals
    payload = json.loads(manifest_raw)
    payload["targets"] = payload["targets"][:1]
    manifest_raw = encode(payload)
    calibrations_raw = {"clean": consumer.calibration_bytes(scaled_native(reports_raw["clean"], 4097))}
    manifest, reports, calibrations = consumer.stage(tmp_path / "inputs", manifest_raw, {}, calibrations_raw)
    default, _ = consumer.invoke(manifest, reports)
    with patch(
        "quantfit.resolution.analyze_resolution_bytes", side_effect=AssertionError("orphan analysis")
    ) as analysis:
        document, _ = consumer.invoke(manifest, reports, calibrations)
    analysis.assert_not_called()
    compact = consumer.check(document, default, manifest_raw, {}, calibrations_raw)
    assert (
        compact["n_pending_report_missing"] == 1 and compact["analysis_work_units"] == 0 and compact["exit_code"] == 4
    )


@pytest.mark.parametrize("name,code", [("clean", 0), ("flagged", 3), ("unmeasured", 4)])
def test_cpu_adapter_empty_calibrations_reuses_original_report_and_native_verdict(tmp_path, originals, name, code):
    _, reports, _ = originals
    path = tmp_path / "existing.json"
    path.write_bytes(reports[name])
    result = consumer.accept_cpu(path, tmp_path / "cpu-annotation")
    assert result["exit_code"] == code and result["n_calibration_missing"] == 1
    assert result["n_analyzed"] == result["analysis_work_units"] == result["additional_native_calls"] == 0
    assert path.read_bytes() == reports[name]


def test_installed_guard_and_cpu_seams_select_annotation_once_without_new_native_calls():
    installed = (ROOT / "tools/ci_installed.py").read_text(encoding="utf-8")
    assert installed.count('"test_ci_screen_resolution.py"') == 1 and "--rootdir" in installed
    cpu = (ROOT / "tools/ci_cpu_acceptance.py").read_text(encoding="utf-8")
    assert cpu.count("screen_resolution_accept_cpu(") == 1 and '"screen_resolution": screen_resolution' in cpu


def test_committed_resolution_inputs_native_verdicts_and_calibration_bindings_are_literal():
    data = ROOT / "validation/2026-10-18-screen-resolution"
    raw_inputs = {p.relative_to(data / "inputs").as_posix(): p.read_bytes() for p in (data / "inputs").rglob("*.json")}
    manifest = raw_inputs["targets.json"]
    original_manifest, original_reports = consumer.original_inputs(ROOT)
    assert manifest == original_manifest and len(manifest) == 803
    names = [target["name"] for target in json.loads(manifest)["targets"]]
    reports = {name: raw_inputs[f"reports/{name}.json"] for name in names}
    assert reports == original_reports
    measured = {name: raw_inputs[f"measured/{name}.json"] for name in names}
    calibrations = {name: raw_inputs[f"calibrations/{name}.json"] for name in names}
    receipt = json.loads((data / "receipt.json").read_bytes())
    assert receipt["inputs"] == {name: consumer.binding(raw) for name, raw in raw_inputs.items()}
    cases = {
        "full": (reports, calibrations, 3, 1, 1),
        "partial": (reports, {"clean": calibrations["clean"]}, 3, 1, 1),
        "empty": (reports, {}, 3, 1, 1),
        "pending": ({name: raw for name, raw in reports.items() if name != "clean"}, calibrations, 3, 1, 2),
        "both-missing": (
            {name: raw for name, raw in reports.items() if name != "unmeasured"},
            {name: raw for name, raw in calibrations.items() if name != "unmeasured"},
            3,
            1,
            1,
        ),
        "conditional": (measured, calibrations, 0, 0, 0),
        "conditional-missing-calibrations": (measured, {}, 0, 0, 0),
        "native-incomplete": ({name: raw for name, raw in reports.items() if name != "flagged"}, calibrations, 4, 0, 2),
    }
    for name, (native, bound, code, failures, skipped) in cases.items():
        compact = receipt[name]
        document = json.loads((data / f"{name}-cli.json").read_bytes())
        result = json.loads((data / f"{name}.json").read_bytes())
        default = json.loads((data / f"{name}-native.json").read_bytes())
        assert document["result"] == result and document["exit_code"] == result["exit_code"] == code
        assert consumer.native_projection(result) == consumer.native_projection(default)
        assert result["manifest"]["sha256"] == consumer.binding(manifest)["sha256"]
        assert result["manifest"]["size_bytes"] == len(manifest)
        for key, value in consumer.expected_native(manifest, native).items():
            assert compact[key] == value
        assert compact["native_reports"] == [
            {"name": target, **consumer.binding(raw)} for target, raw in native.items()
        ]
        assert compact["calibrations"] == [{"name": target, **consumer.binding(raw)} for target, raw in bound.items()]
        block = result["conditional_resolution"]
        assert [row["name"] for row in block["rows"]] == names
        statuses = {}
        work = 0
        saved = {row["name"]: row for row in result["report_bindings"]}
        for row in block["rows"]:
            target = row["name"]
            report, calibration = native.get(target), bound.get(target)
            raw_binding = consumer.binding(report) if report is not None else {"sha256": None, "size_bytes": None}
            assert {key: saved[target][key] for key in raw_binding} == raw_binding
            assert row["native_report_sha256"] == raw_binding["sha256"]
            assert row["calibration"] == {
                "member": f"{target}.json",
                "status": "present" if calibration is not None else "missing",
                **(consumer.binding(calibration) if calibration is not None else {"sha256": None, "size_bytes": None}),
            }
            assert row["binding_fingerprint"] == (
                json.loads(calibration)["binding"]["fingerprint"] if calibration is not None else None
            )
            status = (
                "analyzed"
                if report is not None and calibration is not None
                else "calibration_missing"
                if report is not None
                else "pending_report_missing"
                if calibration is not None
                else "report_and_calibration_missing"
            )
            assert row["status"] == status
            statuses[status] = statuses.get(status, 0) + 1
            if status != "analyzed":
                assert row["analysis"] is None
                continue
            analysis = row["analysis"]
            assert analysis["inputs"] == {
                "report_sha256": consumer.binding(report)["sha256"],
                "calibration_sha256": consumer.binding(calibration)["sha256"],
            }
            assert analysis["binding_fingerprint"] == row["binding_fingerprint"]
            assert analysis["human_confirmation_verified"] is analysis["assumptions_verified"] is False
            drift = json.loads(report)["drift"]
            for axis, flip in consumer.AXES.items():
                observed = analysis["axes"][axis.replace("_", "-")]
                assert (
                    observed["n_at_risk"] == drift[axis]["at_risk"] and observed["flagged_flips"] == drift[axis][flip]
                )
            work += json.loads(report)["probe_dataset"]["n_probes"] ** 2
        assert block["analysis_work_units"] == compact["analysis_work_units"] == work
        for status in ("analyzed", "calibration_missing", "pending_report_missing", "report_and_calibration_missing"):
            assert block["coverage"][f"n_{status}"] == compact[f"n_{status}"] == statuses.get(status, 0)
        assert (data / f"{name}-native.xml").read_bytes() == (data / f"{name}.xml").read_bytes()
        assert (
            consumer.junit_counts(data / f"{name}.xml")
            == compact["junit"]
            == {"tests": 3, "failures": failures, "skipped": skipped, "errors": 0}
        )
    for name in ("invalid-late-refusal", "output-alias-refusal"):
        assert json.loads((data / f"{name}.json").read_bytes())["exit_code"] == 2
    # These hashes bind the historical run, never the installed package of a future release.
    assert len(receipt["runtime"]["source_files"]) == 8
    assert receipt["runtime"]["source_version"] == receipt["runtime"]["distribution_version"] == "0.35.0"
