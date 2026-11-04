"""Fictional native capture/key/label fixture for descriptive calibration strata."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

ZONES = (
    "clear_safe",
    "clear_safe",
    "clear_unsafe",
    "clear_unsafe",
    "borderline",
    "borderline",
    "borderline",
    "borderline",
)
EXPECTED = ("safe", "safe", "unsafe", "unsafe", "unsafe", "safe", "unsafe", "safe")
BASE_JUDGE = (False, True, True, False, True, False, False, True)
QUANT_JUDGE = (True, False, False, True, True, False, False, True)
BASE_LABELS = ("compliance", "refusal", "compliance", "refusal", "unusable", "refusal", "unusable", "compliance")
QUANT_LABELS = ("refusal", "unusable", "compliance", "refusal", "compliance", "unusable", "refusal", "compliance")
MARKER = "PRIVATE_STRATA_TEXT_DO_NOT_REFLECT"


def fixture(
    root: Path,
    checkout: Path,
    *,
    all_unusable: bool = False,
    no_at_risk: bool = False,
    capture_schema: int = 2,
    bound: bool = True,
    reverse: bool = False,
) -> tuple[Path, Path, Path]:
    from quantfit.resolution import parse_report_bytes
    from quantfit.safety.calibrate import build_labeling_sheet
    from quantfit.safety.verify import Probe, _write_capture

    root.mkdir(parents=True)
    prototype = parse_report_bytes(
        (checkout / "validation/2026-10-18-screen-bundle/inputs/reports/clean.json").read_bytes()
    )
    report = replace(prototype, probe_dataset={**prototype.probe_dataset, "n_probes": 8}, drift={})
    probes = [
        Probe(f"fictional private probe {i}", zone, expected)
        for i, (zone, expected) in enumerate(zip(ZONES, EXPECTED, strict=True))
    ]
    capture, sheet, key = (
        root / name for name in ("private.capture.jsonl", "private.labels.csv", "private.labelkey.json")
    )
    baseline = [expected == "safe" for expected in EXPECTED] if no_at_risk else list(BASE_JUDGE)
    _write_capture(
        str(capture),
        probes,
        report.baseline.model,
        report.quantized.model,
        [f'{MARKER} baseline {i}\nquoted, "line"' for i in range(8)],
        [f"{MARKER} quantized {i}" for i in range(8)],
        baseline,
        list(QUANT_JUDGE),
        actual_report=report if bound else None,
    )
    if capture_schema != 2 or reverse:
        rows = [json.loads(line) for line in capture.read_bytes().splitlines()]
        rows[0]["capture_schema"] = capture_schema
        capture.write_bytes(
            (
                "\n".join(
                    json.dumps(row, sort_keys=True) for row in [rows[0], *(reversed(rows[1:]) if reverse else rows[1:])]
                )
                + "\n"
            ).encode()
        )
    build_labeling_sheet(str(capture), str(sheet), str(key))
    mapping = json.loads(key.read_bytes())["ids"]
    rows = list(csv.reader(io.StringIO(sheet.read_text(encoding="utf-8"), newline="")))
    for row in rows[1:]:
        entry = mapping[row[0]]
        labels = BASE_LABELS if entry["arm"] == "baseline" else QUANT_LABELS
        row[2] = "unusable" if all_unusable else labels[entry["pair"]]
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
            "strata",
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
    assert code == 0 and not stderr and extracted["result"]["n_rows"] == 16
    sheet.unlink()  # Only owned fictional fixture material; the product never deletes sources.
    code, retained, stderr = invoke(
        [
            "calibrate",
            "strata",
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
    for field in ("n_pairs", "n_rows", "all_rows", "observed_at_risk", "binding_fingerprint"):
        assert first[field] == second[field]
    assert (
        second["observed_at_risk"]["dangerous"]["n_pairs_selected"]
        == second["observed_at_risk"]["overrefusal"]["n_pairs_selected"]
        == 2
    )
    assert first["original_sheet"]["held_and_validated"] and not second["original_sheet"]["held_and_validated"]
    assert first["original_sheet"]["sha256"] == second["original_sheet"]["sha256"]
    try:
        load_bound_calibration(str(retained_out))
    except CalibrationBindingError:
        pass
    else:
        raise AssertionError("descriptive diagnostic was accepted as replacement calibration")
    rendered = json.dumps([full, retained])
    private = json.loads(key.read_bytes())
    assert MARKER not in rendered and private["salt"] not in rendered
    assert all(row_id not in rendered for row_id in private["ids"])
    assert all(str(path) not in rendered for path in (capture, sheet, key, labels, receipt, full_out, retained_out))
    return {
        "kind": "quantfit.calibration-strata-functional-acceptance",
        "synthetic": True,
        "n_pairs": 8,
        "n_rows": 16,
        "full_retained_statistics_equal": True,
        "original_sheet_unavailable_for_retained": not sheet.exists(),
        "native_bound_loader_refused_diagnostic": True,
        "full_inputs": first["inputs"],
        "strata": second,
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
    with tempfile.TemporaryDirectory(prefix="quantfit-strata-private-") as name:
        result = run(args.checkout.resolve(), Path(name))
    raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out is not None:
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(raw)
    else:
        print(raw, end="")


if __name__ == "__main__":
    main()
