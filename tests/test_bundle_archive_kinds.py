"""Explicit closed archive kinds retain original native evidence and ownership."""

import hashlib
import io
import json
import os
import stat
import struct
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_replay_bundle import inputs as replay_inputs
from test_saved_screen import corpus

from quantfit import bundle_transport as transport
from quantfit.bundle import BundleError


class Clock:
    @staticmethod
    def now(*args):
        return datetime(2026, 11, 15, 4, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def receiving_only(monkeypatch):
    monkeypatch.setattr("quantfit.saved_screen.datetime", Clock)

    def forbidden(*args, **kwargs):
        pytest.fail("archive receiving attempted model, judge or network work")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)


def replay(root, *, adverse=False):
    from quantfit.replay_bundle import create_replay_bundle

    root.mkdir()
    reports, t0 = replay_inputs(root, disagreement=adverse)
    source = root / "bundle"
    create_replay_bundle(reports, str(t0), str(source))
    return source


def screen(root, *, code=3, summary=True):
    from quantfit.screen_bundle import create_screen_bundle

    root.mkdir()

    manifest, reports = corpus(root, [("g0", "gguf", int(code == 3), 0, None)], missing=("g0",) if code == 4 else ())
    if summary:
        (reports / "screen-summary.json").write_bytes(b'{"untrusted_status":"pass"}\n')
    source = root / "bundle"
    create_screen_bundle(str(manifest), str(reports), str(source))
    return source


@pytest.mark.parametrize("kind", ["replay", "screen"])
def test_actual_native_sdk_roundtrip_retains_adverse_originals(tmp_path, kind):
    from quantfit.replay_bundle import verify_replay_bundle
    from quantfit.screen_bundle import verify_screen_bundle

    source = replay(tmp_path / "replay", adverse=True) if kind == "replay" else screen(tmp_path / "screen")
    originals = {
        str(p.relative_to(source)).replace(os.sep, "/"): p.read_bytes() for p in source.rglob("*") if p.is_file()
    }
    archive, destination = tmp_path / "archive.zip", tmp_path / "receiving"
    packed = transport.pack_bundle(str(source), str(archive), kind=kind)
    pin = hashlib.sha256(archive.read_bytes()).hexdigest()
    verified = transport.verify_bundle_archive(str(archive), pin, kind=kind)
    restored = transport.unpack_bundle(str(archive), pin, str(destination), kind=kind)
    assert packed == verified == restored
    assert packed["bundle_transport_schema"] == 2 and packed["kind"] == kind
    assert packed["integrity_verified"] and packed["scientific_claims_verified"] is False
    assert {
        str(p.relative_to(destination)).replace(os.sep, "/"): p.read_bytes()
        for p in destination.rglob("*")
        if p.is_file()
    } == originals
    if kind == "replay":
        native = verify_replay_bundle(str(destination))
        assert not native["original_t0"]["protocol_pass"] and not native["receiving_t0"]["protocol_pass"]
        assert native["original_t0"] == packed["native_verification"]["original_t0"]
        assert native["receiving_t0"]["reports"] != packed["native_verification"]["receiving_t0"]["reports"]
    else:
        native = verify_screen_bundle(str(destination))
        assert native["receiving_summary"]["exit_code"] == 3
        assert native == packed["native_verification"]


def test_actual_os_cli_accepts_explicit_replay_kind(tmp_path):
    source = replay(tmp_path / "replay", adverse=True)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "quantfit.cli",
            "bundle",
            "pack",
            "--kind",
            "replay",
            "--bundle",
            str(source),
            "--out",
            str(tmp_path / "cli.zip"),
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["result"]["native_verification"]["original_t0"]["protocol_pass"] is False


def test_unknown_kind_refuses_before_path_work(monkeypatch):
    monkeypatch.setattr(transport, "canonical", lambda *a, **k: pytest.fail("invalid kind reached paths"))
    with pytest.raises(BundleError):
        transport.pack_bundle("PRIVATE", "PRIVATE", kind="automatic")


@pytest.mark.parametrize("kind", ["replay", "screen"])
def test_actual_os_cli_full_receiving_roundtrip(tmp_path, kind):
    source = (
        replay(tmp_path / "source", adverse=True)
        if kind == "replay"
        else screen(tmp_path / "source", code=4, summary=False)
    )
    archive, restored, receipt = (tmp_path / name for name in ("cli.zip", "restored", "verification.json"))

    def invoke(action, options):
        process = subprocess.run(
            [sys.executable, "-B", "-m", "quantfit.cli", "bundle", action, "--kind", kind, *options, "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
            cwd=tmp_path,
        )
        assert process.returncode == 0, process.stdout + process.stderr
        return json.loads(process.stdout)["result"]

    packed = invoke("pack", ["--bundle", str(source), "--out", str(archive)])
    pin = hashlib.sha256(archive.read_bytes()).hexdigest()
    for action, extra in (("archive-verify", ["--out", str(receipt)]), ("unpack", ["--out", str(restored)])):
        result = invoke(action, ["--archive", str(archive), "--sha256", pin, *extra])
        assert result["archive"] == packed["archive"] and result["kind"] == kind
        assert result["scientific_claims_verified"] is False
        if action == "archive-verify":
            assert json.loads(receipt.read_bytes()) == result
    native_action = "replay-verify" if kind == "replay" else "screen-verify"
    process = subprocess.run(
        [sys.executable, "-B", "-m", "quantfit.cli", "bundle", native_action, "--bundle", str(restored), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
        cwd=tmp_path,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    native = json.loads(process.stdout)["result"]
    if kind == "replay":
        assert native["original_t0"]["protocol_pass"] is False
    else:
        assert native["receiving_summary"]["exit_code"] == 4 and (restored / "reports").is_dir()
        assert not list((restored / "reports").iterdir())


@pytest.mark.parametrize("code", [0, 3, 4])
@pytest.mark.parametrize("summary", [False, True])
def test_screen_native_population_unknowns_and_original_optional_summary(tmp_path, code, summary):
    source = screen(tmp_path / "source", code=code, summary=summary)
    archive = tmp_path / "screen.zip"
    result = transport.pack_bundle(str(source), str(archive), kind="screen")
    native = result["native_verification"]
    assert native["receiving_summary"]["exit_code"] == code
    assert native["receiving_summary"]["coverage"]["n_missing"] == int(code == 4)
    assert len(native["receiving_summary"]["ignored_members"]) == int(summary)
    restored = tmp_path / "received"
    transport.unpack_bundle(str(archive), result["archive"]["sha256"], str(restored), kind="screen")
    assert (restored / "reports").is_dir()
    if summary:
        assert (restored / "reports/screen-summary.json").read_bytes() == b'{"untrusted_status":"pass"}\n'


def test_explicit_aggregate_is_exact_default_bytes_and_result(tmp_path):
    from test_bundle_transport import prepared

    source, _ = prepared(tmp_path)
    a, b = tmp_path / "a.zip", tmp_path / "b.zip"
    default = transport.pack_bundle(str(source), str(a))
    selected = transport.pack_bundle(str(source), str(b), kind="aggregate")
    assert a.read_bytes() == b.read_bytes() and default == selected
    pin = default["archive"]["sha256"]
    assert transport.verify_bundle_archive(str(a), pin) == transport.verify_bundle_archive(
        str(a), pin, kind="aggregate"
    )
    assert transport.unpack_bundle(str(a), pin, str(tmp_path / "r0")) == transport.unpack_bundle(
        str(a), pin, str(tmp_path / "r1"), kind="aggregate"
    )


def test_archive_verification_receipt_preserves_existing_files_and_requires_pin(tmp_path):
    from test_bundle_transport import prepared

    source, _ = prepared(tmp_path)
    archive, receipt = tmp_path / "input.zip", tmp_path / "verification.json"
    pin = transport.pack_bundle(str(source), str(archive))["archive"]["sha256"]
    prior = archive.read_bytes()

    with pytest.raises(BundleError, match="^invalid_bundle_transport$"):
        transport.verify_bundle_archive(str(archive), "0" * 64, out_path=str(receipt))
    assert not receipt.exists()
    with pytest.raises(BundleError, match="^invalid_bundle_transport$"):
        transport.verify_bundle_archive(str(archive), pin, out_path=str(archive))
    assert archive.read_bytes() == prior

    native = transport.verify_bundle_archive(str(archive), pin, out_path=str(receipt))
    saved = receipt.read_bytes()
    assert json.loads(saved) == transport.verify_bundle_archive(str(archive), pin) == native
    with pytest.raises(BundleError, match="^invalid_bundle_transport$"):
        transport.verify_bundle_archive(str(archive), pin, out_path=str(receipt))
    assert receipt.read_bytes() == saved and archive.read_bytes() == prior
    assert not list(tmp_path.glob(".quantfit-archive-*"))


@pytest.mark.parametrize("invalid", [None, True, 1, "", "Replay", "screen ", [], object()])
@pytest.mark.parametrize("action", ["pack", "verify", "unpack"])
def test_exact_kind_admission_precedes_all_path_or_native_work(monkeypatch, invalid, action):
    monkeypatch.setattr(transport, "canonical", lambda *a, **k: pytest.fail("invalid kind reached path work"))
    monkeypatch.setattr(transport, "hold", lambda *a, **k: pytest.fail("invalid kind reached file hold"))
    with pytest.raises(BundleError, match="^invalid_bundle_transport$"):
        if action == "pack":
            transport.pack_bundle("PRIVATE", "PRIVATE", kind=invalid)
        elif action == "verify":
            transport.verify_bundle_archive("PRIVATE", "PRIVATE", kind=invalid)
        else:
            transport.unpack_bundle("PRIVATE", "PRIVATE", "PRIVATE", kind=invalid)


@pytest.mark.parametrize("kind", ["replay", "screen"])
@pytest.mark.parametrize("wrong", ["aggregate", "replay", "screen"])
def test_wrong_kind_never_autodetects_or_restores(tmp_path, kind, wrong):
    if kind == wrong:
        return
    source = replay(tmp_path / "source") if kind == "replay" else screen(tmp_path / "source")
    archive = tmp_path / "source.zip"
    pin = transport.pack_bundle(str(source), str(archive), kind=kind)["archive"]["sha256"]
    if kind == wrong:
        assert transport.verify_bundle_archive(str(archive), pin, kind=wrong)["integrity_verified"]
        assert transport.unpack_bundle(str(archive), pin, str(tmp_path / "matching"), kind=wrong)["kind"] == kind
        assert (tmp_path / "matching/manifest.json").is_file()
        return
    with pytest.raises(BundleError):
        transport.verify_bundle_archive(str(archive), pin, kind=wrong)
    with pytest.raises(BundleError):
        transport.unpack_bundle(str(archive), pin, str(tmp_path / "wrong"), kind=wrong)
    assert not (tmp_path / "wrong").exists()


@pytest.mark.parametrize("kind", ["replay", "screen"])
def test_whole_raw_pin_is_checked_before_zip_parse(tmp_path, monkeypatch, kind):
    from quantfit import bundle_archive_kinds as kinds

    archive = tmp_path / "not-a-zip"
    archive.write_bytes(b"PRIVATE")
    monkeypatch.setattr(kinds, "_decode", lambda *a, **k: pytest.fail("wrong raw pin reached parse"))
    with pytest.raises(BundleError):
        transport.verify_bundle_archive(str(archive), "0" * 64, kind=kind)


@pytest.mark.parametrize("kind", ["replay", "screen"])
@pytest.mark.parametrize(
    "attack", ["low_count", "high_count", "central_size", "offset", "disk", "comment", "magic", "zip64"]
)
def test_pre_zipfile_profiles_refuse_unbounded_directory_work(monkeypatch, kind, attack):
    from quantfit import bundle_archive_kinds as kinds

    profile = kinds._profile(kind)
    prefix = b"x" * profile.central_bytes
    fields = [b"PK\x05\x06", 0, 0, profile.minimum, profile.minimum, profile.central_bytes, 0, 0]
    if attack in ("low_count", "high_count"):
        fields[3] = fields[4] = profile.minimum - 1 if attack == "low_count" else profile.maximum + 1
    elif attack == "central_size":
        fields[5] += 1
        prefix += b"x"
    elif attack == "offset":
        fields[6] = 1
    elif attack == "disk":
        fields[1] = 1
    elif attack == "comment":
        fields[7] = 1
    elif attack == "magic":
        fields[0] = b"BAD!"
    else:
        prefix = prefix[:-20] + b"PK\x06\x07" + b"x" * 16
    raw = prefix + struct.pack("<4s4H2LH", *fields)
    trap = Mock(side_effect=AssertionError("unbounded ZIP directory reached ZipFile"))
    monkeypatch.setattr(kinds.zipfile, "ZipFile", trap)
    with pytest.raises(BundleError):
        kinds._decode(raw, kind)
    trap.assert_not_called()


@pytest.mark.parametrize("kind", ["replay", "screen"])
def test_exact_central_bound_and_count_are_admitted_before_sdk(monkeypatch, kind):
    from quantfit import bundle_archive_kinds as kinds

    profile = kinds._profile(kind)
    raw = b"x" * profile.central_bytes + struct.pack(
        "<4s4H2LH", b"PK\x05\x06", 0, 0, profile.maximum, profile.maximum, profile.central_bytes, 0, 0
    )
    trap = Mock(side_effect=LookupError("exact-boundary-admitted"))
    monkeypatch.setattr(kinds.zipfile, "ZipFile", trap)
    with pytest.raises(LookupError, match="exact-boundary-admitted"):
        kinds._decode(raw, kind)
    trap.assert_called_once()


def hostile_zip(files, *, change):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", allowZip64=False) as archive:
        items = list(files.items())
        if change == "order":
            items.reverse()
        if change == "casefold":
            items.append(("MANIFEST.json", b"{}"))
        if change == "duplicate":
            items.append(items[0])
        for index, (name, raw) in enumerate(items):
            if index == 0 and change in ("traversal", "backslash", "nested", "unicode", "directory"):
                name = {
                    "traversal": "../manifest.json",
                    "backslash": "reports\\bad.json",
                    "nested": "reports/a/b.json",
                    "nul": "manifest.json\x00bad",
                    "unicode": "rèport.json",
                    "directory": "reports/",
                }[change]
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            if index == 0:
                if change == "compression":
                    info.compress_type = zipfile.ZIP_DEFLATED
                elif change == "extra":
                    info.extra = b"\x01\x02\x00\x00"
                elif change == "member_comment":
                    info.comment = b"untrusted"
                elif change == "mode":
                    info.external_attr = (stat.S_IFLNK | 0o600) << 16
                elif change == "system":
                    info.create_system = 0
                elif change == "timestamp":
                    info.date_time = (1981, 1, 1, 0, 0, 0)
            if change == "duplicate" and index == len(items) - 1:
                with pytest.warns(UserWarning, match="Duplicate name"):
                    archive.writestr(info, raw)
            else:
                archive.writestr(info, raw)
        if change == "archive_comment":
            archive.comment = b"untrusted"
    raw = buffer.getvalue()
    if change == "nul":
        mutable = bytearray(raw)
        mutable[38] = 0
        central = raw.index(b"PK\x01\x02")
        mutable[central + 54] = 0
        raw = bytes(mutable)
    elif change == "trailer":
        raw += b"x"
    elif change == "prefix":
        raw = b"polyglot" + raw
    elif change == "crc":
        mutable = bytearray(raw)
        length = struct.unpack_from("<H", mutable, 26)[0]
        mutable[30 + length] ^= 1
        raw = bytes(mutable)
    return raw


@pytest.mark.parametrize("kind", ["replay", "screen"])
@pytest.mark.parametrize(
    "attack",
    [
        "compression",
        "extra",
        "member_comment",
        "mode",
        "system",
        "timestamp",
        "order",
        "casefold",
        "duplicate",
        "traversal",
        "backslash",
        "nested",
        "nul",
        "unicode",
        "directory",
        "archive_comment",
        "trailer",
        "prefix",
        "crc",
    ],
)
def test_noncanonical_or_hostile_zip_never_restores(tmp_path, kind, attack):
    source = replay(tmp_path / "source") if kind == "replay" else screen(tmp_path / "source")
    originals = {
        str(p.relative_to(source)).replace(os.sep, "/"): p.read_bytes() for p in source.rglob("*") if p.is_file()
    }
    if kind == "replay":
        order = ("manifest.json", "report-1.json", "report-2.json", "report-3.json", "t0.json")
    else:
        outer = json.loads(originals["manifest.json"])
        order = (
            "manifest.json",
            "targets.json",
            *(row["path"] for row in [*outer["reports"], outer["producer_summary"]] if row["status"] == "present"),
        )
    originals = {name: originals[name] for name in order}
    raw = hostile_zip(originals, change=attack)
    path = tmp_path / "hostile.zip"
    path.write_bytes(raw)
    with pytest.raises(BundleError, match="^invalid_bundle_transport$"):
        transport.unpack_bundle(str(path), hashlib.sha256(raw).hexdigest(), str(tmp_path / "refused"), kind=kind)
    assert not (tmp_path / "refused").exists()


@pytest.mark.parametrize("kind", ["replay", "screen"])
def test_source_is_held_once_without_native_directory_verification_or_replay(tmp_path, monkeypatch, kind):
    from quantfit import bundle_archive_kinds as kinds
    from quantfit import replay_bundle, saved_screen

    source = replay(tmp_path / "source") if kind == "replay" else screen(tmp_path / "source")
    held = Mock(wraps=kinds.hold)
    analyze = Mock(wraps=replay_bundle._validate if kind == "replay" else saved_screen._summarize_held)
    monkeypatch.setattr(kinds, "hold", held)
    monkeypatch.setattr(
        replay_bundle if kind == "replay" else saved_screen,
        "_validate" if kind == "replay" else "_summarize_held",
        analyze,
    )
    monkeypatch.setattr(replay_bundle, "_verified_bundle", lambda *a, **k: pytest.fail("native directory reread"))
    monkeypatch.setattr(
        "quantfit.screen_bundle_inputs._capture_bundle", lambda *a, **k: pytest.fail("unguarded native capture/reload")
    )
    transport.pack_bundle(str(source), str(tmp_path / "archive.zip"), kind=kind)
    paths = [str(call.args[0]) for call in held.call_args_list]
    assert len(paths) == len(set(paths)) == (5 if kind == "replay" else 4)
    analyze.assert_called_once()


@pytest.mark.parametrize("kind", ["replay", "screen"])
def test_source_mutation_during_native_validation_refuses_before_archive(tmp_path, monkeypatch, kind):
    from quantfit import bundle_archive_kinds as kinds

    source = replay(tmp_path / "source") if kind == "replay" else screen(tmp_path / "source")
    member = source / ("report-1.json" if kind == "replay" else "reports/g0.json")
    native = kinds._native

    def changed(*args, **kwargs):
        result = native(*args, **kwargs)
        member.write_bytes(member.read_bytes() + b" ")
        return result

    monkeypatch.setattr(kinds, "_native", changed)
    with pytest.raises(BundleError):
        transport.pack_bundle(str(source), str(tmp_path / "refused.zip"), kind=kind)
    assert not (tmp_path / "refused.zip").exists()


@pytest.mark.parametrize("kind", ["replay", "screen"])
def test_late_unknown_source_inventory_is_rechecked_before_exclusive_archive_link(tmp_path, monkeypatch, kind):
    source = replay(tmp_path / "source") if kind == "replay" else screen(tmp_path / "source")
    native = transport.tempfile.mkstemp

    def stage(*args, **kwargs):
        value = native(*args, **kwargs)
        (source / "foreign-owned").write_bytes(b"must remain")
        return value

    monkeypatch.setattr(transport.tempfile, "mkstemp", stage)
    with pytest.raises(BundleError):
        transport.pack_bundle(str(source), str(tmp_path / "refused.zip"), kind=kind)
    assert not (tmp_path / "refused.zip").exists() and (source / "foreign-owned").read_bytes() == b"must remain"
    assert not list(tmp_path.glob(".quantfit-archive-*"))


@pytest.mark.parametrize("kind", ["replay", "screen"])
def test_declared_member_size_refuses_before_large_hold(tmp_path, monkeypatch, kind):
    from quantfit import bundle_archive_kinds as kinds

    source = replay(tmp_path / "source") if kind == "replay" else screen(tmp_path / "source")
    path = source / "manifest.json"
    manifest = json.loads(path.read_bytes())
    row = manifest["files"][0] if kind == "replay" else manifest["reports"][0]
    row["size_bytes"] = 8 * 1024 * 1024 + 1
    path.write_text(json.dumps(manifest), encoding="utf-8")
    native = kinds.hold
    calls = []

    def bounded(path, *args, **kwargs):
        calls.append(Path(path))
        assert Path(path).name == "manifest.json", "unadmitted large payload reached hold"
        return native(path, *args, **kwargs)

    monkeypatch.setattr(kinds, "hold", bounded)
    with pytest.raises(BundleError):
        transport.pack_bundle(str(source), str(tmp_path / "refused.zip"), kind=kind)
    assert calls == [path] and not (tmp_path / "refused.zip").exists()


@pytest.mark.parametrize("kind", ["replay", "screen"])
def test_raw_archive_size_refuses_before_open_or_zip_parse(tmp_path, monkeypatch, kind):
    from quantfit import bundle_archive_kinds as kinds

    path = tmp_path / "oversized.zip"
    with path.open("wb") as f:
        f.truncate(kinds._profile(kind).raw_bytes + 1)
    monkeypatch.setattr(kinds, "_decode", lambda *a, **k: pytest.fail("oversized raw archive reached decode"))
    with pytest.raises(BundleError):
        transport.verify_bundle_archive(str(path), "0" * 64, kind=kind)


@pytest.mark.parametrize("fault", ["foreign", "reports_substitution", "archive_changed"])
def test_screen_restore_uses_native_nested_ownership_cleanup_and_preserves_unknowns(tmp_path, monkeypatch, fault):
    from quantfit import screen_bundle_publication as publication

    source = screen(tmp_path / "source")
    archive = tmp_path / "source.zip"
    pin = transport.pack_bundle(str(source), str(archive), kind="screen")["archive"]["sha256"]
    destination = tmp_path / "received"
    native = publication._write_member

    def write(path, raw, owned):
        native(path, raw, owned)
        if path.name == "targets.json":
            if fault == "foreign":
                (destination / "foreign-owned").write_bytes(b"preserve")
                raise RuntimeError("PRIVATE")
            elif fault == "reports_substitution":
                (destination / "reports").rename(destination / "original-reports")
                (destination / "reports").mkdir()
                (destination / "reports/foreign-owned").write_bytes(b"preserve")
            else:
                archive.write_bytes(archive.read_bytes() + b" ")

    monkeypatch.setattr(publication, "_write_member", write)
    with pytest.raises(BundleError) as error:
        transport.unpack_bundle(str(archive), pin, str(destination), kind="screen")
    assert "PRIVATE" not in str(error.value)
    if fault == "archive_changed":
        assert not destination.exists()
    else:
        assert str(error.value) == "partial_destination_preserved"
        assert destination.is_dir() and not (destination / "manifest.json").exists()
        assert (
            destination / ("foreign-owned" if fault == "foreign" else "reports/foreign-owned")
        ).read_bytes() == b"preserve"


def test_screen_maximum_target_count_names_and_original_order(tmp_path):
    from quantfit.screen_bundle import create_screen_bundle

    names = [f"n{i:03}" + "a" * 60 for i in reversed(range(256))]
    manifest, reports = corpus(tmp_path, [(name, "gguf", 0, 0, None) for name in names])
    (reports / "screen-summary.json").write_bytes(b"{}")
    source = tmp_path / "source"
    create_screen_bundle(str(manifest), str(reports), str(source))
    archive = tmp_path / "source.zip"
    result = transport.pack_bundle(str(source), str(archive), kind="screen")
    with zipfile.ZipFile(archive) as z:
        assert len(z.infolist()) == 259 and max(len(e.filename) for e in z.infolist()) == 77
        assert z.namelist() == [
            "manifest.json",
            "targets.json",
            *[f"reports/{name}.json" for name in names],
            "reports/screen-summary.json",
        ]
    checked = transport.verify_bundle_archive(str(archive), result["archive"]["sha256"], kind="screen")
    assert checked["native_verification"]["receiving_summary"]["coverage"]["n_targets"] == 256


@pytest.mark.parametrize("kind", ["replay", "screen"])
def test_maximum_valid_native_payload_is_accepted_without_looser_aggregate_limits(tmp_path, kind):
    from quantfit import bundle_archive_kinds as kinds

    if kind == "replay":
        from quantfit.replay_bundle import create_replay_bundle
        from quantfit.reproduce import within_hardware_identical

        paths, t0 = replay_inputs(tmp_path)
        for path in map(Path, paths):
            raw = path.read_bytes()
            path.write_bytes(raw + b" " * (8 * 1024 * 1024 - len(raw)))
        within_hardware_identical(paths, out_path=str(t0))
        raw = t0.read_bytes()
        t0.write_bytes(raw + b" " * (8 * 1024 * 1024 - len(raw)))
        source = tmp_path / "source"
        create_replay_bundle(paths, str(t0), str(source))
        p = source / "manifest.json"
        raw = p.read_bytes()
        p.write_bytes(raw + b" " * (64 * 1024 - len(raw)))
        expected = kinds.MAX_REPLAY_PAYLOAD_BYTES
    else:
        from quantfit.screen_bundle import create_screen_bundle

        manifest, reports = corpus(tmp_path, [(f"g{i}", "gguf", 0, 0, None) for i in range(8)])
        source = tmp_path / "source"
        create_screen_bundle(str(manifest), str(reports), str(source))
        outer = json.loads((source / "manifest.json").read_bytes())
        for row in outer["reports"][:-1]:
            p = source / row["path"]
            raw = p.read_bytes()
            raw += b" " * (8 * 1024 * 1024 - len(raw))
            p.write_bytes(raw)
            row.update(size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        row = outer["reports"][-1]
        p = source / row["path"]
        original = p.read_bytes()
        row["size_bytes"] = 8 * 1024 * 1024
        for _ in range(4):
            raw_outer = (json.dumps(outer, indent=2, sort_keys=True) + "\n").encode()
            remaining = 64 * 1024 * 1024 - len(raw_outer) - len(manifest.read_bytes()) - 7 * 8 * 1024 * 1024
            raw = original + b" " * (remaining - len(original))
            row.update(size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        p.write_bytes(raw)
        (source / "manifest.json").write_bytes((json.dumps(outer, indent=2, sort_keys=True) + "\n").encode())
        expected = 64 * 1024 * 1024
    total = sum(p.stat().st_size for p in source.rglob("*") if p.is_file())
    assert total == expected
    archive = tmp_path / "maximum.zip"
    result = transport.pack_bundle(str(source), str(archive), kind=kind)
    assert result["integrity_verified"] and archive.stat().st_size <= kinds._profile(kind).raw_bytes
    if kind == "replay":
        assert archive.stat().st_size == 33_620_488
    assert transport.verify_bundle_archive(str(archive), result["archive"]["sha256"], kind=kind)["integrity_verified"]
    assert transport.MAX_ARCHIVE_BYTES == 32 * 1024 * 1024 and transport.MAX_PAYLOAD_BYTES == 27_328_512
    if kind == "screen":
        p = source / "manifest.json"
        p.write_bytes(p.read_bytes() + b" ")
        with pytest.raises(BundleError):
            transport.pack_bundle(str(source), str(tmp_path / "one-over.zip"), kind=kind)
        assert not (tmp_path / "one-over.zip").exists()


@pytest.mark.parametrize("kind", ["replay", "screen"])
@pytest.mark.parametrize("alias", ["root", "manifest", "member", "missing", "existing"])
def test_archive_output_aliases_and_existing_destinations_are_preserved(tmp_path, kind, alias):
    source = replay(tmp_path / "source") if kind == "replay" else screen(tmp_path / "source", code=4)
    member = source / ("report-1.json" if kind == "replay" else "reports/g0.json")
    output = {
        "root": source,
        "manifest": source / "manifest.json",
        "member": member,
        "missing": source / "unlisted.zip",
        "existing": tmp_path / "foreign.zip",
    }[alias]
    if alias == "existing":
        output.write_bytes(b"must preserve")
    before = {p: p.read_bytes() for p in source.rglob("*") if p.is_file()}
    with pytest.raises(BundleError):
        transport.pack_bundle(str(source), str(output), kind=kind)
    assert all(p.read_bytes() == raw for p, raw in before.items())
    if alias == "existing":
        assert output.read_bytes() == b"must preserve"


@pytest.mark.parametrize(
    "command", ["create", "verify", "replay-create", "replay-verify", "screen-create", "screen-verify"]
)
def test_kind_option_is_only_admitted_on_archive_commands(command):
    from quantfit.cli import _build_parser

    # The existing help inventory also checks every parser's public flag coverage.
    parser = _build_parser()
    bundle_parser = next(action for action in parser._actions if action.dest == "cmd").choices["bundle"]
    child = next(action for action in bundle_parser._actions if action.dest == "bundle_cmd").choices[command]
    assert not any("--kind" in action.option_strings for action in child._actions)


@pytest.mark.parametrize("fault", ["initial_attestation", "preexisting", "mkdir_failure"])
def test_screen_initial_destination_attestation_preserves_owned_uncertainty(tmp_path, monkeypatch, fault):
    from quantfit import screen_bundle_publication as publication

    source = screen(tmp_path / "source")
    archive = tmp_path / "source.zip"
    pin = transport.pack_bundle(str(source), str(archive), kind="screen")["archive"]["sha256"]
    destination = tmp_path / "received"
    identity = publication._identity
    mkdir = Path.mkdir
    if fault == "preexisting":
        destination.mkdir()
        (destination / "foreign").write_bytes(b"preserve")
    elif fault == "initial_attestation":

        def unavailable(path):
            if path == destination:
                raise OSError("PRIVATE first post-mkdir identity fault")
            return identity(path)

        monkeypatch.setattr(publication, "_identity", unavailable)
    else:

        def failed(path, *args, **kwargs):
            if path == destination:
                raise OSError("PRIVATE mkdir failure")
            return mkdir(path, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", failed)
    with pytest.raises(BundleError) as error:
        transport.unpack_bundle(str(archive), pin, str(destination), kind="screen")
    assert "PRIVATE" not in str(error.value)
    if fault == "initial_attestation":
        assert destination.is_dir() and not list(destination.iterdir())
        assert str(error.value) == "partial_destination_preserved"
    else:
        assert str(error.value) == "invalid_bundle_transport"
        if fault == "preexisting":
            assert (destination / "foreign").read_bytes() == b"preserve"
        else:
            assert not destination.exists()


@pytest.mark.parametrize("kind", ["aggregate", "replay", "screen"])
@pytest.mark.parametrize("fault", ["substituted", "unstatable", "unlink_failure"])
def test_archive_stage_ownership_uncertainty_is_explicit_for_every_kind(tmp_path, monkeypatch, kind, fault):
    from test_bundle_transport import prepared

    source = (
        prepared(tmp_path)[0]
        if kind == "aggregate"
        else replay(tmp_path / "source")
        if kind == "replay"
        else screen(tmp_path / "source")
    )
    native_temp, native_link, native_identity, native_unlink = (
        transport.tempfile.mkstemp,
        os.link,
        transport._identity,
        Path.unlink,
    )
    stages, linked = [], []

    def stage(*args, **kwargs):
        value = native_temp(*args, **kwargs)
        stages.append(Path(value[1]))
        return value

    def link(src, dst, *args, **kwargs):
        native_link(src, dst, *args, **kwargs)
        linked.append(Path(dst))
        if fault == "substituted":
            Path(src).rename(tmp_path / "attested-original-stage")
            Path(src).write_bytes(b"foreign-owned-stage")

    def identity(path):
        if fault == "unstatable" and linked and path == stages[0]:
            raise OSError("PRIVATE stage identity failure")
        return native_identity(path)

    def unlink(path, *args, **kwargs):
        if fault == "unlink_failure" and linked and path == stages[0]:
            raise OSError("PRIVATE stage unlink failure")
        return native_unlink(path, *args, **kwargs)

    monkeypatch.setattr(transport.tempfile, "mkstemp", stage)
    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(transport, "_identity", identity)
    monkeypatch.setattr(Path, "unlink", unlink)
    output = tmp_path / "published.zip"
    with pytest.raises(BundleError) as error:
        transport.pack_bundle(str(source), str(output), kind=kind)
    assert str(error.value) == "archive_stage_preserved"
    assert len(stages) == len(linked) == 1 and stages[0].exists() and output.exists()
    if fault == "substituted":
        assert stages[0].read_bytes() == b"foreign-owned-stage"
        assert output.read_bytes() == (tmp_path / "attested-original-stage").read_bytes()
    else:
        assert stages[0].read_bytes() == output.read_bytes()
