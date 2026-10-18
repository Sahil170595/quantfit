"""Portable paired reproduction over saved aggregates, with explicit synthetic controls."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from quantfit.bundle import create_replay_bundle
from quantfit.cli import main
from quantfit.reproduce import ReproduceError, compare, compare_bundles, within_hardware_identical
from quantfit.safety.verify import SafetyDrift

SOURCE = Path(__file__).resolve().parents[1] / "validation/2026-10-09-phi4-public-candidate/producer"


def make_bundle(
    tmp_path, label, *, flips=0, unsafe=12, disagreement=False, historical=False, foreign=False, baseline_model=None
):
    producer = tmp_path / f"producer-{label}"
    producer.mkdir()
    paths = []
    for i in range(1, 4):
        raw = (SOURCE / f"run-{i}/report.json").read_bytes()
        if not historical:
            value = json.loads(raw)
            count = flips + int(disagreement and i == 3)
            zones = {
                "clear_unsafe": {"n": 12, "baseline_refused": unsafe, "quant_refused": unsafe - count},
                "clear_safe": {"n": 12, "baseline_refused": 0, "quant_refused": 0},
                "borderline": {"n": 16, "baseline_refused": 0, "quant_refused": 0},
            }
            value["drift"] = SafetyDrift(40, 12, unsafe, unsafe - count, count, 28, 0, 0, 0, zones).to_dict()
            value["judge_runtime_s"] = i + sum(label.encode()) / 1000
            if baseline_model is not None:
                value["baseline"]["model"] = baseline_model
            raw = (json.dumps(value, indent=2) + "\n").encode()
        path = producer / f"run-{i}.json"
        path.write_bytes(raw)
        paths.append(str(path))
    t0_path = producer / "t0.json"
    t0 = within_hardware_identical(paths, out_path=str(t0_path))
    if foreign:
        labels = [f"Z:\\foreign\\{label}\\run-{i}.json" for i in range(1, 4)]
        for member, path in zip(t0["reports"], labels, strict=True):
            member["path"] = path
        for differing in t0["differing"]:
            differing["replicate"], differing["against"] = labels[2], labels[0]
        t0_path.write_text(json.dumps(t0), encoding="utf-8")
    bundle = tmp_path / label
    create_replay_bundle(paths, str(t0_path), str(bundle))
    return bundle, paths, t0


@pytest.mark.parametrize(
    "flips,unsafe,disagreement,outcome,code",
    [
        (0, 12, False, "reproduced", 0),
        (1, 12, False, "breach", 3),
        (0, 11, False, "reproduced_with_denominator_drift", 3),
        (0, 12, True, "void", 4),
        (0, 0, False, "void", 4),
    ],
)
def test_bundle_outcomes_and_loose_report_parity(tmp_path, flips, unsafe, disagreement, outcome, code):
    ref, ref_paths, ref_t0 = make_bundle(tmp_path, "reference")
    cand, cand_paths, cand_t0 = make_bundle(
        tmp_path, "candidate", flips=flips, unsafe=unsafe, disagreement=disagreement
    )
    loose = compare(ref_paths[0], cand_paths[0], t0_reference=ref_t0, t0_candidate=cand_t0)
    paired = compare_bundles(str(ref), str(cand))
    assert paired["outcome"] == loose["outcome"] == outcome
    assert paired["exit_code"] == loose["exit_code"] == code
    for key in ("checks", "void_reasons", "attribution", "passed", "failing_predicates", "witnessed"):
        assert paired[key] == loose[key]


@pytest.mark.parametrize("foreign", [False, True])
def test_removed_producers_and_foreign_labels_remain_usable(tmp_path, foreign):
    ref, _, original = make_bundle(tmp_path, "reference", foreign=foreign)
    cand, _, _ = make_bundle(tmp_path, "candidate", foreign=foreign)
    originals = {path.name: path.read_bytes() for path in ref.iterdir()}
    shutil.rmtree(tmp_path / "producer-reference")
    shutil.rmtree(tmp_path / "producer-candidate")
    moved = tmp_path / "relocated-reference"
    ref.rename(moved)
    output = tmp_path / "comparison.json"
    result = compare_bundles(str(moved), str(cand), str(output))
    assert result["exit_code"] == 0 and json.loads(output.read_bytes()) == result
    evidence = result["bundle_evidence"]["reference"]
    assert evidence["selected_role"] == "replicate-1" and evidence["selected_member"] == "report-1.json"
    assert evidence["selected_report_sha256"] == hashlib.sha256(originals["report-1.json"]).hexdigest()
    assert evidence["original_t0"] == original
    assert evidence["receiving_t0"]["reports"][0]["path"] == str(moved / "report-1.json")
    assert [member["role"] for member in evidence["report_bindings"]] == [f"replicate-{i}" for i in range(1, 4)]
    for binding, producer, receiving in zip(
        evidence["report_bindings"],
        evidence["original_t0"]["reports"],
        evidence["receiving_t0"]["reports"],
        strict=True,
    ):
        assert binding["report_sha256"] == producer["report_sha256"] == receiving["report_sha256"]
        assert binding["producer_path"] == producer["path"] and binding["receiving_path"] == receiving["path"]
    assert evidence["producer_locations_verified"] is False
    assert evidence["independent_execution_verified"] is evidence["scientific_claims_verified"] is False
    t0 = result["preconditions"]["T0_within_hardware_byte_identity"]["reference"]
    assert t0["comparison_report_is_member"] is t0["bound_to_comparison_report"] is True
    assert all((moved / name).read_bytes() == raw for name, raw in originals.items())


def test_valid_t0_does_not_erase_native_t1_void(tmp_path):
    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate", baseline_model="synthetic/different-baseline")
    result = compare_bundles(str(ref), str(cand))
    assert result["exit_code"] == 4 and result["void_reasons"] == ["T1_not_one_measurement"]
    assert result["preconditions"]["T0_within_hardware_byte_identity"]["pass"] is True


def test_manifest_declaration_order_does_not_change_fixed_selection(tmp_path):
    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    path = cand / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["files"].reverse()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = compare_bundles(str(ref), str(cand))
    assert result["exit_code"] == 0
    evidence = result["bundle_evidence"]["candidate"]
    assert evidence["manifest"] == manifest
    assert evidence["selected_report_sha256"] == hashlib.sha256((cand / "report-1.json").read_bytes()).hexdigest()
    assert [binding["role"] for binding in evidence["report_bindings"]] == [f"replicate-{i}" for i in range(1, 4)]


def test_duplicate_historical_bundle_preserves_native_p1_void(tmp_path):
    ref, _, _ = make_bundle(tmp_path, "historical", historical=True)
    copied = tmp_path / "copied"
    shutil.copytree(ref, copied)
    for candidate in (ref, copied):
        result = compare_bundles(str(ref), str(candidate))
        assert result["exit_code"] == 4 and result["void_reasons"] == ["P1_identical_input_files"]
        assert result["reports"]["reference"]["drift_identity"]["over_refusal"]["overrefusal_regressions"] == 2
        assert result["bundle_evidence"]["candidate"]["independent_execution_verified"] is False


def test_receiving_parent_alias_preserves_native_p1_path_observation(tmp_path):
    ref, _, _ = make_bundle(tmp_path, "historical", historical=True)
    alias = ref / ".." / ref.name
    paired = compare_bundles(str(ref), str(alias))
    loose = compare(str(ref / "report-1.json"), str(alias / "report-1.json"))
    assert paired["exit_code"] == loose["exit_code"] == 4
    assert paired["preconditions"]["P1_distinct_reports"] == loose["preconditions"]["P1_distinct_reports"]
    assert paired["preconditions"]["P1_distinct_reports"]["same_path"] is True


def test_after_verify_substitution_cannot_reopen_or_change_core(tmp_path, monkeypatch):
    import quantfit.replay_bundle as replay
    from quantfit import reproduce

    ref, _, _ = make_bundle(tmp_path, "reference", foreign=True)
    cand, _, _ = make_bundle(tmp_path, "candidate", foreign=True)
    verify = replay._verified_bundle
    consumed = []

    def substitute(path):
        verified, held = verify(path)
        consumed.append(path)
        for member in Path(path).iterdir():
            member.write_bytes(b"invalid after verified consumption")
        if len(consumed) == 2:
            monkeypatch.setattr(Path, "resolve", forbidden)
        return verified, held

    def forbidden(*args, **kwargs):
        pytest.fail("reopened/resolved a source in held comparison")

    monkeypatch.setattr(replay, "_verified_bundle", substitute)
    monkeypatch.setattr(reproduce, "_load", forbidden)
    monkeypatch.setattr(reproduce, "within_hardware_identical", forbidden)
    monkeypatch.setattr(reproduce, "_absolute_report_path", forbidden)
    result = compare_bundles(str(ref), str(cand))
    assert result["exit_code"] == 0 and consumed == [str(ref), str(cand)]


def refresh_manifest(bundle, name, raw):
    (bundle / name).write_bytes(raw)
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    for entry in manifest["files"]:
        if entry["path"] == name:
            entry["sha256"], entry["size_bytes"] = hashlib.sha256(raw).hexdigest(), len(raw)
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.mark.parametrize(
    "change", ["pass", "ordered", "short", "identity", "membership", "private", "schema", "duplicate"]
)
def test_rehashed_forged_t0_or_report_still_fails_operationally(tmp_path, change):
    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate", disagreement=True)
    name = "t0.json"
    value = json.loads((cand / name).read_bytes())
    if change == "pass":
        value["pass"] = True
    elif change == "ordered":
        value["reports"].reverse()
    elif change == "short":
        value["reports"].pop()
    elif change == "identity":
        value["environment_identity"]["python"] = "forged"
    elif change == "membership":
        value["reports"][0]["report_sha256"] = "0" * 64
    else:
        name = "report-1.json"
        value = json.loads((cand / name).read_bytes())
        if change == "private":
            value["env"]["renamed_payload"] = {"completion": "synthetic private value"}
        elif change == "schema":
            value["schema_version"] = True
        else:
            refresh_manifest(cand, "report-2.json", (cand / name).read_bytes())
    refresh_manifest(cand, name, json.dumps(value).encode())
    with pytest.raises(ReproduceError):
        compare_bundles(str(ref), str(cand))


@pytest.mark.parametrize("change", ["mismatch", "role", "schema", "extra"])
def test_invalid_integrity_and_closed_layout_fail_operationally(tmp_path, change):
    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    if change == "mismatch":
        member = cand / "report-1.json"
        member.write_bytes(member.read_bytes() + b" ")
    elif change == "extra":
        (cand / "extra.json").write_bytes(b"{}")
    else:
        manifest = json.loads((cand / "manifest.json").read_bytes())
        if change == "role":
            manifest["files"][0]["role"] = "report"
        else:
            manifest["bundle_schema"] = 1
        (cand / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReproduceError):
        compare_bundles(str(ref), str(cand))


@pytest.mark.parametrize("side", ["reference", "candidate"])
@pytest.mark.parametrize(
    "name", ["manifest.json", "report-1.json", "report-3.json", "t0.json", "new.json", "nested/new.json"]
)
def test_both_closed_roots_protected_before_output(tmp_path, side, name):
    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    originals = {path: path.read_bytes() for bundle in (ref, cand) for path in bundle.iterdir()}
    target = (ref if side == "reference" else cand) / name
    with pytest.raises(ReproduceError):
        compare_bundles(str(ref), str(cand), str(target))
    assert all(path.read_bytes() == raw for path, raw in originals.items())


@pytest.mark.parametrize("side", ["reference", "candidate"])
def test_output_hardlink_alias_refused(tmp_path, side):
    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    member = (ref if side == "reference" else cand) / "report-2.json"
    original = member.read_bytes()
    target = tmp_path / "hardlink.json"
    os.link(member, target)
    with pytest.raises(ReproduceError):
        compare_bundles(str(ref), str(cand), str(target))
    assert member.read_bytes() == target.read_bytes() == original


@pytest.mark.parametrize("side", ["reference", "candidate"])
def test_publication_rechecks_output_aliases_after_staging(tmp_path, monkeypatch, side):
    import quantfit.reproduce as module

    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    member = (ref if side == "reference" else cand) / "t0.json"
    original = member.read_bytes()
    target = tmp_path / "result.json"
    factory = module.tempfile.NamedTemporaryFile

    class SubstitutedOutput:
        def __init__(self, *args, **kwargs):
            self.stream = factory(*args, **kwargs)
            self.name = self.stream.name

        def __enter__(self):
            return self.stream

        def __exit__(self, *args):
            self.stream.close()
            os.link(member, target)
            monkeypatch.setattr(Path, "resolve", lambda *args: pytest.fail("resolved a held path before publication"))

    monkeypatch.setattr(module.tempfile, "NamedTemporaryFile", SubstitutedOutput)
    with pytest.raises(ReproduceError):
        compare_bundles(str(ref), str(cand), str(target))
    assert member.read_bytes() == target.read_bytes() == original
    assert not list(tmp_path.glob(".reproduce-*"))


@pytest.mark.parametrize("fault", ["partial", "short", "flush", "close", "replace", "interrupt"])
def test_failed_atomic_output_preserves_existing_result(tmp_path, monkeypatch, fault):
    import quantfit.reproduce as module

    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    out = tmp_path / "result.json"
    out.write_bytes(b"existing unrelated result")
    factory = module.tempfile.NamedTemporaryFile

    class FaultStream:
        def __init__(self, *args, **kwargs):
            self.stream = factory(*args, **kwargs)
            self.name = self.stream.name

        def __enter__(self):
            return self

        def fileno(self):
            return self.stream.fileno()

        def write(self, raw):
            if fault == "interrupt":
                self.stream.write(raw)
                raise KeyboardInterrupt()
            if fault in ("partial", "short"):
                self.stream.write(raw[: len(raw) // 2])
                if fault == "partial":
                    raise OSError("synthetic partial write")
                return len(raw) // 2
            return self.stream.write(raw)

        def flush(self):
            self.stream.flush()
            if fault == "flush":
                raise OSError("synthetic flush failure")

        def __exit__(self, *args):
            self.stream.close()
            if fault == "close":
                raise OSError("synthetic close failure")

    monkeypatch.setattr(module.tempfile, "NamedTemporaryFile", FaultStream)
    if fault == "replace":
        monkeypatch.setattr(module.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("synthetic replace")))
    with pytest.raises(KeyboardInterrupt if fault == "interrupt" else ReproduceError):
        compare_bundles(str(ref), str(cand), str(out))
    assert out.read_bytes() == b"existing unrelated result"
    assert not list(tmp_path.glob(".reproduce-*"))


def test_bundle_cli_preserves_envelope_and_native_exit(tmp_path, capsys):
    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate", flips=1)
    assert main(["reproduce", "--reference-bundle", str(ref), "--candidate-bundle", str(cand), "--json"]) == 3
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["exit_code"] == envelope["result"]["exit_code"] == 3
    assert envelope["result"]["outcome"] == "breach"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--reference-bundle", "ref"],
        ["--candidate-bundle", "cand"],
        ["--reference", "ref", "--candidate-bundle", "cand"],
        ["--reference-bundle", "ref", "--candidate", "cand"],
        ["--reference-bundle", "ref", "--candidate-bundle", "cand", "--reference", "loose"],
        ["--reference-bundle", "ref", "--candidate-bundle", "cand", "--t0-reference", "t0"],
        ["--reference-bundle", "ref", "--candidate-bundle", "cand", "--t0-candidate", "t0"],
    ],
)
def test_cli_incomplete_or_mixed_modes_fail_before_consumption(monkeypatch, arguments):
    import quantfit.reproduce as module

    monkeypatch.setattr(module, "compare_bundles", lambda *args: pytest.fail("consumed invalid input mode"))
    monkeypatch.setattr(module, "compare", lambda *args, **kwargs: pytest.fail("consumed invalid input mode"))
    assert main(["reproduce", *arguments, "--json"]) == 2


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO unavailable")
def test_fifo_bundle_member_refuses_without_hanging(tmp_path):
    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    member = cand / "report-1.json"
    member.unlink()
    os.mkfifo(member)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "quantfit.cli",
            "reproduce",
            "--reference-bundle",
            str(ref),
            "--candidate-bundle",
            str(cand),
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 2 and json.loads(completed.stdout)["result"] is None


@pytest.mark.parametrize("which", ["root", "member", "output"])
def test_symlink_inputs_and_outputs_refused(tmp_path, which):
    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    out = tmp_path / "output.json"
    link = tmp_path / "link"
    source = cand if which == "root" else cand / "report-1.json"
    try:
        link.symlink_to(source, target_is_directory=which == "root")
    except OSError:
        pytest.skip("symlink creation unavailable")
    if which == "root":
        cand = link
    elif which == "member":
        source.unlink()
        source.symlink_to(ref / "report-1.json")
    else:
        out = link
    with pytest.raises(ReproduceError):
        compare_bundles(str(ref), str(cand), str(out))
