"""Footprint estimation from Hub metadata — weight-file selection, no network."""

import pytest

import quantfit.gpufit as g

_GIB = 1024**3


class _Sibling:
    def __init__(self, rfilename, size):
        self.rfilename = rfilename
        self.size = size


def _stub_hub(monkeypatch, siblings):
    class _Info:
        pass

    info = _Info()
    info.siblings = siblings

    class _Api:
        def model_info(self, model_id, files_metadata=True, token=None):
            return info

    monkeypatch.setattr(g, "HfApi", _Api)


def test_sums_safetensors_shards(monkeypatch):
    _stub_hub(
        monkeypatch,
        [
            _Sibling("model-00001-of-00002.safetensors", 2 * _GIB),
            _Sibling("model-00002-of-00002.safetensors", 1 * _GIB),
            _Sibling("tokenizer.json", 4096),  # non-weight files never counted
        ],
    )
    assert g.estimate_fp16_bytes("m") == 3 * _GIB


def test_falls_back_to_bin_when_no_safetensors(monkeypatch):
    _stub_hub(monkeypatch, [_Sibling("pytorch_model.bin", 5 * _GIB)])
    assert g.estimate_fp16_bytes("m") == 5 * _GIB


def test_never_sums_both_formats(monkeypatch):
    # Repos shipping both formats must not double-count: safetensors wins.
    _stub_hub(
        monkeypatch,
        [_Sibling("model.safetensors", 3 * _GIB), _Sibling("pytorch_model.bin", 3 * _GIB)],
    )
    assert g.estimate_fp16_bytes("m") == 3 * _GIB


def test_unsized_files_are_skipped(monkeypatch):
    # Hub metadata can return size=None; those entries carry no information.
    _stub_hub(
        monkeypatch,
        [_Sibling("model-00001.safetensors", None), _Sibling("model-00002.safetensors", 2 * _GIB)],
    )
    assert g.estimate_fp16_bytes("m") == 2 * _GIB


def test_no_weight_files_is_clean_operational_error(monkeypatch):
    # A GGUF-only or gated repo must exit 2 via the CLI's RuntimeError handler,
    # never a raw traceback (the documented error taxonomy).
    _stub_hub(monkeypatch, [_Sibling("model.Q4_K_M.gguf", 1 * _GIB)])
    with pytest.raises(RuntimeError, match="no weight-file sizes"):
        g.estimate_fp16_bytes("m")
