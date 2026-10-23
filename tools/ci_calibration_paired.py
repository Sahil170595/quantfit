"""Fictional paired-label fixture and installed CLI acceptance; no model execution."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

STATES = ("RR", "RC", "CR", "CC")
CELL_COUNTS = ((1, 2, 1, 1), (1, 1, 3, 1), (2, 1, 1, 1), (1, 1, 1, 2))
PairSpec = tuple[str, str, str]
SPECS: tuple[PairSpec, ...] = tuple(
    (judge, human, "unsafe" if (i + j) % 2 == 0 else "safe")
    for i, judge in enumerate(STATES)
    for j, human in enumerate(STATES)
    for _ in range(CELL_COUNTS[i][j])
) + (("RC", "UC", "unsafe"), ("CR", "CU", "safe"), ("RC", "UU", "unsafe"))
MARKER = "PRIVATE_PAIRED_TEXT_DO_NOT_REFLECT"


def fixture(
    root: Path, checkout: Path, *, specs: tuple[PairSpec, ...] = SPECS, reverse: bool = False
) -> tuple[Path, Path, Path]:
    from quantfit.resolution import parse_report_bytes
    from quantfit.safety.calibrate import build_labeling_sheet
    from quantfit.safety.verify import Probe, _write_capture

    root.mkdir(parents=True)
    prototype = parse_report_bytes(
        (checkout / "validation/2026-10-18-screen-bundle/inputs/reports/clean.json").read_bytes()
    )
    report = replace(prototype, probe_dataset={**prototype.probe_dataset, "n_probes": len(specs)}, drift={})
    capture, sheet, key = (
        root / name for name in ("private.capture.jsonl", "private.labels.csv", "private.labelkey.json")
    )
    _write_capture(
        str(capture),
        [Probe(f"fictional private probe {i}", "borderline", spec[2]) for i, spec in enumerate(specs)],
        report.baseline.model,
        report.quantized.model,
        [f"{MARKER} baseline {i}" for i in range(len(specs))],
        [f"{MARKER} quantized {i}" for i in range(len(specs))],
        [spec[0][0] == "R" for spec in specs],
        [spec[0][1] == "R" for spec in specs],
        actual_report=report,
    )
    if reverse:
        lines = capture.read_bytes().splitlines()
        capture.write_bytes(b"\n".join([lines[0], *reversed(lines[1:])]) + b"\n")
    build_labeling_sheet(str(capture), str(sheet), str(key))
    mapping = json.loads(key.read_bytes())["ids"]
    labels = {"R": "refusal", "C": "compliance", "U": "unusable"}
    rows = list(csv.reader(io.StringIO(sheet.read_text(encoding="utf-8"), newline="")))
    for row in rows[1:]:
        entry = mapping[row[0]]
        row[2] = labels[specs[entry["pair"]][1][0 if entry["arm"] == "baseline" else 1]]
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    sheet.write_bytes(buffer.getvalue().encode())
    return capture, sheet, key


def invoke(args: list[str]) -> tuple[int, dict[str, Any], str]:
    import contextlib

    from quantfit.cli import main

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main([*args, "--json"])
    document = json.loads(stdout.getvalue())
    assert document["exit_code"] == code
    return code, document, stderr.getvalue()


def run(checkout: Path, root: Path) -> dict[str, Any]:
    from quantfit.safety.calibration_binding import CalibrationBindingError, load_bound_calibration

    capture, sheet, key = fixture(root / "private", checkout)
    full_out, retained_out = root / "full.json", root / "retained.json"
    code, full, stderr = invoke(
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
            str(full_out),
        ]
    )
    assert code == 0 and not stderr
    labels, receipt = root / "private.retained.labels.csv", root / "retention.json"
    code, extracted, stderr = invoke(
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
        ]
    )
    assert code == 0 and not stderr and extracted["result"]["n_rows"] == 48
    sheet.unlink()  # Only owned fictional fixture material. Product commands do not delete sources.
    code, retained, stderr = invoke(
        [
            "calibrate",
            "paired",
            "--capture",
            str(capture),
            "--retained-labels",
            str(labels),
            "--retention-receipt",
            str(receipt),
            "--key",
            str(key),
            "--out",
            str(retained_out),
        ]
    )
    assert code == 0 and not stderr
    first, second = full["result"], retained["result"]
    for field in (
        "n_pairs",
        "n_rows",
        "coverage",
        "whole_judge_pair_state_counts",
        "common_usable",
        "axes",
        "binding_fingerprint",
    ):
        assert first[field] == second[field]
    assert first["original_sheet"]["held_and_validated"] and not second["original_sheet"]["held_and_validated"]
    assert first["original_sheet"]["sha256"] == second["original_sheet"]["sha256"]
    try:
        load_bound_calibration(str(retained_out))
    except CalibrationBindingError:
        pass
    else:
        raise AssertionError("paired diagnostic accepted as bound calibration")
    gate_out = root / "refused-gate.json"
    gate_code, _, _ = invoke(
        [
            "gate",
            "--from-report",
            str(checkout / "validation/2026-10-18-screen-bundle/inputs/reports/clean.json"),
            "--calibration-report",
            str(retained_out),
            "--tier",
            "smoke",
            "--out",
            str(gate_out),
        ]
    )
    assert gate_code == 2 and not gate_out.exists()
    rendered = json.dumps([full, retained])
    private = json.loads(key.read_bytes())
    assert MARKER not in rendered and private["salt"] not in rendered
    assert all(row_id not in rendered for row_id in private["ids"])
    assert all(str(path) not in rendered for path in (capture, sheet, key, labels, receipt, full_out, retained_out))
    return {
        "kind": "quantfit.calibration-paired-functional-acceptance",
        "synthetic": True,
        "n_pairs": 24,
        "n_rows": 48,
        "full_retained_statistics_equal": True,
        "original_sheet_unavailable_for_retained": not sheet.exists(),
        "native_bound_loader_refused_diagnostic": True,
        "native_gate_refused_diagnostic_exit_code": gate_code,
        "full_inputs": first["inputs"],
        "paired": second,
        "human_labels_authenticated": False,
        "independence_verified": False,
        "scientific_go": False,
    }


def main() -> None:
    import argparse
    import tempfile

    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="quantfit-paired-private-") as name:
        result = run(args.checkout.resolve(), Path(name))
    raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out is not None:
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(raw)
    else:
        print(raw, end="")


if __name__ == "__main__":
    main()
