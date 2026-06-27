"""Method/scheme catalog validation."""

import pytest

from quantfit.registry import METHODS, UnsupportedCombo, catalog, resolve


def test_defaults_resolve():
    m, s = resolve("awq", None)
    assert m.name == "awq" and s == "W4A16_ASYM" and m.needs_calibration
    m, s = resolve("fp8", None)
    assert s == "FP8_DYNAMIC" and not m.needs_calibration


def test_unknown_method_rejected():
    with pytest.raises(UnsupportedCombo):
        resolve("nope", None)


def test_unknown_scheme_rejected():
    with pytest.raises(UnsupportedCombo):
        resolve("awq", "W3A11")


def test_weight_only_method_rejects_float_scheme():
    with pytest.raises(UnsupportedCombo):
        resolve("gptq", "FP8_DYNAMIC")


def test_smoothquant_requires_activation_scheme():
    with pytest.raises(UnsupportedCombo):
        resolve("smoothquant", "W4A16")
    _, s = resolve("smoothquant", "W8A8")
    assert s == "W8A8"


def test_gguf_resolves_to_qtype():
    m, s = resolve("gguf", None)
    assert m.backend == "gguf" and s == "Q4_K_M"
    _, s = resolve("gguf", "Q6_K")
    assert s == "Q6_K"


def test_gguf_rejects_compressed_tensors_scheme():
    with pytest.raises(UnsupportedCombo):
        resolve("gguf", "W4A16")


def test_catalog_lists_every_method():
    c = catalog()
    for name in METHODS:
        assert name in c
