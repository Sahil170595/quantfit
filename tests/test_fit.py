"""Capacity logic — gpu / offload / refuse with cache-aware disk, no hardware."""

import quantfit.fit as f
from quantfit.fit import LIMIT_DISK, LIMIT_MACHINE, MODE_GPU, MODE_OFFLOAD, MODE_REFUSE, capacity_plan

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
    assert capacity_plan("m").mode == MODE_GPU


def test_offload_when_too_big_for_vram_but_ram_ok(monkeypatch):
    _patch(monkeypatch, 14 * _GIB, 11 * _GIB, 32 * _GIB, 100 * _GIB)  # ~7B, ample disk
    p = capacity_plan("m")
    assert p.mode == MODE_OFFLOAD and p.fits


def test_refuse_when_ram_too_small_even_if_vram_fits(monkeypatch):
    # Weights load CPU-first (sequential onloading), so RAM gates even models that
    # fit VRAM: 40GB model, 80GB VRAM, 8GB RAM must refuse — not OOM mid-load.
    _patch(monkeypatch, 40 * _GIB, 80 * _GIB, 8 * _GIB, 500 * _GIB)
    p = capacity_plan("m")
    assert p.mode == MODE_REFUSE and p.limit == LIMIT_MACHINE
    assert "RAM" in p.reason()


def test_refuse_machine_when_too_big_even_for_ram(monkeypatch):
    _patch(monkeypatch, 140 * _GIB, 11 * _GIB, 32 * _GIB, 500 * _GIB, cached=140 * _GIB)
    p = capacity_plan("m")
    assert p.mode == MODE_REFUSE and p.limit == LIMIT_MACHINE and not p.fits


def test_refuse_disk_when_no_room_to_download(monkeypatch):
    _patch(monkeypatch, 14 * _GIB, 11 * _GIB, 32 * _GIB, 5 * _GIB)  # 7B, 5GB disk
    p = capacity_plan("m")
    assert p.mode == MODE_REFUSE and p.limit == LIMIT_DISK


def test_the_printed_amount_carries_the_unit_it_was_computed_in(monkeypatch):
    """`reason()` divided by 1024**3 and printed "GB" until 0.13.x, so a disk of 13,522,411,520
    bytes read "12.6 GB free" - 7.4% short of 13.52 GB in the unit it named (validation-matrix
    section 5, defect 3). Pinned with the exact bytes from that finding, on every branch."""
    disk = 13_522_411_520
    _patch(monkeypatch, 14 * _GIB, 11 * _GIB, 32 * _GIB, disk)  # the disk refusal that found it
    reason = capacity_plan("m").reason()
    assert "12.6 GiB is free" in reason, reason
    assert " GB" not in reason, "a 1024-based figure must not be labelled GB"

    for args in (
        (3 * _GIB, 11 * _GIB, 32 * _GIB, 100 * _GIB),  # gpu
        (14 * _GIB, 11 * _GIB, 32 * _GIB, 100 * _GIB),  # offload
        (40 * _GIB, 80 * _GIB, 8 * _GIB, 500 * _GIB),  # RAM refusal
    ):
        _patch(monkeypatch, *args)
        text = capacity_plan("m").reason()
        assert " GB" not in text and "GiB" in text, text


def test_cache_flips_disk_refuse_to_offload(monkeypatch):
    # Same tiny disk, but the weights are already cached -> only output space needed.
    _patch(monkeypatch, 14 * _GIB, 11 * _GIB, 32 * _GIB, 10 * _GIB, cached=14 * _GIB)
    assert capacity_plan("m").mode == MODE_OFFLOAD
