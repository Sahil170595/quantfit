"""Actual native CLI/API/JSON/JUnit sensitivity; manufactured aggregate choices only."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree as ET


def _fixture(checkout: Path, root: Path, scenario: str) -> tuple[Path, Path, dict[str, str | None]]:
    from quantfit.safety.calibrate import _arm_block

    spec = importlib.util.spec_from_file_location("private_choice_fixture", checkout / "tools/ci_screen_requirement.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    manifest, reports, first = cast(
        tuple[Path, Path, Path],
        helper.fixture(
            checkout, root, population=2, flagged=scenario == "native_flags", unmeasured=scenario == "native_incomplete"
        ),
    )
    second = root / "second"
    second.mkdir()
    for source in first.iterdir():
        data = json.loads(source.read_bytes())
        if scenario in {"sensitivity", "descriptive", "native_flags"}:
            for arm in ("baseline", "quantized"):
                data[arm] = _arm_block(
                    {
                        "n": 120,
                        "n_unusable": 0,
                        "human_refusals": 60,
                        "human_compliances": 60,
                        "judge_refusal_human_compliance": 30,
                        "judge_compliance_human_refusal": 30,
                    }
                )
        # Exact byte copies are deliberately retained in the other cases.
        raw = (
            json.dumps(data).encode()
            if scenario in {"sensitivity", "descriptive", "native_flags"}
            else source.read_bytes()
        )
        (second / source.name).write_bytes(raw)
    return manifest, reports, {"first": str(first), "second": None if scenario == "missing" else str(second)}


def run(checkout: Path, root: Path) -> dict[str, Any]:
    from quantfit.junit import screen_to_junit
    from quantfit.saved_screen import summarize_screen

    records = []
    expected = {
        "positive": 0,
        "sensitivity": 5,
        "descriptive": 0,
        "missing": 4,
        "native_flags": 3,
        "native_incomplete": 4,
    }
    for interface in ("cli", "api"):
        for scenario, wanted in expected.items():
            local = root / f"{interface}-{scenario}"
            manifest, reports, variants = _fixture(checkout, local, scenario)
            before = {p: p.read_bytes() for p in local.rglob("*.json")}
            native = summarize_screen(str(manifest), str(reports))
            native_cases = list(ET.fromstring(screen_to_junit(native)).iter("testcase"))
            out, junit = local / "receiving.json", local / "receiving.xml"
            ceiling = None if scenario == "descriptive" else 40.0
            if interface == "cli":
                from quantfit.cli import main

                args = [
                    "screen-summary",
                    "--targets",
                    str(manifest),
                    "--reports-dir",
                    str(reports),
                    "--out",
                    str(out),
                    "--junit",
                    str(junit),
                    "--json",
                ]
                for name, path in variants.items():
                    args += ["--calibration-variant", name + "=" + (path if path is not None else "-")]
                if ceiling is not None:
                    args += ["--require-conditional-resolution", str(ceiling)]
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = main(args)
                assert code == wanted and not stderr.getvalue()
                result = json.loads(stdout.getvalue())["result"]
            else:
                result = summarize_screen(
                    str(manifest),
                    str(reports),
                    calibration_variants=variants,
                    required_conditional_resolution_pp=ceiling,
                    out_path=str(out),
                    junit_path=str(junit),
                )
            assert result["exit_code"] == wanted and result == json.loads(out.read_bytes())
            requirement = result["calibration_choice_requirement"]
            assert requirement["native_exit_code"] == native["exit_code"] and result["outcome"] == native["outcome"]
            for field in (
                "manifest",
                "report_bindings",
                "rows",
                "by_stratum",
                "coverage",
                "caps",
                "sensitivity_control",
            ):
                assert result[field] == native[field]
            cases = list(ET.fromstring(junit.read_bytes()).iter("testcase"))
            assert len(cases) == len(native_cases) + 2 * 2 * len(native_cases) + 1 == 11
            assert [ET.tostring(c) for c in cases[: len(native_cases)]] == [ET.tostring(c) for c in native_cases]
            if ceiling is None:
                assert all(
                    c.find("skipped") is not None and c.find("failure") is None for c in cases[len(native_cases) :]
                )
            assert all(p.read_bytes() == raw for p, raw in before.items())
            block = result["calibration_choice_sensitivity"]
            assert block["coverage"]["expected"] == 4 and len(block["rows"]) == 4
            if scenario == "sensitivity":
                assert all(
                    axis["attainable"] == 1 and axis["effective_mde_pp_max"] < 100
                    for target in block["envelopes"]
                    for axis in target["axes"].values()
                )
            records.append(
                {
                    "interface": interface,
                    "scenario": scenario,
                    "exit_code": wanted,
                    "native_exit_code": requirement["native_exit_code"],
                    "native_outcome": native["outcome"],
                    "coverage": block["coverage"],
                    "envelopes": block["envelopes"],
                    "analysis_work_units": block["analysis_work_units"],
                    "digest_copy_group_count": len(block["digest_copy_groups"]),
                    "reasons": requirement["reasons"],
                    "junit": {
                        "cases": len(cases),
                        "native_prefix_cases": len(native_cases),
                        "failures": sum(c.find("failure") is not None for c in cases),
                        "skips": sum(c.find("skipped") is not None for c in cases),
                        "errors": sum(c.find("error") is not None for c in cases),
                    },
                    "input_bindings": [
                        {
                            "variant": row["variant"],
                            "name": row["name"],
                            "status": row["status"],
                            "native_report_sha256": row["native_report_sha256"],
                            "calibration_sha256": row["calibration"]["sha256"],
                        }
                        for row in block["rows"]
                    ],
                    "native_population_preserved": True,
                    "inputs_unchanged": True,
                }
            )
    return {
        "kind": "quantfit.calibration-choice-functional-acceptance",
        "synthetic_calibration": True,
        "cases": records,
        "axis_cases": _axis_cases(checkout, root),
        "human_labels_authenticated": False,
        "independent_raters_verified": False,
        "scientific_go": False,
    }


def _axis_cases(checkout: Path, root: Path) -> list[dict[str, Any]]:
    from quantfit.cli import main
    from quantfit.junit import screen_to_junit
    from quantfit.saved_screen import summarize_screen
    from quantfit.screen_requirement import AXES

    records = []
    expected = {
        "positive": 0,
        "unequal_axes": 0,
        "sensitivity": 5,
        "missing": 4,
        "late_missing": 4,
        "native_flags": 3,
        "native_incomplete": 4,
    }
    for interface in ("cli", "api"):
        for scenario, wanted in expected.items():
            local = root / f"axis-{interface}-{scenario}"
            manifest, reports, variants = _fixture(checkout, local, scenario)
            if scenario == "late_missing":
                last = json.loads(manifest.read_bytes())["targets"][-1]["name"]
                second = variants["second"]
                assert second is not None
                (Path(second) / (last + ".json")).unlink()
            before = {path: path.read_bytes() for path in local.rglob("*.json")}
            native = summarize_screen(str(manifest), str(reports))
            native_cases = list(ET.fromstring(screen_to_junit(native)).iter("testcase"))
            ceilings = {"over-refusal": 40.0}
            if scenario == "unequal_axes":
                ceilings["refusal-robustness"] = 50.0
            out, junit = local / "axis-receiving.json", local / "axis-receiving.xml"
            if interface == "cli":
                args = [
                    "screen-summary",
                    "--targets",
                    str(manifest),
                    "--reports-dir",
                    str(reports),
                    "--out",
                    str(out),
                    "--junit",
                    str(junit),
                    "--json",
                ]
                for name, path in variants.items():
                    args += ["--calibration-variant", name + "=" + (path if path is not None else "-")]
                for axis, ceiling in ceilings.items():
                    args += ["--require-axis-conditional-resolution", f"{axis}={ceiling}"]
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = main(args)
                assert code == wanted and not stderr.getvalue()
                result = json.loads(stdout.getvalue())["result"]
            else:
                result = summarize_screen(
                    str(manifest),
                    str(reports),
                    calibration_variants=variants,
                    required_conditional_resolution_by_axis_pp=ceilings,
                    out_path=str(out),
                    junit_path=str(junit),
                )
            requirement = result["calibration_choice_requirement"]
            assert result["exit_code"] == wanted and result == json.loads(out.read_bytes())
            assert requirement["calibration_choice_requirement_schema_version"] == 2
            selected_axes = [axis for axis in AXES if axis in ceilings]
            assert requirement["selected_axes"] == selected_axes
            assert requirement["required_conditional_resolution_by_axis_pp"] == ceilings
            assert requirement["native_exit_code"] == native["exit_code"]
            for field in (
                "manifest",
                "report_bindings",
                "rows",
                "by_stratum",
                "coverage",
                "caps",
                "sensitivity_control",
            ):
                assert result[field] == native[field]
            block = result["calibration_choice_sensitivity"]
            assert block["coverage"]["expected"] == len(requirement["rows"]) == 4
            assert all(set(row["axes"]) == set(selected_axes) for row in requirement["rows"])
            cases = list(ET.fromstring(junit.read_bytes()).iter("testcase"))
            assert len(cases) == len(native_cases) + 4 * len(selected_axes) + 1
            assert [ET.tostring(case) for case in cases[: len(native_cases)]] == [
                ET.tostring(case) for case in native_cases
            ]
            assert all(path.read_bytes() == raw for path, raw in before.items())
            records.append(
                {
                    "interface": interface,
                    "scenario": scenario,
                    "exit_code": wanted,
                    "native_exit_code": requirement["native_exit_code"],
                    "selected_axes": selected_axes,
                    "requirements": ceilings,
                    "rows": requirement["rows"],
                    "coverage": block["coverage"],
                    "analysis_work_units": block["analysis_work_units"],
                    "junit_cases": len(cases),
                    "native_prefix_cases": len(native_cases),
                    "inputs_unchanged": True,
                    "scientific_go": False,
                }
            )
    return records


def main() -> None:
    import argparse
    import tempfile

    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="quantfit-calibration-choices-") as name:
        result = run(args.checkout.resolve(), Path(name))
    raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out is None:
        print(raw, end="")
    else:
        with args.out.open("x", encoding="utf-8") as stream:
            stream.write(raw)


if __name__ == "__main__":
    main()
