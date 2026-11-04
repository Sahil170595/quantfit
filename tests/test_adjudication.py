"""Explicit manufactured judgments bind a whole native capture/report, not human truth."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
from tools.ci_adjudication import filled
from tools.ci_adjudication import fixture as native_fixture


def fixture(root, mode="mixed"):
    return native_fixture(root, ROOT, mode)


def prepared(tmp_path, mode="mixed"):
    from quantfit.safety.adjudication import prepare_adjudication

    report, capture = fixture(tmp_path / "private", mode)
    queue, receipt = tmp_path / "private.adjudication.csv", tmp_path / "private.adjudication-preparation.json"
    value = prepare_adjudication(str(report), str(capture), review_path=str(queue), receipt_path=str(receipt))
    return report, capture, queue, receipt, value


@pytest.mark.parametrize("mode,flags", [("mixed", 8), ("all", 8), ("zero", 0), ("repeated", 8)])
def test_complete_native_prepare_fill_apply_and_actual_modelcard_consumer(tmp_path, mode, flags):
    from quantfit.modelcard import model_card_fragment
    from quantfit.safety.adjudication import apply_adjudication

    report, capture, queue, preparation, receipt = prepared(tmp_path, mode)
    assert receipt["n_selected"] == flags
    originals = [p.read_bytes() for p in (report, capture, preparation)]
    original = model_card_fragment(str(report))
    filled(queue)
    out = tmp_path / "adjudication.json"
    record = apply_adjudication(str(report), str(capture), str(queue), str(preparation), out_path=str(out))
    assert record == json.loads(out.read_bytes()) and len(record["entries"]) == flags
    assert all(
        sum(row[k] for k in ("substantive", "degenerate", "not_confirmed", "unresolved")) == row["flagged"]
        for row in record["counts"].values()
    )
    if flags:
        assert all(
            row == {"flagged": 4, "substantive": 1, "degenerate": 1, "not_confirmed": 1, "unresolved": 1}
            for row in record["counts"].values()
        )
    text = json.dumps(record)
    assert "PRIVATE_" not in text and str(tmp_path) not in text
    md = model_card_fragment(str(report), adjudication_record=str(out))
    assert "### Operator-declared adjudication" in md and "human_confirmation_verified=false" in md
    assert original.split("\n---\n")[0] in md and md.split("\n---\n")[1] == original.split("\n---\n")[1]
    assert [p.read_bytes() for p in (report, capture, preparation)] == originals
    assert model_card_fragment(str(report), adjudication_record=str(out)) == md
