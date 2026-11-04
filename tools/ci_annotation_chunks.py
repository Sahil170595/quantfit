"""Installed CLI/API chunk/collect and unchanged native ingest, using fictional local text."""

from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any


def run(checkout: Path, root: Path) -> dict[str, Any]:
    from quantfit.safety.annotation_chunks import collect_annotation_chunks, prepare_annotation_chunks
    from quantfit.safety.calibrate import ingest_labels

    spec = importlib.util.spec_from_file_location("private_chunk_fixture", checkout / "tools/ci_label_review.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    sheet, _, key = helper.fixture(root / "private", checkout)
    rows = helper.read_rows(sheet)
    for row in rows[1:]:
        row[2] = ""
    helper.write_rows(sheet, rows, bom=True)
    original = [path.read_bytes() for path in (sheet, key)]
    directory = root / "parts"
    directory.mkdir()
    common = ["--sheet", str(sheet), "--key", str(key)]
    code, prepared, stderr = helper.invoke(
        ["calibrate", "chunks", "prepare", *common, "--out-dir", str(directory), "--rows-per-part", "5"]
    )
    assert code == 0 and not stderr and prepared["result"]["n_parts"] == 4
    parts = sorted(directory.glob("part-*.labels.csv"))
    for part in parts:
        helper.fill_fixture_review(part, key)
    manifest = directory / "annotation.chunkmanifest.json"
    full, receipt = root / "collected.labels.csv", root / "collection.json"
    collect_args = [
        "calibrate",
        "chunks",
        "collect",
        *common,
        "--manifest",
        str(manifest),
        "--out",
        str(full),
        "--receipt",
        str(receipt),
    ]
    for part in parts:
        collect_args += ["--part", str(part)]
    bad_args = collect_args[:-2]
    bad_code, refused, stderr = helper.invoke(bad_args)
    assert bad_code == 2 and not stderr and refused["error"]["message"] == "invalid_annotation_chunks"
    assert not full.exists() and not receipt.exists()
    code, collected, stderr = helper.invoke(collect_args)
    assert code == 0 and not stderr and collected["result"]["n_rows"] == 18
    code, ingested, stderr = helper.invoke(
        ["calibrate", "ingest", "--sheet", str(full), "--key", str(key), "--out", str(root / "native.json")]
    )
    assert code == 0 and not stderr
    native = ingested["result"]
    assert native["calibration_schema"] == 2 and native["n_labeled"] == 18 and native["n_unusable"] == 4
    retained, retention = root / "retained.labels.csv", root / "retention.json"
    code, _, stderr = helper.invoke(
        [
            "calibrate",
            "extract",
            "--sheet",
            str(full),
            "--key",
            str(key),
            "--out",
            str(retained),
            "--receipt",
            str(retention),
        ]
    )
    assert code == 0 and not stderr
    code, retained_ingest, stderr = helper.invoke(
        [
            "calibrate",
            "ingest",
            "--retained-labels",
            str(retained),
            "--retention-receipt",
            str(retention),
            "--key",
            str(key),
            "--out",
            str(root / "retained-native.json"),
        ]
    )
    assert code == 0 and not stderr and retained_ingest["result"]["calibration_schema"] == 3
    # Separate installed API path, including complete unusable collection and the
    # unchanged native refusal of an empty calibration measurement.
    api_dir = root / "api-parts"
    api_dir.mkdir()
    api_prepared = prepare_annotation_chunks(str(sheet), str(key), out_dir=str(api_dir), rows_per_part=7)
    api_parts = sorted(api_dir.glob("part-*.labels.csv"))
    for part in api_parts:
        helper.fill_fixture_review(part, key, labels=("unusable",) * 9)
    api_full = root / "api-collected.labels.csv"
    api_collected = collect_annotation_chunks(
        str(sheet),
        str(key),
        str(api_dir / "annotation.chunkmanifest.json"),
        tuple(map(str, api_parts)),
        out_path=str(api_full),
        receipt_path=str(root / "api-collection.json"),
    )
    assert api_collected["n_unusable"] == 18
    from quantfit.safety.calibrate import CalibrationError

    try:
        ingest_labels(str(api_full), str(key), str(root / "empty-calibration.json"))
    except CalibrationError:
        pass
    else:
        raise AssertionError("native all-unusable calibration was not refused")
    assert not (root / "empty-calibration.json").exists()
    assert [path.read_bytes() for path in (sheet, key)] == original
    public = json.dumps([prepared, collected, api_prepared, api_collected])
    private = json.loads(key.read_bytes())
    assert "PRIVATE_" not in public and private["salt"] not in public and str(root) not in public
    assert all(ident not in public for ident in private["ids"])
    return {
        "kind": "quantfit.annotation-chunks-functional-acceptance",
        "synthetic": True,
        "preparation": prepared["result"],
        "collection": collected["result"],
        "missing_part_exit_code": bad_code,
        "native_ingest_exit_code": code,
        "native_counts": {
            name: native[name] for name in ("calibration_schema", "n_labeled", "n_unusable", "unmeasured_arms")
        },
        "retained_calibration_schema": retained_ingest["result"]["calibration_schema"],
        "api_all_unusable": {
            "n_rows": api_collected["n_rows"],
            "n_unusable": api_collected["n_unusable"],
            "native_ingest_refused": True,
        },
        "originals_unchanged": True,
        "synthetic_operator_labels": True,
        "human_labels_authenticated": False,
        "rater_identity_verified": False,
        "scientific_go": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="quantfit-chunks-private-") as name:
        result = run(args.checkout.resolve(), Path(name))
    raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out is None:
        print(raw, end="")
    else:
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(raw)


if __name__ == "__main__":
    main()
