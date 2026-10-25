"""Fictional capture-backed retained review, with real CLI/API and native schema-3 consumers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, cast


def _fixture_module(checkout: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "private_retained_review_fixture", checkout / "tools/ci_label_review.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(checkout: Path, root: Path) -> dict[str, Any]:
    from quantfit.safety.retained_labels import extract_labels, ingest_retained_labels
    from quantfit.safety.retained_review import apply_retained_label_review, prepare_retained_label_review

    helper = _fixture_module(checkout)
    records = {}
    for interface in ("cli", "api"):
        local = root / interface
        local.mkdir()
        a, b, key = cast(tuple[Path, Path, Path], helper.fixture(local / "private", checkout))
        capture = local / "private/private.capture.jsonl"
        retained = []
        for name, sheet in (("a", a), ("b", b)):
            labels, receipt = local / f"{name}.labels.csv", local / f"{name}-retention.json"
            extract_labels(str(sheet), str(key), out_path=str(labels), receipt_path=str(receipt))
            retained += [labels, receipt]
        # ONLY this function's freshly generated fictional sheet files are removed.
        for path in (a, b, local / "private/pristine.labels.csv"):
            path.unlink()
        paths = (capture, key, *retained)
        sources = (str(capture), str(key), str(retained[0]), str(retained[1]), str(retained[2]), str(retained[3]))
        originals = [p.read_bytes() for p in paths]
        queue, preparation = local / "queue.labels.csv", local / "preparation.json"
        full, application = local / "full.labels.csv", local / "application.json"
        common = [
            "--input-mode",
            "retained",
            "--capture",
            str(capture),
            "--key",
            str(key),
            "--retained-labels-a",
            str(retained[0]),
            "--retention-receipt-a",
            str(retained[1]),
            "--retained-labels-b",
            str(retained[2]),
            "--retention-receipt-b",
            str(retained[3]),
        ]
        if interface == "cli":
            code, document, stderr = helper.invoke(
                ["calibrate", "review", "prepare", *common, "--sheet", str(queue), "--receipt", str(preparation)]
            )
            assert code == 0 and not stderr
            prepared = document["result"]
        else:
            prepared = prepare_retained_label_review(*sources, review_path=str(queue), receipt_path=str(preparation))
        assert prepared["n_selected"] == 12
        helper.fill_fixture_review(queue, key)  # Explicit manufactured labels, never a product adjudication rule.
        partial = local / "refused-partial.json"
        partial_code, _, _ = helper.invoke(
            ["calibrate", "ingest", "--sheet", str(queue), "--key", str(key), "--out", str(partial)]
        )
        assert partial_code == 2 and not partial.exists()
        if interface == "cli":
            code, document, stderr = helper.invoke(
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
            assert code == 0 and not stderr
            applied = document["result"]
        else:
            applied = apply_retained_label_review(
                *sources, str(queue), str(preparation), out_path=str(full), receipt_path=str(application)
            )
        assert applied["n_changed_vs_a"] == 10 and applied["n_unusable"] == 4
        new_labels, new_receipt = local / "new.labels.csv", local / "new-retention.json"
        calibration = local / "calibration.json"
        if interface == "cli":
            code, extracted, stderr = helper.invoke(
                [
                    "calibrate",
                    "extract",
                    "--sheet",
                    str(full),
                    "--key",
                    str(key),
                    "--out",
                    str(new_labels),
                    "--receipt",
                    str(new_receipt),
                ]
            )
            assert code == 0 and not stderr and extracted["result"]["inputs"]["sheet"] == applied["output_sheet"]
            code, document, stderr = helper.invoke(
                [
                    "calibrate",
                    "ingest",
                    "--retained-labels",
                    str(new_labels),
                    "--retention-receipt",
                    str(new_receipt),
                    "--key",
                    str(key),
                    "--out",
                    str(calibration),
                ]
            )
            assert code == 0 and not stderr
            # Native CLI deliberately omits model identity/arm blocks from stdout.
            # Inspect its actual emitted calibration file, without recomputing it.
            native = json.loads(calibration.read_bytes())
            assert all(
                native[name] == document["result"][name]
                for name in ("calibration_schema", "n_labeled", "n_unusable", "unmeasured_arms", "source")
            )
        else:
            extracted_receipt = extract_labels(
                str(full), str(key), out_path=str(new_labels), receipt_path=str(new_receipt)
            )
            assert extracted_receipt["inputs"]["sheet"] == applied["output_sheet"]
            native = ingest_retained_labels(str(new_labels), str(new_receipt), str(key), out_path=str(calibration))
        assert native["calibration_schema"] == 3 and native["n_labeled"] == 18 and native["n_unusable"] == 4
        assert native["baseline"]["n"] == native["quantized"]["n"] == 7
        assert [p.read_bytes() for p in paths] == originals
        assert not a.exists() and not b.exists()
        public = json.dumps([prepared, applied])
        private = json.loads(key.read_bytes())
        assert all(value not in public for value in ("PRIVATE_", str(root), private["salt"], *private["ids"]))
        records[interface] = {
            "preparation": prepared,
            "application": applied,
            "partial_review_native_ingest_exit_code": partial_code,
            "separate_truthful_extract_and_schema3": True,
            "native_counts": {
                name: native[name]
                for name in (
                    "calibration_schema",
                    "n_labeled",
                    "n_unusable",
                    "unmeasured_arms",
                    "baseline",
                    "quantized",
                )
            },
            "original_retained_inputs_unchanged": True,
            "original_synthetic_sheets_unavailable": True,
        }
    return {
        "kind": "quantfit.retained-review-functional-acceptance",
        "synthetic": True,
        "interfaces": records,
        "human_labels_authenticated": False,
        "source_authenticity_verified": False,
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
    with tempfile.TemporaryDirectory(prefix="quantfit-retained-review-private-") as name:
        result = run(args.checkout.resolve(), Path(name))
    raw = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out is None:
        print(raw, end="")
    else:
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(raw)


if __name__ == "__main__":
    main()
