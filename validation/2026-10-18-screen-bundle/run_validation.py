"""Record actual offline CLI screen bundles from the committed literal aggregate originals."""

from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
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
    spec = importlib.util.spec_from_file_location("screen_bundle_consumer", checkout / "tools/ci_screen_bundle.py")
    assert spec is not None and spec.loader is not None
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    import quantfit

    expected_source = (args.expected_source or checkout).resolve()
    assert Path(quantfit.__file__).resolve() == expected_source / "quantfit/__init__.py", (
        "unexpected application origin"
    )
    manifest_raw = (here / "inputs/targets.json").read_bytes()
    reports = {
        target["name"]: (here / "inputs/reports" / f"{target['name']}.json").read_bytes()
        for target in json.loads(manifest_raw)["targets"]
    }
    summary_raw = (here / "inputs/reports/screen-summary.json").read_bytes()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    records = {}

    def retain(name: str, value: dict) -> None:
        (output / name).write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())

    with working_directory(output), contextlib.ExitStack() as stack:
        traps = [
            stack.enter_context(
                patch(target, side_effect=AssertionError("unexpected model, resolution or download call"))
            )
            for target in (
                "quantfit.safety.verify.verify_safety",
                "quantfit.safety.gguf_arm.resolve_pair",
                "huggingface_hub.hf_hub_download",
            )
        ]
        source = Path("producer")
        manifest, directory = consumer.stage(source, manifest_raw, reports, summary=summary_raw)
        originals = {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()}
        bundle = Path("bundle")
        created = consumer.create(manifest, directory, bundle)
        records["create"] = consumer.check(created, bundle, manifest_raw, reports, summary=summary_raw)
        assert all((source / path).read_bytes() == raw for path, raw in originals.items())
        retain("create.json", created)
        moved = Path("relocated-bundle")
        bundle.rename(moved)
        source.rename(Path("producer-unavailable"))
        assert not source.exists() and not bundle.exists()
        assert all((Path("producer-unavailable") / path).read_bytes() == raw for path, raw in originals.items())
        verified = consumer.verify(moved)
        records["relocated_verify"] = consumer.check(verified, moved, manifest_raw, reports, summary=summary_raw)
        assert records["create"] == records["relocated_verify"]
        retain("verify.json", verified)
        records["bundle_members"] = [
            {"path": path.relative_to(moved).as_posix(), **consumer.binding(path.read_bytes())}
            for path in sorted(moved.rglob("*"))
            if path.is_file()
        ]
        partial_reports = {name: raw for name, raw in reports.items() if name != "flagged"}
        manifest, directory = consumer.stage(Path("missing-producer"), manifest_raw, partial_reports)
        partial = Path("missing-bundle")
        incomplete = consumer.create(manifest, directory, partial)
        records["missing_create"] = consumer.check(incomplete, partial, manifest_raw, partial_reports)
        assert records["missing_create"]["content_exit_code"] == 0
        assert records["missing_create"]["receiving_exit_code"] == 4
        retain("missing-create.json", incomplete)
        missing_verified = consumer.verify(partial)
        records["missing_verify"] = consumer.check(missing_verified, partial, manifest_raw, partial_reports)
        retain("missing-verify.json", missing_verified)
        assert records["missing_create"] == records["missing_verify"]
        tampered = Path("tampered-bundle")
        shutil.copytree(moved, tampered)
        member = tampered / "reports/clean.json"
        tampered_raw = member.read_bytes() + b" "
        member.write_bytes(tampered_raw)
        refused = consumer.verify(tampered)
        assert refused["exit_code"] == 2 and member.read_bytes() == tampered_raw
        records["tamper_refusal"] = {"exit_code": 2, "unchanged_tampered_member": consumer.binding(tampered_raw)}
        retain("tampered-verify.json", refused)
        manifest, directory = consumer.stage(Path("corrupt-producer"), manifest_raw, partial_reports)
        corrupt_path = directory / "unmeasured.json"
        corrupt_raw = b'{"schema_version":2,"synthetic_corrupt_member":'
        corrupt_path.write_bytes(corrupt_raw)
        corrupt = consumer.create(manifest, directory, Path("refused-bundle"))
        assert corrupt["exit_code"] == 2 and not Path("refused-bundle").exists()
        assert corrupt_path.read_bytes() == corrupt_raw
        records["corrupt_create_refusal"] = {"exit_code": 2, "unchanged_corrupt_member": consumer.binding(corrupt_raw)}
        retain("corrupt-create.json", corrupt)
        for trap in traps:
            trap.assert_not_called()
        records["inputs"] = {
            "targets": consumer.binding(manifest_raw),
            "reports": [{"name": name, **consumer.binding(raw)} for name, raw in reports.items()],
            "producer_summary": consumer.binding(summary_raw),
        }
        versions = {}
        for name in ("torch", "transformers", "huggingface_hub", "pytest"):
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = None
        records["runtime"] = {
            "source_version": quantfit.__version__,
            "distribution_version": importlib.metadata.version("quantfit"),
            "source_origin_verified": True,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "dependencies": versions,
            "source_files": {
                name: consumer.binding((expected_source / "quantfit" / name).read_bytes())
                for name in (
                    "__init__.py",
                    "cli.py",
                    "saved_screen.py",
                    "screen_bundle.py",
                    "screen_bundle_inputs.py",
                    "screen_bundle_publication.py",
                )
            },
        }
        records["limits"] = {
            "synthetic_aggregate_only": True,
            "model_or_judge_calls": 0,
            "model_resolution_or_download_calls": 0,
            "producer_input_bytes_unchanged": True,
            "physical_identities_authenticated": False,
            "independent_execution_verified": False,
            "control_evidence_verified": False,
            "human_labels_authenticated": False,
            "scientific_go": False,
            "proof": "source CLI parser/dispatch/emission and literal transport; not installed wheel or real CPU inference",
        }
        retain("receipt.json", records)
    print(
        json.dumps(
            {
                "source_version": quantfit.__version__,
                "content_exits": [0, 0, 0, 0, 2, 2],
                "nested_receiving_exits": [
                    records["create"]["receiving_exit_code"],
                    records["missing_create"]["receiving_exit_code"],
                ],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
