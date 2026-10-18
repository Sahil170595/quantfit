"""Actual offline comparison CLI records from literal, explicitly synthetic native observations."""

from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import importlib.util
import json
import os
import platform
from pathlib import Path
from unittest.mock import patch


@contextlib.contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expected-source", type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    checkout = here.parents[1]
    spec = importlib.util.spec_from_file_location("comparison_consumer", checkout / "tools/ci_screen_compare.py")
    assert spec is not None and spec.loader is not None
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    import quantfit

    expected_source = (args.expected_source or checkout).resolve()
    assert Path(quantfit.__file__).resolve() == expected_source / "quantfit/__init__.py", (
        "unexpected application origin"
    )
    manifest = (here / "inputs/targets.json").read_bytes()
    names = [target["name"] for target in json.loads(manifest)["targets"]]
    original = {name: (here / "inputs/original" / f"{name}.json").read_bytes() for name in names}
    measured = {name: (here / "inputs/measured" / f"{name}.json").read_bytes() for name in names}
    introduced = {**measured, "clean": (here / "inputs/new-flag/clean.json").read_bytes()}
    unknown = {**measured, "clean": (here / "inputs/unknown-identity/clean.json").read_bytes()}
    contradicted = {**measured, "clean": (here / "inputs/known-identity/clean.json").read_bytes()}
    missing = {name: raw for name, raw in measured.items() if name != "flagged"}
    variants = {
        "measured": measured,
        "introduced": introduced,
        "original": original,
        "missing": missing,
        "unknown-identity": unknown,
        "known-identity": contradicted,
    }
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    records = {}

    def retain(name: str, value: dict) -> None:
        (output / name).write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())

    with working_directory(output), contextlib.ExitStack() as stack:
        traps = [
            stack.enter_context(patch(name, side_effect=AssertionError("unexpected inference or assets")))
            for name in (
                "quantfit.safety.verify.verify_safety",
                "quantfit.safety.gguf_arm.resolve_pair",
                "huggingface_hub.hf_hub_download",
            )
        ]
        bundles = {
            name: consumer.make_bundle(Path("build") / name, manifest, reports) for name, reports in variants.items()
        }
        bundles["byte-different-targets"] = consumer.make_bundle(
            Path("build/byte-different-targets"), manifest + b" ", measured
        )
        before = {path: path.read_bytes() for root in bundles.values() for path in root.rglob("*") if path.is_file()}
        for label, reference, candidate, code in (
            ("conditional-copy", "measured", "measured", 0),
            ("introduced-flag", "measured", "introduced", 3),
            ("apparent-clearance", "original", "measured", 3),
            ("original-copy", "original", "original", 3),
            ("missing-evidence", "measured", "missing", 4),
            ("known-identity", "measured", "known-identity", 4),
            ("unknown-identity", "measured", "unknown-identity", 0),
        ):
            out, junit = Path(f"{label}.json"), Path(f"{label}.xml")
            document, _ = consumer.invoke(bundles[reference], bundles[candidate], out=out, junit=junit)
            compact = consumer.check(
                document,
                bundles[reference],
                bundles[candidate],
                manifest,
                {"reference": variants[reference], "candidate": variants[candidate]},
                code=code,
            )
            assert json.loads(out.read_bytes()) == document["result"]
            records[label] = {
                **compact,
                "junit": consumer.check_junit(junit, document),
                "reference_bundle": reference,
                "candidate_bundle": candidate,
            }
            retain(f"{label}-cli.json", document)
        mismatch, _ = consumer.invoke(
            bundles["measured"], bundles["byte-different-targets"], out=Path("refused.json"), junit=Path("refused.xml")
        )
        assert mismatch["exit_code"] == 2 and not Path("refused.json").exists() and not Path("refused.xml").exists()
        retain("target-bytes-refusal.json", mismatch)
        alias, _ = consumer.invoke(
            bundles["measured"], bundles["measured"], out=bundles["measured"] / "reports/clean.json"
        )
        assert alias["exit_code"] == 2
        retain("output-alias-refusal.json", alias)
        assert all(path.read_bytes() == raw for path, raw in before.items())
        for trap in traps:
            trap.assert_not_called()
        records["refusals"] = {"target_bytes_exit": 2, "output_alias_exit": 2, "all_bundle_bytes_unchanged": True}
        records["inputs"] = {
            "targets": consumer.binding(manifest),
            "variants": {
                name: [{"name": target, **consumer.binding(raw)} for target, raw in reports.items()]
                for name, reports in variants.items()
            },
        }
        records["bundles"] = {
            name: [
                {"path": p.relative_to(root).as_posix(), **consumer.binding(p.read_bytes())}
                for p in sorted(root.rglob("*"))
                if p.is_file()
            ]
            for name, root in bundles.items()
        }
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
                    "saved_screen.py",
                    "screen_bundle.py",
                    "screen_bundle_inputs.py",
                    "screen_bundle_publication.py",
                    "screen_compare.py",
                    "screen_compare_junit.py",
                )
            },
        }
        records["limits"] = {
            "synthetic_observations": True,
            "model_or_judge_calls": 0,
            "resolution_or_download_calls": 0,
            "weights_authenticated": False,
            "independent_execution_verified": False,
            "human_labels_authenticated": False,
            "sensitivity_established": False,
            "scientific_go": False,
            "proof": "source CLI/JSON/XML and aggregate transport; not installed wheel or real CPU inference",
        }
        retain("receipt.json", records)
    print(
        json.dumps(
            {
                "source_version": quantfit.__version__,
                "comparison_exits": [
                    records[name]["exit_code"]
                    for name in (
                        "conditional-copy",
                        "introduced-flag",
                        "apparent-clearance",
                        "original-copy",
                        "missing-evidence",
                        "known-identity",
                        "unknown-identity",
                    )
                ],
                "refusal_exits": [2, 2],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
