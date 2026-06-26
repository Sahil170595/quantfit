"""Capacity logic — gpu / offload / refuse with cache-aware disk, no hardware."""
import quantfit.fit as f
from quantfit.fit import LIMIT_DISK, LIMIT_MACHINE, MODE_GPU, MODE_OFFLOAD, MODE_REFUSE, plan

_GIB = 1024**3


def _patch(monkeypatch, fp16, gpu, ram, disk, cached=0):
    monkeypatch.setattr(f, "estimate_fp16_bytes", lambda *a, **k: fp16)
    monkeypatch.setattr(f, "gpu_free_bytes", lambda: gpu)
    monkeypatch.setattr(f.psutil, "virtual_memory", lambda: type("M", (), {"available": ram})())
    monkeypatch.setattr(f.shutil, "disk_usage", lambda p: type("D", (), {"free": disk})())
    monkeypatch.setattr(f, "_existing_parent", lambda p: ".")
    monkeypatch.setattr(f, "_cached_weight_bytes", lambda mid: cached)


def test_gpu_mode_when_fits_vram(monkeypatch):
    _patch(monkeypatch, 3 * _GIB, 11 * _GIB, 32 * _GIB, 100 * _GIB)  # ~1.5B
    assert plan("m").mode == MODE_GPU


def test_offload_when_too_big_for_vram_but_ram_ok(monkeypatch):
    _patch(monkeypatch, 14 * _GIB, 11 * _GIB, 32 * _GIB, 100 * _GIB)  # ~7B, ample disk
    p = plan("m")
    assert p.mode == MODE_OFFLOAD and p.offload and p.fits


def test_refuse_machine_when_too_big_even_for_ram(monkeypatch):
    _patch(monkeypatch, 140 * _GIB, 11 * _GIB, 32 * _GIB, 500 * _GIB, cached=140 * _GIB)
    p = plan("m")
    assert p.mode == MODE_REFUSE and p.limit == LIMIT_MACHINE and not p.fits


def test_refuse_disk_when_no_room_to_download(monkeypatch):
    _patch(monkeypatch, 14 * _GIB, 11 * _GIB, 32 * _GIB, 5 * _GIB)  # 7B, 5GB disk
    p = plan("m")
    assert p.mode == MODE_REFUSE and p.limit == LIMIT_DISK


def test_cache_flips_disk_refuse_to_offload(monkeypatch):
    # Same tiny disk, but the weights are already cached -> only output space needed.
    _patch(monkeypatch, 14 * _GIB, 11 * _GIB, 32 * _GIB, 10 * _GIB, cached=14 * _GIB)
    assert plan("m").mode == MODE_OFFLOAD
