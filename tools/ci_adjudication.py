"""Actual fictional adjudication producer and native stdout/string model-card consumer."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import importlib.util
import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

LABELS = (
    ("refusal", "compliance", "substantive"),
    ("refusal", "compliance", "degenerate"),
    ("compliance", "compliance", "not-a-flip"),
    ("unusable", "compliance", "unresolved"),
    ("compliance", "refusal", "substantive"),
    ("compliance", "refusal", "degenerate"),
    ("refusal", "refusal", "not-a-flip"),
    ("compliance", "unusable", "unresolved"),
)


def fixture(root: Path, checkout: Path, mode: str = "mixed") -> tuple[Path, Path]:
    from quantfit.resolution import parse_report_bytes
    from quantfit.safety.verify import Probe, _tabulate, _write_capture

    root.mkdir(parents=True)
    n = 8 if mode == "all" else 12
    probes = [
        Probe(
            "",
            "clear_unsafe" if i < 4 or i >= 8 and i % 2 == 0 else "clear_safe",
            "unsafe" if i < 4 or i >= 8 and i % 2 == 0 else "safe",
        )
        for i in range(n)
    ]
    a = [p.expected == "unsafe" for p in probes]
    b = [not flag if i < 8 and mode != "zero" else flag for i, flag in enumerate(a)]
    report = parse_report_bytes(
        (checkout / "validation/2026-10-18-screen-bundle/inputs/reports/clean.json").read_bytes()
    )
    report = replace(
        report, probe_dataset={**report.probe_dataset, "n_probes": n}, drift=_tabulate(probes, a, b).to_dict()
    )
    report_path, capture = root / "report.json", root / "private.capture.jsonl"
    report.to_json(str(report_path))

    def texts(flags: list[bool], arm: str) -> list[str]:
        return [
            ("PRIVATE_ common refusal" if flag else "PRIVATE_ common compliance")
            if mode == "repeated"
            else f'PRIVATE_ {arm} {i}, "quoted"\nfictional'
            for i, flag in enumerate(flags)
        ]

    _write_capture(
        str(capture),
        probes,
        report.baseline.model,
        report.quantized.model,
        texts(a, "baseline"),
        texts(b, "quantized"),
        a,
        b,
        actual_report=report,
    )
    return report_path, capture


def filled(path: Path) -> None:
    rows = list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))
    for row in rows[1:]:
        row[-3:] = LABELS[int(row[0]) % 8]
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    path.write_bytes(stream.getvalue().encode())


def _invoke(args: list[str]) -> tuple[int, dict[str, Any]]:
    from quantfit.cli import main

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main([*args, "--json"])
    assert not stderr.getvalue()
    envelope = json.loads(stdout.getvalue())
    assert envelope["exit_code"] == code
    return code, envelope


def _calibration(checkout: Path, report: Path, destination: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "private_adjudication_calibration", checkout / "tools/ci_screen_resolution.py"
    )
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    destination.write_bytes(helper.calibration_bytes(report.read_bytes()))


def run(checkout: Path, root: Path) -> dict[str, Any]:
    from quantfit.modelcard import model_card_fragment
    from quantfit.safety.adjudication import apply_adjudication, prepare_adjudication

    records = []
    for interface in ("cli", "api"):
        for mode in ("mixed", "all", "zero", "repeated"):
            local = root / f"{interface}-{mode}"
            report, capture = fixture(local / "private", checkout, mode)
            report_bytes, capture_bytes = report.read_bytes(), capture.read_bytes()
            queue, preparation = local / "private.adjudication.csv", local / "private.adjudication-preparation.json"
            if interface == "cli":
                code, envelope = _invoke(
                    [
                        "adjudicate",
                        "prepare",
                        "--report",
                        str(report),
                        "--capture",
                        str(capture),
                        "--review",
                        str(queue),
                        "--receipt",
                        str(preparation),
                    ]
                )
                assert code == 0
                prepared = envelope["result"]
            else:
                prepared = prepare_adjudication(
                    str(report), str(capture), review_path=str(queue), receipt_path=str(preparation)
                )
            expected = 0 if mode == "zero" else 8
            assert prepared["n_selected"] == expected
            filled(queue)  # Explicit manufactured judgments for fictional text only.
            record_path = local / "adjudication.json"
            if interface == "cli":
                code, envelope = _invoke(
                    [
                        "adjudicate",
                        "apply",
                        "--report",
                        str(report),
                        "--capture",
                        str(capture),
                        "--review",
                        str(queue),
                        "--preparation",
                        str(preparation),
                        "--out",
                        str(record_path),
                    ]
                )
                assert code == 0
                record = envelope["result"]
            else:
                record = apply_adjudication(
                    str(report), str(capture), str(queue), str(preparation), out_path=str(record_path)
                )
            assert record == json.loads(record_path.read_bytes()) and len(record["entries"]) == expected
            assert report.read_bytes() == report_bytes and capture.read_bytes() == capture_bytes
            assert "PRIVATE_" not in json.dumps(record) and str(root) not in json.dumps(record)
            if expected:
                assert record["inputs"]["review_queue"] != prepared["review_queue"]
                assert all(
                    row == {"flagged": 4, "substantive": 1, "degenerate": 1, "not_confirmed": 1, "unresolved": 1}
                    for row in record["counts"].values()
                )
            capture.unlink()  # ONLY fresh synthetic fixture; demonstrates capture-free receiving.
            calibration = local / "calibration.json"
            _calibration(checkout, report, calibration)
            cards = {}
            for calibrated in (False, True):
                options = {"calibration_report": str(calibration)} if calibrated else {}
                original = model_card_fragment(str(report), **options)
                if interface == "cli":
                    command = ["emit", "model-card", "--report", str(report), "--adjudication", str(record_path)]
                    if calibrated:
                        command += ["--calibration-report", str(calibration)]
                    code, envelope = _invoke(command)
                    assert code == 0
                    card = envelope["result"]["fragment"]
                else:
                    card = model_card_fragment(str(report), adjudication_record=str(record_path), **options)
                assert "### Operator-declared adjudication" in card and "human_confirmation_verified=false" in card
                assert original.split("\n---\n")[0] in card and original.split("\n---\n")[1] == card.split("\n---\n")[1]
                assert "not freshly verified here" in card and "PRIVATE_" not in card
                assert model_card_fragment(str(report), adjudication_record=str(record_path), **options) == card
                assert report.read_bytes() == report_bytes
                cards["calibrated" if calibrated else "plain"] = {
                    "sha256": hashlib.sha256(card.encode("utf-8")).hexdigest(),
                    "native_prefix_footer_preserved": True,
                    "deterministic": True,
                }
            records.append(
                {
                    "interface": interface,
                    "mode": mode,
                    "n_probes": record["n_probes"],
                    "counts": record["counts"],
                    "inputs": record["inputs"],
                    "record_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest(),
                    "entry_count": len(record["entries"]),
                    "cards": cards,
                    "originals_unchanged_through_production": True,
                    "synthetic_capture_removed_before_receiving": True,
                    "operator_status": record["operator_status"],
                    "proof_limits": record["proof_limits"],
                }
            )
    return {
        "kind": "quantfit.source-bound-adjudication-functional-acceptance",
        "synthetic_operator_labels": True,
        "cases": records,
        "human_confirmation_verified": False,
        "scientific_go": False,
    }


def main() -> None:
    import argparse
    import tempfile

    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="quantfit-adjudication-private-") as name:
        result = run(args.checkout.resolve(), Path(name))
    raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out is None:
        print(raw, end="")
    else:
        with args.out.open("x", encoding="utf-8") as stream:
            stream.write(raw)


if __name__ == "__main__":
    main()
