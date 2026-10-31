"""Regenerate aggregate private-page controls, not a local browser qualification."""

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
    spec = importlib.util.spec_from_file_location(
        "private_review_functional", checkout / "tools/ci_adjudication_review.py"
    )
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    with tempfile.TemporaryDirectory(prefix="quantfit-private-review-") as name:
        private = Path(name)
        result = helper.run(checkout, private)
    result["private_fixture_directory_removed"] = not private.exists()
    names = (
        "quantfit/safety/adjudication_review.py",
        "quantfit/safety/adjudication.py",
        "quantfit/adjudication_record.py",
        "quantfit/modelcard.py",
        "quantfit/cli.py",
        "quantfit/safety/retention_io.py",
        "quantfit/safety/retained_labels.py",
        "quantfit/safety/calibration_inputs.py",
        "quantfit/safety/calibration_binding.py",
        "quantfit/safety/verify.py",
        "quantfit/resolution.py",
        "tools/ci_adjudication_review.py",
        "tools/ci_adjudication_review_browser.py",
        "tools/ci_adjudication.py",
        "tools/ci_installed.py",
        "tests/test_adjudication_review.py",
        "tests/test_ci_adjudication_review.py",
        "tests/test_json_envelope.py",
        ".github/workflows/validate.yml",
        ".gitignore",
        "tools/ci/pyproject.toml",
        "tools/ci/uv.lock",
    )
    result["source_hashes"] = {name: hashlib.sha256((checkout / name).read_bytes()).hexdigest() for name in names}
    result["software"] = {
        "python": platform.python_version(),
        "platform": platform.system(),
        "installed_metadata_version": importlib.metadata.version("quantfit"),
        "scope": "Editable source/native OS CLI and stdlib CSV transport; browser/installed-distribution qualifications remain separate.",
    }
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
