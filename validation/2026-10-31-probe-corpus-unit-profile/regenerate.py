"""Record the native unit-profile correction; historical B executions are not replayed."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import subprocess
from pathlib import Path

import tomllib
from packaging.requirements import Requirement

BASE = "afc239bb0f00bd35d019bf2fe693b1c1d3120db1"
PROFILE = {"tools/ci/pyproject.toml", "tools/ci/uv.lock"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit-export", required=True, type=Path)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[2]

    def git(path: str) -> bytes:
        return subprocess.check_output(["git", "show", BASE + ":" + path], cwd=checkout)

    def digest(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    old_record = "validation/2026-10-31-probe-corpus/summary.json"
    raw = (checkout / old_record).read_bytes()
    assert raw.replace(b"\r\n", b"\n") == git(old_record)
    prior = json.loads(raw)
    held = {name: expected for name, expected in prior["source_hashes"].items() if name not in PROFILE}
    assert len(held) == 22
    assert all(digest((checkout / name).read_bytes()) == expected for name, expected in held.items())
    before = tomllib.loads(git("tools/ci/uv.lock").decode())
    after = tomllib.loads((checkout / "tools/ci/uv.lock").read_text())
    virtual = "quantfit-hosted-validation"

    def registry(lock: dict) -> collections.Counter:
        return collections.Counter(json.dumps(p, sort_keys=True) for p in lock["package"] if p["name"] != virtual)

    assert registry(before) == registry(after)
    assert {k: v for k, v in before.items() if k != "package"} == {k: v for k, v in after.items() if k != "package"}
    old_root = next(p for p in before["package"] if p["name"] == virtual)
    new_root = next(p for p in after["package"] if p["name"] == virtual)
    expected_root = json.loads(json.dumps(old_root))
    for group in ("unit", "numerical"):
        expected_root["dev-dependencies"][group].insert(0, {"name": "datasets"})
        expected_root["metadata"]["requires-dev"][group].insert(0, {"name": "datasets", "specifier": "==5.0.1"})
        expected_root["dev-dependencies"][group].sort(key=lambda item: item["name"])
        expected_root["metadata"]["requires-dev"][group].sort(key=lambda item: item["name"])
    assert expected_root == new_root
    old_project = tomllib.loads(git("tools/ci/pyproject.toml").decode())
    project = tomllib.loads((checkout / "tools/ci/pyproject.toml").read_text())
    old_project["dependency-groups"]["unit"].insert(
        old_project["dependency-groups"]["unit"].index("filelock==4.2.1") + 1, "datasets==5.0.1"
    )
    assert old_project == project
    exported = args.unit_export.read_bytes()
    sdk_lines = [line for line in exported.decode().splitlines() if line.startswith("datasets==")]
    assert len(sdk_lines) == 1
    sdk = Requirement(sdk_lines[0].removesuffix("\\").strip())
    assert sdk.name == "datasets" and str(sdk.specifier) == "==5.0.1"
    selected = {
        f"{version}/{system}": sdk.marker is None
        or sdk.marker.evaluate(
            {"python_version": version, "python_full_version": version + ".0", "sys_platform": system}
        )
        for version in ("3.11", "3.12", "3.13", "3.14")
        for system in ("linux", "win32")
    }
    assert all(selected.values())
    assert not subprocess.check_output(["git", "diff", BASE, "--", "quantfit", "tests", "pyproject.toml"], cwd=checkout)
    result = {
        "candidate": "0.51.0",
        "profile_scope": "Native locked unit+tooling export; no new environment, install or C full/native execution.",
        "historical_B": {
            "head": BASE,
            "record": old_record,
            "record_sha256": digest(raw),
            "positive_cases": prior["positive_cases"],
            "CLI_adverse_cases": prior["adverse_cases"],
            "bound_source_mismatch_controls": prior["bound_source_mismatch_controls"],
            "source_hashes_held": held,
            "changed_profile_source_hashes": {
                name: {"B": prior["source_hashes"][name], "C": digest((checkout / name).read_bytes())}
                for name in sorted(PROFILE)
            },
            "full_source": {
                "passed": 3617,
                "skipped": 55,
                "deselected": 6,
                "log_sha256": "d109613d4735ba50ebb6ed3a412d48c0bd8baa4cc2596d86f909fefd6131b707",
            },
            "installed_each": {"passed": 1325, "skipped": 19, "wheel_Python_files": 94, "loaded_module_count": None},
            "failed_CI": "https://github.com/Sahil170595/quantfit/actions/runs/41222240431",
            "failed_unit_job_ids": [124599049814, 124599049819, 124599049820, 124599049952],
            "failed_numerical_job_id": 124599049822,
            "failure": "datasets absent from unit; all four unit profiles and inherited numerical profile failed",
            "prior_executions_carried_by_held_application_and_public_metadata": True,
        },
        "native_lock": {
            "full_nodes": len(after["package"]),
            "unique_names": len({p["name"] for p in after["package"]}),
            "full_registry_entries_held": sum(registry(after).values()),
            "only_virtual_unit_and_inherited_numerical_edges_and_requirements_added": "datasets==5.0.1",
            "profile_hashes": {name: digest((checkout / name).read_bytes()) for name in sorted(PROFILE)},
        },
        "native_unit_tooling_export": {
            "sha256": digest(exported),
            "bytes": len(exported),
            "datasets_requirement": str(sdk),
            "native_marker_selected_on_declared_profiles": selected,
            "scope": "Exported locked requirements, not execution in a newly constructed unit environment.",
        },
        "C_hosted_qualification": "pending fresh current-head CI/CodeQL/installed/browser",
        "science_or_Hub_model_qualification": False,
    }
    destination = Path(__file__).with_name("summary.json")
    destination.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf8", newline="\n")
    print(
        json.dumps(
            {
                "nodes": result["native_lock"]["full_nodes"],
                "held_registry": sum(registry(after).values()),
                "held_sources": len(held),
                "changed_profiles": len(PROFILE),
                "no_C_full_or_native_rerun_claim": True,
            }
        )
    )


if __name__ == "__main__":
    main()
