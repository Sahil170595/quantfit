"""Historical aggregates and explicitly synthetic policy cases, no new inference."""

import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from quantfit.repeatability import RepeatabilityError, analyze_replicates, publish_outputs
from quantfit.safety.verify import SafetyDrift

SOURCE = Path(__file__).resolve().parents[1] / "validation/2026-10-09-phi4-public-candidate/producer"


def reports(tmp_path, *, unsafe=12, flips=0):
    values = []
    for i in range(1, 4):
        value = json.loads((SOURCE / f"run-{i}/report.json").read_bytes())
        zones = {
            "clear_unsafe": {"n": 12, "baseline_refused": unsafe, "quant_refused": unsafe - flips},
            "clear_safe": {"n": 12, "baseline_refused": 0, "quant_refused": 0},
            "borderline": {"n": 16, "baseline_refused": 0, "quant_refused": 0},
        }
        value["drift"] = SafetyDrift(40, 12, unsafe, unsafe - flips, flips, 28, 0, 0, 0, zones).to_dict()
        path = tmp_path / f"synthetic-{i}.json"
        path.write_bytes((json.dumps(value, indent=2) + "\n").encode())
        values.append(str(path))
    return values


@pytest.mark.parametrize("unsafe,flips,code", [(12, 0, 0), (12, 1, 3), (0, 0, 4)])
def test_unchanged_synthetic_outcomes_preserve_native_axes(tmp_path, unsafe, flips, code):
    result = analyze_replicates(reports(tmp_path, unsafe=unsafe, flips=flips))
    assert result["evidence_valid"] is True and result["exit_code"] == code
    assert result["full_report_repeatability"]["pass"] is True
    assert result["native_t0"]["result"]["protocol_pass"] is True
    assert [r["native_exit_code"] for r in result["runs"]] == [code] * 3
    assert result["scientific_claims_verified"] is False


def test_real_historical_negative_is_repeatable_but_exits_three():
    result = analyze_replicates([str(SOURCE / f"run-{i}/report.json") for i in range(1, 4)])
    assert result["exit_code"] == 3 and result["outcome"] == "native_flags"
    assert result["full_report_repeatability"]["pass"] is True
    assert result["native_t0"]["result"]["protocol_pass"] is True
    assert [r["native_exit_code"] for r in result["runs"]] == [3, 3, 3]
    assert all(r["axes"]["over-refusal"]["flagged_flips"] == 2 for r in result["runs"])
    assert all(
        r["axes"]["refusal-robustness"]["null_interpretation"] == "the detector did not fire" for r in result["runs"]
    )


def test_valid_environment_disagreement_retains_facts_with_t0_refusal(tmp_path):
    paths = reports(tmp_path)
    path = Path(paths[1])
    value = json.loads(path.read_bytes())
    value["env"]["torch"] = "different"
    path.write_text(json.dumps(value), encoding="utf-8")
    result = analyze_replicates(paths)
    assert result["evidence_valid"] is True and result["exit_code"] == 2 and result["outcome"] == "t0_refused"
    assert result["native_t0"]["status"] == "refused" and len(result["runs"]) == 3
    assert result["full_report_repeatability"]["differences"] == [
        {"replicate": paths[1], "against": paths[0], "pointer": "/env/torch"}
    ]


def test_provenance_outside_t0_and_one_ulp_are_not_ignored(tmp_path):
    paths = reports(tmp_path)
    path = Path(paths[2])
    value = json.loads(path.read_bytes())
    value["baseline"]["engine"]["runtime_scope"] = "changed provenance"
    value["drift"]["refusal_robustness"]["mde_at_80pct_power"] = math.nextafter(
        value["drift"]["refusal_robustness"]["mde_at_80pct_power"], 1
    )
    path.write_text(json.dumps(value), encoding="utf-8")
    result = analyze_replicates(paths)
    assert result["exit_code"] == 3 and result["full_report_repeatability"]["pass"] is False
    assert {d["pointer"] for d in result["full_report_repeatability"]["differences"]} == {
        "/baseline/engine/runtime_scope",
        "/drift/refusal_robustness/mde_at_80pct_power",
    }


def test_shared_diff_helper_has_unambiguous_rfc6901_pointers():
    from quantfit.report_comparison import differences

    assert differences({"a/b": 1, "a": {"b": 1}, "a~b": [1]}, {"a/b": 2, "a": {"b": 2}, "a~b": [2]}) == [
        "/a/b",
        "/a~0b/0",
        "/a~1b",
    ]
    assert differences({"x": False}, {"x": 0}) == ["/x"]
    assert differences({"x": 0}, {"x": 0.0}) == ["/x"]
    assert differences({"x": None}, {}) == ["/x"]
    assert differences({"x": [1, 2]}, {"x": [2, 1]}) == ["/x/0", "/x/1"]
    assert differences({"x": [1]}, {"x": [1, 2]}) == ["/x"]


def test_campaign_extraction_preserves_historical_policy_results():
    import importlib.util

    from quantfit.report_comparison import differences, normalized

    spec = importlib.util.spec_from_file_location(
        "reference_campaign", SOURCE.parents[2] / "tools/ci_reference_campaign.py"
    )
    campaign = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(campaign)
    values = [json.loads((SOURCE / f"run-{i}/report.json").read_bytes()) for i in range(1, 4)]
    assert campaign.ALLOWED_VOLATILE_PATHS == [
        "/created_utc",
        "/judge_runtime_s",
        "/baseline/runtime_s",
        "/quantized/runtime_s",
    ]
    assert all(campaign._normalized(value) == normalized(value) for value in values)
    assert all(
        campaign._differences(normalized(values[0]), normalized(value))
        == differences(normalized(values[0]), normalized(value))
        == []
        for value in values[1:]
    )


def test_formatting_is_not_identity_and_only_four_runtime_fields_are_ignored(tmp_path):
    paths = reports(tmp_path)
    path = Path(paths[2])
    value = json.loads(path.read_bytes())
    value["created_utc"] = "explicitly synthetic changed timestamp"
    value["judge_runtime_s"] = 1
    value["baseline"]["runtime_s"] = 2
    value["quantized"]["runtime_s"] = 3
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    result = analyze_replicates(paths)
    assert result["exit_code"] == 0 and result["full_report_repeatability"]["pass"]
    assert result["full_report_repeatability"]["ignored_paths"] == [
        "/created_utc",
        "/judge_runtime_s",
        "/baseline/runtime_s",
        "/quantized/runtime_s",
    ]


@pytest.mark.parametrize("pointer", ["judge_runtime_s", "baseline/runtime_s", "quantized/runtime_s"])
@pytest.mark.parametrize("invalid", [-1, True, "1", float("inf")])
def test_ignored_runtime_fields_are_validated_before_removal(tmp_path, pointer, invalid):
    paths = reports(tmp_path)
    value = json.loads(Path(paths[1]).read_bytes())
    keys = pointer.split("/")
    parent = value if len(keys) == 1 else value[keys[0]]
    parent[keys[-1]] = invalid
    Path(paths[1]).write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(RepeatabilityError):
        analyze_replicates(paths)


@pytest.mark.parametrize("field", ["decode", "binary", "env", "cached"])
def test_valid_causal_or_cache_refusal_retains_three_runs(tmp_path, field):
    paths = reports(tmp_path)
    path = Path(paths[1])
    data = json.loads(path.read_bytes())
    if field == "decode":
        data["decode"]["max_new_tokens"] = 65
    elif field == "binary":
        data["baseline"]["engine"]["binary_sha256"] = "0" * 64
    elif field == "env":
        data["env"]["python"] = "different recorded environment"
    else:
        data["baseline"]["engine"]["baseline_cache"] = {"served": True}
    path.write_text(json.dumps(data), encoding="utf-8")
    result = analyze_replicates(paths)
    assert result["evidence_valid"] is True and result["exit_code"] == 2
    assert result["native_t0"]["status"] == "refused" and len(result["runs"]) == 3


@pytest.mark.parametrize("kind", ["duplicate", "nonfinite", "private", "unknown", "verdict", "flags", "mde", "deep"])
def test_malformed_aggregates_do_not_produce_an_analysis(tmp_path, kind):
    paths = reports(tmp_path)
    path = Path(paths[1])
    data = json.loads(path.read_bytes())
    if kind == "duplicate":
        raw = b'{"schema_version":2,' + path.read_bytes()[1:]
    elif kind == "deep":
        raw = b'{"deep":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"
    else:
        if kind == "nonfinite":
            data["judge_runtime_s"] = float("nan")
        elif kind == "private":
            data["env"]["renamed"] = {"completion": "explicitly synthetic forbidden field"}
        elif kind == "unknown":
            data["env"]["opaque"] = "unknown"
        elif kind == "verdict":
            data["drift"]["verdict"] = "fabricated"
        elif kind == "flags":
            data["drift"]["regression_detected"] = 0
        else:
            data["drift"]["over_refusal"]["mde_at_80pct_power"] = 0.9
        raw = json.dumps(data).encode()
    path.write_bytes(raw)
    out = tmp_path / "result.json"
    with pytest.raises(RepeatabilityError):
        analyze_replicates(paths, out_path=str(out))
    assert not out.exists()


@pytest.mark.parametrize("alias", ["same", "canonical", "hardlink"])
def test_aliases_are_not_distinct_even_with_changing_read_bytes(tmp_path, monkeypatch, alias):
    import quantfit.repeatability as module

    paths = reports(tmp_path)
    held = [Path(p).read_bytes() for p in paths]
    if alias == "same":
        paths[1] = paths[0]
    elif alias == "canonical":
        paths[1] = str(tmp_path / ".." / tmp_path.name / Path(paths[0]).name)
    else:
        Path(paths[1]).unlink()
        os.link(paths[0], paths[1])
    monkeypatch.setattr(module, "_read", lambda p, n: held.pop(0))
    result = analyze_replicates(paths)
    assert len(result["runs"]) == 3 and result["evidence_valid"] is True
    assert len({r["sha256"] for r in result["runs"]}) == 3
    assert result["exit_code"] == 2 and result["native_t0"]["status"] == "refused"
    assert result["native_t0"]["result"] is None


def test_duplicate_bytes_are_refused_without_claiming_distinct_execution(tmp_path):
    paths = reports(tmp_path)
    Path(paths[1]).write_bytes(Path(paths[0]).read_bytes())
    result = analyze_replicates(paths)
    assert result["exit_code"] == 2 and result["native_t0"]["status"] == "refused"


def test_direct_inputs_are_consumed_once_even_when_paths_mutate(tmp_path, monkeypatch):
    import quantfit.repeatability as module

    paths = reports(tmp_path)
    held = {Path(p).resolve(): Path(p).read_bytes() for p in paths}
    seen = []
    read = module._read

    def mutate(path, limit):
        raw = read(path, limit)
        seen.append(path)
        path.write_bytes(b"invalid bytes after consumption")
        return raw

    monkeypatch.setattr(module, "_read", mutate)
    result = analyze_replicates(paths)
    assert result["exit_code"] == 0 and len(seen) == len(set(seen)) == 3
    import hashlib

    assert [r["sha256"] for r in result["runs"]] == [hashlib.sha256(held[Path(p)]).hexdigest() for p in paths]


def test_relocated_bundle_uses_verified_held_bytes_without_reopening(tmp_path, monkeypatch):
    import quantfit.repeatability as module
    import quantfit.replay_bundle as bundle
    from quantfit.bundle import create_replay_bundle
    from quantfit.reproduce import within_hardware_identical

    paths = reports(tmp_path)
    t0 = tmp_path / "t0.json"
    within_hardware_identical(paths, out_path=str(t0))
    out = tmp_path / "bundle"
    create_replay_bundle(paths, str(t0), str(out))
    for path in [*map(Path, paths), t0]:
        path.unlink()
    relocated = tmp_path / "moved"
    out.rename(relocated)
    read, seen = bundle._read, []

    def mutate(path, limit):
        raw = read(path, limit)
        seen.append(path.name)
        path.write_bytes(b"invalid after consumption")
        return raw

    monkeypatch.setattr(bundle, "_read", mutate)
    monkeypatch.setattr(module, "_read", lambda *a: pytest.fail("reopened report bytes"))
    result = analyze_replicates(bundle_path=str(relocated))
    assert result["exit_code"] == 0 and result["native_t0"]["result"]["protocol_pass"]
    assert sorted(seen) == ["manifest.json", "report-1.json", "report-2.json", "report-3.json", "t0.json"]


@pytest.mark.parametrize("unsafe,flips,code,failures,skips", [(12, 0, 0, 0, 0), (12, 1, 3, 3, 0), (0, 0, 4, 0, 3)])
def test_junit_counts_are_derived_from_eight_real_cases(tmp_path, unsafe, flips, code, failures, skips):
    from quantfit.repeatability_junit import repeatability_to_junit

    result = analyze_replicates(reports(tmp_path, unsafe=unsafe, flips=flips))
    assert result["exit_code"] == code
    xml = ET.fromstring(repeatability_to_junit(result))
    assert xml.attrib == {"tests": "8", "failures": str(failures), "errors": "0", "skipped": str(skips)}
    assert len(list(xml.iter("testcase"))) == 8


def test_junit_disagreement_and_refusal_are_different_cases(tmp_path):
    from quantfit.repeatability_junit import repeatability_to_junit

    paths = reports(tmp_path)
    data = json.loads(Path(paths[1]).read_bytes())
    data["env"]["python"] = "changed"
    Path(paths[1]).write_text(json.dumps(data), encoding="utf-8")
    xml = ET.fromstring(repeatability_to_junit(analyze_replicates(paths)))
    assert xml.attrib["failures"] == "1" and xml.attrib["errors"] == "1"


@pytest.mark.parametrize("alias", ["direct", "hardlink", "output", "symlink"])
def test_all_output_aliases_refused_before_any_write(tmp_path, alias):
    paths = reports(tmp_path)
    original = Path(paths[0]).read_bytes()
    other = tmp_path / "other.json"
    target = tmp_path / "target.json"
    if alias == "direct":
        target = Path(paths[0])
    elif alias == "hardlink":
        os.link(paths[0], target)
    elif alias == "symlink":
        try:
            target.symlink_to(paths[0])
        except OSError:
            pytest.skip("symlink creation unavailable")
    else:
        target = other
    with pytest.raises(RepeatabilityError):
        publish_outputs(paths, None, [(str(other), b"new"), (str(target), b"new2")])
    assert Path(paths[0]).read_bytes() == original and not other.exists()


@pytest.mark.parametrize("member", ["manifest.json", "report-1.json", "t0.json", "new.json", "nested/new.json"])
def test_bundle_directory_is_closed_to_any_output(tmp_path, member):
    from quantfit.bundle import create_replay_bundle

    out = tmp_path / "bundle"
    create_replay_bundle(
        [str(SOURCE / f"run-{i}/report.json") for i in range(1, 4)], str(SOURCE / "native-t0.json"), str(out)
    )
    original = {p: p.read_bytes() for p in out.iterdir()}
    with pytest.raises(RepeatabilityError):
        analyze_replicates(bundle_path=str(out), out_path=str(out / member))
    assert all(p.read_bytes() == raw for p, raw in original.items())


@pytest.mark.parametrize("fault", ["partial", "short", "flush", "close", "replace", "interrupt"])
def test_failed_output_staging_leaves_no_partial_or_temporary_file(tmp_path, monkeypatch, fault):
    import quantfit.repeatability as module

    paths = reports(tmp_path)
    out = tmp_path / "result.json"
    out.write_bytes(b"existing unrelated output")
    factory = module.tempfile.NamedTemporaryFile

    class FaultStream:
        def __init__(self, *args, **kw):
            self.stream = factory(*args, **kw)
            self.name = self.stream.name

        def __enter__(self):
            return self

        def write(self, raw):
            if fault in ("partial", "short"):
                self.stream.write(raw[: len(raw) // 2])
                if fault == "partial":
                    raise OSError("synthetic partial write")
                return len(raw) // 2
            if fault == "interrupt":
                self.stream.write(raw)
                raise KeyboardInterrupt()
            return self.stream.write(raw)

        def flush(self):
            self.stream.flush()
            if fault == "flush":
                raise OSError("synthetic flush error")

        def __exit__(self, *args):
            self.stream.close()
            if fault == "close":
                raise OSError("synthetic close error")

    monkeypatch.setattr(module.tempfile, "NamedTemporaryFile", FaultStream)
    if fault == "replace":
        monkeypatch.setattr(module.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("synthetic replace")))
    with pytest.raises(KeyboardInterrupt if fault == "interrupt" else RepeatabilityError):
        analyze_replicates(paths, out_path=str(out))
    assert out.read_bytes() == b"existing unrelated output"
    assert not list(tmp_path.glob(".repeatability-*"))


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO unavailable")
def test_fifo_cli_refuses_without_hanging(tmp_path):
    paths = reports(tmp_path)
    Path(paths[0]).unlink()
    os.mkfifo(paths[0])
    process = subprocess.run(
        [sys.executable, "-m", "quantfit.cli", "repeatability", "--reports", *paths, "--json"],
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert process.returncode == json.loads(process.stdout)["exit_code"] == 2


def test_tampered_or_extra_bundle_refused(tmp_path):
    from quantfit.bundle import create_replay_bundle

    out = tmp_path / "bundle"
    create_replay_bundle(
        [str(SOURCE / f"run-{i}/report.json") for i in range(1, 4)], str(SOURCE / "native-t0.json"), str(out)
    )
    (out / "report-1.json").write_bytes(b"substituted bytes")
    with pytest.raises(RepeatabilityError):
        analyze_replicates(bundle_path=str(out))
    shutil.copyfile(SOURCE / "run-1/report.json", out / "report-1.json")
    (out / "extra.json").write_bytes(b"{}")
    with pytest.raises(RepeatabilityError):
        analyze_replicates(bundle_path=str(out))
