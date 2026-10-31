"""Regenerate aggregate-only fictional native workflow evidence, without inference."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import subprocess
import tempfile
from importlib import metadata
from pathlib import Path

import tomllib


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
    native_hash_count = len(result["source_hashes"])
    assert native_hash_count == 16
    for name in (
        "quantfit/__init__.py",
        ".github/workflows/validate.yml",
        "tools/ci_dependency_audit.py",
        "pyproject.toml",
        "tools/ci/pyproject.toml",
        "tools/ci/uv.lock",
        "tools/ci_installed.py",
        "validation/2026-10-31-screen-adjudication-python311/regenerate.py",
    ):
        result["source_hashes"][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    accepted = "0dae67ae686d486f088c43e3af8bf4f301341ffa"
    lock = tomllib.loads((root / "tools/ci/uv.lock").read_text())
    before = tomllib.loads(subprocess.check_output(["git", "show", f"{accepted}:tools/ci/uv.lock"], cwd=root).decode())
    assert lock == before
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    assert project["version"] == metadata.version("quantfit") == "0.48.0"
    assert project["requires-python"] == ">=3.11"
    assert len(result["cases"]) == result["positive_cases"] == 24
    assert len(result["adverse"]) == result["adverse_cases"] == 46
    assert result["os_entrypoint_raw_utf8_lf_parity"] is True
    result["inheritance"] = {
        "original_048_head": "4a5fe9521f3371b72458ba5ec007785aa1cf84ca",
        "accepted_047_security_head": accepted,
        "private_full_entries_held": True,
        "private_full_entries": len(lock["package"]),
        "private_unique_names": len({p["name"] for p in lock["package"]}),
        "public_requires_python": project["requires-python"],
        "native_producer_hashes": native_hash_count,
        "additional_current_profile_hashes": len(result["source_hashes"]) - native_hash_count,
        "older_validation_records_modified": False,
        "no_vulnerability_service_query_by_recorder": True,
    }
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
