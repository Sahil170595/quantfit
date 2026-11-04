"""Record the existing native axis consumer to a NEW counts-only artifact."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True, help="fresh aggregate JSON; never overwrite a dated run")
    parser.add_argument("--work", type=Path, required=True, help="fresh local controlled scratch directory")
    args = parser.parse_args()
    if args.record.exists() or args.work.exists():
        parser.error("record and work paths must be fresh")
    root = Path(__file__).resolve().parents[1]
    paths = {p for p in (root / "quantfit").rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    paths.update(
        root / name
        for name in [
            "tools/ci_axis_gate.py",
            "tools/ci_axis_gate_record.py",
            "tools/ci_installed.py",
            "tools/ci_gate_fixture/sitecustomize.py",
            ".github/workflows/validate.yml",
        ]
    )
    hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    spec = importlib.util.spec_from_file_location("current_axis_gate_consumer", root / "tools/ci_axis_gate.py")
    assert spec and spec.loader
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    result = consumer.run(root, args.work)
    result.pop("package_origin")
    from quantfit.bundle import _private_fields

    _private_fields(result)
    assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest for name, digest in hashes.items())
    artifact = {
        "schema_version": 1,
        "source_hash_basis": "Actual RAW source bytes on the producing checkout; not a portable Git/archive digest.",
        "profile": "controlled source/editable consumer, not installed artifact qualification",
        "source_hashes": hashes,
        "source_inputs_after_held": True,
        "result": result,
        "limits": [
            "Synthetic declared labels/identities and native tabulation; no real model or judge generation.",
            "Existing controlled live CLI fixture preserves canonical40/12 populations; not a detector sensitivity control.",
            "Per-axis alpha/power are conditional native policies, not joint guarantees/human truth/scientific GO.",
            "Original/rebuilt installed and hosted qualification are separate receiving executions.",
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
                "saved_cases": len(result["cases"]),
                "live_fixture_cases": len(result["live_controlled_OSCLI"]),
            }
        )
    )


if __name__ == "__main__":
    main()
