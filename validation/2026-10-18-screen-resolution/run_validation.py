"""Record actual screen-summary CLI annotations from literal synthetic aggregate inputs."""

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
    spec = importlib.util.spec_from_file_location("resolution_consumer", checkout / "tools/ci_screen_resolution.py")
    assert spec is not None and spec.loader is not None
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    import quantfit

    expected_source = (args.expected_source or checkout).resolve()
    assert Path(quantfit.__file__).resolve() == expected_source / "quantfit/__init__.py", (
        "unexpected application origin"
    )
    assert quantfit.__version__ == importlib.metadata.version("quantfit")
    manifest_raw = (here / "inputs/targets.json").read_bytes()
    names = [target["name"] for target in json.loads(manifest_raw)["targets"]]
    reports_raw = {name: (here / "inputs/reports" / f"{name}.json").read_bytes() for name in names}
    calibrations_raw = {name: (here / "inputs/calibrations" / f"{name}.json").read_bytes() for name in names}
    measured_raw = {name: (here / "inputs/measured" / f"{name}.json").read_bytes() for name in names}
    cases = {
        "full": (reports_raw, calibrations_raw),
        "partial": (reports_raw, {"clean": calibrations_raw["clean"]}),
        "empty": (reports_raw, {}),
        "pending": ({name: raw for name, raw in reports_raw.items() if name != "clean"}, calibrations_raw),
        "both-missing": (
            {name: raw for name, raw in reports_raw.items() if name != "unmeasured"},
            {name: raw for name, raw in calibrations_raw.items() if name != "unmeasured"},
        ),
        "conditional": (measured_raw, calibrations_raw),
        "native-incomplete": ({name: raw for name, raw in reports_raw.items() if name != "flagged"}, calibrations_raw),
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
        for label, (native_raw, bound_raw) in cases.items():
            targets, reports, calibrations = consumer.stage(Path("build") / label, manifest_raw, native_raw, bound_raw)
            before = {p: p.read_bytes() for p in targets.parent.rglob("*") if p.is_file()}
            default, _ = consumer.invoke(
                targets, reports, out=Path(f"{label}-native.json"), junit=Path(f"{label}-native.xml")
            )
            annotated, _ = consumer.invoke(
                targets, reports, calibrations, out=Path(f"{label}.json"), junit=Path(f"{label}.xml")
            )
            compact = consumer.check(annotated, default, manifest_raw, native_raw, bound_raw)
            assert json.loads(Path(f"{label}.json").read_bytes()) == annotated["result"]
            assert json.loads(Path(f"{label}-native.json").read_bytes()) == default["result"]
            assert Path(f"{label}-native.xml").read_bytes() == Path(f"{label}.xml").read_bytes()
            assert all(p.read_bytes() == raw for p, raw in before.items())
            records[label] = {
                **compact,
                "junit": consumer.junit_counts(Path(f"{label}.xml")),
                "native_junit_unchanged": True,
            }
            retain(f"{label}-cli.json", annotated)
        invalid = {**calibrations_raw, "unmeasured": (here / "inputs/invalid-calibration.json").read_bytes()}
        targets, reports, calibrations = consumer.stage(Path("build/invalid-late"), manifest_raw, reports_raw, invalid)
        before = {p: p.read_bytes() for p in targets.parent.rglob("*") if p.is_file()}
        with patch(
            "quantfit.resolution.analyze_resolution_bytes", side_effect=AssertionError("analysis before preflight")
        ) as analysis:
            refused, stderr = consumer.invoke(
                targets, reports, calibrations, out=Path("refused.json"), junit=Path("refused.xml")
            )
        analysis.assert_not_called()
        assert refused["exit_code"] == 2 and not Path("refused.json").exists() and not Path("refused.xml").exists()
        assert "PRIVATE_SENTINEL_DO_NOT_REFLECT" not in json.dumps(refused) + stderr
        assert all(p.read_bytes() == raw for p, raw in before.items())
        retain("invalid-late-refusal.json", refused)
        targets, reports, calibrations = consumer.stage(
            Path("build/alias"), manifest_raw, reports_raw, calibrations_raw
        )
        before = {p: p.read_bytes() for p in targets.parent.rglob("*") if p.is_file()}
        with patch(
            "quantfit.resolution.analyze_resolution_bytes", side_effect=AssertionError("analysis before output guard")
        ) as analysis:
            refused, _ = consumer.invoke(targets, reports, calibrations, out=calibrations / "clean.json")
        analysis.assert_not_called()
        assert refused["exit_code"] == 2 and all(p.read_bytes() == raw for p, raw in before.items())
        retain("output-alias-refusal.json", refused)
        records["refusals"] = {
            "invalid_late_exit": 2,
            "output_alias_exit": 2,
            "analysis_calls": 0,
            "all_input_bytes_unchanged": True,
        }
        for trap in traps:
            trap.assert_not_called()
        records["inputs"] = {
            p.relative_to(here / "inputs").as_posix(): consumer.binding(p.read_bytes())
            for p in sorted((here / "inputs").rglob("*.json"))
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
                    "screen_resolution.py",
                    "resolution.py",
                    "safety/calibration_binding.py",
                    "safety/mde.py",
                    "junit.py",
                )
            },
        }
        records["limits"] = {
            "synthetic_aggregate_labels": True,
            "model_or_judge_calls": 0,
            "resolution_or_download_calls": 0,
            "human_labels_authenticated": False,
            "assumptions_verified": False,
            "sensitivity_established": False,
            "scientific_go": False,
            "proof": "source CLI/JSON/XML conditional analysis; installed wheel and real CPU qualification separate",
        }
        retain("receipt.json", records)
    print(
        json.dumps(
            {
                "source_version": quantfit.__version__,
                "native_exits": [records[name]["exit_code"] for name in cases],
                "refusal_exits": [2, 2],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
