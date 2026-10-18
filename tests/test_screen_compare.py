"""Declared-target transitions preserve both native screens and their limitations."""

import json
import os
from pathlib import Path

import pytest
from test_saved_screen import corpus


def pair(
    tmp_path, reference=(0, None), candidate=(0, None), *, missing_ref=(), missing_cand=(), mutate=None, unknown=False
):
    from quantfit.screen_bundle import create_screen_bundle

    bundles = []
    for side, observation, missing in (("reference", reference, missing_ref), ("candidate", candidate, missing_cand)):
        root = tmp_path / side
        root.mkdir()
        manifest, reports = corpus(
            root, [("g0", "gguf", observation[0], 0, observation[1])], missing=missing, unknown_weights=unknown
        )
        if side == "candidate" and mutate is not None:
            path = reports / "g0.json"
            payload = json.loads(path.read_bytes())
            mutate(payload)
            path.write_text(json.dumps(payload), encoding="utf-8")
        out = root / "bundle"
        create_screen_bundle(str(manifest), str(reports), str(out))
        bundles.append(out)
    assert (bundles[0] / "targets.json").read_bytes() == (bundles[1] / "targets.json").read_bytes()
    return bundles


def compare(reference, candidate, **kwargs):
    from quantfit.screen_compare import compare_screen_bundles

    return compare_screen_bundles(str(reference), str(candidate), **kwargs)


@pytest.mark.parametrize(
    "before,after,transition,code",
    [(0, 0, "no_flag", 0), (0, 1, "newly_flagged", 3), (1, 1, "persisting_flag", 3), (1, 0, "apparent_clearance", 3)],
)
def test_axis_transitions_keep_native_flags_without_flagging_the_other_axis(tmp_path, before, after, transition, code):
    reference, candidate = pair(tmp_path, (before, None), (after, None))
    result = compare(reference, candidate)
    assert result["exit_code"] == code and result["kind"] == "quantfit.screen-comparison"
    row = result["rows"][0]
    danger, over = row["axes"]["refusal_robustness"], row["axes"]["over_refusal"]
    assert danger["transition"] == transition and danger["status"] == "matched"
    assert danger["reference"]["flips"] == before and danger["candidate"]["flips"] == after
    assert danger["reference"]["at_risk"] == 12 and danger["candidate"]["at_risk"] == 12
    assert over["reference"]["flagged"] is False and over["candidate"]["flagged"] is False
    assert over["transition"] == "no_flag"
    assert row["identity"]["same_weights_established"] is False
    assert result["independent_execution_verified"] is False and result["scientific_go"] is False


@pytest.mark.parametrize(
    "missing_ref,missing_cand,status,code",
    [(True, False, "missing_reference", 0), (False, True, "missing_candidate", 3), (True, True, "missing_both", 4)],
)
def test_missing_status_preserves_available_native_flag(tmp_path, missing_ref, missing_cand, status, code):
    reference, candidate = pair(
        tmp_path,
        (1, None),
        (0, None),
        missing_ref=("g0",) if missing_ref else (),
        missing_cand=("g0",) if missing_cand else (),
    )
    result = compare(reference, candidate)
    axis = result["rows"][0]["axes"]["refusal_robustness"]
    assert axis["status"] == status and axis["transition"] is None and axis["comparison_basis"] is None
    assert result["exit_code"] == (4 if code == 0 else code)
    assert result["rows"][0]["protocol_match"] is None


@pytest.mark.parametrize(
    "arm,field,value",
    [
        ("baseline", "revision", "a" * 40),
        ("quantized", "artifact_sha256", "b" * 64),
        ("baseline", "resolved_dtype", "F32"),
        ("quantized", "resolved_dtype", "Q5_K_M"),
    ],
)
def test_each_known_arm_identity_contradiction_blocks_transition(tmp_path, arm, field, value):
    reference, candidate = pair(tmp_path, mutate=lambda payload: payload[arm].__setitem__(field, value))
    result = compare(reference, candidate)
    row = result["rows"][0]
    assert result["exit_code"] == 4 and row["identity"]["state"] == "incompatible"
    assert row["identity"]["differences"] == [{"arm": arm, "field": field}]
    assert row["axes"]["refusal_robustness"]["status"] == "incompatible_target_identity"
    assert row["axes"]["refusal_robustness"]["transition"] is None


def test_unknown_identity_allows_only_qualified_declared_transition(tmp_path):
    reference, candidate = pair(tmp_path, unknown=True)
    result = compare(reference, candidate)
    row = result["rows"][0]
    assert result["exit_code"] == 0 and row["identity"]["state"] == "unavailable"
    assert row["identity"]["unavailable_fields"]["baseline"] == ["revision", "artifact_sha256"]
    assert row["axes"]["refusal_robustness"]["comparison_basis"] == "declared_target_and_compatible_protocol"
    assert row["identity"]["same_weights_established"] is False


def test_unknown_baseline_does_not_hide_known_quantized_contradiction(tmp_path):
    def mutate(payload):
        payload["baseline"]["revision"] = None
        payload["quantized"]["artifact_sha256"] = "b" * 64

    reference, candidate = pair(tmp_path, (1, None), (0, None), mutate=mutate)
    result = compare(reference, candidate)
    row = result["rows"][0]
    assert result["exit_code"] == 3 and row["identity"]["state"] == "incompatible"
    assert row["identity"]["differences"] == [{"arm": "quantized", "field": "artifact_sha256"}]
    assert row["axes"]["refusal_robustness"]["reference"]["flagged"] is True
    assert row["axes"]["refusal_robustness"]["transition"] is None


def test_known_protocol_mismatch_preserves_native_flag(tmp_path):
    reference, candidate = pair(
        tmp_path,
        (1, None),
        (0, None),
        mutate=lambda payload: payload["env"].__setitem__("python", "another declared runtime"),
    )
    result = compare(reference, candidate)
    assert result["exit_code"] == 3 and result["rows"][0]["protocol_match"] is False
    assert all(
        axis["status"] == "incompatible_scope" and axis["transition"] is None
        for axis in result["rows"][0]["axes"].values()
    )


def test_unmeasured_denominator_is_not_apparent_clearance(tmp_path):
    reference, candidate = pair(tmp_path, (1, None), (0, "danger"))
    result = compare(reference, candidate)
    axis = result["rows"][0]["axes"]["refusal_robustness"]
    assert axis["status"] == "unmeasured_candidate" and axis["transition"] is None
    assert axis["candidate"]["at_risk"] == 0 and axis["reference"]["flagged"] is True and result["exit_code"] == 3


def test_exact_target_manifest_bytes_required_even_when_decoded_equal(tmp_path):
    from quantfit.screen_compare import ScreenComparisonError

    reference, candidate = pair(tmp_path)
    outer_path = candidate / "manifest.json"
    outer = json.loads(outer_path.read_bytes())
    raw = json.dumps(json.loads((candidate / "targets.json").read_bytes()), indent=3).encode()
    import hashlib

    (candidate / "targets.json").write_bytes(raw)
    outer["targets"].update(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))
    outer_path.write_text(json.dumps(outer), encoding="utf-8")
    with pytest.raises(ScreenComparisonError, match="target_manifest_mismatch"):
        compare(reference, candidate)


def test_identical_root_is_held_once_and_does_not_prove_independence(tmp_path, monkeypatch):
    from quantfit import screen_bundle_inputs as inputs

    reference, _ = pair(tmp_path, (1, "over"), (0, None))
    read = inputs._read
    calls = []

    def once(path, limit):
        assert path not in calls
        calls.append(path)
        return read(path, limit)

    monkeypatch.setattr(inputs, "_read", once)
    result = compare(reference, reference)
    assert len(calls) == 3 and result["exit_code"] == 3
    assert result["rows"][0]["identical_report_bytes"] is True
    assert result["independent_execution_verified"] is False


@pytest.mark.parametrize("source", ["outer", "targets", "report", "inside", "outputs", "hardlink"])
def test_output_aliases_preserve_all_inputs(tmp_path, source):
    from quantfit.screen_compare import ScreenComparisonError

    reference, candidate = pair(tmp_path)
    output = {
        "outer": reference / "manifest.json",
        "targets": candidate / "targets.json",
        "report": reference / "reports/g0.json",
        "inside": candidate / "new.json",
        "outputs": tmp_path / "same.json",
        "hardlink": tmp_path / "alias.json",
    }[source]
    if source == "hardlink":
        os.link(reference / "reports/g0.json", output)
    before = {path: path.read_bytes() for root in (reference, candidate) for path in root.rglob("*") if path.is_file()}
    with pytest.raises(ScreenComparisonError):
        compare(reference, candidate, out_path=str(output), junit_path=str(output) if source == "outputs" else None)
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize("dtype", ["", "  ", "unknown", " UNAVAILABLE ", "unverified", "not_recorded", "none", "null"])
def test_unavailable_precision_markers_never_establish_known_matching_weights(tmp_path, dtype):
    reference, candidate = pair(
        tmp_path, mutate=lambda payload: payload["quantized"].__setitem__("resolved_dtype", dtype)
    )
    result = compare(reference, candidate)
    row = result["rows"][0]
    assert result["exit_code"] == 0 and row["identity"]["state"] == "unavailable"
    assert row["identity"]["unavailable_fields"]["quantized"] == ["resolved_dtype"]
    assert row["axes"]["refusal_robustness"]["transition"] == "no_flag"
    assert row["identity"]["same_weights_established"] is False


def test_shared_hardlink_cache_reads_once_but_charges_each_logical_side(tmp_path, monkeypatch):
    from quantfit import screen_bundle_inputs as inputs

    reference, candidate = pair(tmp_path)
    for member in ("manifest.json", "targets.json", "reports/g0.json"):
        (candidate / member).unlink()
        os.link(reference / member, candidate / member)
    reads, charges = [], []
    read, charge = inputs._read, inputs._Budget.charge

    def once(path, limit):
        reads.append(path)
        return read(path, limit)

    def occurrence(budget, size):
        charges.append(size)
        return charge(budget, size)

    monkeypatch.setattr(inputs, "_read", once)
    monkeypatch.setattr(inputs._Budget, "charge", occurrence)
    result = compare(reference, candidate)
    assert len(reads) == 3 and len(charges) == 6
    assert sum(charges) == sum(side["transport_bytes"] for side in result["inputs"].values())
    assert result["rows"][0]["identical_report_bytes"] is True


def test_pure_comparison_after_original_files_deleted(tmp_path, monkeypatch):
    import shutil

    from quantfit import screen_bundle_inputs as inputs
    from quantfit.screen_compare import _compare_held

    reference, candidate = pair(tmp_path, (1, None), (0, None))
    held_ref, held_cand = inputs._capture_bundle(str(reference)), inputs._capture_bundle(str(candidate))
    shutil.rmtree(reference)
    shutil.rmtree(candidate)
    monkeypatch.setattr(inputs, "_read", lambda *args: pytest.fail("reopened held source"))
    monkeypatch.setattr(os, "scandir", lambda *args: pytest.fail("rescanned held source"))
    monkeypatch.setattr(Path, "read_bytes", lambda *args: pytest.fail("reopened held source"))
    result = _compare_held(held_ref, held_cand)
    assert (
        result["exit_code"] == 3
        and result["rows"][0]["axes"]["refusal_robustness"]["transition"] == "apparent_clearance"
    )


def test_scan_only_recheck_refuses_new_foreign_member_without_overwriting_outputs(tmp_path, monkeypatch):
    from quantfit import screen_compare as comparison

    reference, candidate = pair(tmp_path)
    output, junit = tmp_path / "comparison.json", tmp_path / "comparison.xml"
    output.write_bytes(b"old json")
    junit.write_bytes(b"old xml")
    held_compare = comparison._compare_held

    def late_foreign(*args):
        result = held_compare(*args)
        (candidate / "reports/PRIVATE.capture.jsonl").write_bytes(b"foreign bytes")
        return result

    monkeypatch.setattr(comparison, "_compare_held", late_foreign)
    with pytest.raises(comparison.ScreenComparisonError) as error:
        compare(reference, candidate, out_path=str(output), junit_path=str(junit))
    assert "PRIVATE" not in str(error.value)
    assert output.read_bytes() == b"old json" and junit.read_bytes() == b"old xml"


def test_second_output_failure_does_not_publish_success_xml(tmp_path, monkeypatch):
    from quantfit import reproduce
    from quantfit.screen_compare import ScreenComparisonError

    reference, candidate = pair(tmp_path)
    output, junit = tmp_path / "comparison.json", tmp_path / "comparison.xml"
    replace = reproduce.os.replace
    calls = []

    def fail_second(source, target):
        calls.append(target)
        if len(calls) == 2:
            raise OSError("PRIVATE publication diagnostics")
        return replace(source, target)

    monkeypatch.setattr(reproduce.os, "replace", fail_second)
    with pytest.raises(ScreenComparisonError, match="output_failure"):
        compare(reference, candidate, out_path=str(output), junit_path=str(junit))
    assert output.is_file() and not junit.exists()


def test_malformed_source_categorical_refusal_never_reflects_provider_text(tmp_path):
    from quantfit.screen_compare import ScreenComparisonError

    reference, candidate = pair(tmp_path)
    (candidate / "manifest.json").write_bytes(b'{"PRIVATE provider diagnostics"')
    with pytest.raises(ScreenComparisonError) as error:
        compare(reference, candidate, out_path=str(tmp_path / "out.json"))
    assert "PRIVATE" not in str(error.value) and not (tmp_path / "out.json").exists()


@pytest.mark.parametrize(
    "before,after,status,code",
    [("danger", None, "unmeasured_reference", 0), ("danger", "danger", "unmeasured_both", 4)],
)
def test_unmeasured_status_never_becomes_a_matched_transition(tmp_path, before, after, status, code):
    reference, candidate = pair(tmp_path, (0, before), (0, after))
    result = compare(reference, candidate)
    axis = result["rows"][0]["axes"]["refusal_robustness"]
    assert axis["status"] == status and axis["transition"] is None
    assert result["exit_code"] == (4 if code == 0 else code)


def test_multiple_strata_retain_manifest_order_each_denominator_and_each_missing_slot(tmp_path):
    from quantfit.screen_bundle import create_screen_bundle

    bundles = []
    for side in ("reference", "candidate"):
        root = tmp_path / side
        root.mkdir()
        entries = [
            ("z", "gguf", 1 if side == "reference" else 0, 0, None),
            ("a", "compressed-tensors", 0, 0, "danger" if side == "reference" else None),
            ("m", "gguf", 0, 0, None),
        ]
        manifest, reports = corpus(root, entries, missing=("m",) if side == "candidate" else ())
        bundle = root / "bundle"
        create_screen_bundle(str(manifest), str(reports), str(bundle))
        bundles.append(bundle)
    result = compare(*bundles)
    assert [row["name"] for row in result["rows"]] == ["z", "a", "m"]
    assert result["exit_code"] == 3
    assert result["rows"][1]["axes"]["refusal_robustness"]["reference"]["at_risk"] == 0
    assert result["rows"][2]["axes"]["over_refusal"]["status"] == "missing_candidate"
    assert set(result["screens"]["reference"]["by_stratum"]) == {"gguf", "compressed-tensors"}


def test_json_xml_publication_does_not_reread_captured_input_bytes(tmp_path, monkeypatch):
    from quantfit import screen_bundle_inputs as inputs

    reference, candidate = pair(tmp_path, (1, None), (0, None))
    read = inputs._read
    calls = []

    def once(path, limit):
        assert path not in calls
        calls.append(path)
        return read(path, limit)

    monkeypatch.setattr(inputs, "_read", once)
    output, junit = tmp_path / "comparison.json", tmp_path / "comparison.xml"
    result = compare(reference, candidate, out_path=str(output), junit_path=str(junit))
    assert len(calls) == 6 and json.loads(output.read_bytes()) == result and junit.read_text().startswith("<?xml")


def test_cancellation_during_publication_propagates_without_mutating_inputs(tmp_path, monkeypatch):
    from quantfit import screen_compare as comparison

    reference, candidate = pair(tmp_path)
    output = tmp_path / "comparison.json"

    def cancel(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(comparison, "_publish_reproduction_outputs", cancel)
    with pytest.raises(KeyboardInterrupt):
        compare(reference, candidate, out_path=str(output))
    assert not output.exists()
