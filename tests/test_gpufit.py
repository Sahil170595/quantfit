"""GPU pre-flight logic — the load-bearing decision, tested without a GPU."""
import quantfit.gpufit as g
from quantfit.gpufit import FitReport, check_fit

_GIB = 1024**3


def test_fits_when_required_under_free(monkeypatch):
    monkeypatch.setattr(g, "estimate_fp16_bytes", lambda *a, **k: 3 * _GIB)  # ~1.5B
    monkeypatch.setattr(g, "gpu_free_bytes", lambda: 11 * _GIB)
    r = check_fit("dummy")
    assert r.fits
    assert "OK" in r.reason()


def test_refuses_when_required_over_free(monkeypatch):
    monkeypatch.setattr(g, "estimate_fp16_bytes", lambda *a, **k: 14 * _GIB)  # ~7B
    monkeypatch.setattr(g, "gpu_free_bytes", lambda: 11 * _GIB)
    r = check_fit("dummy")
    assert not r.fits
    assert "CAN'T QUANTIZE" in r.reason()


def test_required_includes_overhead_and_headroom(monkeypatch):
    monkeypatch.setattr(g, "estimate_fp16_bytes", lambda *a, **k: 4 * _GIB)
    monkeypatch.setattr(g, "gpu_free_bytes", lambda: 99 * _GIB)
    r = check_fit("dummy")
    assert r.required_bytes == int(4 * _GIB * g.CALIB_OVERHEAD_FACTOR) + g.HEADROOM_BYTES


def test_report_gib_conversion():
    r = FitReport("m", fp16_bytes=2 * _GIB, required_bytes=4 * _GIB, free_bytes=8 * _GIB, fits=True)
    assert abs(r.fp16_gib - 2.0) < 1e-6
    assert abs(r.required_gib - 4.0) < 1e-6
