"""Run fictional native two-judge controls; publish aggregates and source hashes only."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import platform
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("summary.json"))
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "judges_functional_consumer", checkout / "tools/ci_calibration_judges.py"
    )
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    with tempfile.TemporaryDirectory(prefix="quantfit-two-judges-private-") as name:
        private = Path(name)
        result = helper.run(checkout, private)
    result["private_fixture_directory_removed"] = not private.exists()
    result["software"] = {
        "python": platform.python_version(),
        "platform": platform.system(),
        "installed_metadata_version": importlib.metadata.version("quantfit"),
        "scope": "Native fictional source/OS-entrypoint acceptance; installed distributions and hosted CI are separate qualifications.",
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf8", newline="\n")
    print(
        json.dumps(
            {
                "positive": result["positive_cases"],
                "adverse": result["adverse_cases"],
                "actual_os_utf8_lf_parity": result["os_cli_utf8_lf_parity"],
                "private_directory_removed": result["private_fixture_directory_removed"],
            }
        )
    )


if __name__ == "__main__":
    main()
