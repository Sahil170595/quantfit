"""Installed offline requirement consumer; synthetic counts, no model or human study."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from xml.etree import ElementTree as ET


def _module(checkout: Path, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location("requirement_" + filename, checkout / "tools" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(
    checkout: Path,
    root: Path,
    *,
    n: int = 120,
    population: int = 1,
    flagged: bool = False,
    unmeasured: bool = False,
    missing: tuple[str, ...] = (),
) -> tuple[Path, Path, Path]:
    from quantfit.safety.verify import SafetyDrift

    native = _module(checkout, "ci_screen_resolution.py")
    raw_manifest, originals = cast(tuple[bytes, dict[str, bytes]], native.original_inputs(checkout))
    manifest = json.loads(raw_manifest)
    manifest["targets"] = manifest["targets"][:population]
    reports, calibrations = {}, {}
    half = n // 2
    for index, target in enumerate(manifest["targets"]):
        name = target["name"]
        payload = json.loads(originals[name])
        risk = 0 if unmeasured and index == 0 else half
        flips = 1 if flagged and index == 0 else 0
        payload["probe_dataset"]["n_probes"] = n
        payload["drift"] = SafetyDrift(
            n,
            half,
            risk,
            risk - flips,
            flips,
            n - half,
            0,
            0,
            0,
            {
                "clear_unsafe": {"n": half, "baseline_refused": risk, "quant_refused": risk - flips},
                "clear_safe": {"n": n - half, "baseline_refused": 0, "quant_refused": 0},
            },
        ).to_dict()
        raw = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        reports[name] = raw
        if name not in missing:
            calibrations[name] = cast(bytes, native.calibration_bytes(raw))
    return cast(
        tuple[Path, Path, Path], native.stage(root, json.dumps(manifest).encode("utf-8"), reports, calibrations)
    )


def invoke(
    paths: tuple[Path, Path, Path], *, ceiling: float | None = None, out: Path | None = None, junit: Path | None = None
) -> tuple[int, dict[str, Any], str]:
    from quantfit.cli import main

    manifest, reports, calibrations = paths
    args = [
        "screen-summary",
        "--targets",
        str(manifest),
        "--reports-dir",
        str(reports),
        "--calibrations-dir",
        str(calibrations),
        "--json",
    ]
    if ceiling is not None:
        args.extend(["--require-conditional-resolution", str(ceiling)])
    if out is not None:
        args.extend(["--out", str(out)])
    if junit is not None:
        args.extend(["--junit", str(junit)])
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(args)
    document = json.loads(stdout.getvalue())
    assert document["exit_code"] == code
    return code, document, stderr.getvalue()


def _case(paths: tuple[Path, Path, Path], ceiling: float, expected: int) -> dict[str, Any]:
    before = {path: path.read_bytes() for path in paths[0].parent.rglob("*.json")}
    native_code, native, stderr = invoke(paths)
    assert not stderr and "conditional_resolution_requirement" not in native["result"]
    out, xml = paths[0].parent / "receiving.json", paths[0].parent / "receiving.xml"
    code, document, stderr = invoke(paths, ceiling=ceiling, out=out, junit=xml)
    assert not stderr and code == expected and document["result"] == json.loads(out.read_bytes())
    result = document["result"]
    requirement = result["conditional_resolution_requirement"]
    assert requirement["native_exit_code"] == native_code and result["outcome"] == native["result"]["outcome"]
    for field in ("manifest", "report_bindings", "rows", "by_stratum", "coverage", "caps", "sensitivity_control"):
        assert result[field] == native["result"][field]
    cases = ET.fromstring(xml.read_bytes()).findall(".//testcase")
    assert len(cases) == 3 * len(result["rows"]) + 1
    assert bool([case for case in cases if case.find("failure") is not None]) == (code != 0)
    assert all(path.read_bytes() == raw for path, raw in before.items())
    axes = []
    for row in result["conditional_resolution"]["rows"]:
        axes.append(
            {
                "name": row["name"],
                "axes": {
                    name: {
                        "n_at_risk": axis["n_at_risk"],
                        "flagged_flips": axis["flagged_flips"],
                        "measurable": axis["measurable"],
                        "effective_mde": axis["resolution"]["effective_mde"],
                        "detectable_at_target_power": axis["detectable_at_target_power"],
                    }
                    for name, axis in row["analysis"]["axes"].items()
                }
                if row["analysis"] is not None
                else None,
            }
        )
    return {
        "exit_code": code,
        "native_exit_code": native_code,
        "native_outcome": result["outcome"],
        "requirement": requirement,
        "native_axes": axes,
        "junit": {
            "cases": len(cases),
            "failures": sum(case.find("failure") is not None for case in cases),
            "skips": sum(case.find("skipped") is not None for case in cases),
        },
        "inputs_unchanged": True,
    }


def run(checkout: Path, root: Path) -> dict[str, Any]:
    from quantfit.safety.retained_labels import extract_labels, ingest_retained_labels

    cases = {}
    for name, ceiling, expected, options in (
        ("qualified", 40, 0, {}),
        ("coarse", 30, 5, {}),
        ("saturated", 100, 5, {"n": 40}),
        ("missing", 40, 4, {"missing": ("clean",)}),
        ("native_flagged", 40, 3, {"flagged": True}),
        ("mixed_flags", 1, 3, {"population": 3, "flagged": True, "missing": ("flagged",)}),
        ("mixed_incomplete", 1, 4, {"population": 3, "unmeasured": True, "missing": ("flagged",)}),
    ):
        cases[name] = _case(fixture(checkout, root / name, **options), ceiling, expected)
    native = _module(checkout, "ci_screen_resolution.py")
    labels = _module(checkout, "ci_label_reconciliation.py")
    raw_manifest, reports = cast(tuple[bytes, dict[str, bytes]], native.original_inputs(checkout))
    manifest = json.loads(raw_manifest)
    manifest["targets"] = [target for target in manifest["targets"] if target["name"] == "clean"]
    sheet, _, key, _ = cast(tuple[Path, Path, Path, dict[str, Any]], labels.fixture(root / "private", checkout, n=40))
    retained, receipt, calibration = root / "private.retained.csv", root / "retention.json", root / "calibration.json"
    extract_labels(str(sheet), str(key), out_path=str(retained), receipt_path=str(receipt))
    sheet.unlink()  # Disposable fictional fixture only; product commands never delete sources.
    payload = ingest_retained_labels(str(retained), str(receipt), str(key), out_path=str(calibration))
    assert payload["calibration_schema"] == 3
    paths = cast(
        tuple[Path, Path, Path],
        native.stage(
            root / "schema3",
            json.dumps(manifest).encode("utf-8"),
            {"clean": reports["clean"]},
            {"clean": calibration.read_bytes()},
        ),
    )
    cases["retained_schema3"] = _case(paths, 100, 5)
    return {
        "kind": "quantfit.screen-conditional-resolution-requirement-functional-acceptance",
        "synthetic": True,
        "cases": cases,
        "retained_calibration_schema": 3,
        "original_sheet_unavailable_for_retained": not sheet.exists(),
        "additional_native_inference_calls": 0,
        "human_labels_authenticated": False,
        "assumptions_verified": False,
        "independent_execution_verified": False,
        "scientific_go": False,
    }


def main() -> None:
    import argparse
    import tempfile

    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="quantfit-requirement-private-") as name:
        result = run(args.checkout.resolve(), Path(name))
    raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out is None:
        print(raw, end="")
    else:
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(raw)


if __name__ == "__main__":
    main()
