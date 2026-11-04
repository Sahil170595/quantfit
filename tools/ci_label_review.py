"""Fictional local review judgments and native prepare/apply/ingest acceptance."""

from __future__ import annotations

import csv
import importlib.util
import io
import json
from pathlib import Path
from typing import Any, cast

FINAL = ("refusal", "compliance", "refusal", "unusable", "compliance", "refusal", "compliance", "refusal", "unusable")
A_LABELS = ("refusal",) * 3 + ("compliance",) * 3 + ("unusable",) * 3
B_LABELS = ("refusal", "compliance", "unusable") * 3


def read_rows(path: Path) -> list[list[str]]:
    return list(csv.reader(io.StringIO(path.read_bytes().decode("utf-8-sig"), newline="")))


def write_rows(path: Path, rows: list[list[str]], *, bom: bool = False) -> None:
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + buffer.getvalue().encode("utf-8"))


def fixture(root: Path, checkout: Path, *, mode: str = "mixed", key_kind: str = "bound-v2") -> tuple[Path, Path, Path]:
    spec = importlib.util.spec_from_file_location(
        "private_review_fixture", checkout / "tools/ci_label_reconciliation.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first, second, key, _ = cast(
        tuple[Path, Path, Path, dict[str, Any]],
        module.fixture(root, checkout, n=9, mode="agreement", key_kind=key_kind),
    )
    ids = json.loads(key.read_bytes())["ids"]
    for path, original in ((first, True), (second, False)):
        rows = read_rows(path)
        for row in rows[1:]:
            pair = ids[row[0]]["pair"]
            if mode == "all-disagree":
                row[2] = "refusal" if original else "compliance"
            elif mode == "all-unusable":
                row[2] = "unusable"
            else:
                assert mode in {"mixed", "zero"}
                row[2] = A_LABELS[pair] if original or mode == "zero" else B_LABELS[pair]
        write_rows(path, rows)
    return first, second, key


def fill_fixture_review(path: Path, key: Path, *, labels: tuple[str, ...] = FINAL) -> None:
    """Explicit manufactured judgments for fictional inputs only, never a product policy."""
    ids = json.loads(key.read_bytes())["ids"]
    rows = read_rows(path)
    for row in rows[1:]:
        row[2] = labels[ids[row[0]]["pair"]]
    write_rows(path, rows)


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
    first, second, key = fixture(root / "private", checkout)
    original_bytes = [path.read_bytes() for path in (first, second, key)]
    queue, preparation = root / "private.review.labels.csv", root / "preparation.json"
    common = ["--sheet-a", str(first), "--sheet-b", str(second), "--key", str(key)]
    code, prepared, stderr = invoke(
        ["calibrate", "review", "prepare", *common, "--sheet", str(queue), "--receipt", str(preparation)]
    )
    assert code == 0 and not stderr and prepared["result"]["n_selected"] == 12
    fill_fixture_review(queue, key)  # Explicit manufactured judgments, never a software adjudication rule.
    partial = root / "refused-partial.json"
    partial_code, _, _ = invoke(
        ["calibrate", "ingest", "--sheet", str(queue), "--key", str(key), "--out", str(partial)]
    )
    assert partial_code == 2 and not partial.exists()
    full, application = root / "private.reviewed.labels.csv", root / "application.json"
    code, applied, stderr = invoke(
        [
            "calibrate",
            "review",
            "apply",
            *common,
            "--review",
            str(queue),
            "--preparation",
            str(preparation),
            "--out",
            str(full),
            "--receipt",
            str(application),
        ]
    )
    assert code == 0 and not stderr and applied["result"]["n_changed_vs_a"] == 10
    calibration = root / "calibration.json"
    code, ingested, stderr = invoke(
        ["calibrate", "ingest", "--sheet", str(full), "--key", str(key), "--out", str(calibration)]
    )
    assert code == 0 and not stderr
    native = ingested["result"]
    assert native["calibration_schema"] == 2 and native["n_labeled"] == 18 and native["n_unusable"] == 4
    assert [path.read_bytes() for path in (first, second, key)] == original_bytes
    rendered = json.dumps([prepared, applied])
    private = json.loads(key.read_bytes())
    assert "PRIVATE_" not in rendered and private["salt"] not in rendered
    assert all(row_id not in rendered for row_id in private["ids"])
    assert all(str(path) not in rendered for path in (first, second, key, queue, preparation, full, application))
    binding = native["binding"]
    # Native FILE/API retains its full declared scope. Public acceptance records
    # whitelist counts/source hashes/fingerprint and never echo native model paths.
    return {
        "kind": "quantfit.label-review-functional-acceptance",
        "synthetic": True,
        "n_pairs": 9,
        "n_rows": 18,
        "preparation": prepared["result"],
        "application": applied["result"],
        "partial_review_native_ingest_exit_code": partial_code,
        "complete_reviewed_native_ingest_exit_code": code,
        "native_ingest_counts": {
            name: native[name]
            for name in (
                "calibration_schema",
                "n_labeled",
                "n_unusable",
                "unmeasured_arms",
                "baseline",
                "quantized",
                "source",
            )
        },
        "binding_fingerprint": binding["fingerprint"] if binding is not None else None,
        "originals_unchanged": True,
        "synthetic_operator_labels": True,
        "human_labels_authenticated": False,
        "independent_adjudication": False,
        "scientific_go": False,
    }


def main() -> None:
    import argparse
    import tempfile

    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="quantfit-review-private-") as name:
        result = run(args.checkout.resolve(), Path(name))
    raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out is None:
        print(raw, end="")
    else:
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(raw)


if __name__ == "__main__":
    main()
