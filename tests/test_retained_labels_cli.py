"""New retained mode emits aggregates only; legacy sheet mode stays distinct."""

import json

import pytest
from test_retained_labels import setup

from quantfit.cli import main


def test_real_extract_then_ingest_cli_never_reflects_private_paths_or_rows(tmp_path, capsys):
    sheet, key, labels, receipt, out = setup(tmp_path)
    raw_key = json.loads(key.read_bytes())
    assert (
        main(
            [
                "calibrate",
                "extract",
                "--sheet",
                str(sheet),
                "--key",
                str(key),
                "--out",
                str(labels),
                "--receipt",
                str(receipt),
                "--json",
            ]
        )
        == 0
    )
    first = capsys.readouterr()
    assert json.loads(first.out)["command"] == "calibrate extract" and not first.err
    sheet.unlink()
    assert (
        main(
            [
                "calibrate",
                "ingest",
                "--retained-labels",
                str(labels),
                "--retention-receipt",
                str(receipt),
                "--key",
                str(key),
                "--out",
                str(out),
                "--json",
            ]
        )
        == 0
    )
    second = capsys.readouterr()
    document = json.loads(second.out)
    assert document["result"]["calibration_schema"] == 3 and "report_path" not in document["result"]
    rendered = first.out + first.err + second.out + second.err
    assert all(str(path) not in rendered for path in (sheet, key, labels, receipt, out))
    assert raw_key["salt"] not in rendered and all(row_id not in rendered for row_id in raw_key["ids"])


def test_retained_cli_categorical_error_suppresses_private_native_values(tmp_path, capsys):
    sheet, key, labels, receipt, _out = setup(tmp_path)
    sheet.write_bytes(b"id,completion,human_label\nPRIVATE_ROW,PRIVATE_TEXT,PRIVATE_LABEL\n")
    assert (
        main(
            [
                "calibrate",
                "extract",
                "--sheet",
                str(sheet),
                "--key",
                str(key),
                "--out",
                str(labels),
                "--receipt",
                str(receipt),
                "--json",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert "PRIVATE" not in captured.out + captured.err
    assert str(sheet) not in captured.out + captured.err
    assert json.loads(captured.out)["error"]["message"] == "invalid_retained_labels"


@pytest.mark.parametrize(
    "args",
    [
        ["--retained-labels", "x"],
        ["--retained-labels", "x", "--sheet", "y", "--retention-receipt", "r"],
        ["--sheet", "x", "--retention-receipt", "r"],
    ],
)
def test_modes_and_receipt_required_with_native_usage_exit2(args):
    with pytest.raises(SystemExit) as error:
        main(["calibrate", "ingest", *args, "--key", "k", "--out", "o"])
    assert error.value.code == 2


def test_retained_cli_summary_does_not_echo_private_declared_model_paths(tmp_path, capsys):
    from quantfit.safety.calibration_binding import identity_fingerprint

    sheet, key, labels, receipt, out = setup(tmp_path)
    payload = json.loads(key.read_bytes())
    model = "C:/PRIVATE_DECLARED_MODEL_PATH/model"
    payload["binding"]["identity"]["baseline"]["model"] = model
    payload["capture"]["baseline"] = model
    payload["binding"]["fingerprint"] = identity_fingerprint(payload["binding"]["identity"])
    key.write_bytes((json.dumps(payload) + "\n").encode())
    assert (
        main(
            [
                "calibrate",
                "extract",
                "--sheet",
                str(sheet),
                "--key",
                str(key),
                "--out",
                str(labels),
                "--receipt",
                str(receipt),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "calibrate",
                "ingest",
                "--retained-labels",
                str(labels),
                "--retention-receipt",
                str(receipt),
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
    assert model not in captured.out + captured.err
    assert "binding" not in json.loads(captured.out)["result"]
    # The native artifact must retain exact declared scope for later matching.
    assert json.loads(out.read_bytes())["binding"]["identity"]["baseline"]["model"] == model
