"""Strata CLI never exposes private paths, rows or declared model identity."""

import json

import pytest
from test_calibration_strata import ROOT, fixture_module

from quantfit.cli import main


def test_actual_strata_cli_emits_fixed_aggregates_without_private_rows_or_paths(tmp_path, capsys):
    capture, sheet, key = fixture_module.fixture(tmp_path / "private", ROOT)
    out = tmp_path / "strata.json"
    assert (
        main(
            [
                "calibrate",
                "strata",
                "--capture",
                str(capture),
                "--sheet",
                str(sheet),
                "--key",
                str(key),
                "--out",
                str(out),
                "--json",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    assert document["command"] == "calibrate strata" and document["exit_code"] == 0
    assert document["result"]["observed_at_risk"]["dangerous"]["n_pairs_selected"] == 2
    assert document["result"] == json.loads(out.read_bytes())
    assert not captured.err
    for value in (
        fixture_module.MARKER,
        *(str(p) for p in (capture, sheet, key, out)),
        json.loads(key.read_bytes())["salt"],
    ):
        assert value not in captured.out


def test_strata_cli_error_is_categorical_even_for_private_parser_values(tmp_path, capsys):
    capture, sheet, key = fixture_module.fixture(tmp_path / "private", ROOT)
    sheet.write_bytes(b"PRIVATE_MALFORMED_SHEET")
    assert (
        main(
            [
                "calibrate",
                "strata",
                "--capture",
                str(capture),
                "--sheet",
                str(sheet),
                "--key",
                str(key),
                "--out",
                str(tmp_path / "x"),
                "--json",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert "PRIVATE" not in captured.out + captured.err and str(tmp_path) not in captured.out + captured.err
    assert json.loads(captured.out)["error"]["message"] == "invalid_calibration_strata"


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--retained-labels", "x"],
        ["--sheet", "x", "--retention-receipt", "r"],
        ["--sheet", "x", "--retained-labels", "y", "--retention-receipt", "r"],
    ],
)
def test_strata_label_modes_keep_native_usage_refusals(args):
    with pytest.raises(SystemExit) as error:
        main(["calibrate", "strata", "--capture", "c", "--key", "k", "--out", "o", *args])
    assert error.value.code == 2
