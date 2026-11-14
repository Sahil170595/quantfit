"""Closed aggregate container integrity does not upgrade native adverse results."""

import hashlib
import io
import json
import os
import stat
import struct
import subprocess
import sys
import warnings
import zipfile
from pathlib import Path

import pytest
from test_bundle import inputs

from quantfit.bundle import create_bundle, verify_bundle


def prepared(tmp_path):
    report, calibration, resolution, gate = inputs(tmp_path)
    directory = tmp_path / "source"
    native = create_bundle(
        str(report),
        str(directory),
        calibration_path=str(calibration),
        resolution_path=str(resolution),
        gate_path=str(gate),
    )
    return directory, native


def test_existing_directory_preserves_native_adverse_outcomes(tmp_path):
    directory, result = prepared(tmp_path)
    assert verify_bundle(str(directory))["declared_results"] == result["declared_results"]
    assert result["declared_results"]["gate"]["exit_code"] == 5


def test_deterministic_archive_and_native_roundtrip(tmp_path):
    from quantfit.bundle_transport import pack_bundle, unpack_bundle, verify_bundle_archive

    directory, native = prepared(tmp_path)
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    result = pack_bundle(str(directory), str(first))
    pack_bundle(str(directory), str(second))
    assert first.read_bytes() == second.read_bytes()
    pin = hashlib.sha256(first.read_bytes()).hexdigest()
    assert verify_bundle_archive(str(first), pin)["declared_results"] == native["declared_results"]
    restored = tmp_path / "received"
    received = unpack_bundle(str(first), pin, str(restored))
    assert received["integrity_verified"] and received["scientific_claims_verified"] is False
    assert received["declared_results"] == result["declared_results"] == native["declared_results"]
    assert {p.name: p.read_bytes() for p in restored.iterdir()} == {p.name: p.read_bytes() for p in directory.iterdir()}
    assert verify_bundle(str(restored))["declared_results"] == native["declared_results"]


def test_actual_cli_transport_does_not_promote_nested_gate_five(tmp_path):
    directory, _ = prepared(tmp_path)
    archive = tmp_path / "portable.zip"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "quantfit.cli",
            "bundle",
            "pack",
            "--bundle",
            str(directory),
            "--out",
            str(archive),
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["result"]["declared_results"]["gate"]["exit_code"] == 5


def test_zip64_override_is_refused_before_sdk_construction(monkeypatch):
    from quantfit import bundle_transport as transport
    from quantfit.bundle import BundleError

    # Valid ZIP64 override locators are recognized even with allowZip64=False.
    record = struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, 1_000_000, 1_000_000, 46_000_000, 0)
    locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, 0, 1)
    classic = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 2, 2, 76, 0, 0)

    def forbidden(*args, **kwargs):
        raise AssertionError("unadmitted ZIP64 directory reached SDK construction")

    monkeypatch.setattr(transport.zipfile, "ZipFile", forbidden)
    with pytest.raises(BundleError):
        transport._decode(record + locator + classic)


@pytest.mark.parametrize("where", ["stage", "restore"])
def test_failed_initial_fd_attestation_closes_descriptor_and_preserves_uncertain_file(tmp_path, monkeypatch, where):
    from quantfit import bundle_transport as transport
    from quantfit.bundle import BundleError

    directory, _ = prepared(tmp_path)
    archive = tmp_path / "portable.zip"
    transport.pack_bundle(str(directory), str(archive))
    pin = hashlib.sha256(archive.read_bytes()).hexdigest()
    original_fstat, original_open, original_temp = os.fstat, os.open, transport.tempfile.mkstemp
    acquired = []

    def temp(*args, **kwargs):
        fd, path = original_temp(*args, **kwargs)
        acquired.append((fd, path))
        return fd, path

    def opened(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        if flags & os.O_WRONLY and "received" in str(path):
            acquired.append((fd, path))
        return fd

    def fault(fd):
        if acquired and fd == acquired[-1][0]:
            raise OSError("controlled first descriptor attestation failure")
        return original_fstat(fd)

    monkeypatch.setattr(os, "fstat", fault)
    if where == "stage":
        monkeypatch.setattr(transport.tempfile, "mkstemp", temp)
    else:
        monkeypatch.setattr(os, "open", opened)
    try:
        with pytest.raises(BundleError):
            if where == "stage":
                transport.pack_bundle(str(directory), str(tmp_path / "second.zip"))
            else:
                transport.unpack_bundle(str(archive), pin, str(tmp_path / "received"))
        assert len(acquired) == 1
        fd, path = acquired[0]
        assert Path(path).exists()
        with pytest.raises(OSError):
            original_fstat(fd)
    finally:
        # Close the deliberately demonstrated pre-fix descriptor leak in the test.
        if acquired:
            try:
                os.close(acquired[0][0])
            except OSError:
                pass


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "extra",
        "nested",
        "traversal",
        "absolute",
        "backslash",
        "nul",
        "symlink",
        "special",
        "compressed",
        "extra_header",
        "comment",
        "trailer",
        "crc",
        "size",
        "encrypted",
        "manifest",
        "role_hash",
        "relationship",
    ],
)
def test_hostile_or_invalid_native_archive_never_creates_destination(tmp_path, fault):
    from quantfit import bundle_transport as transport
    from quantfit.bundle import BundleError

    source, _ = prepared(tmp_path)
    files = {p.name: p.read_bytes() for p in source.iterdir()}
    if fault in {"manifest", "role_hash", "relationship"}:
        manifest = json.loads(files["manifest.json"])
        if fault == "manifest":
            manifest["bundle_schema"] = 1.0
        elif fault == "role_hash":
            manifest["files"][0]["sha256"] = "0" * 64
        else:
            report = json.loads(files["report.json"])
            report["drift"]["regression_detected"] = False
            files["report.json"] = json.dumps(report).encode()
            for entry in manifest["files"]:
                if entry["role"] == "report":
                    entry.update(
                        sha256=hashlib.sha256(files["report.json"]).hexdigest(), size_bytes=len(files["report.json"])
                    )
        files["manifest.json"] = json.dumps(manifest).encode()
        raw = transport._encode(files)
    else:
        data = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(data, "w") as z:
                for name in transport.ORDER:
                    if name not in files:
                        continue
                    alias = (
                        {
                            "nested": "nested/report.json",
                            "traversal": "../report.json",
                            "absolute": "/report.json",
                            "backslash": "nested\\report.json",
                        }.get(fault, name)
                        if name == "report.json"
                        else name
                    )
                    info = zipfile.ZipInfo(alias, (1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o600) << 16
                    if name == "report.json":
                        if fault == "symlink":
                            info.external_attr = (stat.S_IFLNK | 0o600) << 16
                        elif fault == "special":
                            info.external_attr = (stat.S_IFIFO | 0o600) << 16
                        elif fault == "compressed":
                            info.compress_type = zipfile.ZIP_DEFLATED
                        elif fault == "extra_header":
                            info.extra = b"\x99\x00\x00\x00"
                        elif fault == "comment":
                            info.comment = b"unrecognized metadata"
                    z.writestr(info, files[name])
                    if fault == "duplicate" and name == "report.json":
                        z.writestr(info, files[name])
                if fault == "extra":
                    z.writestr("private.capture.jsonl", b"PRIVATE_SENTINEL")
        raw = bytearray(data.getvalue())
        if fault == "trailer":
            raw += b"trailing bytes"
        elif fault == "crc":
            pos = raw.find(files["report.json"])
            raw[pos + 3] ^= 1
        elif fault == "nul":
            raw = raw.replace(b"report.json", b"report\x00json")
        elif fault in {"size", "encrypted"}:
            for pos in range(len(raw) - 46):
                if raw[pos : pos + 4] == b"PK\x01\x02" and raw[pos + 46 : pos + 57] == b"report.json":
                    if fault == "size":
                        struct.pack_into("<L", raw, pos + 24, 0x7FFFFFFF)
                    else:
                        struct.pack_into("<H", raw, pos + 8, 1)
                    break
        raw = bytes(raw)
    archive = tmp_path / "hostile.zip"
    archive.write_bytes(raw)
    with pytest.raises(BundleError):
        transport.unpack_bundle(str(archive), hashlib.sha256(raw).hexdigest(), str(tmp_path / "refused"))
    assert not (tmp_path / "refused").exists()


def test_all_budgets_and_digest_admit_before_sdk_or_publication(tmp_path, monkeypatch):
    from quantfit import bundle_transport as transport
    from quantfit.bundle import BundleError

    source, _ = prepared(tmp_path)
    archive = tmp_path / "portable.zip"
    transport.pack_bundle(str(source), str(archive))
    pin = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(BundleError):
        transport.verify_bundle_archive(str(archive), "0" * 64)
    monkeypatch.setattr(transport, "MAX_ARCHIVE_BYTES", 1)
    with pytest.raises(BundleError):
        transport.unpack_bundle(str(archive), pin, str(tmp_path / "too-big"))
    assert not (tmp_path / "too-big").exists()
    monkeypatch.undo()
    monkeypatch.setattr(transport, "MAX_PAYLOAD_BYTES", 1)
    with pytest.raises(BundleError):
        transport.pack_bundle(str(source), str(tmp_path / "too-big.zip"))
    assert not (tmp_path / "too-big.zip").exists()


@pytest.mark.parametrize("fault", ["duplicate_destination", "archive_alias", "inside_source", "unsupported_link"])
def test_exclusive_roles_and_atomic_archive_failure(tmp_path, monkeypatch, fault):
    from quantfit import bundle_transport as transport
    from quantfit.bundle import BundleError

    source, _ = prepared(tmp_path)
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    archive = tmp_path / "portable.zip"
    transport.pack_bundle(str(source), str(archive))
    pin = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(BundleError):
        if fault == "duplicate_destination":
            transport.unpack_bundle(str(archive), pin, str(source))
        elif fault == "archive_alias":
            transport.unpack_bundle(str(archive), pin, str(archive))
        elif fault == "inside_source":
            transport.pack_bundle(str(source), str(source / "new.zip"))
        else:

            def unsupported(*args, **kwargs):
                raise OSError("controlled link failure")

            monkeypatch.setattr(os, "link", unsupported)
            with pytest.raises(BundleError):
                transport.pack_bundle(str(source), str(tmp_path / "not-published.zip"))
            assert not (tmp_path / "not-published.zip").exists()
            assert not list(tmp_path.glob(".quantfit-archive-*"))
            raise BundleError("expected refusal inspected")
    assert {p.name: p.read_bytes() for p in source.iterdir()} == before


@pytest.mark.parametrize("unexpected", [False, True])
def test_owned_partial_restoration_cleanup_retry_and_unknown_file_preservation(tmp_path, monkeypatch, unexpected):
    from quantfit import bundle_transport as transport
    from quantfit.bundle import BundleError

    source, _ = prepared(tmp_path)
    archive, target = tmp_path / "portable.zip", tmp_path / "received"
    transport.pack_bundle(str(source), str(archive))
    pin = hashlib.sha256(archive.read_bytes()).hexdigest()

    def fail(fd):
        if unexpected:
            (target / "operator-sentinel").write_bytes(b"DO_NOT_REMOVE")
        raise OSError("controlled failure after write, before readiness")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(BundleError):
        transport.unpack_bundle(str(archive), pin, str(target))
    if unexpected:
        assert (target / "operator-sentinel").read_bytes() == b"DO_NOT_REMOVE"
        assert not (target / "manifest.json").exists()
    else:
        assert not target.exists()
        monkeypatch.undo()
        assert transport.unpack_bundle(str(archive), pin, str(target))["integrity_verified"]
        with pytest.raises(BundleError):
            transport.unpack_bundle(str(archive), pin, str(target))


def test_post_mkdir_attestation_failure_reports_preserved_unattested_root(tmp_path, monkeypatch):
    from quantfit import bundle_transport as transport
    from quantfit.bundle import BundleError

    source, _ = prepared(tmp_path)
    archive, target = tmp_path / "portable.zip", tmp_path / "received"
    transport.pack_bundle(str(source), str(archive))
    native_identity = transport._identity

    def fault(path):
        if path == target and path.exists():
            raise OSError("controlled new-root attestation failure")
        return native_identity(path)

    monkeypatch.setattr(transport, "_identity", fault)
    with pytest.raises(BundleError, match="^partial_destination_preserved$"):
        transport.unpack_bundle(str(archive), hashlib.sha256(archive.read_bytes()).hexdigest(), str(target))
    assert target.is_dir() and not list(target.iterdir())
