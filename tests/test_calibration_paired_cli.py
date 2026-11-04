"""Actual paired CLI keeps aggregate output separate from private label material."""

import json

import pytest
from test_calibration_paired import CHECKOUT, fixture

from quantfit.cli import main


def test_actual_paired_cli_json_and_human_output_do_not_reflect_private_paths(tmp_path, capsys):
    capture, sheet, key = fixture(tmp_path / "private", CHECKOUT)
    out = tmp_path / "paired.json"
    args = ["calibrate", "paired", "--capture", str(capture), "--sheet", str(sheet), "--key", str(key)]
    assert main([*args, "--out", str(out), "--json"]) == 0
    emitted = capsys.readouterr()
    value = json.loads(emitted.out)
    assert value["command"] == "calibrate paired" and value["exit_code"] == 0
    assert value["result"] == json.loads(out.read_bytes())
    assert value["result"]["coverage"]["n_pairs_both_usable"] == 21 and not emitted.err
    assert main([*args, "--out", str(tmp_path / "human.json")]) == 0
    human = capsys.readouterr()
    private = json.loads(key.read_bytes())
    for canary in ("PRIVATE_PAIRED", str(tmp_path), private["salt"], *private["ids"]):
        assert canary not in emitted.out + emitted.err + human.out + human.err


def test_paired_cli_errors_are_categorical(tmp_path, capsys):
    capture, sheet, key = fixture(tmp_path / "private", CHECKOUT)
    sheet.write_bytes(b"PRIVATE_MALFORMED_LABEL")
    assert (
        main(
            [
                "calibrate",
                "paired",
                "--capture",
                str(capture),
                "--sheet",
                str(sheet),
                "--key",
                str(key),
                "--out",
                str(tmp_path / "out"),
                "--json",
            ]
        )
        == 2
    )
    output = capsys.readouterr()
    assert json.loads(output.out)["error"]["message"] == "invalid_calibration_paired"
    assert str(tmp_path) not in output.out + output.err and "PRIVATE" not in output.out + output.err


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--retained-labels", "x"],
        ["--sheet", "x", "--retention-receipt", "r"],
        ["--sheet", "x", "--retained-labels", "y", "--retention-receipt", "r"],
    ],
)
def test_paired_usage_refuses_inconsistent_label_modes(args):
    with pytest.raises(SystemExit) as error:
        main(["calibrate", "paired", "--capture", "c", "--key", "k", "--out", "o", *args])
    assert error.value.code == 2
