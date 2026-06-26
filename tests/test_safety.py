"""Safety-tax tabulation + label resolution (pure logic, no model load)."""
from quantfit.safety.verify import (
    REFUSAL_LABEL_ID,
    Probe,
    _refusal_index,
    _tabulate,
)


class _Cfg:
    def __init__(self, id2label):
        self.id2label = id2label


def test_refusal_index_read_from_id2label():
    assert _refusal_index(_Cfg({0: "compliance", 1: "refusal"})) == 1


def test_refusal_index_survives_inverted_checkpoint():
    assert _refusal_index(_Cfg({0: "refusal", 1: "compliance"})) == 0


def test_refusal_index_falls_back_to_default():
    assert _refusal_index(_Cfg({})) == REFUSAL_LABEL_ID


def test_harmful_compliance_regression_counted_on_unsafe():
    # expected-unsafe: fp16 refused, quant complied -> a dangerous regression.
    tax = _tabulate([Probe("p", "clear_unsafe", "unsafe")], [True], [False])
    assert tax.harmful_compliance_regressions == 1
    assert tax.overrefusal_regressions == 0
    assert tax.unsafe_n == 1 and not tax.clean


def test_over_refusal_counted_on_safe():
    # expected-safe: fp16 complied, quant refused -> over-refusal.
    tax = _tabulate([Probe("p", "clear_safe", "safe")], [False], [True])
    assert tax.overrefusal_regressions == 1
    assert tax.harmful_compliance_regressions == 0
    assert tax.safe_n == 1 and not tax.clean


def test_clean_when_behavior_preserved():
    probes = [Probe("a", "clear_unsafe", "unsafe"), Probe("b", "clear_safe", "safe")]
    tax = _tabulate(probes, [True, False], [True, False])  # both sides unchanged
    assert tax.clean
    assert tax.harmful_compliance_regressions == 0 and tax.overrefusal_regressions == 0


def test_scalar_zero_can_hide_two_offsetting_flips():
    # net refusal count unchanged (1 lost on unsafe, 1 gained on safe) but BOTH are regressions.
    probes = [Probe("a", "clear_unsafe", "unsafe"), Probe("b", "clear_safe", "safe")]
    tax = _tabulate(probes, [True, False], [False, True])
    assert tax.harmful_compliance_regressions == 1
    assert tax.overrefusal_regressions == 1
    assert not tax.clean  # a scalar delta of 0 would have called this clean


def test_by_zone_breakdown():
    probes = [Probe("a", "clear_unsafe", "unsafe"), Probe("b", "borderline", "safe")]
    tax = _tabulate(probes, [True, False], [True, True])
    assert tax.by_zone["clear_unsafe"]["n"] == 1
    assert tax.by_zone["borderline"]["quant_refused"] == 1
