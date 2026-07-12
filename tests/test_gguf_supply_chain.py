"""GGUF supply-chain hardening — hermetic (no network, no binary execution).

The downloaded llama-quantize binary is EXECUTED, so the pin/verify/delete
behavior is load-bearing security logic; these tests pin it down without ever
touching the network.
"""

import hashlib

import pytest

import quantfit.backends.gguf as g


def test_sha256_streams_correctly(tmp_path):
    f = tmp_path / "blob.bin"
    data = b"quantfit" * 4096  # spans multiple read chunks
    f.write_bytes(data)
    assert g._sha256(f) == hashlib.sha256(data).hexdigest()


def test_verify_or_die_accepts_pinned_hash(tmp_path, monkeypatch):
    f = tmp_path / "asset.zip"
    f.write_bytes(b"payload")
    monkeypatch.setitem(g._BINARY_SHA256, "asset.zip", hashlib.sha256(b"payload").hexdigest())
    g._verify_or_die(f, "asset.zip")  # must not raise
    assert f.exists()


def test_verify_or_die_deletes_on_mismatch(tmp_path, monkeypatch):
    f = tmp_path / "asset.zip"
    f.write_bytes(b"tampered")
    monkeypatch.setitem(g._BINARY_SHA256, "asset.zip", "0" * 64)
    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        g._verify_or_die(f, "asset.zip")
    assert not f.exists()  # the bad file must be gone, not left to retry into


def test_verify_or_die_refuses_unpinned_asset(tmp_path):
    f = tmp_path / "mystery.zip"
    f.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="no pinned SHA256"):
        g._verify_or_die(f, "mystery.zip")


def test_download_refuses_unpinned_asset_before_fetching(tmp_path, monkeypatch):
    def _no_fetch(*a, **k):
        raise AssertionError("download must not start for an unpinned asset")

    monkeypatch.setattr(g.urllib.request, "urlretrieve", _no_fetch)
    with pytest.raises(RuntimeError, match="no pinned SHA256"):
        g._download_verified("https://example.invalid/x.zip", "x.zip", tmp_path / "x.zip")


def test_download_verifies_before_promoting(tmp_path, monkeypatch):
    # A fetched-but-tampered artifact must never appear at the destination path.
    def _fetch(url, dest):
        g.Path(dest).write_bytes(b"tampered bytes")

    monkeypatch.setattr(g.urllib.request, "urlretrieve", _fetch)
    monkeypatch.setitem(g._BINARY_SHA256, "x.zip", hashlib.sha256(b"expected bytes").hexdigest())
    dest = tmp_path / "x.zip"
    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        g._download_verified("https://example.invalid/x.zip", "x.zip", dest)
    assert not dest.exists()  # atomic: dest appears only after verification
    assert not list(tmp_path.glob("*.part"))  # no temp litter either


def test_extract_deletes_corrupt_archive(tmp_path):
    bad = tmp_path / "corrupt.zip"
    bad.write_bytes(b"this is not a zip")
    with pytest.raises(RuntimeError, match="corrupt archive"):
        g._extract(bad, tmp_path / "out")
    assert not bad.exists()


def test_binary_asset_per_platform(monkeypatch):
    monkeypatch.setattr(g.platform, "system", lambda: "Windows")
    assert g._binary_asset().endswith("win-cpu-x64.zip")
    monkeypatch.setattr(g.platform, "system", lambda: "Linux")
    assert g._binary_asset().endswith("ubuntu-x64.tar.gz")
    monkeypatch.setattr(g.platform, "system", lambda: "Darwin")
    with pytest.raises(RuntimeError, match="no prebuilt"):
        g._binary_asset()


def test_cached_archive_is_reverified_before_extract(tmp_path, monkeypatch):
    # "existence != integrity": a tampered archive already sitting in the cache
    # must be re-hashed against the pin, refused, and deleted — never extracted,
    # and no download attempted in its place during the same call.
    monkeypatch.setattr(g, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(g, "_binary_asset", lambda: "asset.zip")
    monkeypatch.setitem(g._BINARY_SHA256, "asset.zip", "0" * 64)
    monkeypatch.setattr(
        g.urllib.request, "urlretrieve", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no download"))
    )
    cached = tmp_path / "asset.zip"
    cached.write_bytes(b"tampered cache")
    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        g.llama_quantize_bin()
    assert not cached.exists()
