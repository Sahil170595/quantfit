"""Safety-verify label resolution + delta semantics (no model load)."""
from quantfit.safety.verify import REFUSAL_LABEL_ID, SafetyDelta, _refusal_index


class _Cfg:
    def __init__(self, id2label):
        self.id2label = id2label


def test_refusal_index_read_from_id2label():
    assert _refusal_index(_Cfg({0: "compliance", 1: "refusal"})) == 1


def test_refusal_index_survives_inverted_checkpoint():
    # A relabeled checkpoint must not silently invert the refusal count.
    assert _refusal_index(_Cfg({0: "refusal", 1: "compliance"})) == 0


def test_refusal_index_falls_back_to_default():
    assert _refusal_index(_Cfg({})) == REFUSAL_LABEL_ID


def test_delta_negative_is_regression():
    d = SafetyDelta(n=40, fp16_refusals=30, quant_refusals=28, delta_refusal=-2, flipped=["x", "y"])
    assert d.delta_refusal < 0 and len(d.flipped) == 2
