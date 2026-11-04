"""Exercise held-judge API inputs and the real CLI against a controlled classifier seam."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(checkout: Path, work: Path) -> dict[str, Any]:
    import quantfit
    from quantfit.bundle import _private_fields

    work.mkdir()
    spec = importlib.util.spec_from_file_location(
        "judge_observation_fixture", checkout / "tools/ci_calibration_judges.py"
    )
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    source = helper.fixture(work / "original", checkout, "a", native_report=True)
    before = {path: path.read_bytes() for path in source.values()}
    events = work / "events.jsonl"
    observed = work / "private.judge-observation.json"
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(checkout / "tools/ci_corpus_fixture"),
        "QUANTFIT_JUDGE_OBSERVATION_CI": str(events),
        "QUANTFIT_JUDGE_OBSERVATION_ORIGIN": str(Path(quantfit.__file__).resolve()),
        "HF_HUB_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    common = [arg for role in ("report", "capture", "key") for arg in (f"--{role}", str(source[role]))]
    cases: list[dict[str, Any]] = []

    def invoke(command: str, options: list[str], out: Path, code: int = 0) -> dict[str, Any]:
        child = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                "-m",
                "quantfit.cli",
                "calibrate",
                command,
                *common,
                *options,
                "--out",
                str(out),
                "--json",
            ],
            cwd=work,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=60,
            check=False,
        )
        index = len(cases)
        (work / f"cli-{index}.stdout").write_bytes(child.stdout)
        (work / f"cli-{index}.stderr").write_bytes(child.stderr)
        assert child.returncode == code and not child.stderr, "controlled CLI outcome differed; child logs retained"
        assert helper.MARKER.encode() not in child.stdout and str(work).encode() not in child.stdout
        envelope = json.loads(child.stdout)
        assert envelope["exit_code"] == code
        cases.append({"command": command, "exit_code": code})
        result: dict[str, Any] = envelope["result"] or {}
        if code == 0:
            assert envelope["command"] == f"calibrate {command}"
        return result

    receipt = invoke("observe-judge", [], observed)
    assert receipt["n_pairs"] == 8 and receipt["n_rows"] == 16 and "flags" not in receipt
    pin = hashlib.sha256(observed.read_bytes()).hexdigest()
    assert receipt["observation"] == {"sha256": pin, "size_bytes": observed.stat().st_size}
    options = ["--observation", str(observed), "--observation-sha256", pin]
    results = []
    for mode, label_args in (
        ("full", ["--sheet", str(source["sheet"])]),
        ("retained", ["--retained-labels", str(source["retained"]), "--retention-receipt", str(source["receipt"])]),
    ):
        out = work / f"comparison-{mode}.json"
        result = invoke("compare-observed-judge", [*options, *label_args], out)
        assert result == json.loads(out.read_bytes())
        _private_fields(result)
        assert result["n_pairs"] == 8 and result["n_rows_per_judge"] == 16
        assert result["truth_coverage"]["both_usable"] == 3
        assert result["per_arm"]["baseline"]["judge_a_by_judge_b"] == [[2, 2], [2, 2]]
        assert result["per_arm"]["baseline"]["error_a_by_error_b"] == [[1, 1], [2, 1]]
        assert result["per_arm"]["quantized"]["error_a_by_error_b"] == [[2, 1], [2, 0]]
        assert result["gate_eligible"] is result["scientific_go"] is False
        results.append(result)
    refusal = work / "no-output.json"
    invoke(
        "compare-observed-judge",
        [*options[:-1], "0" * 64, "--sheet", str(source["sheet"])],
        refusal,
        2,
    )
    assert not refusal.exists()
    invoke("observe-judge", [], source["key"], 2)
    assert all(path.read_bytes() == data for path, data in before.items())
    assert [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()] == [
        {"classifier_calls": 1, "rows": 16, "origin_matched": True}
    ]
    assert results[0]["native_per_judge"] == results[1]["native_per_judge"]
    return {
        "tool_version": quantfit.__version__,
        "real_os_cli": cases,
        "classifier_calls": 1,
        "package_origin_matched_parent": True,
        "rows_per_judge": 16,
        "n_pairs": 8,
        "truth_coverage": results[0]["truth_coverage"],
        "per_arm": results[0]["per_arm"],
        "native_per_judge": results[0]["native_per_judge"],
        "original_sources_preserved": True,
        "human_truth_authenticated": False,
        "scientific_go": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True, help="new private fixture directory")
    parser.add_argument("--record", type=Path, required=True, help="new counts-only aggregate JSON")
    args = parser.parse_args()
    if args.record.exists() or args.work.exists():
        parser.error("work and record must be fresh")
    checkout = Path(__file__).resolve().parents[1]
    sources = (
        "quantfit/cli.py",
        "quantfit/calibration_judges_cli.py",
        "quantfit/safety/calibration_judges.py",
        "quantfit/safety/verify.py",
        "quantfit/safety/calibrate.py",
        "quantfit/safety/calibration_strata.py",
        "quantfit/safety/calibration_inputs.py",
        "quantfit/safety/calibration_binding.py",
        "quantfit/safety/retained_labels.py",
        "quantfit/safety/retention_io.py",
        "quantfit/resolution.py",
        "quantfit/safety/adjudication.py",
        "quantfit/adjudication_record.py",
        "tools/ci_judge_observation.py",
        "tools/ci_calibration_judges.py",
        "tools/ci_corpus_fixture/sitecustomize.py",
        "tools/ci_installed.py",
        "tests/test_judge_observation.py",
        ".github/workflows/validate.yml",
        "validation/2026-10-18-screen-bundle/inputs/reports/clean.json",
    )
    hashes = {name: hashlib.sha256((checkout / name).read_bytes()).hexdigest() for name in sources}
    result = run(checkout, args.work.resolve())
    assert all(hashlib.sha256((checkout / name).read_bytes()).hexdigest() == sha for name, sha in hashes.items())
    from quantfit.bundle import _private_fields

    _private_fields(result)
    record = {
        "schema_version": 1,
        "profile": "source/editable with fictional inputs and controlled classifier",
        "source_raw_sha256": hashes,
        "result": result,
        "limits": [
            "No original or fresh model execution, corpus/network call, human truth, or scientific qualification.",
            "A controlled classifier supplied flags. Real CLI/report/capture/key/truth and comparison paths ran.",
            "Installed wheel/sdist and hosted qualification are separate.",
        ],
    }
    args.record.parent.mkdir(parents=True, exist_ok=True)
    with args.record.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(f"{len(result['real_os_cli'])} CLI cases; SHA256 {hashlib.sha256(args.record.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
