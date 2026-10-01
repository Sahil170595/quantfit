"""The calibration set is loaded at a pinned commit, never at `main` (hermetic).

Until 0.14.2 both readers of the calibration set — the quantize path and `probe` — called
`load_dataset` with no revision, so a push to the dataset's `main` would have changed every
quant and every probe number silently (validation/2026-10-01-probe-at-n64/). A fake
`datasets` module records the call and stops it: no network, no dataset, no torch.
"""

from __future__ import annotations

import re
import sys
import types

import pytest

from quantfit.spec import DEFAULT_SPEC


class _Stop(Exception):
    pass


@pytest.fixture
def calls(monkeypatch):
    seen: list[dict] = []

    def load_dataset(*args, **kwargs):
        seen.append({"args": args, **kwargs})
        raise _Stop

    fake = types.ModuleType("datasets")
    fake.load_dataset = load_dataset
    fake.Dataset = object
    monkeypatch.setitem(sys.modules, "datasets", fake)
    return seen


def test_the_pin_is_a_full_commit_sha():
    # A branch or tag name would move; only a 40-hex commit is a pin.
    assert re.fullmatch(r"[0-9a-f]{40}", DEFAULT_SPEC.calib_revision)


def test_the_probe_loads_the_calibration_set_at_the_pin(calls):
    from quantfit.policy.probe import _probe_batch

    with pytest.raises(_Stop):
        _probe_batch(tokenizer=None, n_samples=8, seqlen=512, device="cpu", token=None)
    (call,) = calls
    assert call["revision"] == DEFAULT_SPEC.calib_revision
    assert call["args"] == (DEFAULT_SPEC.calib_dataset, DEFAULT_SPEC.calib_config)
    assert call["split"] == DEFAULT_SPEC.calib_split


def test_the_quantize_path_loads_the_calibration_set_at_the_pin(calls):
    from quantfit.backends.compressed_tensors import calib_dataset

    with pytest.raises(_Stop):
        calib_dataset(DEFAULT_SPEC, tokenizer=None)
    (call,) = calls
    assert call["revision"] == DEFAULT_SPEC.calib_revision
    assert call["args"] == (DEFAULT_SPEC.calib_dataset, DEFAULT_SPEC.calib_config)
