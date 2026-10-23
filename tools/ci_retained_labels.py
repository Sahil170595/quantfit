"""Installed offline retained-label consumer; fictional private inputs live only in temp dirs."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import tempfile
from pathlib import Path
from typing import Any, cast


def invoke(args: list[str]) -> tuple[int, dict[str, Any], str]:
    from quantfit.cli import main

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main([*args, "--json"])
    document = json.loads(stdout.getvalue())
    assert type(document) is dict and document["exit_code"] == code
    return code, document, stderr.getvalue()


def run(checkout: Path, root: Path) -> dict[str, Any]:
    """Exercise installed CLI extract→retained ingest→native resolution without inference."""
    from quantfit.safety.calibrate import ingest_labels

    spec = importlib.util.spec_from_file_location(
        "private_retention_fixture", checkout / "tools/ci_label_reconciliation.py"
    )
    assert spec is not None and spec.loader is not None
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    sheet, _, key, _ = cast(tuple[Path, Path, Path, dict[str, Any]], fixture.fixture(root / "private", checkout, n=40))
    private_key = json.loads(key.read_bytes())
    legacy = ingest_labels(str(sheet), str(key), str(root / "legacy.json"))
    labels, receipt, out = (root / name for name in ("private.labels.csv", "retention.json", "calibration.json"))
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
    assert code == 0 and not stderr
    sheet.unlink()  # Only disposable synthetic data; the product never deletes caller inputs.
    code, ingested, stderr = invoke(
        [
            "calibrate",
            "ingest",
            "--retained-labels",
            str(labels),
            "--retention-receipt",
            str(receipt),
            "--key",
            str(key),
            "--out",
            str(out),
        ]
    )
    assert code == 0 and not stderr
    retained = json.loads(out.read_bytes())
    assert retained["calibration_schema"] == 3 and legacy["calibration_schema"] == 2
    for field in (
        "baseline",
        "quantized",
        "n_labeled",
        "n_unusable",
        "unmeasured_arms",
        "arm_epsilon_delta",
        "binding",
    ):
        assert retained[field] == legacy[field]
    original_report = checkout / "validation/2026-10-18-screen-bundle/inputs/reports/clean.json"
    code, resolved, stderr = invoke(
        [
            "resolution",
            "--report",
            str(original_report),
            "--calibration-report",
            str(out),
            "--out",
            str(root / "resolution.json"),
        ]
    )
    assert code == 0 and not stderr
    assert resolved["result"]["human_confirmation_verified"] is resolved["result"]["assumptions_verified"] is False
    rendered = json.dumps([extracted, ingested])
    assert private_key["salt"] not in rendered and fixture.MARKER not in rendered
    assert all(row_id not in rendered for row_id in private_key["ids"])
    assert all(str(path) not in rendered for path in (sheet, key, labels, receipt, out))
    assert "report_path" not in retained
    return {
        "kind": "quantfit.retained-label-functional-acceptance",
        "synthetic": True,
        "n_pairs": extracted["result"]["n_pairs"],
        "n_rows": retained["n_labeled"],
        "n_unusable": retained["n_unusable"],
        "retention": extracted["result"],
        "calibration": retained,
        "native_resolution": resolved["result"],
        "original_sheet_unavailable": not sheet.exists(),
        "legacy_statistics_equal": True,
        "human_labels_authenticated": False,
        "rater_identity_verified": False,
        "independence_verified": False,
        "scientific_go": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="quantfit-retained-private-") as name:
        result = run(args.checkout.resolve(), Path(name))
    raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out is not None:
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(raw)
    else:
        print(raw, end="")


if __name__ == "__main__":
    main()
