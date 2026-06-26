"""verify() structural check for GGUF artifacts (no model load)."""
from quantfit.verify import _GGUF_MAGIC, verify


def test_verify_gguf_magic_ok(tmp_path):
    (tmp_path / "model.Q4_K_M.gguf").write_bytes(_GGUF_MAGIC + b"\x00" * 16)
    ok, msg = verify(str(tmp_path))
    assert ok and "OK" in msg


def test_verify_gguf_magic_bad(tmp_path):
    (tmp_path / "model.Q4_K_M.gguf").write_bytes(b"XXXX" + b"\x00" * 16)
    ok, _ = verify(str(tmp_path))
    assert not ok
