"""One packing for every reader of the calibration set (hermetic: fake datasets, no torch).

The probe's 4-bit spread on Qwen2.5-1.5B came from tokenizing rows one by one: a 9-token
heading weighed as much as a 437-token paragraph (validation/2026-10-01-probe-at-n64/).
Since 0.15.0 the probe packs blocks with the quantize path's own function. These tests pin
that both readers share one stream and that every block is the same length.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from quantfit.calibset import packed_blocks
from quantfit.spec import DEFAULT_SPEC, QuantSpec

# Rows as the fake dataset holds them; "" and None are dropped like the real filter drops them.
_ROWS = ["abcdefghij", "", "kl", None, "mnopqrstuvwxyz", "   ", "0123456789"]


class _FakeDS:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, keep):
        return _FakeDS(r for r in self.rows if keep({"text": r}))

    def shuffle(self, seed):
        # Deterministic and visibly not the identity, so a test can see the order was used.
        assert seed == DEFAULT_SPEC.seed
        return _FakeDS(reversed(self.rows))

    def __iter__(self):
        return iter({"text": r} for r in self.rows)


def _tokenizer(text):
    return SimpleNamespace(input_ids=[ord(c) for c in text])


@pytest.fixture
def fake_datasets(monkeypatch):
    calls: list[dict] = []

    def load_dataset(*args, **kwargs):
        calls.append(kwargs)
        return _FakeDS(_ROWS)

    module = types.ModuleType("datasets")
    module.load_dataset = load_dataset
    module.Dataset = SimpleNamespace(from_dict=lambda d: d)
    monkeypatch.setitem(sys.modules, "datasets", module)
    return calls


def _stream():
    """The token stream the fake set should produce: non-empty rows, shuffled, concatenated."""
    kept = [r for r in _ROWS if r is not None and r.strip() != ""]
    return [ord(c) for c in "".join(reversed(kept))]


def test_blocks_are_exactly_seqlen_and_follow_the_shuffled_stream(fake_datasets):
    blocks = packed_blocks(DEFAULT_SPEC, _tokenizer, n_blocks=3, seqlen=5)
    assert blocks == [_stream()[i : i + 5] for i in (0, 5, 10)]
    assert all(len(b) == 5 for b in blocks), "no ragged block, whatever the row lengths were"
    assert fake_datasets[0]["revision"] == DEFAULT_SPEC.calib_revision


def test_a_set_that_runs_out_yields_fewer_whole_blocks_never_a_ragged_one(fake_datasets):
    total = len(_stream())  # 36 tokens
    blocks = packed_blocks(DEFAULT_SPEC, _tokenizer, n_blocks=100, seqlen=10)
    assert len(blocks) == total // 10
    assert all(len(b) == 10 for b in blocks)


def test_the_probes_blocks_are_the_head_of_the_quantize_paths_stream(fake_datasets):
    """`probe.py` promises to "measure sensitivity on the same distribution the quantize
    path calibrates on". Before 0.15.0 it read rows one at a time while the quantize path
    packed them, so the promise did not hold. Now the probe's first k blocks, laid end to
    end, ARE the quantize path's first block when the lengths divide."""
    quantize = packed_blocks(DEFAULT_SPEC, _tokenizer, n_blocks=1, seqlen=12)
    probe = packed_blocks(DEFAULT_SPEC, _tokenizer, n_blocks=3, seqlen=4)
    assert [t for block in probe for t in block] == quantize[0]


def test_the_quantize_path_calibrates_on_packed_blocks(fake_datasets):
    from quantfit.backends.compressed_tensors import calib_dataset

    spec = QuantSpec(calib_samples=3, calib_seqlen=6)
    ds = calib_dataset(spec, _tokenizer)
    assert ds["input_ids"] == packed_blocks(spec, _tokenizer, 3, 6)
    assert ds["attention_mask"] == [[1] * 6] * 3


def test_the_quantize_path_refuses_a_short_set_rather_than_calibrating_on_less(fake_datasets):
    from quantfit.backends.compressed_tensors import calib_dataset

    with pytest.raises(RuntimeError, match="yielded 3 of 128 requested sequences of 10 tokens"):
        calib_dataset(QuantSpec(calib_samples=128, calib_seqlen=10), _tokenizer)


def test_the_probe_batch_is_the_packed_blocks_as_tensors(fake_datasets):
    torch = pytest.importorskip("torch")
    from quantfit.policy.probe import _probe_batch

    batch = _probe_batch(_tokenizer, n_samples=2, seqlen=7, device="cpu", token=None)
    assert [b["input_ids"].tolist() for b in batch] == [[blk] for blk in packed_blocks(DEFAULT_SPEC, _tokenizer, 2, 7)]
    assert all(b["attention_mask"].shape == (1, 7) and bool(b["attention_mask"].all()) for b in batch)
    assert all(b["input_ids"].dtype == torch.long for b in batch)
