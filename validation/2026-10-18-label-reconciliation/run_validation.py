"""Record aggregate-only real CLI outcomes; native SDK inputs stay in separate private temporary storage."""

from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import importlib.util
import json
import platform
from pathlib import Path
from unittest.mock import patch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--private-work", type=Path, required=True)
    parser.add_argument("--expected-source", type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    checkout = here.parents[1]
    spec = importlib.util.spec_from_file_location(
        "reconciliation_consumer", checkout / "tools/ci_label_reconciliation.py"
    )
    assert spec is not None and spec.loader is not None
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    import quantfit

    expected_source = (args.expected_source or checkout).resolve()
    assert Path(quantfit.__file__).resolve() == expected_source / "quantfit/__init__.py", (
        "unexpected application origin"
    )
    assert quantfit.__version__ == importlib.metadata.version("quantfit")
    output, private = args.out.resolve(), args.private_work.resolve()
    assert not private.is_relative_to(checkout) and not private.is_relative_to(expected_source)
    assert not private.is_relative_to(output) and not output.is_relative_to(private)
    output.mkdir(parents=True, exist_ok=False)
    private.mkdir(parents=True, exist_ok=False)
    records = {}

    def retain(name: str, value: dict) -> None:
        (output / name).write_bytes(consumer.encode(value))

    def inputs(paths: tuple[Path, Path, Path]) -> dict:
        return {
            name: consumer.binding(path.read_bytes())
            for name, path in zip(("sheet_a", "sheet_b", "key"), paths, strict=True)
        }

    with contextlib.ExitStack() as stack:
        traps = [
            stack.enter_context(patch(name, side_effect=AssertionError("unexpected model, assets or label ingestion")))
            for name in (
                "quantfit.safety.verify.verify_safety",
                "quantfit.safety.gguf_arm.resolve_pair",
                "huggingface_hub.hf_hub_download",
                "quantfit.safety.calibrate.ingest_labels",
            )
        ]
        directed = consumer.fixture(private / "directed", checkout)
        self_control = consumer.fixture(private / "self-control", checkout)
        variants = {
            "directed": directed,
            "swapped": (
                directed[1],
                directed[0],
                directed[2],
                {arm: consumer.expected_arm(list(consumer.B[arm]), list(consumer.A[arm])) for arm in consumer.ARMS},
            ),
            "agreement": consumer.fixture(private / "agreement", checkout, mode="agreement"),
            "all-unusable": consumer.fixture(private / "all-unusable", checkout, mode="unusable"),
            "self-control": (
                self_control[0],
                self_control[0],
                self_control[2],
                {arm: consumer.expected_arm(list(consumer.A[arm]), list(consumer.A[arm])) for arm in consumer.ARMS},
            ),
            "bom-reordered": consumer.fixture(private / "bom-reordered", checkout, reverse_b=True, bom_b=True),
            "unbound-v2": consumer.fixture(private / "unbound-v2", checkout, key_kind="unbound-v2"),
            "legacy-v1": consumer.fixture(private / "legacy-v1", checkout, key_kind="legacy-v1"),
        }
        for label, (first, second, key, expected) in variants.items():
            before = inputs((first, second, key))
            document, stderr = consumer.invoke(first, second, key, output / f"{label}.json")
            records[label] = consumer.check(document, first, second, key, expected)
            consumer.assert_private_not_reflected(document, stderr, key.read_bytes())
            assert str(private) not in json.dumps(document) + stderr
            assert inputs((first, second, key)) == before
            assert json.loads((output / f"{label}.json").read_bytes()) == document["result"]
            retain(f"{label}-cli.json", document)
        for label in ("missing-id", "changed-value", "invalid-legacy-population", "record-budget", "output-alias"):
            first, second, key, _ = consumer.fixture(
                private / label, checkout, key_kind="legacy-v1" if label == "invalid-legacy-population" else "bound-v2"
            )
            if label in {"missing-id", "changed-value"}:
                table = consumer.read_rows(second)
                if label == "missing-id":
                    table.pop()
                else:
                    table[1][1] += " changed"
                consumer.write_rows(second, table)
            elif label == "invalid-legacy-population":
                value = json.loads(key.read_bytes())
                value["capture"]["n_pairs"] = True
                key.write_bytes(consumer.encode(value))
            elif label == "record-budget":
                count = len(consumer.read_rows(second))
                second.write_bytes(second.read_bytes() + b"\n" * (16386 - count))
            before = inputs((first, second, key))
            destination = key if label == "output-alias" else output / f"{label}-must-not-exist.json"
            with contextlib.ExitStack() as probe:
                sdk = (
                    probe.enter_context(
                        patch(
                            "quantfit.safety.calibrate._read_key",
                            side_effect=AssertionError("SDK before population preflight"),
                        )
                    )
                    if label == "invalid-legacy-population"
                    else None
                )
                document, stderr = consumer.invoke(first, second, key, destination)
            if sdk is not None:
                sdk.assert_not_called()
            assert document["exit_code"] == 2 and document["result"] is None
            assert label == "output-alias" or not destination.exists()
            assert inputs((first, second, key)) == before
            consumer.assert_private_not_reflected(document, stderr, key.read_bytes())
            assert str(private) not in json.dumps(document) + stderr
            retain(f"{label}-refusal.json", document)
            records[label] = {"exit_code": 2, "inputs": before, "private_bytes_unchanged": True}
            if sdk is not None:
                records[label]["sdk_key_parse_calls"] = 0
        for trap in traps:
            trap.assert_not_called()
        dependencies = {}
        for name in ("torch", "transformers", "huggingface_hub", "pytest"):
            try:
                dependencies[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                dependencies[name] = None
        records["runtime"] = {
            "source_version": quantfit.__version__,
            "distribution_version": importlib.metadata.version("quantfit"),
            "source_origin_verified": True,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "dependencies": dependencies,
            "source_files": {
                name: consumer.binding((expected_source / "quantfit" / name).read_bytes())
                for name in (
                    "__init__.py",
                    "cli.py",
                    "safety/reconcile.py",
                    "safety/calibrate.py",
                    "safety/calibration_binding.py",
                    "safety/verify.py",
                )
            },
        }
        records["limits"] = {
            "fictional_labels": True,
            "private_inputs_published": False,
            "per_row_identifiers_published": False,
            "model_or_judge_calls": 0,
            "model_arm_resolution_or_download_calls": 0,
            "ingestion_calls": 0,
            "human_labels_authenticated": False,
            "independence_verified": False,
            "consensus_calibration": False,
            "scientific_go": False,
            "proof": "source CLI aggregate/hash receiving; installed wheel qualification separate",
            "reproduction": "Fresh native blinding salts change private input hashes on rerun; label plans and aggregate counts are reproducible.",
            "private_provenance_limit": "Whole-input hashes identify this private local run; without the private files they cannot authenticate or recover the sheets or key.",
        }
        retain("receipt.json", records)
    print(
        json.dumps(
            {
                "source_version": quantfit.__version__,
                "descriptive_exits": [records[name]["exit_code"] for name in variants],
                "refusal_exits": [2] * 5,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
