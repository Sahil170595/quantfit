"""Record the native local-source consumer into a fresh counts-only source artifact."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True, help="new aggregate; never overwrite a dated run")
    parser.add_argument("--work", type=Path, required=True, help="new private controlled scratch directory")
    args = parser.parse_args()
    if args.record.exists() or args.work.exists():
        parser.error("record and work paths must be fresh")
    root = Path(__file__).resolve().parents[1]
    paths = {p for p in (root / "quantfit").rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    paths.update(
        root / name
        for name in [
            "tools/ci_probe_bundle.py",
            "tools/ci_probe_bundle_record.py",
            "tools/ci_installed.py",
            "tools/ci_corpus_fixture/sitecustomize.py",
            ".github/workflows/validate.yml",
            "tests/test_probe_bundle.py",
            "tests/test_probe_bundle_flows.py",
            "tests/test_probe_bundle_admission.py",
            "tests/test_probe_bundle_cache_identity.py",
            "tests/test_probe_bundle_cache_roles.py",
            "tests/test_ci_probe_bundle.py",
        ]
    )
    hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    spec = importlib.util.spec_from_file_location("current_local_corpus_consumer", root / "tools/ci_probe_bundle.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    result = helper.run(root, args.work)
    from quantfit.bundle import _private_fields

    _private_fields(result)
    assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest for name, digest in hashes.items())
    artifact = {
        "schema_version": 1,
        "profile": "current source/editable, controlled inference; not installed artifact qualification",
        "source_hash_basis": "Actual RAW source bytes of the producing checkout; not a portable Git/archive hash.",
        "source_hashes": hashes,
        "source_inputs_after_held": True,
        "result": result,
        "limits": [
            "Fictional ordered thirty-row population; controlled generation/judge/environment and no Hub/model/backend work.",
            "API child and sixteen real fresh OS CLI commands; four refusals. Capture/key/direct-calibration2 and extracted-calibration3 keep non-null full local binding.",
            "Whole raw digest is an exact byte pin, not source curation/authentication, sensitivity, human truth or scientific clearance.",
            "Four Linux/Windows wheel/sdist receiving profiles and two build artifacts are separate later hosted evidence.",
        ],
    }
    args.record.parent.mkdir(parents=True, exist_ok=True)
    with args.record.open("x", encoding="utf-8") as stream:
        json.dump(artifact, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "record": str(args.record),
                "sha256": hashlib.sha256(args.record.read_bytes()).hexdigest(),
                "tool_version": result["tool_version"],
                "source_hashes": len(hashes),
                "profiles": result["n_profiles"],
            }
        )
    )


if __name__ == "__main__":
    main()
