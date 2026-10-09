"""Offline T0 handoff of saved aggregates; no new model or independence proof."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from quantfit.bundle import BundleError, create_replay_bundle, verify_replay_bundle
from quantfit.cli import main
from quantfit.reproduce import within_hardware_identical
from quantfit.safety.verify import SafetyDrift

SOURCE = Path(__file__).resolve().parents[1] / "validation/2026-10-09-phi4-public-candidate/producer"


def inputs(tmp_path, *, disagreement=False):
    paths = []
    for i in range(1, 4):
        path = tmp_path / f"rep-{i}.json"
        path.write_bytes((SOURCE / f"run-{i}/report.json").read_bytes())
        paths.append(str(path))
    if disagreement:
        data = json.loads(Path(paths[2]).read_bytes())
        data["drift"] = SafetyDrift(
            n=40,
            unsafe_n=12,
            unsafe_baseline_refused=12,
            unsafe_quant_refused=12,
            harmful_compliance_regressions=0,
            safe_n=28,
            safe_baseline_refused=8,
            safe_quant_refused=9,
            overrefusal_regressions=1,
            by_zone=data["drift"]["by_zone"],
        ).to_dict()
        Path(paths[2]).write_text(json.dumps(data), encoding="utf-8")
    t0 = tmp_path / "original-t0.json"
    within_hardware_identical(paths, out_path=str(t0))
    return paths, t0


@pytest.mark.parametrize("disagreement", [False, True])
def test_exact_originals_survive_producer_removal_and_relocation(tmp_path, disagreement):
    paths, t0 = inputs(tmp_path, disagreement=disagreement)
    originals = [Path(p).read_bytes() for p in paths] + [t0.read_bytes()]
    out = tmp_path / "bundle"
    result = create_replay_bundle(paths, str(t0), str(out))
    assert result["integrity_verified"] is True
    assert result["original_t0"]["protocol_pass"] is (not disagreement)
    assert result["scientific_claims_verified"] is False
    for i, raw in enumerate(originals[:3], 1):
        assert (out / f"report-{i}.json").read_bytes() == raw
    assert (out / "t0.json").read_bytes() == originals[3]
    for path in [*paths, t0]:
        Path(path).unlink()
    moved = tmp_path / "relocated"
    out.rename(moved)
    checked = verify_replay_bundle(str(moved))
    assert checked["integrity_verified"] is True
    assert checked["original_t0"]["protocol_pass"] is (not disagreement)
    assert checked["receiving_t0"]["protocol_pass"] is (not disagreement)
    assert checked["producer_locations_verified"] is False
    assert checked["receiving_t0"]["independent_execution_verified"] is False
    assert checked["original_t0"]["reports"] != checked["receiving_t0"]["reports"]
    assert (moved / "t0.json").read_bytes() == originals[3]


def test_preserved_original_historical_phi4_t0(tmp_path):
    reports = [str(SOURCE / f"run-{i}/report.json") for i in range(1, 4)]
    t0 = SOURCE / "native-t0.json"
    original = t0.read_bytes()
    result = create_replay_bundle(reports, str(t0), str(tmp_path / "bundle"))
    assert result["original_t0"] == json.loads(original)
    assert result["original_t0"]["protocol_pass"] is True
    assert all(
        json.loads((tmp_path / f"bundle/report-{i}.json").read_bytes())["drift"]["over_refusal"][
            "overrefusal_regressions"
        ]
        == 2
        for i in range(1, 4)
    )


@pytest.mark.parametrize(
    "change",
    ["pass", "count", "identity", "hash", "ordered", "statement", "distinct", "independence", "unknown", "missing"],
)
def test_forged_t0_refused_before_creation(tmp_path, change):
    paths, t0 = inputs(tmp_path)
    data = json.loads(t0.read_bytes())
    if change == "pass":
        data["pass"] = False
    elif change == "count":
        data["n_replicates"] = True
    elif change == "identity":
        data["environment_identity"]["python"] = "forged"
    elif change == "hash":
        data["reports"][0]["report_sha256"] = "0" * 64
    elif change == "ordered":
        data["reports"].reverse()
    elif change == "statement":
        data["statement"] = "Independent reproduction is certified."
    elif change == "distinct":
        data["replicates_are_distinct_files"] = False
    elif change == "independence":
        data["independent_execution_verified"] = True
    elif change == "unknown":
        data["extra"] = True
    else:
        del data["measurement_identity"]
    t0.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "bundle"
    with pytest.raises(BundleError):
        create_replay_bundle(paths, str(t0), str(out))
    assert not out.exists()


def test_manifest_tampering_is_byte_mismatch_not_science_failure(tmp_path, capsys):
    paths, t0 = inputs(tmp_path)
    out = tmp_path / "bundle"
    create_replay_bundle(paths, str(t0), str(out))
    member = out / "report-2.json"
    member.write_bytes(member.read_bytes() + b" ")
    assert main(["bundle", "replay-verify", "--bundle", str(out), "--json"]) == 3
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["integrity_verified"] is False and result["receiving_t0"] is None


@pytest.mark.parametrize("foreign", [False, True])
def test_identity_bound_producer_labels_are_not_resolved_or_opened(tmp_path, monkeypatch, foreign):
    paths, t0 = inputs(tmp_path, disagreement=True)
    data = json.loads(t0.read_bytes())
    labels = [f"/foreign/host/run-{i}.json" if foreign else f"relative-{i}.json" for i in range(3)]
    for item, label in zip(data["reports"], labels, strict=True):
        item["path"] = label
    for item in data["differing"]:
        item["replicate"], item["against"] = labels[2], labels[0]
    t0.write_text(json.dumps(data), encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("portable validation resolved a path or used the native filesystem loader")

    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr("quantfit.reproduce._load", forbidden)
    out = tmp_path / "bundle"
    result = create_replay_bundle(paths, str(t0), str(out))
    assert result["original_t0"]["protocol_pass"] is False
    assert verify_replay_bundle(str(out))["producer_locations_verified"] is False


@pytest.mark.parametrize("kind", ["repeated", "duplicate-bytes", "swapped", "two", "four", "hardlink"])
def test_missing_distinctness_or_ordered_membership_refused(tmp_path, kind):
    paths, t0 = inputs(tmp_path)
    if kind == "repeated":
        paths[1] = paths[0]
    elif kind == "duplicate-bytes":
        Path(paths[1]).write_bytes(Path(paths[0]).read_bytes())
    elif kind == "swapped":
        paths.reverse()
    elif kind == "two":
        paths.pop()
    elif kind == "four":
        paths.append(paths[0])
    else:
        alias = tmp_path / "hardlink.json"
        os.link(paths[0], alias)
        paths[1] = str(alias)
    with pytest.raises(BundleError):
        create_replay_bundle(paths, str(t0), str(tmp_path / "bundle"))
    assert not (tmp_path / "bundle").exists()


@pytest.mark.parametrize(
    "kind",
    ["env", "decode", "binary", "cached", "stats", "private", "unknown", "nonfinite", "duplicate-json", "substituted"],
)
def test_corrupt_or_changed_reports_refused(tmp_path, kind):
    paths, t0 = inputs(tmp_path)
    path = Path(paths[1])
    data = json.loads(path.read_bytes())
    if kind == "env":
        data["env"]["python"] = "changed"
    elif kind == "decode":
        data["decode"]["max_new_tokens"] = 65
    elif kind == "binary":
        data["baseline"]["engine"]["binary_sha256"] = "0" * 64
    elif kind == "cached":
        data["baseline"]["engine"]["baseline_cache"] = {"served": True}
    elif kind == "stats":
        data["drift"]["over_refusal"]["mde_at_80pct_power"] = 0.9
    elif kind == "private":
        data["env"]["renamed_payload"] = {"completion": "synthetic private data"}
    elif kind == "unknown":
        data["env"]["opaque"] = "synthetic payload"
    elif kind == "nonfinite":
        data["judge_runtime_s"] = float("nan")
    elif kind == "substituted":
        data["created_utc"] = "synthetic different source"
    if kind == "duplicate-json":
        path.write_bytes(b'{"schema_version":2,' + path.read_bytes()[1:])
    else:
        path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BundleError):
        create_replay_bundle(paths, str(t0), str(tmp_path / "bundle"))
    assert not (tmp_path / "bundle").exists()


@pytest.mark.parametrize("kind", ["disagreement", "protocol-pass", "identity-sha", "repeat-label", "unbound"])
def test_negative_t0_facts_and_identity_are_recomputed(tmp_path, kind):
    paths, t0 = inputs(tmp_path, disagreement=True)
    data = json.loads(t0.read_bytes())
    if kind == "disagreement":
        data["differing"] = []
    elif kind == "protocol-pass":
        data["protocol_pass"] = True
    elif kind == "identity-sha":
        data["identity_sha256"] = "0" * 64
    elif kind == "repeat-label":
        data["reports"][1]["path"] = data["reports"][0]["path"]
    else:
        del data["reports"][0]["report_sha256"]
    t0.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BundleError):
        create_replay_bundle(paths, str(t0), str(tmp_path / "bundle"))


@pytest.mark.parametrize(
    "kind", ["traversal", "absolute", "extra", "missing", "repeat-role", "wrong-schema", "bool-size", "raw", "unknown"]
)
def test_manifest_layout_refuses_unsupported_inputs(tmp_path, kind):
    paths, t0 = inputs(tmp_path)
    out = tmp_path / "bundle"
    create_replay_bundle(paths, str(t0), str(out))
    path = out / "manifest.json"
    data = json.loads(path.read_bytes())
    if kind == "traversal":
        data["files"][0]["path"] = "../rep-1.json"
    elif kind == "absolute":
        data["files"][0]["path"] = paths[0]
    elif kind == "extra":
        (out / "unlisted.json").write_text("{}")
    elif kind == "missing":
        (out / "report-1.json").unlink()
    elif kind == "repeat-role":
        data["files"][1] = data["files"][0]
    elif kind == "wrong-schema":
        data["bundle_schema"] = 1
    elif kind == "bool-size":
        data["files"][0]["size_bytes"] = True
    elif kind == "raw":
        data["completion"] = "synthetic raw"
    else:
        data["extra"] = False
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BundleError):
        verify_replay_bundle(str(out))


@pytest.mark.parametrize("hardlink", [False, True])
def test_output_alias_preserves_source(tmp_path, hardlink):
    paths, t0 = inputs(tmp_path)
    output = Path(paths[0])
    original = output.read_bytes()
    if hardlink:
        output = tmp_path / "alias"
        os.link(paths[0], output)
    with pytest.raises(BundleError):
        create_replay_bundle(paths, str(t0), str(output))
    assert Path(paths[0]).read_bytes() == original


def test_held_input_substitution_cannot_change_copied_members(tmp_path, monkeypatch):
    import quantfit.replay_bundle as replay

    paths, t0 = inputs(tmp_path)
    held = Path(paths[0]).read_bytes()
    read = replay._read

    def substituted(path, limit):
        raw = read(path, limit)
        if path == t0:
            Path(paths[0]).write_bytes(b"changed after consumption")
        return raw

    monkeypatch.setattr(replay, "_read", substituted)
    out = tmp_path / "bundle"
    create_replay_bundle(paths, str(t0), str(out))
    assert (out / "report-1.json").read_bytes() == held
    assert verify_replay_bundle(str(out))["integrity_verified"] is True


@pytest.mark.parametrize("fault", ["partial", "short", "flush", "close", "interrupt"])
@pytest.mark.parametrize("member", ["report-2.json", "manifest.json"])
def test_incomplete_staging_never_advertises_a_valid_bundle(tmp_path, monkeypatch, fault, member):
    paths, t0 = inputs(tmp_path)
    out = tmp_path / "bundle"
    original_open = Path.open

    class Broken:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def write(self, raw):
            if fault in ("partial", "short"):
                n = self.handle.write(raw[: len(raw) // 2])
                if fault == "partial":
                    raise OSError("synthetic partial write")
                return n
            n = self.handle.write(raw)
            if fault == "interrupt":
                raise KeyboardInterrupt()
            return n

        def flush(self):
            self.handle.flush()
            if fault == "flush":
                raise OSError("synthetic flush failure")

        def __exit__(self, *args):
            self.handle.close()
            if fault == "close":
                raise OSError("synthetic close failure")

    def failing(path, mode="r", *args, **kwargs):
        h = original_open(path, mode, *args, **kwargs)
        return Broken(h) if path.parent == out and path.name == member and mode == "xb" else h

    monkeypatch.setattr(Path, "open", failing)
    with pytest.raises((BundleError, KeyboardInterrupt)):
        create_replay_bundle(paths, str(t0), str(out))
    assert not out.exists()
    assert all(Path(p).exists() for p in paths) and t0.exists()


@pytest.mark.parametrize("which", ["source", "member", "manifest"])
def test_links_are_refused(tmp_path, which):
    paths, t0 = inputs(tmp_path)
    out = tmp_path / "bundle"
    link = tmp_path / "link.json"
    try:
        link.symlink_to(paths[0])
    except OSError:
        pytest.skip("symlink creation unavailable to this account")
    if which == "source":
        paths[0] = str(link)
        with pytest.raises(BundleError):
            create_replay_bundle(paths, str(t0), str(out))
    else:
        create_replay_bundle(paths, str(t0), str(out))
        member = out / ("manifest.json" if which == "manifest" else "report-1.json")
        copied = tmp_path / "saved.json"
        member.rename(copied)
        member.symlink_to(copied)
        with pytest.raises(BundleError):
            verify_replay_bundle(str(out))


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO unavailable on this platform")
@pytest.mark.parametrize("which", ["source", "member", "manifest"])
def test_fifo_cli_refuses_without_hanging(tmp_path, which):
    paths, t0 = inputs(tmp_path)
    out = tmp_path / "bundle"
    if which == "source":
        Path(paths[0]).unlink()
        os.mkfifo(paths[0])
        command = ["replay-create", "--reports", *paths, "--t0", str(t0), "--out", str(out)]
    else:
        create_replay_bundle(paths, str(t0), str(out))
        member = out / ("manifest.json" if which == "manifest" else "report-1.json")
        member.unlink()
        os.mkfifo(member)
        command = ["replay-verify", "--bundle", str(out)]
    completed = subprocess.run(
        [sys.executable, "-m", "quantfit.cli", "bundle", *command, "--json"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert completed.returncode == 2 and json.loads(completed.stdout)["exit_code"] == 2


def test_cli_create_and_verify_preserve_negative_t0(tmp_path, capsys):
    paths, t0 = inputs(tmp_path, disagreement=True)
    out = tmp_path / "bundle"
    assert main(["bundle", "replay-create", "--reports", *paths, "--t0", str(t0), "--out", str(out), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["original_t0"]["protocol_pass"] is False
    assert main(["bundle", "replay-verify", "--bundle", str(out), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["receiving_t0"]["protocol_pass"] is False


@pytest.mark.skipif(os.name != "nt", reason="Windows junction check")
def test_junction_sources_output_parents_and_bundle_roots_are_refused(tmp_path):
    paths, t0 = inputs(tmp_path)
    junction = tmp_path / "junction"
    quoted_link, quoted_target = [str(p).replace("'", "''") for p in (junction, tmp_path)]
    command = f"New-Item -ItemType Junction -Path '{quoted_link}' -Target '{quoted_target}' | Out-Null"
    completed = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    try:
        with pytest.raises(BundleError, match="junction"):
            create_replay_bundle([str(junction / Path(paths[0]).name), *paths[1:]], str(t0), str(tmp_path / "refused"))
        with pytest.raises(BundleError, match="junction"):
            create_replay_bundle(paths, str(t0), str(junction / "refused"))
        out = tmp_path / "bundle"
        create_replay_bundle(paths, str(t0), str(out))
        with pytest.raises(BundleError, match="junction"):
            verify_replay_bundle(str(junction / out.name))
    finally:
        junction.rmdir()  # only this owned link, never its target directory


def test_private_loader_retains_exact_verified_buffers(tmp_path, monkeypatch):
    import quantfit.replay_bundle as replay
    from quantfit.replay_bundle import _verified_bundle

    paths, t0 = inputs(tmp_path)
    out = tmp_path / "bundle"
    create_replay_bundle(paths, str(t0), str(out))
    calls = []
    read = replay._read

    def counted(path, limit):
        calls.append(path.name)
        return read(path, limit)

    monkeypatch.setattr(replay, "_read", counted)
    result, held = _verified_bundle(str(out))
    assert result["integrity_verified"] is True
    assert set(held) == {"replicate-1", "replicate-2", "replicate-3", "t0"}
    assert len(calls) == 5 and len(set(calls)) == 5
    assert held["replicate-1"] == Path(paths[0]).read_bytes()
    assert held["t0"] == t0.read_bytes()
