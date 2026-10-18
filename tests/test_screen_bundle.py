"""Exact-byte screen handoff, finite receiving and conservative publication."""

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
from test_saved_screen import corpus


def api():
    from quantfit import screen_bundle

    return screen_bundle


@pytest.mark.parametrize(
    "danger,missing,unmeasured,code",
    [(0, False, None, 0), (1, False, None, 3), (0, True, None, 4), (0, False, "danger", 4)],
)
def test_original_bytes_relocate_and_content_success_is_separate(tmp_path, danger, missing, unmeasured, code):
    module = api()
    manifest, reports = corpus(tmp_path, [("g0", "gguf", danger, 0, unmeasured)], missing=("g0",) if missing else ())
    raw_manifest = json.dumps(json.loads(manifest.read_bytes()), indent=3).replace("\n", "\r\n").encode()
    manifest.write_bytes(raw_manifest)
    ignored = b'{\r\n  "rows": [], "untrusted_status":"pass"\r\n}\r\n'
    (reports / "screen-summary.json").write_bytes(ignored)
    original = {path.name: path.read_bytes() for path in reports.iterdir()}
    out = tmp_path / "bundle"
    created = module.create_screen_bundle(str(manifest), str(reports), str(out))
    assert created["exit_code"] == 0 and created["status"] == "verified_content"
    assert created["kind"] == "quantfit.screen-bundle-verification"
    assert created["receiving_summary"]["exit_code"] == code
    assert created["scientific_go"] is False and created["source_authentication"] == "unverified"
    assert (out / "targets.json").read_bytes() == raw_manifest
    assert all((out / "reports" / name).read_bytes() == raw for name, raw in original.items())
    outer = json.loads((out / "manifest.json").read_bytes())
    assert set(outer) == {"bundle_schema_version", "kind", "targets", "reports", "producer_summary"}
    row = outer["reports"][0]
    assert row == {
        "name": "g0",
        "path": "reports/g0.json",
        "status": "missing" if missing else "present",
        "sha256": None if missing else hashlib.sha256(original["g0.json"]).hexdigest(),
        "size_bytes": None if missing else len(original["g0.json"]),
    }
    assert outer["targets"] == {
        "path": "targets.json",
        "sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "size_bytes": len(raw_manifest),
    }
    assert created["transport_bytes"] == sum(path.stat().st_size for path in out.rglob("*") if path.is_file())
    moved = tmp_path / "moved"
    out.rename(moved)
    verified = module.verify_screen_bundle(str(moved))
    assert verified["manifest_sha256"] == created["manifest_sha256"]
    assert verified["bundle_manifest"] == outer
    assert verified["receiving_summary"]["ignored_members"][0]["sha256"] == hashlib.sha256(ignored).hexdigest()
    assert verified["receiving_summary"]["manifest"]["path"] == "targets.json"
    assert verified["receiving_summary"]["reports_dir"] == "reports"


@pytest.mark.parametrize(
    "mutation",
    [
        "outer_extra",
        "dupe_json",
        "native",
        "targets",
        "unsafe_path",
        "missing_binding",
        "unknown_root",
        "unknown_report",
        "report_directory",
    ],
)
def test_tamper_and_closed_inventory_refuse(tmp_path, mutation):
    module = api()
    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    out = tmp_path / "bundle"
    module.create_screen_bundle(str(manifest), str(reports), str(out))
    outer_path = out / "manifest.json"
    outer = json.loads(outer_path.read_bytes())
    if mutation == "outer_extra":
        outer["extra"] = "PRIVATE"
    elif mutation == "unsafe_path":
        outer["reports"][0]["path"] = "../PRIVATE"
    elif mutation == "missing_binding":
        outer["reports"][0].update(status="missing", sha256=None, size_bytes=None)
    elif mutation == "dupe_json":
        outer_path.write_bytes(b'{"kind":"quantfit.screen-bundle","kind":"PRIVATE"}')
    elif mutation == "native":
        (out / "reports/g0.json").write_bytes(b'{"PRIVATE":true}')
    elif mutation == "targets":
        (out / "targets.json").write_bytes(b'{"PRIVATE":true}')
    elif mutation == "unknown_root":
        (out / "PRIVATE").write_bytes(b"foreign")
    elif mutation == "unknown_report":
        (out / "reports/PRIVATE.capture.jsonl").write_bytes(b"foreign")
    else:
        (out / "reports/g0.json").unlink()
        (out / "reports/g0.json").mkdir()
    if mutation in ("outer_extra", "unsafe_path", "missing_binding"):
        outer_path.write_text(json.dumps(outer), encoding="utf-8")
    with pytest.raises(module.ScreenBundleError) as error:
        module.verify_screen_bundle(str(out))
    assert "PRIVATE" not in str(error.value)


def test_exclusive_existing_destination_and_source_subdirectory_are_untouched(tmp_path):
    module = api()
    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    out = tmp_path / "exists"
    out.mkdir()
    sentinel = out / "foreign"
    sentinel.write_bytes(b"owner bytes")
    for target in (out, reports / "nested", tmp_path / "absent" / "bundle"):
        with pytest.raises(module.ScreenBundleError):
            module.create_screen_bundle(str(manifest), str(reports), str(target))
    assert sentinel.read_bytes() == b"owner bytes" and not (reports / "nested").exists()


def test_held_verification_remains_pure_after_deletion(tmp_path, monkeypatch):
    module = api()
    from quantfit import screen_bundle_inputs as inputs

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    out = tmp_path / "bundle"
    module.create_screen_bundle(str(manifest), str(reports), str(out))
    held = inputs._capture_bundle(str(out))
    shutil.rmtree(out)
    monkeypatch.setattr(Path, "read_bytes", lambda *args: pytest.fail("held data reopened"))
    monkeypatch.setattr(inputs, "_read", lambda *args: pytest.fail("held data reopened"))
    monkeypatch.setattr(os, "scandir", lambda *args: pytest.fail("held data rescanned"))
    assert inputs._verify_held(held)["exit_code"] == 0


def test_transport_exact_boundary_includes_both_manifests_and_refuses_before_member_read(tmp_path, monkeypatch):
    module = api()
    from quantfit import screen_bundle_inputs as inputs

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    out = tmp_path / "first"
    original = module.create_screen_bundle(str(manifest), str(reports), str(out))
    size = original["transport_bytes"]
    monkeypatch.setattr(inputs, "MAX_TRANSPORT_BYTES", size)
    assert module.create_screen_bundle(str(manifest), str(reports), str(tmp_path / "exact"))["transport_bytes"] == size
    assert module.verify_screen_bundle(str(out))["transport_bytes"] == size
    monkeypatch.setattr(inputs, "MAX_TRANSPORT_BYTES", size - 1)
    calls = []
    read = inputs._read

    def bounded(path, limit):
        calls.append(path.name)
        return read(path, limit)

    monkeypatch.setattr(inputs, "_read", bounded)
    with pytest.raises(module.ScreenBundleError, match="transport_byte_limit"):
        module.verify_screen_bundle(str(out))
    assert calls == ["manifest.json"]
    with pytest.raises(module.ScreenBundleError):
        module.create_screen_bundle(str(manifest), str(reports), str(tmp_path / "one-over"))
    assert not (tmp_path / "one-over").exists()


def test_hardlink_occurrences_charge_before_cached_read_and_never_reread(tmp_path, monkeypatch):
    from quantfit import screen_bundle_inputs as inputs

    first, second = tmp_path / "first", tmp_path / "second"
    first.write_bytes(b"same original bytes")
    os.link(first, second)
    raw = first.read_bytes()
    monkeypatch.setattr(inputs, "MAX_TRANSPORT_BYTES", 2 * len(raw))
    calls = []
    read = inputs._read

    def once(path, limit):
        calls.append(path)
        return read(path, limit)

    monkeypatch.setattr(inputs, "_read", once)
    budget, cache = inputs._Budget(), {}
    assert inputs._hold(first, 1024, budget, cache) == raw
    assert inputs._hold(second, 1024, budget, cache) == raw
    assert budget.charged == 2 * len(raw) and calls == [first]
    with pytest.raises(inputs.ScreenBundleError, match="transport_byte_limit"):
        inputs._hold(second, 1024, budget, cache)
    assert calls == [first]


@pytest.mark.parametrize(
    "entries", [["foreign", "must-not-enumerate"], ["targets.json", "targets.json", "must-not-enumerate"]]
)
def test_inventory_stops_on_unknown_or_duplicate_and_closes(tmp_path, monkeypatch, entries):
    from quantfit import screen_bundle_inputs as inputs

    (tmp_path / "targets.json").write_bytes(b"held")
    visited = []

    class Entry:
        def __init__(self, name):
            self.name = name

    class Scan:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            visited.append("closed")

        def __iter__(self):
            for name in entries:
                if name == "must-not-enumerate":
                    pytest.fail("unbounded inventory continuation")
                visited.append(name)
                yield Entry(name)

    monkeypatch.setattr(os, "scandir", lambda *args: Scan())
    monkeypatch.setattr(Path, "iterdir", lambda *args: pytest.fail("materialized inventory"))
    with pytest.raises(inputs.ScreenBundleError, match="invalid_inventory"):
        inputs._scan(tmp_path, {"targets.json": False})
    assert visited == entries[:-1] + ["closed"]


@pytest.mark.parametrize("mutation", ["private", "arithmetic", "protocol", "target"])
def test_resealed_native_content_is_still_strictly_received_before_creation(tmp_path, mutation):
    module = api()
    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    path = reports / "g0.json"
    payload = json.loads(path.read_bytes())
    if mutation == "private":
        payload["completions"] = ["PRIVATE provider data"]
    elif mutation == "arithmetic":
        payload["drift"]["regression_detected"] = True
    elif mutation == "protocol":
        payload["judge"]["revision"] = "a" * 40
    else:
        payload["baseline"]["model"] = "PRIVATE foreign model"
    raw = json.dumps(payload).encode()
    path.write_bytes(raw)
    with pytest.raises(module.ScreenBundleError) as error:
        module.create_screen_bundle(str(manifest), str(reports), str(tmp_path / "bundle"))
    assert "PRIVATE" not in str(error.value)
    assert path.read_bytes() == raw and not (tmp_path / "bundle").exists()


def test_publication_concurrent_destination_is_not_replaced(tmp_path, monkeypatch):
    module = api()
    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    out = tmp_path / "bundle"
    publish = module._publish

    def appeared(root, files):
        root.mkdir()
        (root / "foreign").write_bytes(b"foreign owner")
        return publish(root, files)

    monkeypatch.setattr(module, "_publish", appeared)
    with pytest.raises(module.ScreenBundleError):
        module.create_screen_bundle(str(manifest), str(reports), str(out))
    assert (out / "foreign").read_bytes() == b"foreign owner" and list(out.iterdir()) == [out / "foreign"]


@pytest.mark.parametrize("foreign", [False, True])
def test_partial_publication_cleans_only_unchanged_owned_members(tmp_path, monkeypatch, foreign):
    module = api()
    from quantfit import screen_bundle_publication as publication

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    out = tmp_path / "bundle"
    write = publication._write_member
    calls = []

    def failed(path, raw, owned):
        calls.append(path)
        if len(calls) == 2:
            if foreign:
                (out / "reports" / "foreign").write_bytes(b"another owner")
            raise OSError("PRIVATE disk diagnostics")
        return write(path, raw, owned)

    monkeypatch.setattr(publication, "_write_member", failed)
    with pytest.raises(module.ScreenBundleError) as error:
        module.create_screen_bundle(str(manifest), str(reports), str(out))
    assert "PRIVATE" not in str(error.value)
    assert not (out / "manifest.json").exists()
    if foreign:
        assert out.is_dir() and (out / "reports/foreign").read_bytes() == b"another owner"
        assert (out / "targets.json").read_bytes() == manifest.read_bytes()
    else:
        assert not out.exists()


def test_completed_manifest_is_revoked_before_foreign_cleanup_preservation(tmp_path, monkeypatch):
    module = api()
    from quantfit import screen_bundle_publication as publication

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    out = tmp_path / "bundle"
    write = publication._write_member

    def foreign_after_manifest(path, raw, owned):
        result = write(path, raw, owned)
        if path.name == "manifest.json":
            (out / "reports/foreign").write_bytes(b"foreign bytes")
            raise OSError("PRIVATE publication fault")
        return result

    monkeypatch.setattr(publication, "_write_member", foreign_after_manifest)
    with pytest.raises(module.ScreenBundleError):
        module.create_screen_bundle(str(manifest), str(reports), str(out))
    assert not (out / "manifest.json").exists()
    assert (out / "reports/foreign").read_bytes() == b"foreign bytes"


@pytest.mark.skipif(os.name == "nt", reason="Windows uses inherited ACLs, not POSIX access-mode guarantees")
def test_posix_owner_modes(tmp_path):
    module = api()
    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    out = tmp_path / "bundle"
    module.create_screen_bundle(str(manifest), str(reports), str(out))
    assert out.stat().st_mode & 0o777 == 0o700
    assert (out / "reports").stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in out.rglob("*") if path.is_file())


def test_reserved_outer_names_are_valid_report_names_and_all_missing_stays_declared(tmp_path):
    module = api()
    manifest, reports = corpus(
        tmp_path, [("targets", "gguf", 0, 0, None), ("manifest", "gguf", 0, 0, None)], missing=("targets", "manifest")
    )
    out = tmp_path / "bundle"
    result = module.create_screen_bundle(str(manifest), str(reports), str(out))
    assert (out / "reports").is_dir() and list((out / "reports").iterdir()) == []
    assert [row["name"] for row in result["bundle_manifest"]["reports"]] == ["targets", "manifest"]
    assert all(row["status"] == "missing" for row in result["bundle_manifest"]["reports"])
    assert result["receiving_summary"]["coverage"]["n_missing"] == 2
    assert module.verify_screen_bundle(str(out))["receiving_summary"]["exit_code"] == 4


@pytest.mark.parametrize("substitution", ["changed_bytes", "new_identity", "root"])
def test_uncertain_publication_ownership_is_preserved(tmp_path, monkeypatch, substitution):
    module = api()
    from quantfit import screen_bundle_publication as publication

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    out = tmp_path / "bundle"
    relocated = tmp_path / "relocated-owned-root"
    write = publication._write_member

    def substituted(path, raw, owned):
        result = write(path, raw, owned)
        if path.name == "targets.json":
            if substitution == "changed_bytes":
                path.write_bytes(b"foreign changed bytes")
            elif substitution == "new_identity":
                replacement = tmp_path / "foreign-file"
                replacement.write_bytes(raw)
                os.replace(replacement, path)
            else:
                out.rename(relocated)
                out.mkdir()
                (out / "foreign").write_bytes(b"foreign root bytes")
            raise OSError("PRIVATE ownership fault")
        return result

    monkeypatch.setattr(publication, "_write_member", substituted)
    with pytest.raises(module.ScreenBundleError, match="publication_failed_preserved"):
        module.create_screen_bundle(str(manifest), str(reports), str(out))
    if substitution == "root":
        assert (out / "foreign").read_bytes() == b"foreign root bytes"
        assert (relocated / "targets.json").read_bytes() == manifest.read_bytes()
    else:
        assert (out / "targets.json").read_bytes() == (
            b"foreign changed bytes" if substitution == "changed_bytes" else manifest.read_bytes()
        )
    assert not (out / "manifest.json").exists()


def test_cancellation_cleans_proven_owned_complete_members(tmp_path, monkeypatch):
    module = api()
    from quantfit import screen_bundle_publication as publication

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    out = tmp_path / "bundle"
    write = publication._write_member

    def cancelled(path, raw, owned):
        write(path, raw, owned)
        assert not (out / "manifest.json").exists()
        raise KeyboardInterrupt()

    monkeypatch.setattr(publication, "_write_member", cancelled)
    with pytest.raises(KeyboardInterrupt):
        module.create_screen_bundle(str(manifest), str(reports), str(out))
    assert not out.exists()


def test_capture_inputs_once_and_publication_reads_only_destination(tmp_path, monkeypatch):
    module = api()
    from quantfit import screen_bundle_inputs as inputs

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    original = {manifest: manifest.read_bytes(), reports / "g0.json": (reports / "g0.json").read_bytes()}
    read = inputs._read
    calls = []

    def once(path, limit):
        assert path not in calls
        calls.append(path)
        return read(path, limit)

    monkeypatch.setattr(inputs, "_read", once)
    module.create_screen_bundle(str(manifest), str(reports), str(tmp_path / "bundle"))
    assert set(calls) == set(original)
    assert all(path.read_bytes() == raw for path, raw in original.items())


def test_declared_order_and_forged_held_members_are_not_trusted(tmp_path):
    module = api()
    from dataclasses import replace

    from quantfit import screen_bundle_inputs as inputs

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None), ("g1", "gguf", 0, 0, None)])
    out = tmp_path / "bundle"
    module.create_screen_bundle(str(manifest), str(reports), str(out))
    held = inputs._capture_bundle(str(out))
    with pytest.raises(inputs.ScreenBundleError):
        inputs._verify_held(replace(held, members=(*held.members, held.members[0])))
    outer = json.loads(held.outer)
    outer["reports"].reverse()
    with pytest.raises(inputs.ScreenBundleError, match="target_inventory_mismatch"):
        inputs._verify_held(replace(held, outer=json.dumps(outer).encode()))
