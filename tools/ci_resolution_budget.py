"""Native CLI/API finite-grid functional checks; no future evidence or sampling campaign."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from typing import Any


def _sources(checkout: Path, root: Path) -> tuple[Path, Path]:
    # Existing committed fictional reports plus existing native calibration
    # fixture generator; no model, report scope rebinding or human labels.
    spec = importlib.util.spec_from_file_location("private_budget_fixture", checkout / "tools/ci_screen_resolution.py")
    assert spec is not None and spec.loader is not None
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    _, reports = helper.original_inputs(checkout)
    raw = reports[min(reports)]
    report, calibration = root / "report.json", root / "calibration.json"
    report.write_bytes(raw)
    calibration.write_bytes(helper.calibration_bytes(raw))
    return report, calibration


def run(checkout: Path, root: Path) -> dict[str, Any]:
    from quantfit.cli import main
    from quantfit.resolution import analyze_resolution
    from quantfit.resolution_budget import ResolutionBudget

    report, calibration = _sources(checkout, root)
    before = (report.read_bytes(), calibration.read_bytes())
    native = analyze_resolution(str(report), str(calibration))
    records = {}
    for interface in ("cli", "api"):
        target = root / f"{interface}.json"
        if interface == "cli":
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(
                    [
                        "resolution",
                        "--report",
                        str(report),
                        "--calibration-report",
                        str(calibration),
                        "--plan-n-min",
                        "0",
                        "--plan-n-max",
                        "128",
                        "--plan-mde-pp",
                        "100",
                        "--plan-effect",
                        "30",
                        "--out",
                        str(target),
                        "--json",
                    ]
                )
            assert code == 0 and not stderr.getvalue()
            result = json.loads(stdout.getvalue())["result"]
            assert result == json.loads(target.read_bytes())
        else:
            result = analyze_resolution(
                str(report), str(calibration), str(target), planning=ResolutionBudget(0, 128, 100.0, (30.0,))
            )
        assert result["axes"] == native["axes"] and result["inputs"] == native["inputs"]
        assert result["binding_fingerprint"] == native["binding_fingerprint"] and "verdict" not in result
        plan = result["planning"]
        assert len(plan["curve"]) == 129 and plan["first_passing_n"] is not None
        assert plan["stable_suffix"] is not None and plan["stable_suffix"]["n_max"] == 128
        assert all(not row["passes"] for row in plan["curve"] if not row["detectable_at_target_power"])
        assert plan["work_admission"]["total_upper_bound"] <= plan["work_admission"]["limit"]
        records[interface] = {
            "planning": {key: value for key, value in plan.items() if key != "curve"},
            "curve_sha256": hashlib.sha256(
                json.dumps(plan["curve"], sort_keys=True, allow_nan=False).encode()
            ).hexdigest(),
            "curve_point_count": len(plan["curve"]),
            "actual_axes": result["axes"],
            "inputs": result["inputs"],
            "binding_fingerprint": result["binding_fingerprint"],
            "actual_analysis_preserved": True,
            "exit_code": 0,
        }
    empty = analyze_resolution(str(report), str(calibration), planning=ResolutionBudget(0, 0, 100.0))
    assert empty["planning"]["no_feasible_point"] is True
    assert empty["planning"]["first_passing_n"] is None and empty["planning"]["stable_suffix"] is None
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        empty_code = main(
            [
                "resolution",
                "--report",
                str(report),
                "--calibration-report",
                str(calibration),
                "--plan-n-min",
                "0",
                "--plan-n-max",
                "0",
                "--plan-mde-pp",
                "100",
                "--out",
                str(root / "empty-cli.json"),
                "--json",
            ]
        )
    assert (
        empty_code == 0
        and not stderr.getvalue()
        and json.loads(stdout.getvalue())["result"]["planning"]["no_feasible_point"]
    )
    assert (report.read_bytes(), calibration.read_bytes()) == before
    return {
        "kind": "quantfit.resolution-budget-functional-acceptance",
        "synthetic_calibration": True,
        "interfaces": records,
        "no_feasible_grid_analysis_completed": True,
        "actual_inputs_unchanged": True,
        "future_evidence_collected": False,
        "human_labels_authenticated": False,
        "scientific_go": False,
    }


def main() -> None:
    import argparse
    import tempfile

    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="quantfit-resolution-budget-") as name:
        result = run(args.checkout.resolve(), Path(name))
    raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out is None:
        print(raw, end="")
    else:
        with args.out.open("x", encoding="utf-8") as stream:
            stream.write(raw)


if __name__ == "__main__":
    main()
