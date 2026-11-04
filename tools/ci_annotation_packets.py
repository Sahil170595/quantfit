"""Fictional full-population packet consumer; no human/model/browser execution here."""

from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

TEXTS = [
    "duplicate",
    "duplicate",
    "bare\rCR",
    "line\r\nend",
    "NUL\0tail",
    "雪🙂",
    "</script><script>bad()</script>",
    '=SUM("x",2),quoted',
]
CASES = (("mixed", "refusal"), ("zero", "compliance"), ("unusable", "unusable"))


def payload(page: Path) -> dict[str, Any]:
    match = re.search(
        r'<script type="application/json" id="annotation-data">(.*?)</script>', page.read_bytes().decode(), re.DOTALL
    )
    assert match
    data: dict[str, Any] = json.loads(match.group(1))
    assert set(data) == {"annotation_packet_schema", "rows", "filename", "max_csv_bytes"}
    assert data["annotation_packet_schema"] == 1 and data["max_csv_bytes"] == 8 * 1024 * 1024
    assert all(type(row) is list and len(row) == 2 and all(type(cell) is str for cell in row) for row in data["rows"])
    return data


def fixture(root: Path, mode: str) -> dict[str, Path]:
    from quantfit.safety import calibrate
    from quantfit.safety.annotation_chunks import prepare_annotation_chunks

    root.mkdir()
    paths = {
        "capture": root / "fictional.capture.jsonl",
        "sheet": root / "blank.labels.csv",
        "key": root / "private.labelkey.json",
        "manifest": root / "parts/annotation.chunkmanifest.json",
    }
    # Four actual declared pairs: two concordant/two discordant in mixed; zero
    # flagged pairs in zero. These are fixtures, not judge/model observations.
    a, b = ([False] * 4, [False] * 4) if mode == "zero" else ([True, True, False, False], [True, False, False, True])
    records = [
        {
            "capture_schema": 1,
            "created_utc": "2026-11-02T00:00:00Z",
            "baseline": "fictional/base",
            "quant": "fictional/quant",
            "n_pairs": 4,
        }
    ]
    records.extend(
        {"pair": i, "arm": arm, "judge_refusal": (a if j == 0 else b)[i], "completion": TEXTS[2 * i + j]}
        for i in range(4)
        for j, arm in enumerate(calibrate.ARMS)
    )
    paths["capture"].write_bytes(("\n".join(json.dumps(record) for record in records) + "\n").encode())
    calibrate.build_labeling_sheet(str(paths["capture"]), str(paths["sheet"]), str(paths["key"]))
    paths["manifest"].parent.mkdir()
    prepare_annotation_chunks(
        str(paths["sheet"]), str(paths["key"]), out_dir=str(paths["manifest"].parent), rows_per_part=3
    )
    key = json.loads(paths["key"].read_bytes())
    pairs = {(value["pair"], value["arm"]): value["judge_refusal"] for value in key["ids"].values()}
    assert sum(pairs[(i, "baseline")] != pairs[(i, "quantized")] for i in range(4)) == (0 if mode == "zero" else 2)
    assert len(key["ids"]) == 8
    return paths


def _produce(paths: dict[str, Path], out: Path, interface: str) -> dict[str, Any]:
    from quantfit.safety.annotation_packets import prepare_annotation_packets

    out.mkdir()
    if interface == "api":
        return prepare_annotation_packets(
            str(paths["sheet"]), str(paths["key"]), str(paths["manifest"]), out_dir=str(out)
        )
    child = subprocess.run(
        [
            sys.executable,
            "-B",
            "-X",
            "utf8",
            "-m",
            "quantfit.cli",
            "calibrate",
            "chunks",
            "packets",
            "--sheet",
            str(paths["sheet"]),
            "--key",
            str(paths["key"]),
            "--manifest",
            str(paths["manifest"]),
            "--out-dir",
            str(out),
            "--json",
        ],
        cwd=out.parent,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    assert child.returncode == 0 and not child.stderr, (child.returncode, child.stderr)
    document: dict[str, Any] = json.loads(child.stdout)
    assert document["exit_code"] == 0 and b"fictional/" not in child.stdout and b"duplicate" not in child.stdout
    result: dict[str, Any] = document["result"]
    return result


def _cli(arguments: list[str], cwd: Path, expected: int = 0) -> dict[str, Any]:
    child = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", "-m", "quantfit.cli", *arguments, "--json"],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    assert child.returncode == expected and not child.stderr, (child.returncode, child.stderr)
    result = json.loads(child.stdout)
    assert result["exit_code"] == expected
    return result.get("result") or result.get("error") or {}


def prepare_pages(checkout: Path, root: Path) -> dict[str, Any]:
    del checkout
    cases = []
    for index, (mode, label) in enumerate(CASES):
        paths = fixture(root / f"case-{index}", mode)
        before = {role: path.read_bytes() for role, path in paths.items()}
        api, cli = root / f"case-{index}/api", root / f"case-{index}/recipient"
        a, b = _produce(paths, api, "api"), _produce(paths, cli, "cli")
        assert a == b and a["n_rows"] == 8 and a["n_parts"] == 3
        public = json.dumps(a)
        private = json.loads(paths["key"].read_bytes())
        assert private["salt"] not in public and str(root) not in public
        assert all(ident not in public for ident in private["ids"])
        pages = sorted(cli.glob("*.annotation.html"))
        assert [p.read_bytes() for p in sorted(api.glob("*.annotation.html"))] == [p.read_bytes() for p in pages]
        data = [payload(page) for page in pages]
        assert [len(item["rows"]) for item in data] == [3, 3, 2]
        assert len({row[0] for item in data for row in item["rows"]}) == 8
        assert sorted(row[1] for item in data for row in item["rows"]) == sorted(TEXTS)
        assert all(path.read_bytes() == before[role] for role, path in paths.items())
        returned = root / f"case-{index}/returned"
        returned.mkdir()
        cases.append(
            {
                "index": index,
                "label": label,
                "pages": [str(page.relative_to(root)) for page in pages],
                "returns": [str((returned / item["filename"]).relative_to(root)) for item in data],
            }
        )
    # This browser controller input contains recipient paths and a public fixed
    # test choice only. Never private keys, source captures, manifests or arm maps.
    handoff = {"cases": cases}
    (root / "handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
    return handoff


def _receive(paths: dict[str, Path], returned: list[Path], root: Path, label: str | None) -> dict[str, Any]:
    from quantfit.safety.annotation_chunks import collect_annotation_chunks
    from quantfit.safety.calibrate import CalibrationError, ingest_labels
    from quantfit.safety.retained_labels import extract_labels, ingest_retained_labels

    original = {role: path.read_bytes() for role, path in paths.items()}
    full, receipt = root / "full.labels.csv", root / "collection.json"
    collection = collect_annotation_chunks(
        str(paths["sheet"]),
        str(paths["key"]),
        str(paths["manifest"]),
        tuple(str(p) for p in returned),
        out_path=str(full),
        receipt_path=str(receipt),
    )
    assert collection["n_rows"] == 8 and collection["n_unusable"] == (
        8 if label == "unusable" else 4 if label is None else 0
    )
    retained, retained_receipt = root / "retained.labels.csv", root / "retention.json"
    extract_labels(str(full), str(paths["key"]), out_path=str(retained), receipt_path=str(retained_receipt))
    direct, stripped = root / "calibration2.json", root / "calibration3.json"
    result: dict[str, Any]
    if label == "unusable":
        for call in (
            lambda: ingest_labels(str(full), str(paths["key"]), str(direct)),
            lambda: ingest_retained_labels(
                str(retained), str(retained_receipt), str(paths["key"]), out_path=str(stripped)
            ),
        ):
            try:
                call()
            except (CalibrationError, RuntimeError):
                pass
            else:
                raise AssertionError("all-unusable must refuse native calibration")
        assert not direct.exists() and not stripped.exists()
        result = {"n_rows": 8, "n_unusable": 8, "both_ingestions_refused": True}
    else:
        a = ingest_labels(str(full), str(paths["key"]), str(direct))
        b = ingest_retained_labels(str(retained), str(retained_receipt), str(paths["key"]), out_path=str(stripped))
        assert a["calibration_schema"] == 2 and b["calibration_schema"] == 3
        for arm in ("baseline", "quantized"):
            assert a[arm] == b[arm]
            block = a[arm]
            if label is None and arm == "baseline":
                assert block["n"] == 0 and block["n_unusable"] == 4 and block["epsilon"] is None
            else:
                assert block["n"] == 4 and block["n_unusable"] == 0
                assert block["human_refusals"] == (4 if label == "refusal" else 0)
                assert block["human_compliances"] == (0 if label == "refusal" else 4)
                assert block["judge_errors"] == (2 if label == "refusal" else 0)
            assert block["mde_epsilon_upper"] is None
            fc, fr = block["directional"]["false_compliance"], block["directional"]["false_refusal"]
            if label is None and arm == "baseline":
                assert fc["n"] == fr["n"] == fc["errors"] == fr["errors"] == 0
                assert fc["epsilon"] is fr["epsilon"] is None
            elif label == "refusal":
                assert fc["n"] == 4 and fc["errors"] == 2 and fc["epsilon"] == 0.5
                assert fr["n"] == fr["errors"] == 0 and fr["epsilon"] is None
            else:
                assert fr["n"] == 4 and fr["errors"] == 0 and fr["epsilon"] == 0.0
                assert fc["n"] == fc["errors"] == 0 and fc["epsilon"] is None
        assert a["unmeasured_arms"] == (["baseline"] if label is None else [])
        result = {
            "n_rows": 8,
            "n_unusable": a["n_unusable"],
            "baseline_n": a["baseline"]["n"],
            "quantized_n": a["quantized"]["n"],
            "schema2_schema3_arm_blocks_equal": True,
            "native_arm_blocks": {arm: a[arm] for arm in ("baseline", "quantized")},
            "unmeasured_arms": a["unmeasured_arms"],
        }
    assert all(path.read_bytes() == original[role] for role, path in paths.items())
    result["sources_held"] = True
    return result


def receive_pages(checkout: Path, root: Path) -> dict[str, Any]:
    del checkout
    handoff = json.loads((root / "handoff.json").read_bytes())
    results = []
    for case in handoff["cases"]:
        directory = root / f"case-{case['index']}"
        paths = {
            "capture": directory / "fictional.capture.jsonl",
            "sheet": directory / "blank.labels.csv",
            "key": directory / "private.labelkey.json",
            "manifest": directory / "parts/annotation.chunkmanifest.json",
        }
        results.append(_receive(paths, [root / p for p in case["returns"]], directory, case["label"]))
    return {
        "cases": results,
        "n_cases": 3,
        "n_parts": 9,
        "all_2N_rows_per_case": 8,
        "native_collect_then_separate_ingest": True,
        "source_authenticity_verified": False,
        "human_review_verified": False,
        "scientific_go": False,
    }


def _cli_receiving(root: Path) -> dict[str, Any]:
    directory = root / "case-0"
    key = directory / "private.labelkey.json"
    common = [
        "calibrate",
        "chunks",
        "collect",
        "--sheet",
        str(directory / "blank.labels.csv"),
        "--key",
        str(key),
        "--manifest",
        str(directory / "parts/annotation.chunkmanifest.json"),
    ]
    parts = sorted((directory / "returned").glob("*.labels.csv"))
    all_parts = [arg for part in parts for arg in ("--part", str(part))]
    full, receipt = directory / "cli-full.labels.csv", directory / "cli-collection.json"
    result = _cli([*common, *all_parts, "--out", str(full), "--receipt", str(receipt)], directory)
    assert result["n_rows"] == 8 and full.read_bytes() == (directory / "full.labels.csv").read_bytes()
    a = _cli(
        [
            "calibrate",
            "ingest",
            "--sheet",
            str(full),
            "--key",
            str(key),
            "--out",
            str(directory / "cli-calibration2.json"),
        ],
        directory,
    )
    labels, retention = directory / "cli-retained.labels.csv", directory / "cli-retention.json"
    _cli(
        [
            "calibrate",
            "extract",
            "--sheet",
            str(full),
            "--key",
            str(key),
            "--out",
            str(labels),
            "--receipt",
            str(retention),
        ],
        directory,
    )
    b = _cli(
        [
            "calibrate",
            "ingest",
            "--retained-labels",
            str(labels),
            "--retention-receipt",
            str(retention),
            "--key",
            str(key),
            "--out",
            str(directory / "cli-calibration3.json"),
        ],
        directory,
    )
    assert a["calibration_schema"] == 2 and b["calibration_schema"] == 3
    direct = json.loads((directory / "cli-calibration2.json").read_bytes())
    stripped = json.loads((directory / "cli-calibration3.json").read_bytes())
    assert all(direct[arm] == stripped[arm] for arm in ("baseline", "quantized"))
    bad_out, bad_receipt = directory / "bad-full.labels.csv", directory / "bad-collection.json"
    _cli([*common, *all_parts[:-2], "--out", str(bad_out), "--receipt", str(bad_receipt)], directory, 2)
    assert not bad_out.exists() and not bad_receipt.exists()
    mutated = directory / "changed.labels.csv"
    rows = list(csv.reader(io.StringIO(parts[0].read_bytes().decode(), newline="")))
    rows[1][1] += "ALTERED"
    buf = io.StringIO(newline="")
    csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(rows)
    mutated.write_bytes(buf.getvalue().encode())
    altered = [arg for part in [mutated, *parts[1:]] for arg in ("--part", str(part))]
    _cli([*common, *altered, "--out", str(bad_out), "--receipt", str(bad_receipt)], directory, 2)
    assert not bad_out.exists() and not bad_receipt.exists()
    # Strict supplied manifest type failure is refused by the new actual CLI.
    manifest = directory / "parts/annotation.chunkmanifest.json"
    original = manifest.read_bytes()
    bad = json.loads(original)
    bad["annotation_chunk_schema"] = True
    rejected = directory / "rejected-recipient"
    rejected.mkdir()
    try:
        manifest.write_text(json.dumps(bad), encoding="utf-8")
        _cli(
            [
                "calibrate",
                "chunks",
                "packets",
                "--sheet",
                str(directory / "blank.labels.csv"),
                "--key",
                str(key),
                "--manifest",
                str(manifest),
                "--out-dir",
                str(rejected),
            ],
            directory,
            2,
        )
        assert not list(rejected.iterdir())
    finally:
        manifest.write_bytes(original)
    return {
        "collect_exit": 0,
        "schema2_schema3_arm_blocks_equal": True,
        "missing_part_exit": 2,
        "changed_record_exit": 2,
        "typed_manifest_exit": 2,
        "no_refused_outputs": True,
    }


def run(checkout: Path, root: Path) -> dict[str, Any]:
    handoff = prepare_pages(checkout, root)
    for case in handoff["cases"]:
        for page, destination in zip(case["pages"], case["returns"], strict=True):
            data = payload(root / page)
            stream = io.StringIO(newline="")
            csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
                [["id", "completion", "human_label"], *[[*row, case["label"]] for row in data["rows"]]]
            )
            (root / destination).write_bytes(stream.getvalue().encode())
    result = receive_pages(checkout, root)
    # A separate maintainer-side control leaves exactly one arm unmeasured;
    # it is never a browser payload or an inferred automatic human judgment.
    paths = fixture(root / "one-empty", "zero")
    _produce(paths, root / "one-empty/recipient", "api")
    key = json.loads(paths["key"].read_bytes())
    returned = []
    for page in sorted((root / "one-empty/recipient").glob("*.annotation.html")):
        data = payload(page)
        stream = io.StringIO(newline="")
        csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
            [
                ["id", "completion", "human_label"],
                *[
                    [*row, "unusable" if key["ids"][row[0]]["arm"] == "baseline" else "compliance"]
                    for row in data["rows"]
                ],
            ]
        )
        destination = root / "one-empty" / data["filename"]
        destination.write_bytes(stream.getvalue().encode())
        returned.append(destination)
    result["one_empty_arm"] = _receive(paths, returned, root / "one-empty", None)
    result["actual_cli_receiving"] = _cli_receiving(root)
    result["transport"] = "stdlib explicit synthetic choices; NOT browser/human execution"
    result["api_cli_page_bytes_equal"] = True
    return result


def main() -> None:
    import argparse

    import quantfit

    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", type=Path)
    modes.add_argument("--receive", type=Path)
    args = parser.parse_args()
    package = Path(quantfit.__file__).resolve().parent

    def guard() -> int:
        assert not package.is_relative_to(args.checkout.resolve())
        modules = [
            module for name, module in tuple(sys.modules.items()) if name == "quantfit" or name.startswith("quantfit.")
        ]
        for module in modules:
            origin = getattr(module, "__file__", None)
            assert isinstance(origin, str) and Path(origin).resolve().is_relative_to(package)
        return len(modules)

    guard()
    value = prepare_pages(args.checkout, args.prepare) if args.prepare else receive_pages(args.checkout, args.receive)
    print(
        json.dumps(
            {
                "result": {"n_cases": 3, "n_parts": 9} if args.prepare else value,
                "actual_loaded_package_modules": guard(),
            }
        )
    )


if __name__ == "__main__":
    main()
