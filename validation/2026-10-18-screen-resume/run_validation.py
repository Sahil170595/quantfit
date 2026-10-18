"""Execute actual CLI resume under explicit offline protocol-only execution hooks."""

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
    parser.add_argument("--expected-source", type=Path, help="assert this application checkout before any CLI call")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    checkout = here.parents[1]
    spec = importlib.util.spec_from_file_location("resume_consumer", checkout / "tools/ci_screen_resume.py")
    assert spec is not None and spec.loader is not None
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    import quantfit
    from quantfit.safety.verify import SafetyDrift

    expected_source = (args.expected_source or checkout).resolve()
    assert Path(quantfit.__file__).resolve() == expected_source / "quantfit/__init__.py", (
        "unexpected application origin"
    )
    manifest_data = json.loads((here / "inputs/manifest.json").read_bytes())
    reports = {
        target["name"]: (here / "inputs/reports" / f"{target['name']}.json").read_bytes()
        for target in manifest_data["targets"]
    }
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    records = {}
    with working_directory(output):
        manifest, out = consumer.write_fixture(Path("all-present"), manifest_data, reports)
        (out / "screen-summary.json").write_text('{"rows":[],"scientific_go":true}\n', encoding="utf-8")
        with patch(
            "quantfit.safety.verify.verify_safety", side_effect=AssertionError("unexpected native execution")
        ) as execution:
            all_present, _ = consumer.invoke(manifest, out, junit=Path("screen.xml"))
        execution.assert_not_called()
        records["all_present"] = consumer.check(all_present, manifest, out, reports)
        records["junit"] = consumer.check_junit(Path("screen.xml"), reports)
        Path("all-present.json").write_text(json.dumps(all_present, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest, out = consumer.write_fixture(Path("missing-one"), manifest_data, reports, missing=("clean",))

        def bounded_execution(baseline, quant, *, report_path, max_new_tokens, **kwargs):
            target = manifest_data["targets"][0]
            assert baseline == target["baseline"] and quant == target["quant"] and max_new_tokens == 64
            raw = reports["clean"]
            assert Path(report_path).resolve() == (out / "clean.json").resolve()
            Path(report_path).write_bytes(raw)
            drift = json.loads(raw)["drift"]
            d, o = drift["refusal_robustness"], drift["over_refusal"]
            return SafetyDrift(
                40,
                12,
                d["baseline_refused"],
                d["quant_refused"],
                d["harmful_compliance_regressions"],
                28,
                o["baseline_refused"],
                o["quant_refused"],
                o["overrefusal_regressions"],
                drift["by_zone"],
            )

        with patch("quantfit.safety.verify.verify_safety", side_effect=bounded_execution) as execution:
            missing_one, _ = consumer.invoke(manifest, out)
        assert execution.call_count == 1
        records["missing_one"] = consumer.check(missing_one, manifest, out, reports, executed=("clean",))
        Path("missing-one.json").write_text(json.dumps(missing_one, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest, out = consumer.write_fixture(Path("refused"), manifest_data, reports, missing=("clean",))
        invalid_path = out / "unmeasured.json"
        invalid_bytes = b'{"schema_version":2,"synthetic_corrupt_member":'
        invalid_path.write_bytes(invalid_bytes)
        with patch(
            "quantfit.safety.verify.verify_safety", side_effect=AssertionError("executed before preflight")
        ) as execution:
            refused, stderr = consumer.invoke(manifest, out)
        execution.assert_not_called()
        assert refused["exit_code"] == 2 and invalid_path.read_bytes() == invalid_bytes
        assert not (out / "clean.json").exists()
        assert "synthetic_corrupt_member" not in json.dumps(refused) + stderr
        records["refused"] = {
            "exit_code": 2,
            "category": refused["error"]["kind"],
            "unchanged_invalid_member": consumer.binding(invalid_bytes),
            "native_calls": 0,
        }
        Path("refused.json").write_text(json.dumps(refused, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest, out = consumer.write_fixture(Path("alias"), manifest_data, reports)
        originals = {path: path.read_bytes() for path in (manifest, *out.iterdir())}
        with patch(
            "quantfit.safety.verify.verify_safety", side_effect=AssertionError("executed before output admission")
        ) as execution:
            alias, _ = consumer.invoke(manifest, out, junit=manifest)
        execution.assert_not_called()
        assert alias["exit_code"] == 2 and all(path.read_bytes() == raw for path, raw in originals.items())
        records["output_alias"] = {"exit_code": 2, "native_calls": 0, "all_original_bytes_unchanged": True}
        Path("output-alias.json").write_text(json.dumps(alias, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        dependencies = {}
        for name in ("torch", "transformers", "huggingface_hub", "pytest"):
            try:
                dependencies[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                dependencies[name] = None
        records["runtime"] = {
            "source_version": quantfit.__version__,
            "distribution_version": importlib.metadata.version("quantfit"),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "dependencies": dependencies,
            "source_origin_verified": True,
            "source_files": {
                name: consumer.binding((expected_source / "quantfit" / name).read_bytes())
                for name in ("__init__.py", "cli.py", "screen.py", "screen_resume.py", "saved_screen.py")
            },
        }
        records["limits"] = {
            "synthetic_aggregate_only": True,
            "physical_identities_authenticated": False,
            "independent_execution_verified": False,
            "control_evidence_verified": False,
            "human_labels_authenticated": False,
            "scientific_go": False,
            "model_or_judge_calls": 0,
            "bounded_native_write_hooks": 1,
            "proof": "source CLI parser/dispatch/emission; not installed wheel or real CPU inference",
        }
        Path("receipt.json").write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "source_version": quantfit.__version__,
                "cases": {
                    "all_present": all_present["exit_code"],
                    "missing_one": missing_one["exit_code"],
                    "refused": refused["exit_code"],
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
