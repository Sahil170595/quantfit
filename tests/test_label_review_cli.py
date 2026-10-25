"""Nested review leaves use the native JSON/error contract without private-path output."""

import json

import pytest
from test_label_review import ROOT, fill_fixture_review, fixture, prepared

from quantfit.cli import main


def test_actual_nested_prepare_and_apply_json_are_aggregate_only(tmp_path, capsys):
    a, b, key = fixture(tmp_path / "private", ROOT)
    queue, preparation = tmp_path / "private.review.labels.csv", tmp_path / "preparation.json"
    common = ["--sheet-a", str(a), "--sheet-b", str(b), "--key", str(key)]
    assert (
        main(
            ["calibrate", "review", "prepare", *common, "--sheet", str(queue), "--receipt", str(preparation), "--json"]
        )
        == 0
    )
    first = capsys.readouterr()
    document = json.loads(first.out)
    assert document["command"] == "calibrate review prepare" and document["result"]["n_selected"] == 12
    assert document["result"] == json.loads(preparation.read_bytes()) and not first.err
    fill_fixture_review(queue, key)
    out, receipt = tmp_path / "reviewed.labels.csv", tmp_path / "application.json"
    assert (
        main(
            [
                "calibrate",
                "review",
                "apply",
                *common,
                "--review",
                str(queue),
                "--preparation",
                str(preparation),
                "--out",
                str(out),
                "--receipt",
                str(receipt),
                "--json",
            ]
        )
        == 0
    )
    second = capsys.readouterr()
    document = json.loads(second.out)
    assert document["command"] == "calibrate review apply" and document["result"]["n_changed_vs_a"] == 10
    assert document["result"] == json.loads(receipt.read_bytes()) and not second.err
    private = json.loads(key.read_bytes())
    for value in ("PRIVATE", str(tmp_path), private["salt"], *private["ids"]):
        assert value not in first.out + first.err + second.out + second.err


def test_apply_json_keeps_existing_top_level_error_command_and_categorical_message(tmp_path, capsys):
    paths, _ = prepared(tmp_path)
    a, b, key, queue, preparation = paths
    assert (
        main(
            [
                "calibrate",
                "review",
                "apply",
                "--sheet-a",
                str(a),
                "--sheet-b",
                str(b),
                "--key",
                str(key),
                "--review",
                str(queue),
                "--preparation",
                str(preparation),
                "--out",
                str(tmp_path / "out.labels.csv"),
                "--receipt",
                str(tmp_path / "application.json"),
                "--json",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    document = json.loads(output.out)
    assert document["command"] == "calibrate" and document["exit_code"] == 2 and document["result"] is None
    assert document["error"]["message"] == "invalid_label_review"
    assert "PRIVATE" not in output.out + output.err and str(tmp_path) not in output.out + output.err


@pytest.mark.parametrize("args", [[], ["--json"], ["prepare", "--json"], ["apply", "--json"]])
def test_nested_usage_requires_complete_leaf_arguments(args):
    with pytest.raises(SystemExit) as error:
        main(["calibrate", "review", *args])
    assert error.value.code == 2
