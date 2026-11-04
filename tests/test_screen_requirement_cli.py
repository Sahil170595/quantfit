"""Existing screen-summary CLI emits distinct native and opt-in qualification exits."""

import contextlib
import io
import json
from xml.etree import ElementTree as ET

import pytest
from test_screen_requirement import inputs

from quantfit.cli import main


def invoke(paths, ceiling, *, json_output=True, extra=()):
    manifest, reports, calibrations = paths
    argv = [
        "screen-summary",
        "--targets",
        str(manifest),
        "--reports-dir",
        str(reports),
        "--calibrations-dir",
        str(calibrations),
        "--require-conditional-resolution",
        str(ceiling),
        *extra,
    ]
    if json_output:
        argv.append("--json")
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


@pytest.mark.parametrize("ceiling,expected", [(40, 0), (30, 5)])
def test_cli_json_artifact_junit_agree_on_same_native_analyses(tmp_path, ceiling, expected):
    paths = inputs(tmp_path)
    out, xml = tmp_path / "receiving.json", tmp_path / "receiving.xml"
    code, stdout, stderr = invoke(paths, ceiling, extra=["--out", str(out), "--junit", str(xml)])
    document = json.loads(stdout)
    assert code == expected == document["exit_code"] and not stderr
    assert document["result"] == json.loads(out.read_bytes())
    requirement = document["result"]["conditional_resolution_requirement"]
    assert requirement["native_exit_code"] == 0 and requirement["qualification_exit_code"] == code
    cases = ET.fromstring(xml.read_bytes()).findall(".//testcase")
    assert len(cases) == 4 and sum(case.find("failure") is not None for case in cases) == (3 if code else 0)


def test_human_headline_exposes_failed_requirement_before_native_no_detection(tmp_path):
    code, stdout, stderr = invoke(inputs(tmp_path), 30, json_output=False)
    assert code == 5 and not stderr
    assert stdout.index("30 pp — UNMET") < stdout.index("conditional_no_detection")
    assert "Qualification exit 5; native exit 0" in stdout and "resolution_exceeds_requirement" in stdout


def test_invalid_cli_requirement_is_categorical_two_without_publication(tmp_path):
    paths = inputs(tmp_path)
    out = tmp_path / "receiving.json"
    code, stdout, stderr = invoke(paths, "nan", extra=["--out", str(out)])
    document = json.loads(stdout)
    assert code == document["exit_code"] == 2 and document["result"] is None
    assert "PRIVATE" not in stdout + stderr and not out.exists()
