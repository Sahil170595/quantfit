"""Regenerate aggregate controlled whole-corpus source behavior, not Hub/model qualification."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import tempfile
from pathlib import Path


def main() -> None:
    checkout = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("probe_corpus_functional", checkout / "tools/ci_probe_corpus.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    with tempfile.TemporaryDirectory(prefix="quantfit-probe-corpus-") as name:
        private = Path(name)
        result = helper.run(checkout, private)
    result["private_fixture_directory_removed"] = not private.exists()
    names = (
        "quantfit/safety/verify.py",
        "quantfit/inspect_task.py",
        "quantfit/inspect_hf.py",
        "quantfit/inspect_gguf.py",
        "quantfit/modelcard.py",
        "quantfit/safety/cache.py",
        "quantfit/safety/calibration_binding.py",
        "quantfit/safety/report.py",
        "quantfit/resolution.py",
        "quantfit/reference_assessment.py",
        "quantfit/reference_replay.py",
        "quantfit/__init__.py",
        "quantfit/cli.py",
        "tools/ci_probe_corpus.py",
        "tools/ci_installed.py",
        "tests/test_probe_corpus.py",
        "tests/test_ci_probe_corpus.py",
        "tests/test_modelcard.py",
        "tests/test_baseline_cache_wiring.py",
        "tests/test_inspect_gguf.py",
        ".github/workflows/validate.yml",
        "pyproject.toml",
        "tools/ci/pyproject.toml",
        "tools/ci/uv.lock",
    )
    result["source_hashes"] = {name: hashlib.sha256((checkout / name).read_bytes()).hexdigest() for name in names}
    result["software"] = {
        "python": platform.python_version(),
        "platform": platform.system(),
        "installed_metadata_version": importlib.metadata.version("quantfit"),
        "scope": "Editable source/API/OS module entrypoint with controlled SDK/gen/judge; no real Hub/model or installed-distribution qualification.",
    }
    result["datasets_policy"] = {
        "version": importlib.metadata.version("datasets"),
        "source_sha256": hashlib.sha256(
            (Path(importlib.util.find_spec("datasets").origin).parent / "load.py").read_bytes()
        ).hexdigest(),
        "public_pin": "==5.0.1",
        "old3_compatibility": "official source inference only, not executed",
    }
    names_installed = {
        d.metadata["Name"].lower().replace("_", "-").replace(".", "-")
        for d in importlib.metadata.distributions()
        if d.metadata["Name"]
    }
    result["software"]["active_external_name_count"] = len(names_installed - {"quantfit"})
    Path(__file__).with_name("summary.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf8", newline="\n"
    )
    print(
        json.dumps(
            {
                "positive": result["positive_cases"],
                "adverse": result["adverse_cases"],
                "source_hashes": len(names),
                "private_directory_removed": result["private_fixture_directory_removed"],
                "browser_executed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
