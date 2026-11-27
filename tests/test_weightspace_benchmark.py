import copy

import pytest

from quantfit.weightspace import WeightspaceError, benchmark_heads
from tools.ci_weightspace_benchmark import check, fixture


def test_matched_budgets_and_row_tallies():
    record = check()
    assert len(record["trials"]) == 6 and record["target_logit_rows_materialized"] == 32
    for trial in record["trials"]:
        b = trial["budget"]
        a = trial["arms"]
        assert a["output_only_matched"]["archive_logit_queries"] == record["archive_cases"]
        assert a["output_only_target"]["archive_cases_used"] == 0
        assert a["compiled"]["target_logit_queries"] == a["labeled_student"]["target_logit_queries"] == 0
        assert a["output_only_matched"]["target_logit_queries"] == a["compiled_adapted"]["target_logit_queries"] == b
        assert a["labeled_student"]["target_gold_labels"] == b
        assert all(row["cases"] == row["ties"] + row["reference_losses"] + row["reference_wins"] for row in a.values())


def test_no_target_queries_at_zero_and_no_holdout_training():
    spec = fixture() | {"budgets": [0]}
    before = benchmark_heads(spec)
    assert before["target_logit_rows_materialized"] == 0
    if_change = copy.deepcopy(spec)
    if_change["queries"]["donor"] = [[999, 333, -24] for _ in if_change["queries"]["ids"]]
    assert benchmark_heads(if_change) == before
    first, second = [], []
    benchmark_heads(spec, observe=first.append)
    if_change["held_out"]["labels"] = [1 - i for i in if_change["held_out"]["labels"]]
    benchmark_heads(if_change, observe=second.append)
    assert [v["predictions"] for v in first] == [v["predictions"] for v in second]


def test_partition_leakage_and_invalid_controls():
    spec = fixture()
    spec["queries"]["ids"][0] = spec["archive"]["ids"][0]
    with pytest.raises(WeightspaceError, match="disjoint"):
        benchmark_heads(spec)
    for invalid in [
        {"budgets": [33]},
        {"budgets": [True]},
        {"labels": []},
        {"seeds": []},
        {"wrong_donor_weight": fixture()["donor_weight"], "wrong_donor_bias": fixture()["donor_bias"]},
    ]:
        with pytest.raises(WeightspaceError):
            benchmark_heads(fixture() | invalid)
