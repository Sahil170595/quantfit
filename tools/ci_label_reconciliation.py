"""Private synthetic SDK fixtures and aggregate-only label-reconciliation consumers."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path

LABELS = ("refusal", "compliance", "unusable")
ARMS = ("baseline", "quantized")
A = {arm: ("refusal",) * 3 + ("compliance",) * 3 + ("unusable",) * 3 for arm in ARMS}
B = {
    "baseline": (
        "refusal",
        "refusal",
        "compliance",
        "compliance",
        "unusable",
        "unusable",
        "refusal",
        "unusable",
        "unusable",
    ),
    "quantized": (
        "compliance",
        "unusable",
        "unusable",
        "refusal",
        "refusal",
        "unusable",
        "refusal",
        "compliance",
        "compliance",
    ),
}
MARKER = "PRIVATE_SYNTHETIC_SENTINEL_DO_NOT_REFLECT"


def binding(raw: bytes) -> dict:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def encode(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def read_rows(path: Path) -> list[list[str]]:
    with io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="") as stream:
        return list(csv.reader(stream))


def write_rows(path: Path, rows: list[list[str]], *, bom: bool = False) -> None:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerows(rows)
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + stream.getvalue().encode())


def fixture(
    root: Path,
    checkout: Path,
    *,
    n: int = 9,
    mode: str = "directed",
    key_kind: str = "bound-v2",
    reverse_b: bool = False,
    bom_b: bool = False,
) -> tuple[Path, Path, Path, dict]:
    """Create captures/key/sheets ONLY in the caller's private temporary directory.

    The native blinding producer draws its real fresh salt. No RNG is patched.
    Fictional labels and private text are generated locally, without model work.
    """
    from quantfit.resolution import parse_report_bytes
    from quantfit.safety.calibrate import build_labeling_sheet
    from quantfit.safety.verify import Probe, _write_capture

    root.mkdir(parents=True)
    prototype = checkout / "validation/2026-10-18-screen-bundle/inputs/reports/clean.json"
    report = parse_report_bytes(prototype.read_bytes())
    report = replace(report, probe_dataset={**report.probe_dataset, "n_probes": n}, drift={})
    capture, pristine, key = (
        root / "private.capture.jsonl",
        root / "pristine.labels.csv",
        root / "private.labelkey.json",
    )
    probes = [Probe(f"fictional private probe {i}", "clear_safe", "safe") for i in range(n)]
    outputs = {arm: [f'{MARKER} {arm} {i}, "quoted"\nsynthetic local-only line' for i in range(n)] for arm in ARMS}
    _write_capture(
        str(capture),
        probes,
        report.baseline.model,
        report.quantized.model,
        outputs["baseline"],
        outputs["quantized"],
        [i % 2 == 0 for i in range(n)],
        [i % 2 == 1 for i in range(n)],
        actual_report=report if key_kind == "bound-v2" else None,
    )
    build_labeling_sheet(str(capture), str(pristine), str(key))
    payload = json.loads(key.read_bytes())
    if key_kind == "legacy-v1":
        payload = {name: payload[name] for name in ("key_schema", "capture", "salt", "ids")}
        payload["key_schema"] = 1
        key.write_bytes(encode(payload))
    elif key_kind != "bound-v2":
        assert key_kind == "unbound-v2" and payload["binding"] is None
    labels_a = {arm: ["unusable" if mode == "unusable" else A[arm][i % 9] for i in range(n)] for arm in ARMS}
    labels_b = {
        arm: [
            "unusable" if mode == "unusable" else A[arm][i % 9] if mode == "agreement" else B[arm][i % 9]
            for i in range(n)
        ]
        for arm in ARMS
    }
    assert mode in {"directed", "agreement", "unusable"}
    table = read_rows(pristine)
    first, second = root / "sheet-a.labels.csv", root / "sheet-b.labels.csv"
    for path, labels, reverse, bom in ((first, labels_a, False, False), (second, labels_b, reverse_b, bom_b)):
        filled = [
            [row_id, value, labels[payload["ids"][row_id]["arm"]][payload["ids"][row_id]["pair"]]]
            for row_id, value, _ in table[1:]
        ]
        write_rows(path, [table[0], *(reversed(filled) if reverse else filled)], bom=bom)
    expected = {arm: expected_arm(labels_a[arm], labels_b[arm]) for arm in ARMS}
    return first, second, key, expected


def expected_arm(first: list[str], second: list[str]) -> dict:
    """Count literal fictional label pairs; no native reconciliation or ingest oracle."""
    matrix = [
        [sum(a == row and b == column for a, b in zip(first, second, strict=True)) for column in LABELS]
        for row in LABELS
    ]
    usable = sum(matrix[i][j] for i in range(2) for j in range(2))
    agreement = matrix[0][0] + matrix[1][1]
    return {
        "matrix": matrix,
        "n_rows": len(first),
        "n_both_usable": usable,
        "n_usable_agreement": agreement,
        "n_usable_disagreement": usable - agreement,
        "n_one_unusable": sum(matrix[2][j] + matrix[j][2] for j in range(2)),
        "n_both_unusable": matrix[2][2],
        "usable_agreement_rate": agreement / usable if usable else None,
    }


def invoke(first: Path, second: Path, key: Path, out: Path) -> tuple[dict, str]:
    from quantfit.cli import main

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(
            [
                "calibrate",
                "reconcile",
                "--sheet-a",
                str(first),
                "--sheet-b",
                str(second),
                "--key",
                str(key),
                "--out",
                str(out),
                "--json",
            ]
        )
    document = json.loads(stdout.getvalue())
    assert document["exit_code"] == code and document["command"] == (
        "calibrate reconcile" if code == 0 else "calibrate"
    )
    return document, stderr.getvalue()


def assert_private_not_reflected(value: dict, stderr: str, key_raw: bytes) -> None:
    key = json.loads(key_raw)
    rendered = json.dumps(value) + stderr
    assert MARKER not in rendered and key["salt"] not in rendered
    for row_id, entry in key["ids"].items():
        assert row_id not in rendered and entry["completion_sha256"] not in rendered
    for field in (
        "completion",
        "completion_sha256",
        "salt",
        "ids",
        "human_label",
        "capture_path",
        "sheet_path",
        "key_path",
    ):
        assert f'"{field}"' not in rendered


def check(document: dict, first: Path, second: Path, key: Path, expected: dict) -> dict:
    assert document["exit_code"] == 0
    result = document["result"]
    assert result["label_reconciliation_schema_version"] == 1 and result["kind"] == "quantfit.label-reconciliation"
    assert result["label_order"] == list(LABELS)
    assert result["arms"] == expected
    n = expected["baseline"]["n_rows"]
    assert result["n_pairs"] == n and result["n_rows"] == 2 * n
    assert result["inputs"] == {
        name: binding(path.read_bytes()) for name, path in (("sheet_a", first), ("sheet_b", second), ("key", key))
    }
    assert result["identical_sheet_bytes"] is (first.read_bytes() == second.read_bytes())
    for field in (
        "rater_identity_verified",
        "human_labels_authenticated",
        "independence_verified",
        "consensus_calibration",
        "scientific_go",
    ):
        assert result[field] is False
    assert result["scope"] and result["limits"] == {
        "key_bytes": 2097152,
        "sheet_bytes": 8388608,
        "total_input_bytes": 18874368,
        "max_pairs": 4096,
        "max_ids": 8192,
        "max_csv_records": 16385,
    }
    return {
        "exit_code": 0,
        "n_pairs": n,
        "n_rows": 2 * n,
        "inputs": result["inputs"],
        "arms": result["arms"],
        "identical_sheet_bytes": result["identical_sheet_bytes"],
        "human_labels_authenticated": False,
        "independence_verified": False,
        "consensus_calibration": False,
        "scientific_go": False,
    }
