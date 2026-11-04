"""Native fictional two-judge fixtures; no model or human execution."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

BASE_TRUTH = ("compliance", "refusal", "compliance", "refusal", "unusable", "refusal", "unusable", "unusable")
QUANT_TRUTH = ("refusal", "unusable", "compliance", "refusal", "compliance", "unusable", "refusal", "unusable")
JUDGES = {
    "a": ((False, True, True, False, True, False, False, True), (True, False, False, True, True, False, False, True)),
    "b": ((True, True, False, False, False, True, False, True), (False, True, False, True, False, True, True, False)),
}
MARKER = "PRIVATE_TWO_JUDGE_CONTENT_DO_NOT_REFLECT"


def fixture(
    root: Path,
    checkout: Path,
    side: str,
    *,
    base_truth: tuple[str, ...] = BASE_TRUTH,
    quant_truth: tuple[str, ...] = QUANT_TRUTH,
    content_suffix: str = "",
    scope_marker: bool | float | None = None,
    zones: tuple[str, ...] | None = None,
    expected: tuple[str, ...] | None = None,
    input_contract: str | None = None,
) -> dict[str, Path]:
    from quantfit.resolution import parse_report_bytes
    from quantfit.safety.calibrate import build_labeling_sheet
    from quantfit.safety.retained_labels import extract_labels
    from quantfit.safety.verify import JUDGE_INPUT_CONTRACT, Probe, _write_capture

    root.mkdir(parents=True)
    prototype = parse_report_bytes(
        (checkout / "validation/2026-10-18-screen-bundle/inputs/reports/clean.json").read_bytes()
    )
    report = replace(
        prototype,
        judge={
            **prototype.judge,
            "id": f"fictional/judge-{side}",
            "revision": side * 40,
            "input_contract": JUDGE_INPUT_CONTRACT if input_contract is None else input_contract,
        },
        probe_dataset={**prototype.probe_dataset, "n_probes": 8},
        decode={**prototype.decode, **({"scope_marker": scope_marker} if scope_marker is not None else {})},
        drift={},
    )
    paths = {
        name: root / filename
        for name, filename in (
            ("capture", "private.capture.jsonl"),
            ("key", "private.labelkey.json"),
            ("sheet", "private.labels.csv"),
            ("retained", "private.retained.labels.csv"),
            ("receipt", "retention.json"),
        )
    }
    _write_capture(
        str(paths["capture"]),
        [
            Probe(
                f"fictional probe {i}",
                zones[i] if zones else "borderline",
                expected[i] if expected else ("safe" if i % 2 else "unsafe"),
            )
            for i in range(8)
        ],
        report.baseline.model,
        report.quantized.model,
        [f"{MARKER} baseline {i % 2}{content_suffix}" for i in range(8)],
        [f"{MARKER} quantized {i % 2}{content_suffix}" for i in range(8)],
        list(JUDGES[side][0]),
        list(JUDGES[side][1]),
        actual_report=report,
    )
    if side == "b":
        lines = paths["capture"].read_bytes().splitlines()
        paths["capture"].write_bytes(b"\n".join((lines[0], *reversed(lines[1:]))) + b"\n")
    build_labeling_sheet(str(paths["capture"]), str(paths["sheet"]), str(paths["key"]))
    key = json.loads(paths["key"].read_bytes())
    rows = list(csv.reader(io.StringIO(paths["sheet"].read_text(encoding="utf8"), newline="")))
    for row in rows[1:]:
        entry = key["ids"][row[0]]
        row[2] = (base_truth if entry["arm"] == "baseline" else quant_truth)[entry["pair"]]
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    paths["sheet"].write_bytes(buffer.getvalue().encode())
    extract_labels(
        str(paths["sheet"]), str(paths["key"]), out_path=str(paths["retained"]), receipt_path=str(paths["receipt"])
    )
    return paths


def _receive(
    interface: str, a: dict[str, Path], b: dict[str, Path], out: Path, modes: tuple[str, str]
) -> tuple[int, dict[str, Any]]:
    from quantfit.safety.calibration_judges import CalibrationJudgesError, analyze_calibration_judges

    kwargs: dict[str, str] = {}
    args = [
        "calibrate",
        "compare-judges",
        "--capture-a",
        str(a["capture"]),
        "--key-a",
        str(a["key"]),
        "--capture-b",
        str(b["capture"]),
        "--key-b",
        str(b["key"]),
        "--out",
        str(out),
    ]
    for name, side, mode in zip(("a", "b"), (a, b), modes, strict=True):
        if mode == "full":
            kwargs[f"sheet_{name}"] = str(side["sheet"])
            args += [f"--sheet-{name}", str(side["sheet"])]
        else:
            kwargs[f"retained_labels_{name}"] = str(side["retained"])
            kwargs[f"retention_receipt_{name}"] = str(side["receipt"])
            args += [
                f"--retained-labels-{name}",
                str(side["retained"]),
                f"--retention-receipt-{name}",
                str(side["receipt"]),
            ]
    if interface == "api":
        try:
            return 0, analyze_calibration_judges(
                str(a["capture"]), str(a["key"]), str(b["capture"]), str(b["key"]), out_path=str(out), **kwargs
            )
        except CalibrationJudgesError as error:
            assert str(error) == "invalid_calibration_judges" and error.__cause__ is None
            return 2, {}
    from quantfit.cli import main

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main([*args, "--json"])
    assert not stderr.getvalue()
    envelope = json.loads(stdout.getvalue())
    assert envelope["exit_code"] == code and len(stdout.getvalue().encode()) <= 256 * 1024
    return code, envelope.get("result", {})


def run(checkout: Path, root: Path) -> dict[str, Any]:
    import os
    import subprocess
    import sys

    from quantfit.safety import calibration_judges as module

    cases: list[dict[str, Any]] = []
    adverse: list[dict[str, Any]] = []
    for interface in ("api", "cli"):
        for index, modes in enumerate(
            (("full", "full"), ("retained", "retained"), ("full", "retained"), ("retained", "full"))
        ):
            local = root / f"{interface}-{index}"
            a, b = fixture(local / "a", checkout, "a"), fixture(local / "b", checkout, "b")
            before = {p: p.read_bytes() for side in (a, b) for p in side.values()}
            out = local / "judges.json"
            code, result = _receive(interface, a, b, out, modes)
            assert code == 0 and result == json.loads(out.read_bytes())
            assert result["n_pairs"] == 8 and result["n_rows_per_judge"] == 16
            assert result["truth_coverage"]["both_usable"] == 3
            for arm in ("baseline", "quantized"):
                table = result["per_arm"][arm]
                assert table["whole_n"] == 8 and table["usable_truth_n"] == 5
                assert table["error_a_margin"] == result["native_per_judge"]["a"]["arms"][arm]["judge_errors"]
                assert table["error_b_margin"] == result["native_per_judge"]["b"]["arms"][arm]["judge_errors"]
            rendered = json.dumps(result)
            assert MARKER not in rendered and all(str(path) not in rendered for path in before)
            assert all(path.read_bytes() == raw for path, raw in before.items())
            cases.append(
                {
                    "interface": interface,
                    "mode_a": modes[0],
                    "mode_b": modes[1],
                    "exit_code": 0,
                    "pairs": 8,
                    "usable_each_arm": 5,
                }
            )
        for mode in ("self", "unusable", "one-arm", "long"):
            local = root / f"{interface}-{mode}"
            options: dict[str, Any] = {}
            if mode in ("unusable", "one-arm"):
                options["base_truth"] = ("unusable",) * 8
            if mode == "unusable":
                options["quant_truth"] = ("unusable",) * 8
            if mode == "long":
                options["content_suffix"] = "x" * 131073
            old_limit = csv.field_size_limit()
            try:
                if mode == "long":
                    csv.field_size_limit(300000)
                a, b = fixture(local / "a", checkout, "a", **options), fixture(local / "b", checkout, "b", **options)
            finally:
                csv.field_size_limit(old_limit)
            code, result = _receive(
                interface, a, a if mode == "self" else b, local / "out.json", ("retained", "retained")
            )
            assert code == 0
            if mode in ("unusable", "one-arm"):
                assert result["native_per_judge"]["a"]["arms"]["baseline"]["epsilon"] is None
            if mode == "self":
                assert all(table["flag_disagreements"] == 0 for table in result["per_arm"].values())
            cases.append({"interface": interface, "case": mode, "exit_code": 0, "pairs": 8})

        for mutation in (
            "capture",
            "key",
            "receipt",
            "strings",
            "truth",
            "zone",
            "expected",
            "bool-int",
            "input-contract",
            "extra-csv",
            "late-field",
            "existing",
            "alias",
            "output-limit",
            "total-limit",
            "population",
        ):
            local = root / f"{interface}-bad-{mutation}"
            a = fixture(local / "a", checkout, "a", scope_marker=1)
            adverse_options: dict[str, Any] = {"scope_marker": 1}
            if mutation == "strings":
                adverse_options["content_suffix"] = "CHANGED_PRIVATE"
            if mutation == "truth":
                adverse_options["base_truth"] = ("refusal", *BASE_TRUTH[1:])
            if mutation == "zone":
                adverse_options["zones"] = ("clear_safe", *("borderline",) * 7)
            if mutation == "expected":
                adverse_options["expected"] = ("safe", *("safe" if i % 2 else "unsafe" for i in range(1, 8)))
            if mutation == "bool-int":
                adverse_options["scope_marker"] = True
            if mutation == "input-contract":
                adverse_options["input_contract"] = "unsupported judge input"
            b = fixture(local / "b", checkout, "b", **adverse_options)
            modes = ("retained", "retained") if mutation == "receipt" else ("full", "full")
            out = local / "refused.json"
            if mutation == "capture":
                a["capture"].write_bytes(a["capture"].read_bytes() + b" ")
            if mutation == "key":
                a["key"].write_bytes(b["key"].read_bytes())
            if mutation == "receipt":
                a["receipt"].write_bytes(b["receipt"].read_bytes())
            if mutation in ("extra-csv", "late-field"):
                with a["sheet"].open("a", encoding="utf8", newline="") as stream:
                    csv.writer(stream).writerow(
                        ("extra", "PRIVATE_EXTRA" if mutation == "extra-csv" else "x" * 131073, "unusable")
                    )
            if mutation == "population":
                document = json.loads(a["key"].read_bytes())
                document["capture"]["n_pairs"] = 4097
                a["key"].write_text(json.dumps(document), encoding="utf8")
            if mutation == "existing":
                out.write_bytes(b"KEEP")
            if mutation == "alias":
                out = a["key"]
            before = {p: p.read_bytes() for side in (a, b) for p in side.values()}
            old = module.MAX_INPUT_BYTES, module.MAX_JUDGES_BYTES
            try:
                if mutation == "output-limit":
                    module.MAX_JUDGES_BYTES = 64
                if mutation == "total-limit":
                    module.MAX_INPUT_BYTES = 1
                assert _receive(interface, a, b, out, modes)[0] == 2
            finally:
                module.MAX_INPUT_BYTES, module.MAX_JUDGES_BYTES = old
            assert all(p.read_bytes() == raw for p, raw in before.items())
            if mutation not in ("existing", "alias"):
                assert not out.exists()
            if mutation == "existing":
                assert out.read_bytes() == b"KEEP"
            adverse.append({"interface": interface, "case": mutation, "exit_code": 2})

    a, b = fixture(root / "os-a", checkout, "a"), fixture(root / "os-b", checkout, "b")
    out = root / "os.json"
    args = [
        sys.executable,
        "-B",
        "-X",
        "utf8",
        "-m",
        "quantfit.cli",
        "calibrate",
        "compare-judges",
        "--capture-a",
        str(a["capture"]),
        "--key-a",
        str(a["key"]),
        "--sheet-a",
        str(a["sheet"]),
        "--capture-b",
        str(b["capture"]),
        "--key-b",
        str(b["key"]),
        "--sheet-b",
        str(b["sheet"]),
        "--out",
        str(out),
        "--json",
    ]
    child = subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        cwd=root,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
    )
    assert child.returncode == 0 and not child.stderr and b"\r" not in child.stdout
    envelope = json.loads(child.stdout)
    assert (
        envelope["result"] == json.loads(out.read_bytes())
        and child.stdout == (json.dumps(envelope, indent=2) + "\n").encode()
    )
    paths = (
        "quantfit/safety/calibration_judges.py",
        "quantfit/calibration_judges_cli.py",
        "quantfit/cli.py",
        "quantfit/safety/calibration_inputs.py",
        "quantfit/safety/calibration_strata.py",
        "quantfit/safety/calibrate.py",
        "quantfit/safety/retained_labels.py",
        "quantfit/safety/retention_io.py",
        "quantfit/safety/calibration_binding.py",
        "quantfit/safety/calibration_aggregate.py",
        "quantfit/safety/verify.py",
        "tools/ci_calibration_judges.py",
        "tools/ci_installed.py",
        "tests/test_calibration_judges.py",
        "tests/test_ci_calibration_judges.py",
        ".github/workflows/validate.yml",
    )
    return {
        "positive_cases": len(cases),
        "cases": cases,
        "adverse_cases": len(adverse),
        "adverse": adverse,
        "os_cli_utf8_lf_parity": True,
        "synthetic_operator_declarations": True,
        "human_confirmation_verified": False,
        "source_authenticity_verified": False,
        "scientific_go": False,
        "source_hashes": {name: hashlib.sha256((checkout / name).read_bytes()).hexdigest() for name in paths},
    }
