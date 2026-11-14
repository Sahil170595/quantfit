"""Fictional native adjudication -> supplied control consistency, never human truth."""

import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("control_native_producer", ROOT / "tools/ci_adjudication.py")
assert SPEC and SPEC.loader
producer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(producer)


def case(root, *, labels="substantive", mode="mixed", mutation=None):
    from quantfit.safety.adjudication import apply_adjudication, prepare_adjudication

    root.mkdir(parents=True)
    report, capture = producer.fixture(root / "private", ROOT, mode)
    if mutation is not None:
        mutation(report, capture)
    queue, preparation, record = (root / name for name in ("private.csv", "preparation.json", "record.json"))
    prepare_adjudication(str(report), str(capture), review_path=str(queue), receipt_path=str(preparation))
    producer.filled(queue)
    rows = list(csv.reader(io.StringIO(queue.read_text(encoding="utf-8"), newline="")))
    for row in rows[1:]:
        if row[1] == "over-refusal":
            row[-3:] = ("compliance", "refusal", "substantive")
        if row[1] == "refusal-robustness" and labels != "mixed":
            row[-3:] = (
                ("refusal", "compliance", labels)
                if labels != "unresolved"
                else ("unusable", "compliance", "unresolved")
            )
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    queue.write_text(stream.getvalue(), encoding="utf-8", newline="")
    apply_adjudication(str(report), str(capture), str(queue), str(preparation), out_path=str(record))
    queue.unlink()
    preparation.unlink()
    reports = root / "reports"
    reports.mkdir()
    value = json.loads(report.read_bytes())
    for arm in ("baseline", "quantized"):
        value[arm]["model"] = f"hf:synthetic/target/{arm}.gguf"
        value[arm]["artifact_sha256"] = hashlib.sha256(arm.encode()).hexdigest()
    (reports / "target.json").write_text(json.dumps(value), encoding="utf-8")
    manifest = root / "targets.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "explicit fictional screen",
                "targets": [
                    {
                        "name": "target",
                        "stratum": "gguf",
                        "baseline": value["baseline"]["model"],
                        "quant": value["quantized"]["model"],
                    }
                ],
                "sensitivity_control": {"status": "pass", "report": str(report), "human_verifier": "declared"},
            }
        ),
        encoding="utf-8",
    )
    return manifest, reports, report, capture, record


def options(paths):
    return dict(zip(("control_report", "control_capture", "control_adjudication"), map(str, paths[2:])))


def command(paths):
    return [
        sys.executable,
        "-m",
        "quantfit.cli",
        "screen-summary",
        "--targets",
        str(paths[0]),
        "--reports-dir",
        str(paths[1]),
        "--control-report",
        str(paths[2]),
        "--control-capture",
        str(paths[3]),
        "--control-adjudication",
        str(paths[4]),
        "--json",
    ]


def test_native_positive_control_triplet(tmp_path):
    from quantfit.safety.adjudication import verify_adjudication

    paths = case(tmp_path / "positive")
    result = verify_adjudication(*map(str, paths[2:]))
    assert result["source_verified"] is True and result["counts"]["refusal-robustness"]["substantive"] == 4


def test_public_saved_screen_control_api(tmp_path):
    from quantfit.saved_screen import summarize_screen

    paths = case(tmp_path / "api")
    result = summarize_screen(str(paths[0]), str(paths[1]), **options(paths))
    assert result["control_evidence"]["status"] == "consistent"
    assert result["control_evidence"]["applicability_by_stratum"]["gguf"]["status"] == "applicable"
    assert result["exit_code"] == 3 and result["scientific_go"] is result["control_evidence_verified"] is False


def test_actual_os_cli_control_receiving(tmp_path):
    paths = case(tmp_path / "cli")
    result = subprocess.run(command(paths), capture_output=True, text=True, check=False)
    assert result.returncode == 3, result.stderr
    assert json.loads(result.stdout)["result"]["control_evidence"]["status"] == "consistent"


@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline control intake tried model or network work")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)


def receive(paths, **kwargs):
    from quantfit.saved_screen import summarize_screen

    return summarize_screen(str(paths[0]), str(paths[1]), **options(paths), **kwargs)


def rewrite(report_path, capture_path, change=None, flags=None):
    """Only controlled fictional bytes, re-bound through the genuine native capture writer."""
    from dataclasses import replace

    from quantfit.resolution import parse_report_bytes
    from quantfit.safety.calibrate import _read_capture
    from quantfit.safety.verify import Probe, _tabulate, _write_capture

    report = parse_report_bytes(report_path.read_bytes())
    _, rows = _read_capture("private fixture", data=capture_path.read_bytes())
    by_pair = {(row["pair"], row["arm"]): row for row in rows}
    n = report.probe_dataset["n_probes"]
    first = [by_pair[(i, "baseline")] for i in range(n)]
    second = [by_pair[(i, "quantized")] for i in range(n)]
    probes = [Probe("", row["zone"], row["expected"]) for row in first]
    a, b = [[row["judge_refusal"] for row in arm] for arm in (first, second)]
    if flags is not None:
        a, b = flags(probes, a, b)
        report = replace(report, drift=_tabulate(probes, a, b).to_dict())
    if change is not None:
        report = change(report)
    report.to_json(str(report_path))
    _write_capture(
        str(capture_path),
        probes,
        report.baseline.model,
        report.quantized.model,
        [row["completion"] for row in first],
        [row["completion"] for row in second],
        a,
        b,
        actual_report=report,
    )


@pytest.mark.parametrize("labels,confirmed", [("substantive", 4), ("degenerate", 4), ("mixed", 2)])
def test_positive_dangerous_declarations_include_degenerate_and_mixed(tmp_path, labels, confirmed):
    paths = case(tmp_path / labels, labels=labels)
    result = receive(paths)
    evidence = result["control_evidence"]
    assert evidence["status"] == "consistent" and evidence["dangerous"]["positive_supported"]
    assert evidence["dangerous"]["both_arm_correct_confirmed"] == confirmed
    assert evidence["dangerous"]["unresolved"] == int(labels == "mixed")
    assert evidence["dangerous"]["not_confirmed"] == int(labels == "mixed")
    assert not any(result[name] for name in ("sensitivity_established", "scientific_go", "human_labels_authenticated"))
    text = json.dumps(evidence)
    assert "PRIVATE_" not in text and str(tmp_path) not in text and "entries" not in evidence


@pytest.mark.parametrize("scenario", ["unresolved", "zero", "safe-only", "zero-risk"])
def test_valid_insufficient_controls_are_annotations_not_gate_overrides(tmp_path, scenario):
    def mutation(report, capture):
        def flags(probes, a, b):
            if scenario == "safe-only":
                return a, [x if p.expected == "unsafe" else not x for p, x in zip(probes, a)]
            return [False] * len(a), [False] * len(b)

        rewrite(report, capture, flags=flags)

    paths = case(
        tmp_path / scenario,
        labels="unresolved" if scenario == "unresolved" else "substantive",
        mode="zero" if scenario == "zero" else "mixed",
        mutation=mutation if scenario in ("safe-only", "zero-risk") else None,
    )
    from quantfit.saved_screen import summarize_screen

    original = summarize_screen(str(paths[0]), str(paths[1]))
    result = receive(paths)
    assert result["control_evidence"]["status"] == "conflicting"
    assert result["control_evidence"]["dangerous"]["positive_supported"] is False
    for key in ("exit_code", "rows", "by_stratum", "sensitivity_control", "effective_conditionality", "scientific_go"):
        assert result[key] == original[key]
    if scenario == "safe-only":
        assert result["exit_code"] == 3 and result["control_evidence"]["dangerous"]["flips"] == 0


def test_applicability_never_promotes_one_gguf_control_to_other_strata(tmp_path):
    paths = case(tmp_path / "strata")
    value = json.loads((paths[1] / "target.json").read_bytes())
    for arm in ("baseline", "quantized"):
        value[arm].update(
            model=f"synthetic/hf-{arm}",
            revision="a" * 40,
            artifact_sha256=None,
            resolved_dtype="float16",
            engine={"name": "transformers", "version": "fixture-not-used", "device": "cpu"},
        )
    (paths[1] / "hf.json").write_text(json.dumps(value), encoding="utf-8")
    manifest = json.loads(paths[0].read_bytes())
    manifest["targets"].append(
        {
            "name": "hf",
            "stratum": "compressed-tensors",
            "baseline": value["baseline"]["model"],
            "quant": value["quantized"]["model"],
        }
    )
    paths[0].write_text(json.dumps(manifest), encoding="utf-8")
    evidence = receive(paths)["control_evidence"]
    assert evidence["status"] == "conflicting"
    assert evidence["applicability_by_stratum"]["gguf"]["status"] == "applicable"
    assert evidence["applicability_by_stratum"]["compressed-tensors"]["status"] == "conflicting"


def test_native_nullable_hf_arm_identity_stays_valid_with_control_annotation(tmp_path):
    paths = case(tmp_path / "nullable-hf")
    value = json.loads((paths[1] / "target.json").read_bytes())
    for arm in ("baseline", "quantized"):
        value[arm].update(
            model=f"synthetic/hf-{arm}",
            revision=None,
            artifact_sha256=None,
            resolved_dtype="float16",
            engine={"name": "transformers", "version": "fixture-not-used", "device": "cpu"},
        )
    (paths[1] / "hf.json").write_text(json.dumps(value), encoding="utf-8")
    manifest = json.loads(paths[0].read_bytes())
    manifest["targets"].append(
        {
            "name": "hf",
            "stratum": "compressed-tensors",
            "baseline": value["baseline"]["model"],
            "quant": value["quantized"]["model"],
        }
    )
    paths[0].write_text(json.dumps(manifest), encoding="utf-8")
    from quantfit.saved_screen import summarize_screen

    original = summarize_screen(str(paths[0]), str(paths[1]))
    actual = receive(paths)
    assert actual["rows"] == original["rows"] and actual["exit_code"] == original["exit_code"] == 3
    assert actual["control_evidence"]["applicability_by_stratum"]["compressed-tensors"]["status"] == "conflicting"


@pytest.mark.parametrize("absent", [True, False])
def test_missing_saved_reports_or_nonpass_declaration_do_not_create_consistency(tmp_path, absent):
    paths = case(tmp_path / "missing")
    if absent:
        (paths[1] / "target.json").unlink()
    else:
        value = json.loads(paths[0].read_bytes())
        value["sensitivity_control"]["status"] = "not_run"
        paths[0].write_text(json.dumps(value), encoding="utf-8")
    result = receive(paths)
    assert result["control_evidence"]["status"] == ("missing" if absent else "conflicting")
    assert result["exit_code"] == (4 if absent else 3)


@pytest.mark.parametrize("field", ["population", "decode", "judge", "engine", "revision", "local-sha"])
def test_valid_control_source_or_protocol_differences_are_not_applicable(tmp_path, field):
    paths = case(tmp_path / field)
    target = paths[1] / "target.json"
    value = json.loads(target.read_bytes())
    kwargs = {}
    if field == "population":
        # Same N and both totals, different whole zone population; native statistics re-tabulated.
        from quantfit.safety.verify import Probe, _tabulate

        probes = [
            Probe(
                "",
                "borderline" if i == 0 else "clear_unsafe" if i < 4 or i >= 8 and i % 2 == 0 else "clear_safe",
                "unsafe" if i < 4 or i >= 8 and i % 2 == 0 else "safe",
            )
            for i in range(12)
        ]
        a = [p.expected == "unsafe" for p in probes]
        b = [not x if i < 8 else x for i, x in enumerate(a)]
        value["drift"] = _tabulate(probes, a, b).to_dict()
    elif field == "decode":
        value["decode"]["max_new_tokens"] += 1
    elif field == "engine":
        for arm in ("baseline", "quantized"):
            value[arm]["engine"]["threads"] += 1
    elif field == "judge":
        # Native triplet is independently consistent but carries another pinned judge.
        def change(report, capture):
            from dataclasses import replace

            rewrite(report, capture, lambda r: replace(r, judge={**r.judge, "revision": "b" * 40}))

        paths = case(tmp_path / "other-judge", mutation=change)
        target = paths[1] / "target.json"
        value = json.loads(target.read_bytes())
        from quantfit.safety.verify import JUDGE_REVISION

        value["judge"]["revision"] = JUDGE_REVISION
    elif field == "revision":
        from quantfit.safety.verify import ProbeCorpus

        value["probe_dataset"].update(id="synthetic/custom", revision="c" * 40, split="test")
        kwargs["probe_corpus"] = ProbeCorpus("synthetic/custom", "c" * 40, "test")
    else:
        from quantfit.probe_bundle import LocalProbeCorpus

        value["probe_dataset"] = {
            "source_kind": "local",
            "format": "quantfit-probe-bundle-v1",
            "sha256": "d" * 64,
            "n_probes": 12,
        }
        kwargs["probe_corpus"] = LocalProbeCorpus("d" * 64)
    target.write_text(json.dumps(value), encoding="utf-8")
    evidence = receive(paths, **kwargs)["control_evidence"]
    assert evidence["status"] == "conflicting"
    assert evidence["applicability_by_stratum"]["gguf"]["protocol_matches"] is False


@pytest.mark.parametrize("local", [False, True])
def test_custom_hub_and_local_sha_sources_match_without_source_locator_io(tmp_path, local):
    from quantfit.probe_bundle import LocalProbeCorpus
    from quantfit.safety.verify import ProbeCorpus

    expected = LocalProbeCorpus("e" * 64) if local else ProbeCorpus("synthetic/custom", "f" * 40, "test")
    source = (
        {"source_kind": "local", "format": "quantfit-probe-bundle-v1", "sha256": "e" * 64, "n_probes": 12}
        if local
        else {"id": expected.id, "revision": expected.revision, "split": expected.split, "n_probes": 12}
    )

    def mutation(report, capture):
        from dataclasses import replace

        rewrite(report, capture, lambda r: replace(r, probe_dataset=source))

    paths = case(tmp_path / "custom", mutation=mutation)
    result = receive(paths, probe_corpus=expected)
    assert result["control_evidence"]["status"] == "consistent"
    assert (
        result["probe_corpus"]["source_kind"] == "local"
        if local
        else result["probe_corpus"]["id"] == "synthetic/custom"
    )
    target = paths[1] / "target.json"
    payload = json.loads(target.read_bytes())
    payload["probe_dataset"]["sha256" if local else "revision"] = "a" * (64 if local else 40)
    target.write_text(json.dumps(payload), encoding="utf-8")
    changed = LocalProbeCorpus("a" * 64) if local else ProbeCorpus("synthetic/custom", "a" * 40, "test")
    assert receive(paths, probe_corpus=changed)["control_evidence"]["status"] == "conflicting"


@pytest.mark.parametrize("role", ["report", "capture", "adjudication"])
@pytest.mark.parametrize("sink", ["out_path", "junit_path"])
def test_all_control_roles_are_protected_before_parsing(tmp_path, monkeypatch, role, sink):
    import quantfit.screen_control_evidence as control
    from quantfit.saved_screen import SavedScreenError

    paths = case(tmp_path / "aliases")
    target = paths[{"report": 2, "capture": 3, "adjudication": 4}[role]]
    before = target.read_bytes()
    monkeypatch.setattr(control, "hold", lambda *a, **k: pytest.fail("role alias reached private parser"))
    with pytest.raises(SavedScreenError):
        receive(paths, **{sink: str(target)})
    assert target.read_bytes() == before


@pytest.mark.parametrize("change", ["capture", "record", "locator", "late-capture", "schema"])
def test_wrong_bound_inputs_refuse_without_publishing(tmp_path, change):
    from quantfit.saved_screen import SavedScreenError

    paths = case(tmp_path / change)
    if change in ("capture", "late-capture"):
        with paths[3].open("ab") as stream:
            stream.write(b'\n{"private_late_invalid":true}\n' if change == "late-capture" else b" ")
    elif change in ("record", "schema"):
        value = json.loads(paths[4].read_bytes())
        value["inputs"]["report"]["sha256"] = "0" * 64
        if change == "schema":
            value["extra"] = True
        paths[4].write_text(json.dumps(value), encoding="utf-8")
    else:
        value = json.loads(paths[0].read_bytes())
        value["sensitivity_control"]["report"] = "never-open-this-manifest-locator.json"
        paths[0].write_text(json.dumps(value), encoding="utf-8")
    output = tmp_path / "prior-summary.json"
    output.write_bytes(b"prior")
    with pytest.raises(SavedScreenError):
        receive(paths, out_path=str(output))
    assert output.read_bytes() == b"prior"


@pytest.mark.parametrize(
    "combination", ["partial", "calibrations_dir", "calibration_variants", "required_conditional_resolution_pp"]
)
def test_unsupported_combinations_refuse_before_io(tmp_path, monkeypatch, combination):
    from quantfit.saved_screen import SavedScreenError, summarize_screen

    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("invalid combination reached IO"))
    kwargs = {"control_report": "missing-report"}
    if combination != "partial":
        kwargs.update(control_capture="missing-capture", control_adjudication="missing-record")
        kwargs[combination] = (
            {"a": None}
            if combination == "calibration_variants"
            else 1.0
            if combination == "required_conditional_resolution_pp"
            else "missing-dir"
        )
    with pytest.raises(SavedScreenError):
        summarize_screen("missing-manifest", "missing-reports", **kwargs)


def test_relative_locator_uses_invocation_cwd_not_manifest_directory(tmp_path, monkeypatch):
    paths = case(tmp_path / "elsewhere")
    value = json.loads(paths[0].read_bytes())
    value["sensitivity_control"]["report"] = "private/report.json"
    paths[0].write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.chdir(paths[0].parent)
    assert receive(paths)["control_evidence"]["status"] == "consistent"


def test_native_defaults_and_xml_are_exact_with_none_roles(tmp_path, monkeypatch):
    import quantfit.saved_screen as saved

    class Clock:
        @staticmethod
        def now(*args):
            from datetime import datetime, timezone

            return datetime(2026, 11, 7, tzinfo=timezone.utc)

    monkeypatch.setattr(saved, "datetime", Clock)
    paths = case(tmp_path / "defaults")
    original = saved.summarize_screen(str(paths[0]), str(paths[1]))
    absent = saved.summarize_screen(
        str(paths[0]), str(paths[1]), control_report=None, control_capture=None, control_adjudication=None
    )
    annotated = receive(paths)
    assert absent == original
    del annotated["control_evidence"]
    assert annotated == original


def test_held_once_rechecks_before_both_publications(tmp_path, monkeypatch):
    import quantfit.screen_control_evidence as control
    from quantfit.saved_screen import SavedScreenError

    paths = case(tmp_path / "once")
    actual = control.hold
    calls = []

    def counted(path, limit):
        calls.append(Path(path))
        return actual(path, limit)

    monkeypatch.setattr(control, "hold", counted)
    json_out, xml_out = tmp_path / "out.json", tmp_path / "out.xml"
    receive(paths, out_path=str(json_out), junit_path=str(xml_out))
    assert calls == list(paths[2:])
    assert "control_evidence" in json.loads(json_out.read_bytes())
    from quantfit.junit import screen_to_junit

    assert xml_out.read_bytes() == screen_to_junit(json.loads(json_out.read_bytes())).encode()
    prior = json_out.read_bytes(), xml_out.read_bytes()
    original = control._verify_held

    def altered(*args):
        result = original(*args)
        paths[3].write_bytes(paths[3].read_bytes() + b" ")
        return result

    monkeypatch.setattr(control, "_verify_held", altered)
    with pytest.raises(SavedScreenError):
        receive(paths, out_path=str(json_out), junit_path=str(xml_out))
    assert (json_out.read_bytes(), xml_out.read_bytes()) == prior


@pytest.mark.parametrize("index,limit", [(2, 8 * 1024 * 1024), (3, 16 * 1024 * 1024), (4, 4 * 1024 * 1024)])
def test_native_role_size_admission_preserves_outputs(tmp_path, index, limit):
    from quantfit.saved_screen import SavedScreenError

    paths = case(tmp_path / "oversize")
    with paths[index].open("r+b") as stream:
        stream.truncate(limit + 1)
    out = tmp_path / "out.json"
    with pytest.raises(SavedScreenError):
        receive(paths, out_path=str(out))
    assert not out.exists()


def test_combined_role_budget_and_duplicate_roles_are_closed(tmp_path, monkeypatch):
    import quantfit.screen_control_evidence as control
    from quantfit.saved_screen import SavedScreenError

    paths = case(tmp_path / "total")
    monkeypatch.setattr(control, "MAX_CONTROL_BYTES", sum(path.stat().st_size for path in paths[2:]) - 1)
    with pytest.raises(SavedScreenError, match="control_byte_limit"):
        receive(paths)
    kwargs = options(paths)
    kwargs["control_capture"] = kwargs["control_report"]
    from quantfit.saved_screen import summarize_screen

    with pytest.raises(SavedScreenError, match="duplicate_control_roles"):
        summarize_screen(str(paths[0]), str(paths[1]), **kwargs)


def test_output_hardlink_alias_is_refused_without_opening_control(tmp_path, monkeypatch):
    import os

    import quantfit.screen_control_evidence as control
    from quantfit.saved_screen import SavedScreenError

    paths = case(tmp_path / "hardlink")
    output = tmp_path / "alias.json"
    os.link(paths[2], output)
    before = paths[2].read_bytes()
    monkeypatch.setattr(control, "hold", lambda *a, **k: pytest.fail("hardlink output reached private read"))
    with pytest.raises(SavedScreenError):
        receive(paths, out_path=str(output))
    assert output.read_bytes() == paths[2].read_bytes() == before


def test_cli_operational_refusal_preserves_prior_output(tmp_path):
    paths = case(tmp_path / "bad-cli")
    before = paths[2].read_bytes()
    value = subprocess.run([*command(paths), "--out", str(paths[2])], capture_output=True, text=True, check=False)
    assert value.returncode == 2
    assert json.loads(value.stdout)["exit_code"] == 2
    assert paths[2].read_bytes() == before


@pytest.mark.parametrize("value", ["other", True])
def test_additional_native_decode_declarations_are_exact_for_control_transfer(tmp_path, value):
    from dataclasses import replace

    def mutation(report, capture):
        rewrite(report, capture, lambda r: replace(r, decode={**r.decode, "recorded_by": "fixture"}))

    paths = case(tmp_path / "decode-declaration", mutation=mutation)
    assert receive(paths)["control_evidence"]["status"] == "consistent"
    target = paths[1] / "target.json"
    payload = json.loads(target.read_bytes())
    payload["decode"]["recorded_by"] = value
    target.write_text(json.dumps(payload), encoding="utf-8")
    assert receive(paths)["control_evidence"]["status"] == "conflicting"


def test_every_actual_report_contributes_to_exact_decode_applicability(tmp_path):
    from dataclasses import replace

    def mutation(report, capture):
        rewrite(report, capture, lambda r: replace(r, decode={**r.decode, "recorded_by": "fixture"}))

    paths = case(tmp_path / "whole-stratum", mutation=mutation)
    second = json.loads((paths[1] / "target.json").read_bytes())
    second["decode"]["recorded_by"] = "different-declaration"
    for arm in ("baseline", "quantized"):
        second[arm]["model"] = second[arm]["model"].replace(".gguf", "-second.gguf")
        second[arm]["artifact_sha256"] = hashlib.sha256(f"second:{arm}".encode()).hexdigest()
    (paths[1] / "second.json").write_text(json.dumps(second), encoding="utf-8")
    manifest = json.loads(paths[0].read_bytes())
    manifest["targets"].append(
        {
            "name": "second",
            "stratum": "gguf",
            "baseline": second["baseline"]["model"],
            "quant": second["quantized"]["model"],
        }
    )
    paths[0].write_text(json.dumps(manifest), encoding="utf-8")
    from quantfit.saved_screen import summarize_screen

    original = summarize_screen(str(paths[0]), str(paths[1]))
    actual = receive(paths)
    assert actual["control_evidence"]["status"] == "conflicting"
    assert actual["control_evidence"]["applicability_by_stratum"]["gguf"]["protocol_matches"] is False
    assert actual["rows"] == original["rows"] and actual["exit_code"] == original["exit_code"] == 3
