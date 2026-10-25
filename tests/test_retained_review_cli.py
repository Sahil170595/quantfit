"""Explicit retained-mode admission preserves default full-sheet parser contracts."""

import json

import pytest
from test_retained_review import retained_inputs

from quantfit.cli import main


def args_for(tmp_path):
    paths = retained_inputs(tmp_path)
    capture, key, a, ar, b, br = map(str, paths)
    return [
        "--input-mode",
        "retained",
        "--capture",
        capture,
        "--key",
        key,
        "--retained-labels-a",
        a,
        "--retention-receipt-a",
        ar,
        "--retained-labels-b",
        b,
        "--retention-receipt-b",
        br,
        "--sheet",
        str(tmp_path / "q.labels.csv"),
        "--receipt",
        str(tmp_path / "p.json"),
    ]


@pytest.mark.parametrize(
    "missing",
    ["--capture", "--retained-labels-a", "--retention-receipt-a", "--retained-labels-b", "--retention-receipt-b"],
)
def test_retained_mode_requires_every_actual_role(tmp_path, missing):
    args = args_for(tmp_path)
    i = args.index(missing)
    del args[i : i + 2]
    with pytest.raises(SystemExit) as exc:
        main(["calibrate", "review", "prepare", *args])
    assert exc.value.code == 2 and not (tmp_path / "q.labels.csv").exists()


def test_retained_mode_is_explicit_and_cannot_mix_full_sheet_arms(tmp_path):
    args = args_for(tmp_path)
    args[1] = "full-sheet"
    with pytest.raises(SystemExit) as exc:
        main(["calibrate", "review", "prepare", *args])
    assert exc.value.code == 2
    args[1] = "retained"
    args[args.index("--retained-labels-a")] = "--sheet-a"
    with pytest.raises(SystemExit) as exc:
        main(["calibrate", "review", "prepare", *args])
    assert exc.value.code == 2


def test_invalid_retained_cli_has_categorical_private_error(tmp_path, capsys):
    args = args_for(tmp_path)
    args[args.index("--capture") + 1] = str(tmp_path / "PRIVATE_missing.capture.jsonl")
    assert main(["calibrate", "review", "prepare", *args, "--json"]) == 2
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["error"]["message"] == "invalid_retained_label_review"
    assert "PRIVATE" not in output.out + output.err and str(tmp_path) not in output.out + output.err
