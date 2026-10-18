"""Actual CLI screen comparison, also selected by the installed application-origin guard."""

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("screen_compare_consumer", ROOT / "tools/ci_screen_compare.py")
assert SPEC is not None and SPEC.loader is not None
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


@pytest.fixture(autouse=True)
def no_inference_or_assets(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline comparison attempted inference, resolution or download")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)


@pytest.fixture
def originals():
    return consumer.original_inputs(ROOT)


@pytest.fixture
def measured(originals):
    manifest, reports = originals
    return manifest, {name: consumer.observation(raw) for name, raw in reports.items()}


def pair(tmp_path, manifest, reference, candidate):
    return consumer.make_bundle(tmp_path / "reference", manifest, reference), consumer.make_bundle(
        tmp_path / "candidate", manifest, candidate
    )


def snapshot(root):
    return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_changed_observations_keep_exact_declared_arm_identities_and_native_statistics(measured, originals, tmp_path):
    from quantfit.screen_bundle import verify_screen_bundle

    manifest, reports = measured
    _, old = originals
    for name, raw in reports.items():
        value, source = json.loads(raw), json.loads(old[name])
        assert value["baseline"] == source["baseline"] and value["quantized"] == source["quantized"]
        assert value["drift"]["refusal_robustness"]["at_risk"] == 12
        assert value["drift"]["over_refusal"]["at_risk"] == 28
    bundle = consumer.make_bundle(tmp_path / "fixture", manifest, reports)
    assert verify_screen_bundle(str(bundle))["receiving_summary"]["exit_code"] == 0


def test_actual_cli_complete_conditional_json_output_and_two_axes_plus_overall_junit(tmp_path, measured):
    manifest, reports = measured
    reference, candidate = pair(tmp_path, manifest, reports, reports)
    before = snapshot(tmp_path)
    out, xml = tmp_path / "comparison.json", tmp_path / "comparison.xml"
    document, _ = consumer.invoke(reference, candidate, out=out, junit=xml)
    result = consumer.check(
        document, reference, candidate, manifest, {"reference": reports, "candidate": reports}, code=0
    )
    assert result["n_identical_report_pairs"] == 3 and result["n_matched_axes"] == 6
    assert json.loads(out.read_bytes()) == document["result"]
    assert consumer.check_junit(xml, document) == {"tests": 7, "failures": 0, "skipped": 0, "errors": 0}
    assert all(path.read_bytes() == raw for path, raw in before.items())


def test_new_flag_is_not_softened_by_compatible_declared_identity(tmp_path, measured):
    manifest, reference_reports = measured
    candidate_reports = dict(reference_reports)
    candidate_reports["clean"] = consumer.observation(reference_reports["clean"], dangerous=1)
    reference, candidate = pair(tmp_path, manifest, reference_reports, candidate_reports)
    xml = tmp_path / "comparison.xml"
    document, _ = consumer.invoke(reference, candidate, junit=xml)
    consumer.check(
        document,
        reference,
        candidate,
        manifest,
        {"reference": reference_reports, "candidate": candidate_reports},
        code=3,
    )
    assert document["result"]["rows"][0]["axes"]["refusal_robustness"]["transition"] == "newly_flagged"
    assert consumer.check_junit(xml, document) == {"tests": 7, "failures": 2, "skipped": 0, "errors": 0}


def test_apparent_clearance_preserves_old_flag_and_unmeasured_axes(tmp_path, originals, measured):
    manifest, reference_reports = originals
    _, candidate_reports = measured
    reference, candidate = pair(tmp_path, manifest, reference_reports, candidate_reports)
    xml = tmp_path / "comparison.xml"
    document, _ = consumer.invoke(reference, candidate, junit=xml)
    consumer.check(
        document,
        reference,
        candidate,
        manifest,
        {"reference": reference_reports, "candidate": candidate_reports},
        code=3,
    )
    axis = document["result"]["rows"][1]["axes"]["refusal_robustness"]
    assert (
        axis["transition"] == "apparent_clearance"
        and axis["reference"]["flips"] == 1
        and axis["candidate"]["flips"] == 0
    )
    assert consumer.check_junit(xml, document) == {"tests": 7, "failures": 2, "skipped": 2, "errors": 0}


def test_original_bundle_compared_to_itself_keeps_flags_and_no_independence_claim(tmp_path, originals):
    manifest, reports = originals
    bundle = consumer.make_bundle(tmp_path / "fixture", manifest, reports)
    document, _ = consumer.invoke(bundle, bundle)
    result = consumer.check(document, bundle, bundle, manifest, {"reference": reports, "candidate": reports}, code=3)
    assert result["n_identical_report_pairs"] == 3 and result["independent_execution_verified"] is False


def test_missing_candidate_target_is_explicit_and_junit_skipped(tmp_path, measured):
    manifest, reference_reports = measured
    candidate_reports = {name: raw for name, raw in reference_reports.items() if name != "flagged"}
    reference, candidate = pair(tmp_path, manifest, reference_reports, candidate_reports)
    xml = tmp_path / "comparison.xml"
    document, _ = consumer.invoke(reference, candidate, junit=xml)
    consumer.check(
        document,
        reference,
        candidate,
        manifest,
        {"reference": reference_reports, "candidate": candidate_reports},
        code=4,
    )
    assert consumer.check_junit(xml, document) == {"tests": 7, "failures": 0, "skipped": 3, "errors": 0}


@pytest.mark.parametrize("known", [True, False])
def test_known_identity_contradiction_blocks_but_unknown_identity_remains_qualified(tmp_path, measured, known):
    manifest, reference_reports = measured
    candidate_reports = dict(reference_reports)
    report = json.loads(candidate_reports["clean"])
    report["baseline"]["artifact_sha256"] = "f" * 64 if known else None
    candidate_reports["clean"] = json.dumps(report).encode()
    reference, candidate = pair(tmp_path, manifest, reference_reports, candidate_reports)
    document, _ = consumer.invoke(reference, candidate)
    consumer.check(
        document,
        reference,
        candidate,
        manifest,
        {"reference": reference_reports, "candidate": candidate_reports},
        code=4 if known else 0,
    )
    row = document["result"]["rows"][0]
    assert row["identity"]["state"] == ("incompatible" if known else "unavailable")
    assert row["axes"]["refusal_robustness"]["status"] == ("incompatible_target_identity" if known else "matched")
    assert row["identity"]["same_weights_established"] is False


@pytest.mark.parametrize(
    "dtype,baseline_unknown,code",
    [("", False, 0), (" \t ", False, 0), ("unknown", False, 0), ("Q8_0", False, 4), ("Q8_0", True, 4)],
)
def test_unknown_precision_never_masks_known_quantized_identity_contradictions(
    tmp_path, measured, dtype, baseline_unknown, code
):
    manifest, reference_reports = measured
    candidate_reports = dict(reference_reports)
    report = json.loads(candidate_reports["clean"])
    report["quantized"]["resolved_dtype"] = dtype
    if baseline_unknown:
        report["baseline"]["artifact_sha256"] = None
    candidate_reports["clean"] = json.dumps(report).encode()
    reference, candidate = pair(tmp_path, manifest, reference_reports, candidate_reports)
    document, _ = consumer.invoke(reference, candidate)
    consumer.check(
        document,
        reference,
        candidate,
        manifest,
        {"reference": reference_reports, "candidate": candidate_reports},
        code=code,
    )
    row = document["result"]["rows"][0]
    if code == 0:
        assert row["identity"]["state"] == "unavailable"
        assert "resolved_dtype" in row["identity"]["unavailable_fields"]["quantized"]
        assert row["axes"]["refusal_robustness"]["status"] == "matched"
    else:
        assert row["identity"]["state"] == "incompatible"
        assert {"arm": "quantized", "field": "resolved_dtype"} in row["identity"]["differences"]
        assert row["axes"]["refusal_robustness"]["status"] == "incompatible_target_identity"
        assert row["axes"]["refusal_robustness"]["transition"] is None
    assert row["identity"]["same_weights_established"] is False


@pytest.mark.parametrize("flagged", [False, True])
def test_protocol_mismatch_retains_any_known_native_flag_before_incomplete(tmp_path, measured, flagged):
    manifest, reference_reports = measured
    candidate_reports = {}
    for name, raw in reference_reports.items():
        changed = consumer.observation(raw, dangerous=int(flagged and name == "clean"))
        report = json.loads(changed)
        report["decode"]["max_new_tokens"] = 63
        candidate_reports[name] = json.dumps(report).encode()
    reference, candidate = pair(tmp_path, manifest, reference_reports, candidate_reports)
    xml = tmp_path / "comparison.xml"
    document, _ = consumer.invoke(reference, candidate, junit=xml)
    consumer.check(
        document,
        reference,
        candidate,
        manifest,
        {"reference": reference_reports, "candidate": candidate_reports},
        code=3 if flagged else 4,
    )
    assert all(row["protocol_match"] is False for row in document["result"]["rows"])
    junit = consumer.check_junit(xml, document)
    assert junit["failures"] == (2 if flagged else 0) and junit["skipped"] == (5 if flagged else 7)


def test_semantically_equal_but_byte_different_target_manifest_refuses_without_outputs(tmp_path, measured):
    manifest, reports = measured
    reference = consumer.make_bundle(tmp_path / "reference", manifest, reports)
    candidate = consumer.make_bundle(tmp_path / "candidate", manifest + b" ", reports)
    before = snapshot(tmp_path)
    out, xml = tmp_path / "comparison.json", tmp_path / "comparison.xml"
    document, _ = consumer.invoke(reference, candidate, out=out, junit=xml)
    assert document["exit_code"] == 2 and document["result"] is None
    assert not out.exists() and not xml.exists() and all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize("mutation", ["corrupt", "unknown", "budget"])
def test_malformed_inventory_and_transport_limits_refuse_without_reflection(tmp_path, measured, mutation):
    manifest, reports = measured
    reference, candidate = pair(tmp_path, manifest, reports, reports)
    if mutation == "corrupt":
        (candidate / "reports/clean.json").write_bytes(b'{"PRIVATE_SENTINEL_DO_NOT_REFLECT":')
    elif mutation == "unknown":
        (candidate / "PRIVATE_SENTINEL_DO_NOT_REFLECT.json").write_bytes(b"{}")
    else:
        path = candidate / "manifest.json"
        raw = path.read_bytes()
        path.write_bytes(raw + b" " * (256 * 1024 + 1 - len(raw)))
    before = snapshot(tmp_path)
    document, stderr = consumer.invoke(reference, candidate)
    assert document["exit_code"] == 2 and document["result"] is None
    assert "PRIVATE_SENTINEL_DO_NOT_REFLECT" not in json.dumps(document) + stderr
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize("alias", ["outer", "native", "targets", "outside-hardlink", "same-outputs"])
def test_output_alias_protection_keeps_original_bytes(tmp_path, measured, alias):
    manifest, reports = measured
    reference, candidate = pair(tmp_path, manifest, reports, reports)
    output = {
        "outer": candidate / "manifest.json",
        "native": candidate / "reports/clean.json",
        "targets": reference / "targets.json",
        "outside-hardlink": tmp_path / "outside.json",
        "same-outputs": tmp_path / "same.json",
    }[alias]
    if alias == "outside-hardlink":
        os.link(reference / "reports/clean.json", output)
    before = snapshot(tmp_path)
    document, _ = consumer.invoke(reference, candidate, out=output, junit=output if alias == "same-outputs" else None)
    assert document["exit_code"] == 2 and all(path.read_bytes() == raw for path, raw in before.items())
    if alias == "same-outputs":
        assert not output.exists()


@pytest.mark.parametrize("name,expected", [("clean", 0), ("flagged", 3), ("unmeasured", 4)])
def test_cpu_adapter_uses_existing_one_target_bundle_and_original_report_only(tmp_path, originals, name, expected):
    manifest_raw, reports = originals
    manifest = json.loads(manifest_raw)
    manifest["targets"] = [next(target for target in manifest["targets"] if target["name"] == name)]
    raw_manifest = json.dumps(manifest).encode()
    bundle = consumer.make_bundle(tmp_path / "existing", raw_manifest, {name: reports[name]})
    original = tmp_path / "original-native.json"
    original.write_bytes(reports[name])
    before = snapshot(bundle)
    result = consumer.accept_cpu(bundle, original, tmp_path / "cpu-comparison")
    assert result["additional_native_calls"] == 0 and result["exit_code"] == expected
    assert result["n_identical_report_pairs"] == 1 and original.read_bytes() == reports[name]
    assert all(path.read_bytes() == raw for path, raw in before.items())


def test_installed_guard_and_existing_cpu_seams_are_single_offline_calls():
    installed = (ROOT / "tools/ci_installed.py").read_text(encoding="utf-8")
    assert installed.count('"test_ci_screen_compare.py"') == 1 and "--rootdir" in installed
    cpu = (ROOT / "tools/ci_cpu_acceptance.py").read_text(encoding="utf-8")
    assert cpu.count("screen_compare_accept_cpu(") == 1 and '"screen_comparison": screen_comparison' in cpu


def test_committed_comparison_originals_outer_manifests_and_receiving_bindings_are_literal():
    data = ROOT / "validation/2026-10-18-screen-comparison"
    manifest = (data / "inputs/targets.json").read_bytes()
    old_manifest, old_reports = consumer.original_inputs(ROOT)
    assert manifest == old_manifest and len(manifest) == 803
    names = [target["name"] for target in json.loads(manifest)["targets"]]
    original = {name: (data / "inputs/original" / f"{name}.json").read_bytes() for name in names}
    assert original == old_reports
    measured = {name: (data / "inputs/measured" / f"{name}.json").read_bytes() for name in names}
    variants = {
        "original": original,
        "measured": measured,
        "introduced": {**measured, "clean": (data / "inputs/new-flag/clean.json").read_bytes()},
        "missing": {name: raw for name, raw in measured.items() if name != "flagged"},
        "known-identity": {**measured, "clean": (data / "inputs/known-identity/clean.json").read_bytes()},
        "unknown-identity": {**measured, "clean": (data / "inputs/unknown-identity/clean.json").read_bytes()},
        "byte-different-targets": measured,
    }
    receipt = json.loads((data / "receipt.json").read_bytes())
    assert receipt["inputs"]["targets"] == consumer.binding(manifest)
    outers = {}
    for name, reports in variants.items():
        raw = (data / "bundle-manifests" / f"{name}.json").read_bytes()
        outer = json.loads(raw)
        outers[name] = raw
        target_raw = (
            (data / "inputs/byte-different-targets.json").read_bytes() if name == "byte-different-targets" else manifest
        )
        assert target_raw == manifest + b" " if name == "byte-different-targets" else target_raw == manifest
        assert outer["targets"] == {"path": "targets.json", **consumer.binding(target_raw)}
        members = {"manifest.json": raw, "targets.json": target_raw}
        for entry, target in zip(outer["reports"], names, strict=True):
            source = reports.get(target)
            assert entry == {
                "name": target,
                "path": f"reports/{target}.json",
                "status": "present" if source is not None else "missing",
                **(consumer.binding(source) if source is not None else {"sha256": None, "size_bytes": None}),
            }
            if source is not None:
                members[entry["path"]] = source
        assert receipt["bundles"][name] == [
            {"path": path, **consumer.binding(value)} for path, value in sorted(members.items())
        ]
        if name != "byte-different-targets":
            assert receipt["inputs"]["variants"][name] == [
                {"name": target, **consumer.binding(source)} for target, source in reports.items()
            ]
    for name, code, failures, skipped in (
        ("conditional-copy", 0, 0, 0),
        ("introduced-flag", 3, 2, 0),
        ("apparent-clearance", 3, 2, 2),
        ("original-copy", 3, 2, 2),
        ("missing-evidence", 4, 0, 3),
        ("known-identity", 4, 0, 3),
        ("unknown-identity", 0, 0, 0),
    ):
        compact = receipt[name]
        document = json.loads((data / f"{name}-cli.json").read_bytes())
        result = json.loads((data / f"{name}.json").read_bytes())
        assert document["result"] == result and document["exit_code"] == result["exit_code"] == code
        for side in ("reference", "candidate"):
            variant = compact[f"{side}_bundle"]
            assert result["inputs"][side]["bundle_manifest_sha256"] == consumer.binding(outers[variant])["sha256"]
            assert result["inputs"][side]["transport_bytes"] == sum(
                entry["size_bytes"] for entry in receipt["bundles"][variant]
            )
            assert result["inputs"][side] == compact["inputs"][side]
            saved = {entry["name"]: entry for entry in result["screens"][side]["report_bindings"]}
            for row in result["rows"]:
                source = variants[variant].get(row["name"])
                expected = consumer.binding(source) if source is not None else {"sha256": None, "size_bytes": None}
                for entry in (row["bindings"][side], saved[row["name"]]):
                    assert {key: entry[key] for key in expected} == expected
                for axis in consumer.AXES:
                    assert row["axes"][axis][side] == consumer.native_axis(source, axis)
        assert (
            consumer.check_junit(data / f"{name}.xml", document)
            == compact["junit"]
            == {"tests": 7, "failures": failures, "skipped": skipped, "errors": 0}
        )
    for name in ("target-bytes-refusal", "output-alias-refusal"):
        assert json.loads((data / f"{name}.json").read_bytes())["exit_code"] == 2
    # Recorded source hashes are historical provenance, never a future-current package assertion.
    assert len(receipt["runtime"]["source_files"]) == 8 and receipt["runtime"]["source_version"] == "0.34.0"
