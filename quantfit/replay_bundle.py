"""Portable three-report T0 handoff, preserving producer bytes and negative results."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from quantfit import __version__
from quantfit.bundle import _SHA, MAX_MANIFEST_BYTES, BundleError, _json, _no_links, _read, _report, _require
from quantfit.reproduce import _t0_from_views, _view_from_report
from quantfit.resolution import MAX_REPORT_BYTES

BUNDLE_SCHEMA = 2
ROLES = {**{f"replicate-{i}": f"report-{i}.json" for i in range(1, 4)}, "t0": "t0.json"}
SCOPE = (
    "Offline exact-byte integrity and native T0 over three saved aggregates only. Producer locations are "
    "unverified labels; no full-payload repeatability, independent execution or physical-host authentication, "
    "human-label truth, sensitivity, scientific GO or reproduction qualification is established."
)


def _validate(data: dict[str, bytes], receiving_paths: list[str]) -> tuple[dict, dict]:
    original = _json(data["t0"])
    members = original.get("reports")
    _require(isinstance(members, list) and len(members) == 3, "original T0 must bind exactly three ordered reports")
    labels = []
    for item in members:
        _require(isinstance(item, dict) and set(item) == {"path", "report_sha256"}, "unsupported T0 report binding")
        _require(isinstance(item["path"], str) and bool(item["path"].strip()), "T0 producer path must be a label")
        labels.append(item["path"])
    views = []
    for i, label in enumerate(labels, 1):
        raw = data[f"replicate-{i}"]
        _json(raw)  # Duplicate/nonfinite/private-field scan, separate from report arithmetic.
        report = _report(raw)
        views.append(_view_from_report(report, raw, label, f"replicate[{i - 1}]"))
    expected = _t0_from_views(views)
    # T0 has declarations/identities, not newly calculated MDE/CI statistics.
    # Canonical serialization also keeps bool/int/float/null types distinct.
    _require(
        json.dumps(original, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True, allow_nan=False),
        "original T0 facts do not match the ordered consumed reports",
    )
    relocated = [
        _view_from_report(v.report, data[f"replicate-{i}"], path, v.side)
        for i, (v, path) in enumerate(zip(views, receiving_paths, strict=True), 1)
    ]
    return original, _t0_from_views(relocated)


def _result(root: Path, manifest: dict, *, mismatches=None, original=None, receiving=None) -> dict:
    return {
        "bundle_path": str(root),
        "bundle_schema": BUNDLE_SCHEMA,
        "manifest": manifest,
        "integrity_verified": not mismatches,
        "mismatches": mismatches or [],
        "original_t0": original,
        "receiving_t0": receiving,
        "producer_locations_verified": False,
        "scientific_claims_verified": False,
        "scope": SCOPE,
    }


def _write_member(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        _require(handle.write(raw) == len(raw), "incomplete bundle member write")
        handle.flush()
    _require(_read(path, MAX_REPORT_BYTES) == raw, "persisted bundle member differs from consumed bytes")


def create_replay_bundle(report_paths: list[str], t0_path: str, out_path: str) -> dict:
    """Consume inputs once, validate native T0, then publish the manifest last."""
    target = Path(out_path).absolute()
    try:
        _require(isinstance(report_paths, (list, tuple)) and len(report_paths) == 3, "exactly three reports required")
        _no_links(target)
        _require(not target.exists(), "bundle output must be a new directory, never an input/output alias")
        _require(target.parent.is_dir(), "bundle output parent must exist")
        paths = [Path(path).absolute() for path in report_paths]
        for i, path in enumerate(paths):
            _no_links(path)
            _require(all(not path.samefile(other) for other in paths[:i]), "replicates must be distinct files")
        data = {f"replicate-{i}": _read(path, MAX_REPORT_BYTES) for i, path in enumerate(paths, 1)}
        data["t0"] = _read(Path(t0_path).absolute(), MAX_REPORT_BYTES)
        original, receiving = _validate(data, [str(target / ROLES[f"replicate-{i}"]) for i in range(1, 4)])
        manifest = {
            "bundle_schema": BUNDLE_SCHEMA,
            "quantfit_version": __version__,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "scientific_claims_verified": False,
            "files": [
                {"role": role, "path": ROLES[role], "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
                for role, raw in data.items()
            ],
            "scope": SCOPE,
        }
        target.mkdir()
        try:
            for role, raw in data.items():
                _write_member(target / ROLES[role], raw)
            _write_member(target / "manifest.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
        except BaseException:
            # Revoke advertisement first; only remove files in this exclusively owned new directory.
            (target / "manifest.json").unlink(missing_ok=True)
            for name in ROLES.values():
                (target / name).unlink(missing_ok=True)
            target.rmdir()
            raise
        return _result(target, manifest, original=original, receiving=receiving)
    except (OSError, RuntimeError, RecursionError, TypeError, ValueError) as exc:
        if isinstance(exc, BundleError):
            raise
        raise BundleError(str(exc)) from exc


def _verified_bundle(bundle_path: str) -> tuple[dict, dict[str, bytes]]:
    """Return the result and its held buffers; producer locators are never accessed."""
    root = Path(bundle_path).absolute()
    try:
        _no_links(root)
        _require(root.is_dir(), "bundle must be a directory")
        manifest = _json(_read(root / "manifest.json", MAX_MANIFEST_BYTES))
        _require(
            set(manifest)
            == {"bundle_schema", "quantfit_version", "created_utc", "scientific_claims_verified", "files", "scope"},
            "unsupported replay manifest fields",
        )
        _require(
            type(manifest["bundle_schema"]) is int and manifest["bundle_schema"] == BUNDLE_SCHEMA,
            "unsupported replay schema",
        )
        _require(
            manifest["scientific_claims_verified"] is False and manifest["scope"] == SCOPE,
            "integrity cannot claim scientific proof",
        )
        for key in ("quantfit_version", "created_utc"):
            _require(isinstance(manifest[key], str) and bool(manifest[key].strip()), f"manifest {key} must be a string")
        entries = manifest["files"]
        _require(isinstance(entries, list) and len(entries) == 4, "replay manifest needs exactly four roles")
        roles = set()
        for entry in entries:
            _require(
                isinstance(entry, dict) and set(entry) == {"role", "path", "sha256", "size_bytes"},
                "unsupported file entry",
            )
            role = entry["role"]
            _require(isinstance(role, str) and role in ROLES and role not in roles, "unsupported/duplicate replay role")
            _require(entry["path"] == ROLES[role], "member paths must be canonical relative role filenames")
            _require(
                isinstance(entry["sha256"], str) and bool(_SHA.fullmatch(entry["sha256"])), "invalid member SHA256"
            )
            _require(
                type(entry["size_bytes"]) is int and 0 < entry["size_bytes"] <= MAX_REPORT_BYTES,
                "unsupported member size",
            )
            roles.add(role)
        _require(
            {p.name for p in root.iterdir()} == {"manifest.json", *ROLES.values()}, "unlisted/missing files are refused"
        )
        data, mismatches = {}, []
        for entry in entries:
            raw = _read(root / entry["path"], MAX_REPORT_BYTES)
            actual = hashlib.sha256(raw).hexdigest()
            if actual != entry["sha256"] or len(raw) != entry["size_bytes"]:
                mismatches.append(
                    {
                        "role": entry["role"],
                        "expected_sha256": entry["sha256"],
                        "actual_sha256": actual,
                        "expected_bytes": entry["size_bytes"],
                        "actual_bytes": len(raw),
                    }
                )
            data[entry["role"]] = raw
        if mismatches:
            return _result(root, manifest, mismatches=mismatches), data
        original, receiving = _validate(data, [str(root / ROLES[f"replicate-{i}"]) for i in range(1, 4)])
        return _result(root, manifest, original=original, receiving=receiving), data
    except (OSError, RuntimeError, RecursionError, TypeError, ValueError) as exc:
        if isinstance(exc, BundleError):
            raise
        raise BundleError(str(exc)) from exc


def verify_replay_bundle(bundle_path: str) -> dict:
    """Check fixed local members and return separate receiving-path T0 evidence."""
    return _verified_bundle(bundle_path)[0]
