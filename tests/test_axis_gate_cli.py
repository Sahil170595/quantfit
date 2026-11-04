"""Real saved-report OS CLI, JSON/JUnit and closed policy admission controls."""

import json
import os
import subprocess
import sys
from xml.etree import ElementTree as ET

import pytest
from test_axis_gate import saved_axis_report

from quantfit.gate import evaluate_report


def cli(*args):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1", HF_HUB_DISABLE_IMPLICIT_TOKEN="1")
    return subprocess.run(
        [sys.executable, "-B", "-X", "utf8", "-m", "quantfit.cli", "gate", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize(
    "counts,policy,code",
    [
        ({}, {"over-refusal": 0.30}, 0),
        ({"safe_flips": 1}, {"over-refusal": 0.30}, 3),
        ({"safe_refused": 28}, {"over-refusal": 0.30}, 4),
        ({}, {"refusal-robustness": 0.0001, "over-refusal": 0.30}, 5),
    ],
)
def test_os_cli_saved_json_junit_and_api_agree(tmp_path, counts, policy, code):
    source = saved_axis_report(tmp_path, **counts)
    before = source.read_bytes()
    out, xml = tmp_path / "gate.json", tmp_path / "junit.xml"
    argv = ["--from-report", str(source), "--out", str(out), "--junit", str(xml), "--json"]
    for name, value in policy.items():
        argv.extend(["--axis-threshold", f"{name}={value * 100}"])
    completed = cli(*argv)
    assert completed.returncode == code, completed.stdout + completed.stderr
    envelope = json.loads(completed.stdout)
    assert envelope["exit_code"] == code
    emitted = json.loads(out.read_bytes())
    for key, value in emitted.items():
        assert envelope["result"][key] == value
    expected = evaluate_report(str(source), axis_thresholds=policy, out_path=str(out))
    emitted.pop("created_utc")
    expected.pop("created_utc")
    assert emitted == expected
    assert source.read_bytes() == before
    root = ET.parse(xml)
    assert len(root.findall(".//testcase")) == (5 if len(policy) == 2 else 4)
    assert bool(root.findall(".//failure")) is (code != 0)


@pytest.mark.parametrize(
    "declared",
    [
        ["over-refusal=30", "over-refusal=15"],
        ["refusal_robustness=30"],
        ["late=30"],
        ["over-refusal=nan"],
        ["over-refusal=inf"],
        ["over-refusal=true"],
        ["over-refusal=0"],
        ["over-refusal=-1"],
        ["over-refusal=30.001"],
        ["over-refusal=30", "refusal-robustness=nan"],
    ],
)
def test_os_cli_invalid_complete_policy_precedes_file_read_and_preserves_outputs(tmp_path, declared):
    out, xml = tmp_path / "gate.json", tmp_path / "junit.xml"
    out.write_bytes(b"gate sentinel")
    xml.write_bytes(b"xml sentinel")
    args = ["--from-report", str(tmp_path / "absent.json"), "--out", str(out), "--junit", str(xml), "--json"]
    for entry in declared:
        args.extend(["--axis-threshold", entry])
    result = cli(*args)
    assert result.returncode == 2
    assert json.loads(result.stdout)["result"] is None
    assert "unreadable" not in result.stdout + result.stderr
    assert out.read_bytes() == b"gate sentinel" and xml.read_bytes() == b"xml sentinel"


@pytest.mark.parametrize("legacy", [["--threshold", "30"], ["--tier", "smoke"]])
def test_os_cli_mutual_exclusion_preserves_output(tmp_path, legacy):
    out = tmp_path / "gate.json"
    out.write_bytes(b"sentinel")
    result = cli(
        "--baseline", "base", "--quant", "quant", "--axis-threshold", "over-refusal=30", *legacy, "--out", str(out)
    )
    assert result.returncode == 2
    assert out.read_bytes() == b"sentinel"


def test_os_cli_junit_cannot_alias_source_or_gate(tmp_path):
    source = saved_axis_report(tmp_path)
    raw = source.read_bytes()
    for target in [source, tmp_path / "gate.json"]:
        result = cli(
            "--from-report",
            str(source),
            "--axis-threshold",
            "over-refusal=30",
            "--out",
            str(target),
            "--junit",
            str(target),
            "--json",
        )
        assert result.returncode == 2
    assert source.read_bytes() == raw
