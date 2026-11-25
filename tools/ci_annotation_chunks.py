"""Installed CLI/API chunk/collect and unchanged native ingest, using fictional local text."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


def _indexed_collection(args: list[str], parts: list[Path], root: Path, sheet: Path, receipt: Path) -> dict[str, Any]:
    renamed = []
    for index, part in enumerate(parts, 1):
        path = root / f"returned={index}.csv"
        path.write_bytes(part.read_bytes())
        renamed.append(path)

    cases = (
        ("reversed", tuple(reversed(range(1, len(renamed) + 1))), 0),
        ("missing", (4, 2, 1), 2),
        ("duplicate", (4, 3, 2, 2), 2),
        ("wrong_assignment", (4, 3, 1, 2), 2),
    )
    recorded = {}
    for name, indices, expected in cases:
        output, evidence = root / f"{name}.labels.csv", root / f"{name}.json"
        options: list[str] = []
        sources = reversed(renamed) if name == "wrong_assignment" else (renamed[i - 1] for i in indices)
        for index, source in zip(indices, sources, strict=True):
            options.extend(["--indexed-part", f"{index}={source}"])
        run = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-m",
                "quantfit.cli",
                *args,
                *options,
                "--out",
                str(output),
                "--receipt",
                str(evidence),
                "--json",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=30,
        )
        document = json.loads(run.stdout)
        assert run.returncode == document["exit_code"] == expected and not run.stderr
        if expected == 0:
            assert output.read_bytes() == sheet.read_bytes() and evidence.read_bytes() == receipt.read_bytes()
            result = document["result"]
            assert result == json.loads(evidence.read_bytes())
            assert [part["index"] for part in result["parts"]] == list(range(1, len(parts) + 1))
            recorded[name] = {
                "exit_code": run.returncode,
                "n_rows": result["n_rows"],
                "n_parts": result["n_parts"],
                "n_unusable": result["n_unusable"],
                "part_indices": indices,
                "sheet_and_receipt_byte_parity": True,
            }
        else:
            assert document["error"]["message"] == "invalid_annotation_chunks"
            assert not output.exists() and not evidence.exists()
            recorded[name] = {"exit_code": run.returncode, "part_indices": indices, "outputs_present": False}
    assert all(local.read_bytes() == part.read_bytes() for local, part in zip(renamed, parts, strict=True))
    return recorded


def run(checkout: Path, root: Path) -> dict[str, Any]:
    from quantfit.safety.annotation_chunks import (
        collect_annotation_chunks,
        prepare_annotation_chunks,
        validate_annotation_returns,
    )
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
    validate_args = ["calibrate", "chunks", "validate", *common, "--manifest", str(manifest)]
    code, partial, stderr = helper.invoke(
        [
            *validate_args,
            "--part",
            f"4={parts[3]}",
            "--part",
            f"2={parts[1]}",
            "--out",
            str(root / "partial-inspection.json"),
        ]
    )
    assert code == 0 and not stderr
    assert partial["result"]["received_part_indices"] == [2, 4]
    assert partial["result"]["missing_part_indices"] == [1, 3]
    assert partial["result"]["n_received_rows"] == 8 and partial["result"]["complete"] is False
    required_xml = root / "required-partial.xml"
    required_args = [
        *validate_args,
        "--part",
        f"4={parts[3]}",
        "--part",
        f"2={parts[1]}",
        "--require-complete",
        "--out",
        str(root / "required-partial.json"),
        "--junit",
        str(required_xml),
    ]
    required_code, required_partial, stderr = helper.invoke(required_args)
    assert required_code == 4 and not stderr
    assert required_partial["result"]["completeness_requirement"]["exit_code"] == 4
    assert [case.get("name") for case in ET.fromstring(required_xml.read_bytes()).iter("testcase")] == [
        "overall",
        "1",
        "2",
        "3",
        "4",
    ]
    # Actual OS subprocess, distinct from this consumer's in-process dispatch seam.
    os_cli = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "quantfit.cli",
            *validate_args,
            "--part",
            f"2={parts[1]}",
            "--require-complete",
            "--out",
            str(root / "os-cli-required.json"),
            "--junit",
            str(root / "os-cli-required.xml"),
            "--json",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    assert os_cli.returncode == 4 and not os_cli.stderr
    os_required = json.loads(os_cli.stdout)
    assert os_required["result"]["completeness_requirement"]["exit_code"] == os_required["exit_code"] == 4
    assert os_required["result"] == json.loads((root / "os-cli-required.json").read_bytes())
    all_args = [*validate_args, "--out", str(root / "complete-inspection.json")]
    for index in reversed(range(len(parts))):
        all_args += ["--part", f"{index + 1}={parts[index]}"]
    code, inspected, stderr = helper.invoke(all_args)
    assert code == 0 and not stderr and inspected["result"]["complete"] is True
    assert inspected["result"]["n_received_rows"] == 18 and inspected["result"]["missing_part_indices"] == []
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
    indexed = _indexed_collection(
        ["calibrate", "chunks", "collect", *common, "--manifest", str(manifest)], parts, root, full, receipt
    )
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
    api_inspected = validate_annotation_returns(
        str(sheet), str(key), str(api_dir / "annotation.chunkmanifest.json"), ((2, str(api_parts[1])),)
    )
    assert api_inspected["complete"] is False and api_inspected["n_received_rows"] == 7
    api_complete = validate_annotation_returns(
        str(sheet),
        str(key),
        str(api_dir / "annotation.chunkmanifest.json"),
        tuple((index + 1, str(part)) for index, part in reversed(list(enumerate(api_parts)))),
        require_complete=True,
        junit_path=str(root / "api-all-unusable.xml"),
    )
    assert api_complete["complete"] and api_complete["completeness_requirement"]["exit_code"] == 0
    assert len(list(ET.fromstring((root / "api-all-unusable.xml").read_bytes()).iter("testcase"))) == len(api_parts) + 1

    api_full = root / "api-collected.labels.csv"
    api_collected = collect_annotation_chunks(
        str(sheet),
        str(key),
        str(api_dir / "annotation.chunkmanifest.json"),
        indexed_parts=tuple((index, str(part)) for index, part in reversed(list(enumerate(api_parts, 1)))),
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
    public = (
        json.dumps(
            [
                prepared,
                partial,
                inspected,
                collected,
                api_prepared,
                api_inspected,
                api_collected,
                required_partial,
                os_required,
                api_complete,
            ]
        )
        + required_xml.read_text(encoding="utf-8")
        + (root / "api-all-unusable.xml").read_text(encoding="utf-8")
    )
    private = json.loads(key.read_bytes())
    assert "PRIVATE_" not in public and private["salt"] not in public and str(root) not in public
    assert all(ident not in public for ident in private["ids"])
    return {
        "kind": "quantfit.annotation-chunks-functional-acceptance",
        "synthetic": True,
        "preparation": prepared["result"],
        "collection": collected["result"],
        "indexed_collection": indexed,
        "return_validation": {
            "partial": partial["result"],
            "complete": inspected["result"],
            "api_unusable_subset": api_inspected,
            "required_partial": required_partial["result"],
            "api_unusable_complete": api_complete,
            "os_cli_required_partial": os_required["result"],
        },
        "missing_part_exit_code": bad_code,
        "required_missing_exit_code": required_code,
        "os_cli_required_exit_code": os_cli.returncode,
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
