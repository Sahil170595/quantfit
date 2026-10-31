"""Regenerate aggregate-only fictional native workflow evidence, without inference."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import tempfile
from importlib import metadata
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "screen_adjudication_record", root / "tools/ci_screen_adjudication.py"
    )
    assert spec and spec.loader
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    with tempfile.TemporaryDirectory(prefix="quantfit-screen-adjudication-") as directory:
        result = consumer.run(root, Path(directory))
    result["qualification"] = {
        "profile": "native editable source, fictional CPU-only saved-file controls",
        "python": platform.python_version(),
        "quantfit": metadata.version("quantfit"),
        "no_model_execution": True,
        "no_human_authentication": True,
        "no_installed_distribution_claim": True,
        "regenerator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    output = Path(__file__).with_name("summary.json")
    output.write_bytes((json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
    print(
        json.dumps(
            {
                "positive_cases": result["positive_cases"],
                "adverse_cases": result["adverse_cases"],
                "source_hashes": len(result["source_hashes"]),
                "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
