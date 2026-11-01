"""Regenerate aggregates only; the earlier dated feature record is never modified."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote

import tomllib
from packaging.requirements import Requirement
from packaging.utils import parse_wheel_filename

BASELINE = "b1e123a939c70710041aecc35ac160946830f578"


def main() -> None:
    checkout = Path(__file__).resolve().parents[2]
    output = Path(__file__).resolve().parent
    before_raw = subprocess.check_output(["git", "show", f"{BASELINE}:tools/ci/uv.lock"], cwd=checkout)
    after_raw = (checkout / "tools/ci/uv.lock").read_bytes()
    before = tomllib.loads(before_raw.decode())
    after = tomllib.loads(after_raw.decode())

    def identity(value: dict) -> tuple[str, str, str]:
        return value["name"], value["version"], json.dumps(value["source"], sort_keys=True)

    old = {identity(p): p for p in before["package"]}
    new = {identity(p): p for p in after["package"]}
    assert len(old) == len(before["package"]) and len(new) == len(after["package"])
    assert not new.keys() - old.keys()
    removed_wheels, changed_entries = 0, 0
    for key, current in new.items():
        prior = old[key]
        assert current["source"] == prior["source"] and current.get("sdist") == prior.get("sdist")
        prior_wheels = {w["url"]: w for w in prior.get("wheels", [])}
        current_wheels = {w["url"]: w for w in current.get("wheels", [])}
        assert not current_wheels.keys() - prior_wheels.keys()
        for url, artifact in current_wheels.items():
            assert artifact == prior_wheels[url]
        for url in prior_wheels.keys() - current_wheels.keys():
            tags = parse_wheel_filename(unquote(url.rsplit("/", 1)[-1]))[3]
            assert all((tag.interpreter, tag.abi) in {("cp310", "cp310"), ("pp310", "pypy310_pp73")} for tag in tags)
            removed_wheels += 1
        changed_entries += current != prior

    project = tomllib.loads((checkout / "pyproject.toml").read_text())["project"]
    baseline_project = tomllib.loads(
        subprocess.check_output(["git", "show", f"{BASELINE}:pyproject.toml"], cwd=checkout).decode()
    )["project"]
    baseline_affected = {}
    for classifier in baseline_project["classifiers"]:
        if not classifier.startswith("Programming Language :: Python :: 3."):
            continue
        version = classifier.rsplit(" :: ", 1)[-1]
        environment = {"python_version": version, "python_full_version": version + ".0"}
        active = [
            r
            for raw in baseline_project["dependencies"]
            if (r := Requirement(raw)).name == "filelock" and (r.marker is None or r.marker.evaluate(environment))
        ]
        admitted = [
            value for value in ("3.20.3", "4.0.10", "4.2.0") if active and all(value in r.specifier for r in active)
        ]
        if admitted:
            baseline_affected[version] = admitted
    supported = [
        c.rsplit(" :: ", 1)[-1] for c in project["classifiers"] if c.startswith("Programming Language :: Python :: 3.")
    ]
    requirements = [Requirement(raw) for raw in project["dependencies"]]
    for version in supported:
        environment = {"python_version": version, "python_full_version": version + ".0"}
        active = [
            r for r in requirements if r.name == "filelock" and (r.marker is None or r.marker.evaluate(environment))
        ]
        assert active
        assert all("4.2.1" in r.specifier for r in active)
        for affected in ("3.20.3", "4.0.10", "4.2.0"):
            assert not all(affected in r.specifier for r in active)
    assert {p["version"] for p in after["package"] if p["name"] == "filelock"} == {"4.2.1"}

    audit_spec = importlib.util.spec_from_file_location(
        "security_native_audit", checkout / "tools/ci_dependency_audit.py"
    )
    assert audit_spec and audit_spec.loader
    auditor = importlib.util.module_from_spec(audit_spec)
    audit_spec.loader.exec_module(auditor)
    inventory = auditor._inventory()
    with contextlib.redirect_stdout(io.StringIO()):
        layers = auditor._layers(inventory)

    spec = importlib.util.spec_from_file_location(
        "security_native_verification", checkout / "tools/ci_adjudication_verification.py"
    )
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    with tempfile.TemporaryDirectory(prefix="quantfit-python311-security-") as name:
        functional = helper.run(checkout, Path(name))
    assert len(functional["cases"]) == functional["positive_cases"] == 10
    assert len(functional["adverse"]) == functional["adverse_cases"] == 20
    assert len(functional["auxiliary"]) == functional["auxiliary_cases"] == 4
    assert sum(len(case["cards"]) for case in functional["cases"]) == functional["capture_backed_cards"] == 20

    paths = (
        "pyproject.toml",
        "tools/ci/pyproject.toml",
        "tools/ci/uv.lock",
        ".github/workflows/validate.yml",
        "tests/test_dependencies.py",
        "tools/ci_dependency_audit.py",
        "tests/test_ci_dependency_audit.py",
        "validation/2026-10-31-python311-security/regenerate.py",
    )
    result = {
        "kind": "quantfit.python311-security-candidate-validation",
        "candidate_version": project["version"],
        "baseline_commit": BASELINE,
        "baseline_lock_git_lf_sha256": hashlib.sha256(before_raw).hexdigest(),
        "baseline_admitted_affected_versions_by_supported_python": baseline_affected,
        "current_lock_raw_sha256": hashlib.sha256(after_raw).hexdigest(),
        "public_requires_python": project["requires-python"],
        "private_requires_python": after["requires-python"],
        "supported_classifiers": supported,
        "disclosed_affected_versions_refused": ["3.20.3", "4.0.10", "4.2.0"],
        "fixed_private_filelock": "4.2.1",
        "graph": {
            "before_entries": len(old),
            "after_entries": len(new),
            "before_unique_names": len({key[0] for key in old}),
            "after_unique_names": len({key[0] for key in new}),
            "removed_packages": [{"name": key[0], "version": key[1]} for key in sorted(old.keys() - new.keys())],
            "added_packages": [],
            "changed_surviving_full_entries": changed_entries,
            "removed_cp310_pp310_wheels": removed_wheels,
            "surviving_versions_sources_and_retained_artifacts_held": True,
        },
        "fresh_native_feature_counts": {
            key: functional[key]
            for key in ("positive_cases", "adverse_cases", "auxiliary_cases", "capture_backed_cards")
        },
        "advisory_inventory": {
            "original_pairs": [
                {"name": name, "version": version, "roles": sorted(roles)}
                for (name, version), roles in sorted(inventory.items())
            ],
            "installed_pairs": sum("installed" in roles for roles in inventory.values()),
            "lock_pairs": sum("lock" in roles for roles in inventory.values()),
            "lookup_pairs": sum(map(len, layers)),
            "layers": layers,
            "network_queries_executed_by_recorder": False,
        },
        "source_hashes": {name: hashlib.sha256((checkout / name).read_bytes()).hexdigest() for name in paths},
        "source_authenticity_verified": False,
        "human_confirmation_verified": False,
        "scientific_go": False,
    }
    for name, value in (("functional.json", functional), ("security.json", result)):
        (output / name).write_text(
            json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
        )
    print(
        json.dumps({"output": str(output), "graph": result["graph"], "counts": result["fresh_native_feature_counts"]})
    )


if __name__ == "__main__":
    main()
