"""Record controlled packet transport to a fresh counts-only source artifact."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record", type=Path, required=True, help="fresh counts-only artifact, never overwrite a dated run"
    )
    parser.add_argument("--work", type=Path, required=True, help="fresh private synthetic scratch directory")
    args = parser.parse_args()
    if args.record.exists() or args.work.exists():
        parser.error("record and work must be fresh")
    checkout = Path(__file__).resolve().parents[1]
    paths = {p for p in (checkout / "quantfit").rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    paths.update(
        checkout / name
        for name in (
            "tools/ci_annotation_packets.py",
            "tools/ci_annotation_packets_browser.py",
            "tools/ci_annotation_packets_record.py",
            "tools/ci_installed.py",
            "tests/test_annotation_packets.py",
            "tests/test_ci_annotation_packets.py",
            ".github/workflows/validate.yml",
            "tools/ci/pyproject.toml",
            "tools/ci/uv.lock",
        )
    )
    hashes = {p.relative_to(checkout).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    spec = importlib.util.spec_from_file_location("source_packet_consumer", checkout / "tools/ci_annotation_packets.py")
    assert spec and spec.loader
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    args.work.mkdir(parents=True)
    result = consumer.run(checkout, args.work)
    from quantfit import __version__
    from quantfit.bundle import _private_fields

    _private_fields(result)
    assert all(hashlib.sha256((checkout / name).read_bytes()).hexdigest() == digest for name, digest in hashes.items())
    artifact = {
        "schema_version": 1,
        "tool_version": __version__,
        "profile": "controlled source/editable, not installed/browser qualification",
        "source_hash_basis": "Actual RAW bytes on this producing checkout, not portable Git/archive hashes",
        "source_hashes": hashes,
        "source_inputs_after_held": True,
        "result": result,
        "limits": [
            "Explicit synthetic choices over fictional capture rows; native blank/chunk/packet/collection and separate calibration ingestion, not human reading or model/judge execution.",
            "Local returned CSVs are stdlib simulations, not browser downloads. Four installed Linux/Windows wheel/sdist profiles and two hosted Linux browser executions are later separate evidence.",
            "Source/capture/rater authentication, human truth, independent labeling, sensitivity and scientific GO are not established.",
            "Missing native directional denominators retain null MDE epsilon bounds; no perfect-judge or resolution claim.",
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
                "tool_version": __version__,
                "source_hashes": len(hashes),
                "cases": result["n_cases"],
                "parts": result["n_parts"],
                "native_cli_refusals": result["actual_cli_receiving"],
            }
        )
    )


if __name__ == "__main__":
    main()
