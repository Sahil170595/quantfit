"""Producer/consumer and fail-closed tests on synthetic completions and scope only."""

import csv
import hashlib
import json
from dataclasses import replace

import pytest
from test_calibration_binding import calibration_fixture, report_fixture, write_calibration

from quantfit.gate import run_gate
from quantfit.safety.calibrate import CalibrationError, build_labeling_sheet, ingest_labels
from quantfit.safety.calibration_binding import CalibrationBindingError, load_bound_calibration


def synthetic_roundtrip(tmp_path, monkeypatch):
    import quantfit.safety.report as reports
    import quantfit.safety.verify as sv

    actual = report_fixture()
    probes = [
        sv.Probe(f"synthetic-{i}", "clear_unsafe" if i < 12 else "clear_safe", "unsafe" if i < 12 else "safe")
        for i in range(40)
    ]
    monkeypatch.setattr(sv, "_load_probes", lambda token: probes)
    monkeypatch.setattr(reports, "environment_fingerprint", lambda: dict(actual.env))
    monkeypatch.setattr(
        sv,
        "_generate_completions",
        lambda model, *args: (
            [f"synthetic-{model}-{i}" for i in range(40)],
            actual.baseline if model == "base" else actual.quantized,
        ),
    )
    flags = [i < 20 for i in range(40)] + [i < 10 for i in range(40)]
    monkeypatch.setattr(sv, "_classify_refusals", lambda *args: (flags, 0.5))
    capture, sheet, key, calibration = (
        tmp_path / name for name in ("run.capture.jsonl", "run.labels.csv", "run.labelkey.json", "calibration.json")
    )
    report_path = tmp_path / "drift.json"
    sv.verify_safety("base", "quant", report_path=str(report_path), capture_path=str(capture))
    build_labeling_sheet(str(capture), str(sheet), str(key))
    mapping = json.loads(key.read_text(encoding="utf-8"))["ids"]
    with sheet.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        # Test labels are manufactured from fixture flags, never passed off as human.
        row["human_label"] = "refusal" if mapping[row["id"]]["judge_refusal"] else "compliance"
    with sheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("id", "completion", "human_label"))
        writer.writeheader()
        writer.writerows(rows)
    payload = ingest_labels(str(sheet), str(key), str(calibration))
    payload["label"] = "SYNTHETIC functional fixture: no human labels or measured judge error"
    calibration.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload, calibration, report_path, capture, sheet, key


def test_actual_capture_key_and_calibration_scope_round_trip(tmp_path, monkeypatch):
    from quantfit.safety.report import DriftReport

    payload, path, report, capture, _, key = synthetic_roundtrip(tmp_path, monkeypatch)
    header = json.loads(capture.read_text(encoding="utf-8").splitlines()[0])
    assert header["capture_schema"] == 2
    assert header["binding"] == json.loads(key.read_text(encoding="utf-8"))["binding"] == payload["binding"]
    bound = load_bound_calibration(str(path), report=DriftReport.from_json(str(report)))
    assert bound.eps_baseline_upper < bound.eps_quant_upper
    assert payload["n_labeled"] == 80


def test_bound_pre_run_refusal_never_claims_actual_weights_matched(tmp_path, monkeypatch):
    import quantfit.safety.verify as sv

    _, path, *_ = synthetic_roundtrip(tmp_path, monkeypatch)
    monkeypatch.setattr(
        sv, "verify_safety", lambda *args, **kwargs: pytest.fail("refusal must precede model generation")
    )
    decision = run_gate("base", "quant", tier="smoke", calibration_report=str(path))
    assert decision["exit_code"] == 5
    assert decision["eps"]["binding_status"] == "scope_validated_actual_run_unobserved"
    assert decision["eps"]["actual_run_matched"] is False
    assert decision["eps"]["measured"] is False
    assert decision["eps"]["assumptions_verified"] is False
    assert set(decision["eps"]["assumptions"]) == {"A1", "A2", "A3"}
    assert decision["mde_block"]["eps_baseline_upper"] != decision["mde_block"]["eps_quant_upper"]
    assert "actual arm weights/environment not yet observed" in decision["headline"]


def test_cli_calibration_flag_produces_json_refusal_and_rejects_operator_conflict(tmp_path, monkeypatch, capsys):
    from quantfit.cli import main

    _, path, *_ = synthetic_roundtrip(tmp_path, monkeypatch)
    argv = [
        "gate",
        "--baseline",
        "base",
        "--quant",
        "quant",
        "--tier",
        "smoke",
        "--calibration-report",
        str(path),
        "--json",
    ]
    assert main(argv) == 5
    payload = json.loads(capsys.readouterr().out)
    assert payload["exit_code"] == 5 and payload["result"]["eps"]["source_sha256"]
    assert main([*argv, "--eps-upper", "1"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert "mutually exclusive" in payload["error"]["message"]


@pytest.mark.parametrize("legacy", ["capture", "key"])
def test_legacy_local_evidence_is_ingestible_but_never_bound(tmp_path, monkeypatch, legacy):
    _, _, _, capture, sheet, key = synthetic_roundtrip(tmp_path, monkeypatch)
    if legacy == "capture":
        lines = capture.read_text(encoding="utf-8").splitlines()
        header = json.loads(lines[0])
        header["capture_schema"] = 1
        header.pop("binding")
        lines[0] = json.dumps(header)
        capture.write_text("\n".join(lines) + "\n", encoding="utf-8")
        build_labeling_sheet(str(capture), str(tmp_path / "legacy.labels.csv"), str(tmp_path / "legacy.labelkey.json"))
        assert json.loads((tmp_path / "legacy.labelkey.json").read_text(encoding="utf-8"))["binding"] is None
    metadata = json.loads(key.read_text(encoding="utf-8"))
    metadata["key_schema"] = 1
    # Even a spurious historical binding is ignored, not filled from today's pins.
    key.write_text(json.dumps(metadata), encoding="utf-8")
    out = tmp_path / "legacy.json"
    payload = ingest_labels(str(sheet), str(key), str(out))
    assert payload["binding"] is None
    assert payload["source"]["capture_sha256"] is None
    with pytest.raises(CalibrationBindingError):
        load_bound_calibration(str(out))


def _large_synthetic_run(tmp_path, monkeypatch, mismatch=False):
    """A deliberately widened fixture corpus tests the post-run path; no real corpus changed."""
    import quantfit.safety.verify as sv
    from quantfit import gate

    actual = report_fixture(2000)
    path = write_calibration(tmp_path, calibration_fixture(actual))
    monkeypatch.setattr(gate, "SHIPPED_CORPUS_N", 2000)
    monkeypatch.setattr(gate, "SHIPPED_EXPECTED_UNSAFE_N", 1500)
    probes = [
        sv.Probe("fixture", "clear_unsafe" if i < 1500 else "clear_safe", "unsafe" if i < 1500 else "safe")
        for i in range(2000)
    ]
    flags = [i < 1500 for i in range(2000)]
    drift = sv._tabulate(probes, flags, flags)
    actual = replace(actual, drift=drift.to_dict())
    if mismatch:
        actual = replace(actual, quantized=replace(actual.quantized, revision="c" * 40))
    calls = []

    def fake(baseline, quant, **kwargs):
        calls.append(kwargs)
        actual.to_json(kwargs["report_path"])
        return drift

    monkeypatch.setattr(sv, "verify_safety", fake)
    return path, calls


def test_only_observed_matching_run_can_emit_bound_calibrated_decision(tmp_path, monkeypatch):
    path, calls = _large_synthetic_run(tmp_path, monkeypatch)
    decision = run_gate("base", "quant", tier="smoke", calibration_report=path)
    assert len(calls) == 1
    assert decision["exit_code"] == 0
    assert decision["eps"]["actual_run_matched"] is True
    assert decision["eps"]["measured"] is False
    assert decision["resolution"]["resolution_proven"] is True
    assert decision["eps"]["assumptions_verified"] is False
    assert "At-risk applicability (A1)" in decision["headline"]
    assert "majority-real at-risk probes (A3)" in decision["headline"]
    assert decision["mde_block"]["eps_baseline_upper"] < decision["mde_block"]["eps_quant_upper"]


def test_resolved_weight_mismatch_refuses_before_decision_output(tmp_path, monkeypatch):
    path, calls = _large_synthetic_run(tmp_path, monkeypatch, mismatch=True)
    output = tmp_path / "gate.json"
    with pytest.raises(CalibrationBindingError, match="actual run"):
        run_gate("base", "quant", tier="smoke", calibration_report=path, out_path=str(output))
    assert len(calls) == 1
    assert not output.exists()


@pytest.mark.parametrize("operator", [{"eps_upper": 0.01}, {"eps_source": "hypothetical"}])
def test_calibration_is_exclusive_with_each_operator_input(operator):
    with pytest.raises(RuntimeError, match="mutually exclusive"):
        run_gate("base", "quant", tier="smoke", calibration_report="must-not-be-read.json", **operator)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["ids"].pop(next(iter(p["ids"]))),
        lambda p: p.update(capture=None),
        lambda p: p["capture"].update(n_pairs=True),
        lambda p: p["capture"].update(quant="other-weights"),
    ],
)
def test_bound_key_cannot_drop_pairs_or_change_capture_scope(tmp_path, monkeypatch, mutation):
    _, _, _, _, sheet, key = synthetic_roundtrip(tmp_path, monkeypatch)
    payload = json.loads(key.read_text(encoding="utf-8"))
    mutation(payload)
    key.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "refused.json"
    with pytest.raises(CalibrationError, match="bound arms|capture scope"):
        ingest_labels(str(sheet), str(key), str(out))
    assert not out.exists()


def test_unidentified_local_capture_stays_usable_without_inventing_revision(tmp_path, monkeypatch):
    import quantfit.safety.verify as sv

    _, _, _, _, _, _ = synthetic_roundtrip(tmp_path, monkeypatch)
    actual = report_fixture()
    local = replace(actual.baseline, revision=None)
    monkeypatch.setattr(
        sv,
        "_generate_completions",
        lambda model, *args: ([f"fixture-{i}" for i in range(40)], local if model == "base" else actual.quantized),
    )
    capture = tmp_path / "unbound.capture.jsonl"
    sv.verify_safety("base", "quant", capture_path=str(capture))
    header = json.loads(capture.read_text(encoding="utf-8").splitlines()[0])
    assert header["binding"] is None
    assert "insufficient immutable identity" in header["binding_error"]
    key = tmp_path / "unbound.labelkey.json"
    build_labeling_sheet(str(capture), str(tmp_path / "unbound.labels.csv"), str(key))
    assert json.loads(key.read_text(encoding="utf-8"))["binding"] is None


def test_capture_hash_describes_the_buffer_parsed_even_if_file_changes(tmp_path, monkeypatch):
    from quantfit.safety import calibrate

    _, _, _, capture, _, _ = synthetic_roundtrip(tmp_path, monkeypatch)
    parsed_bytes = capture.read_bytes()
    read_capture = calibrate._read_capture

    def swap_after_parse(path, **kwargs):
        parsed = read_capture(path, **kwargs)
        capture.write_text('{"substituted": true}\n', encoding="utf-8")
        return parsed

    monkeypatch.setattr(calibrate, "_read_capture", swap_after_parse)
    key = tmp_path / "snapshot.labelkey.json"
    build_labeling_sheet(str(capture), str(tmp_path / "snapshot.labels.csv"), str(key))
    assert json.loads(key.read_text(encoding="utf-8"))["capture_sha256"] == hashlib.sha256(parsed_bytes).hexdigest()
    assert capture.read_bytes() != parsed_bytes


@pytest.mark.parametrize("changed", ["sheet", "key"])
def test_ingest_hashes_the_exact_parsed_buffers_not_later_disk_bytes(tmp_path, monkeypatch, changed):
    from quantfit.safety import calibrate

    _, _, _, _, sheet, key = synthetic_roundtrip(tmp_path, monkeypatch)
    parsed_sheet, parsed_key = sheet.read_bytes(), key.read_bytes()
    join = calibrate._join

    def swap_after_parse(*args, **kwargs):
        parsed = join(*args, **kwargs)
        if changed == "sheet":
            rows = list(csv.DictReader(parsed_sheet.decode("utf-8").splitlines()))
            with sheet.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("id", "completion", "human_label"))
                writer.writeheader()
                writer.writerows({**row, "human_label": "unusable"} for row in rows)
        else:
            key.write_text('{"substituted": true}\n', encoding="utf-8")
        return parsed

    monkeypatch.setattr(calibrate, "_join", swap_after_parse)
    payload = ingest_labels(str(sheet), str(key), str(tmp_path / "snapshot.json"))
    assert payload["baseline"]["n"] == payload["quantized"]["n"] == 40
    assert payload["n_unusable"] == 0
    assert payload["source"]["sheet_sha256"] == hashlib.sha256(parsed_sheet).hexdigest()
    assert payload["source"]["key_sha256"] == hashlib.sha256(parsed_key).hexdigest()
    assert (sheet if changed == "sheet" else key).read_bytes() != (parsed_sheet if changed == "sheet" else parsed_key)
