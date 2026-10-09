"""verify() structural check for GGUF artifacts (no model load)."""

import struct

from quantfit.verify import _GGUF_MAGIC, verify


def fixture_bytes():
    name = b"test.weight"
    raw = _GGUF_MAGIC + struct.pack("<IQQQ", 3, 1, 0, len(name)) + name
    raw += struct.pack("<IQQIQ", 2, 32, 2, 2, 0)
    return raw + b"\x00" * (-len(raw) % 32) + b"\x00" * 36


def test_legacy_structural_api_keeps_ignored_token_parameter(tmp_path):
    path = tmp_path / "model.GGUF"
    path.write_bytes(fixture_bytes())
    assert verify(str(path), max_new_tokens=128)[0] is True


def test_ambiguity_refuses_after_second_matching_file(tmp_path, monkeypatch):
    from pathlib import Path

    import pytest

    from quantfit.verify import gguf_path

    for name in ("a.gguf", "b.GGUF"):
        (tmp_path / name).write_bytes(fixture_bytes())

    def entries(path):
        yield tmp_path / "a.gguf"
        yield tmp_path / "b.GGUF"
        pytest.fail("enumerated after proven ambiguity")

    monkeypatch.setattr(Path, "iterdir", entries)
    with pytest.raises(RuntimeError, match="multiple GGUF"):
        gguf_path(str(tmp_path))


def test_verify_gguf_magic_ok(tmp_path):
    (tmp_path / "model.Q4_K_M.gguf").write_bytes(fixture_bytes())
    ok, msg = verify(str(tmp_path))
    assert ok and "OK" in msg


def test_verify_gguf_magic_bad(tmp_path):
    (tmp_path / "model.Q4_K_M.gguf").write_bytes(b"XXXX" + b"\x00" * 16)
    ok, _ = verify(str(tmp_path))
    assert not ok


def test_verify_accepts_direct_gguf_file_path(tmp_path):
    f = tmp_path / "m.Q4_K_M.gguf"
    f.write_bytes(fixture_bytes())
    ok, msg = verify(str(f))  # the CLI documents "dir or .gguf" — cover the file form
    assert ok and "GGUF structure" in msg
