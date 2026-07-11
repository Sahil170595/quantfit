"""quantize() dispatch — routing, refusal, and card provenance (hermetic)."""

import pytest

import quantfit.backends.compressed_tensors as ct_backend
import quantfit.backends.gguf as gguf_backend
import quantfit.fit as fit
import quantfit.quantize as q
from quantfit.fit import LIMIT_MACHINE, MODE_GPU, MODE_REFUSE, CapacityPlan
from quantfit.registry import UnsupportedCombo

_GIB = 1024**3


def _cap(mode, limit=""):
    return CapacityPlan("m", 3 * _GIB, 11 * _GIB, 32 * _GIB, 100 * _GIB, 5 * _GIB, mode, limit)


def test_ct_method_routes_to_compressed_tensors(tmp_path, monkeypatch):
    calls = {}

    def fake_ct(model_id, method, scheme, out_dir, spec, needs_calibration, token=None):
        calls.update(model=model_id, method=method, scheme=scheme, calib=needs_calibration)
        out = tmp_path / "out"
        out.mkdir(exist_ok=True)
        return out

    monkeypatch.setattr(q, "plan", lambda *a, **k: _cap(MODE_GPU))
    monkeypatch.setattr(ct_backend, "quantize_ct", fake_ct)
    out = q.quantize("m", "awq", str(tmp_path / "out"))
    assert calls["model"] == "m" and calls["method"] == "awq"
    assert calls["scheme"] == "W4A16_ASYM" and calls["calib"]  # registry default resolved
    card = (out / "README.md").read_text(encoding="utf-8")
    assert "AWQ" in card and "spec fingerprint" in card  # provenance lands on the card


def test_refusal_raises_cannot_quantize(monkeypatch):
    monkeypatch.setattr(q, "plan", lambda *a, **k: _cap(MODE_REFUSE, LIMIT_MACHINE))
    with pytest.raises(q.CannotQuantize, match="CAN'T QUANTIZE"):
        q.quantize("m", "awq", "out")


def test_no_gpu_plan_error_becomes_refusal(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("no CUDA device visible")

    monkeypatch.setattr(q, "plan", _boom)
    with pytest.raises(q.CannotQuantize, match="no CUDA"):
        q.quantize("m", "awq", "out")


def test_gguf_routes_to_gguf_backend(tmp_path, monkeypatch):
    calls = {}

    def fake_gguf(model_id, qtype, out_dir, token=None):
        calls.update(model=model_id, qtype=qtype)
        out = tmp_path / "gg"
        out.mkdir(exist_ok=True)
        return out

    monkeypatch.setattr(fit, "gguf_disk_need", lambda *a, **k: (100 * _GIB, 10 * _GIB))
    monkeypatch.setattr(gguf_backend, "quantize_gguf", fake_gguf)
    out = q.quantize("m", "gguf", str(tmp_path / "gg"))
    assert calls["qtype"] == "Q4_K_M"  # registry default resolved
    card = (out / "README.md").read_text(encoding="utf-8")
    assert "GGUF" in card and "llama.cpp" in card


def test_gguf_disk_refusal_names_the_numbers(monkeypatch):
    monkeypatch.setattr(fit, "gguf_disk_need", lambda *a, **k: (1 * _GIB, 30 * _GIB))
    with pytest.raises(q.CannotQuantize, match="free disk"):
        q.quantize("m", "gguf", "out")


def test_unknown_method_is_unsupported():
    with pytest.raises(UnsupportedCombo):
        q.quantize("m", "bogus", "out", run_check=False)


def test_no_check_skips_preflight(tmp_path, monkeypatch):
    def _fail(*a, **k):
        raise AssertionError("plan() must not run with run_check=False")

    monkeypatch.setattr(q, "plan", _fail)
    monkeypatch.setattr(ct_backend, "quantize_ct", lambda *a, **k: tmp_path)
    q.quantize("m", "rtn", str(tmp_path), run_check=False)
