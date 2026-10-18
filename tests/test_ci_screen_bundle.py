"""Actual screen-bundle CLI receiving cases, including the installed-origin guarded lane."""

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("screen_bundle_consumer", ROOT / "tools/ci_screen_bundle.py")
assert SPEC is not None and SPEC.loader is not None
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


@pytest.fixture(autouse=True)
def no_execution_or_resolution(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline screen bundle attempted inference, resolution or download")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)


@pytest.fixture
def originals():
    return consumer.committed_inputs(ROOT)


def snapshot(root):
    return {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_originals_are_literal_native_aggregate_inputs_with_independent_counts(tmp_path, originals):
    from quantfit.saved_screen import summarize_screen

    manifest_raw, reports = originals
    manifest, directory = consumer.stage(tmp_path / "producer", manifest_raw, reports)
    assert manifest.read_bytes() == manifest_raw and [len(raw) for raw in reports.values()] == [3321, 3303, 3343]
    receiving = summarize_screen(str(manifest), str(directory))
    expected = consumer.expected_counts(manifest_raw, reports)
    assert receiving["exit_code"] == expected["exit_code"] == 3
    assert expected["axes"]["gguf"] == {
        "refusal_robustness": {"n_measured": 2, "n_regressed": 1, "n_regressed_human_verified": 0},
        "over_refusal": {"n_measured": 2, "n_regressed": 0, "n_regressed_human_verified": 0},
    }


def test_actual_cli_exact_pretty_bytes_relocate_and_ignore_producer_claims(tmp_path, originals):
    manifest_raw, reports = originals
    summary = b'{\n  "scientific_go": true,\n  "PRIVATE_SENTINEL_DO_NOT_REFLECT": "untrusted claim"\n}\n'
    source = tmp_path / "producer"
    manifest, directory = consumer.stage(source, manifest_raw, reports, summary=summary)
    before = snapshot(source)
    bundle = tmp_path / "bundle"
    created = consumer.create(manifest, directory, bundle)
    first = consumer.check(created, bundle, manifest_raw, reports, summary=summary)
    assert all(path.read_bytes() == raw for path, raw in before.items())
    moved = tmp_path / "relocated"
    bundle.rename(moved)
    source.rename(tmp_path / "producer-unavailable")
    assert not source.exists() and not bundle.exists()
    verified = consumer.verify(moved)
    assert consumer.check(verified, moved, manifest_raw, reports, summary=summary) == first
    assert "PRIVATE_SENTINEL_DO_NOT_REFLECT" not in json.dumps(created) + json.dumps(verified)
    assert str(source) not in json.dumps(created) + json.dumps(verified)
    assert first["content_exit_code"] == 0 and first["receiving_exit_code"] == 3


@pytest.mark.parametrize(
    "missing,expected_code", [(("clean",), 3), (("flagged",), 4), (("clean", "flagged", "unmeasured"), 4)]
)
def test_valid_incomplete_bundle_stays_content_zero_with_explicit_missing_population(
    tmp_path, originals, missing, expected_code
):
    manifest_raw, all_reports = originals
    reports = {name: raw for name, raw in all_reports.items() if name not in missing}
    manifest, directory = consumer.stage(tmp_path / "producer", manifest_raw, reports)
    bundle = tmp_path / "bundle"
    created = consumer.create(manifest, directory, bundle)
    result = consumer.check(created, bundle, manifest_raw, reports)
    assert result["receiving_exit_code"] == expected_code and result["coverage"]["n_missing"] == len(missing)
    assert consumer.check(consumer.verify(bundle), bundle, manifest_raw, reports) == result


def test_corrupt_present_source_refuses_without_rewriting_or_publishing(tmp_path, originals):
    manifest_raw, reports = originals
    manifest, directory = consumer.stage(tmp_path / "producer", manifest_raw, reports)
    (directory / "unmeasured.json").write_bytes(b'{"PRIVATE_SENTINEL_DO_NOT_REFLECT":')
    before = snapshot(manifest.parent)
    out = tmp_path / "bundle"
    document = consumer.create(manifest, directory, out)
    assert document["exit_code"] == 2 and document["result"] is None and not out.exists()
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert "PRIVATE_SENTINEL_DO_NOT_REFLECT" not in json.dumps(document)


@pytest.mark.parametrize(
    "mutation", ["native", "targets", "unknown-key", "extra-member", "extra-report", "missing-record"]
)
def test_actual_cli_tamper_and_closed_inventory_refusals(tmp_path, originals, mutation):
    manifest_raw, reports = originals
    manifest, directory = consumer.stage(tmp_path / "producer", manifest_raw, reports)
    bundle = tmp_path / "bundle"
    assert consumer.create(manifest, directory, bundle)["exit_code"] == 0
    outer_path = bundle / "manifest.json"
    outer = json.loads(outer_path.read_bytes())
    if mutation == "native":
        with (bundle / "reports/clean.json").open("ab") as stream:
            stream.write(b" ")
    elif mutation == "targets":
        with (bundle / "targets.json").open("ab") as stream:
            stream.write(b" ")
    elif mutation == "unknown-key":
        outer["PRIVATE_SENTINEL_DO_NOT_REFLECT"] = True
        outer_path.write_bytes(json.dumps(outer).encode())
    elif mutation == "extra-member":
        (bundle / "undeclared.json").write_bytes(b"{}")
    elif mutation == "extra-report":
        (bundle / "reports/undeclared.json").write_bytes(b"{}")
    elif mutation == "missing-record":
        outer["reports"].pop()
        outer_path.write_bytes(json.dumps(outer).encode())
    before = snapshot(bundle)
    document = consumer.verify(bundle)
    assert document["exit_code"] == 2 and document["result"] is None
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert "PRIVATE_SENTINEL_DO_NOT_REFLECT" not in json.dumps(document)


@pytest.mark.parametrize("operation", ["create", "verify"])
def test_valid_json_report_over_byte_budget_refuses(tmp_path, originals, operation):
    manifest_raw, reports = originals
    manifest, directory = consumer.stage(tmp_path / "producer", manifest_raw, reports)
    bundle = tmp_path / "bundle"
    if operation == "verify":
        assert consumer.create(manifest, directory, bundle)["exit_code"] == 0
        member = bundle / "reports/clean.json"
    else:
        member = directory / "clean.json"
    original = member.read_bytes()
    raw = original + b" " * (8 * 1024 * 1024 + 1 - len(original))
    member.write_bytes(raw)
    if operation == "verify":
        outer_path = bundle / "manifest.json"
        outer = json.loads(outer_path.read_bytes())
        outer["reports"][0].update(consumer.binding(raw))
        outer_path.write_bytes(json.dumps(outer).encode())
        document = consumer.verify(bundle)
    else:
        document = consumer.create(manifest, directory, bundle)
        assert not bundle.exists()
    assert document["exit_code"] == 2 and member.read_bytes() == raw


def test_valid_outer_json_over_outer_byte_cap_refuses(tmp_path, originals):
    manifest_raw, reports = originals
    manifest, directory = consumer.stage(tmp_path / "producer", manifest_raw, reports)
    bundle = tmp_path / "bundle"
    assert consumer.create(manifest, directory, bundle)["exit_code"] == 0
    outer = bundle / "manifest.json"
    raw = outer.read_bytes()
    oversized = raw + b" " * (256 * 1024 + 1 - len(raw))
    outer.write_bytes(oversized)
    assert consumer.verify(bundle)["exit_code"] == 2 and outer.read_bytes() == oversized


@pytest.mark.parametrize("alias", ["inside-source", "existing-source", "existing-targets", "existing-destination"])
def test_create_destination_admission_preserves_all_original_bytes(tmp_path, originals, alias):
    manifest_raw, reports = originals
    manifest, directory = consumer.stage(tmp_path / "producer", manifest_raw, reports)
    out = {
        "inside-source": directory / "new-bundle",
        "existing-source": directory,
        "existing-targets": manifest,
        "existing-destination": tmp_path / "already-there",
    }[alias]
    if alias == "existing-destination":
        out.mkdir()
        (out / "existing.json").write_bytes(b'{"preserve":true}')
    before = snapshot(tmp_path)
    document = consumer.create(manifest, directory, out)
    assert document["exit_code"] == 2 and all(path.read_bytes() == raw for path, raw in before.items())
    if alias == "inside-source":
        assert not out.exists()


@pytest.mark.parametrize("operation", ["create", "verify"])
def test_readonly_input_hardlink_preserves_exact_receiving_and_outside_bytes(tmp_path, originals, operation):
    manifest_raw, reports = originals
    manifest, directory = consumer.stage(tmp_path / "producer", manifest_raw, reports)
    bundle = tmp_path / "bundle"
    if operation == "verify":
        assert consumer.create(manifest, directory, bundle)["exit_code"] == 0
        original = bundle / "reports/clean.json"
    else:
        original = directory / "clean.json"
    outside = tmp_path / "outside-hardlink.json"
    os.link(original, outside)
    raw = original.read_bytes()
    document = consumer.verify(bundle) if operation == "verify" else consumer.create(manifest, directory, bundle)
    assert document["exit_code"] == 0 and outside.read_bytes() == original.read_bytes() == raw
    assert consumer.check(document, bundle, manifest_raw, reports)["receiving_exit_code"] == 3


def test_duplicate_native_evidence_refuses_even_when_each_declared_ref_matches(tmp_path, originals):
    manifest_raw, reports = originals
    declaration = json.loads(manifest_raw)
    declaration["targets"][1] = {**declaration["targets"][0], "name": "flagged"}
    altered = dict(reports)
    altered["flagged"] = reports["clean"]
    manifest, directory = consumer.stage(tmp_path / "producer", json.dumps(declaration).encode(), altered)
    before = snapshot(manifest.parent)
    out = tmp_path / "bundle"
    assert consumer.create(manifest, directory, out)["exit_code"] == 2
    assert not out.exists() and all(path.read_bytes() == raw for path, raw in before.items())


def test_foreign_hardlinked_output_member_refuses_exclusive_write_and_preserves_input(tmp_path, originals, monkeypatch):
    import quantfit.screen_bundle_publication as publication

    manifest_raw, reports = originals
    manifest, directory = consumer.stage(tmp_path / "producer", manifest_raw, reports)
    original = directory / "clean.json"
    bundle = tmp_path / "bundle"
    destination = bundle / "reports/clean.json"
    write_member = publication._write_member

    def insert_foreign_member(path, raw, owned):
        if path == destination:
            os.link(original, destination)
        return write_member(path, raw, owned)

    monkeypatch.setattr(publication, "_write_member", insert_foreign_member)
    document = consumer.create(manifest, directory, bundle)
    assert document["exit_code"] == 2
    assert original.read_bytes() == destination.read_bytes() == reports["clean"]
    assert original.stat().st_ino == destination.stat().st_ino
    assert not (bundle / "manifest.json").exists()


def test_symbolic_report_link_refuses(tmp_path, originals):
    manifest_raw, reports = originals
    manifest, directory = consumer.stage(tmp_path / "producer", manifest_raw, reports)
    outside = tmp_path / "outside.json"
    original = directory / "clean.json"
    original.rename(outside)
    try:
        original.symlink_to(outside)
    except OSError:
        pytest.skip("host does not permit symbolic link creation")
    assert consumer.create(manifest, directory, tmp_path / "bundle")["exit_code"] == 2
    assert outside.read_bytes() == reports["clean"]


def test_injected_destination_publication_race_never_overwrites_existing_data(tmp_path, originals, monkeypatch):
    import quantfit.screen_bundle as core

    manifest_raw, reports = originals
    manifest, directory = consumer.stage(tmp_path / "producer", manifest_raw, reports)
    bundle = tmp_path / "bundle"
    publish = core._publish

    def intervene(root, files):
        root.mkdir()
        (root / "unrelated.json").write_bytes(b'{"unrelated":true}')
        return publish(root, files)

    monkeypatch.setattr(core, "_publish", intervene)
    document = consumer.create(manifest, directory, bundle)
    assert document["exit_code"] == 2
    assert snapshot(bundle) == {bundle / "unrelated.json": b'{"unrelated":true}'}


@pytest.mark.parametrize("name,expected", [("clean", 0), ("flagged", 3), ("unmeasured", 4)])
def test_cpu_adapter_reuses_existing_native_for_all_measured_outcome_classes(tmp_path, originals, name, expected):
    _, reports = originals
    source = tmp_path / "original-native.json"
    source.write_bytes(reports[name])
    result = consumer.accept_cpu(source, tmp_path / "cpu-bundle")
    assert result["additional_native_calls"] == 0 and result["receiving_exit_code"] == expected
    assert result["content_exit_code"] == 0 and result["coverage"] == {
        "n_targets": 1,
        "n_present": 1,
        "n_missing": 0,
        "complete": True,
    }
    assert source.read_bytes() == reports[name]


def test_installed_and_existing_cpu_seams_are_single_offline_calls():
    installed = (ROOT / "tools/ci_installed.py").read_text(encoding="utf-8")
    assert installed.count('"test_ci_screen_bundle.py"') == 1
    cpu = (ROOT / "tools/ci_cpu_acceptance.py").read_text(encoding="utf-8")
    assert cpu.count("screen_bundle_accept_cpu(") == 1
    assert '"screen_bundle": screen_bundle' in cpu


def test_committed_originals_bundle_members_and_receiving_bindings_are_literal():
    artifact = ROOT / "validation/2026-10-18-screen-bundle"
    manifest = (artifact / "inputs/targets.json").read_bytes()
    assert manifest == (ROOT / "validation/2026-10-18-screen-resume/inputs/manifest.json").read_bytes()
    assert consumer.binding(manifest) == {
        "sha256": "60a61566f4d18c6f87619bdcf7cea4ba36e26ca64be824da4cd4e05f7e58937c",
        "size_bytes": 803,
    }
    targets = json.loads(manifest)["targets"]
    originals = {
        target["name"]: (artifact / "inputs/reports" / f"{target['name']}.json").read_bytes() for target in targets
    }
    for name, raw in originals.items():
        assert raw == (ROOT / "validation/2026-10-18-screen-resume/inputs/reports" / f"{name}.json").read_bytes()
    producer = (artifact / "inputs/reports/screen-summary.json").read_bytes()
    receipt = json.loads((artifact / "receipt.json").read_bytes())
    assert receipt["inputs"]["targets"] == consumer.binding(manifest)
    assert receipt["inputs"]["producer_summary"] == consumer.binding(producer)
    for row in receipt["inputs"]["reports"]:
        assert {key: row[key] for key in ("sha256", "size_bytes")} == consumer.binding(originals[row["name"]])
    for directory, documents, compact_keys, missing, code in (
        ("bundle", ("create.json", "verify.json"), ("create", "relocated_verify"), (), 3),
        (
            "missing-bundle",
            ("missing-create.json", "missing-verify.json"),
            ("missing_create", "missing_verify"),
            ("flagged",),
            4,
        ),
    ):
        bundle = artifact / directory
        outer_raw = (bundle / "manifest.json").read_bytes()
        outer = json.loads(outer_raw)
        assert (bundle / "targets.json").read_bytes() == manifest
        assert outer["targets"] == {"path": "targets.json", **consumer.binding(manifest)}
        expected_paths = {"manifest.json", "targets.json"}
        assert [row["name"] for row in outer["reports"]] == [target["name"] for target in targets]
        for row in outer["reports"]:
            name = row["name"]
            assert row["path"] == f"reports/{name}.json"
            if name in missing:
                assert row["status"] == "missing" and row["sha256"] is row["size_bytes"] is None
                assert not (bundle / row["path"]).exists()
            else:
                assert row["status"] == "present" and (bundle / row["path"]).read_bytes() == originals[name]
                assert {key: row[key] for key in ("sha256", "size_bytes")} == consumer.binding(originals[name])
                expected_paths.add(row["path"])
        if not missing:
            expected_paths.add("reports/screen-summary.json")
            assert (bundle / "reports/screen-summary.json").read_bytes() == producer
            assert outer["producer_summary"] == {
                "path": "reports/screen-summary.json",
                "status": "present",
                **consumer.binding(producer),
            }
        else:
            assert outer["producer_summary"] == {
                "path": "reports/screen-summary.json",
                "status": "absent",
                "sha256": None,
                "size_bytes": None,
            }
        actual_paths = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file()}
        assert actual_paths == expected_paths
        total = sum((bundle / path).stat().st_size for path in actual_paths)
        for filename, compact_key in zip(documents, compact_keys, strict=True):
            document = json.loads((artifact / filename).read_bytes())
            result = document["result"]
            assert document["exit_code"] == 0 and result["bundle_manifest"] == outer
            assert result["manifest_sha256"] == consumer.binding(outer_raw)["sha256"]
            assert result["transport_bytes"] == receipt[compact_key]["transport_bytes"] == total
            receiving = result["receiving_summary"]
            assert receiving["exit_code"] == receipt[compact_key]["receiving_exit_code"] == code
            assert {key: receiving["manifest"][key] for key in ("sha256", "size_bytes")} == consumer.binding(manifest)
            assert len(receiving["report_bindings"]) == len(targets)
            for row in receiving["report_bindings"]:
                expected = (
                    {"sha256": None, "size_bytes": None}
                    if row["name"] in missing
                    else consumer.binding(originals[row["name"]])
                )
                assert {key: row[key] for key in ("sha256", "size_bytes")} == expected
                assert row["status"] == ("missing_evidence" if row["name"] in missing else "validated")
    assert json.loads((artifact / "tampered-verify.json").read_bytes())["exit_code"] == 2
    assert json.loads((artifact / "corrupt-create.json").read_bytes())["exit_code"] == 2
