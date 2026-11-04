"""Supplied-source adjudication verification uses real fictional producer artifacts."""

import contextlib
import io
import json
from pathlib import Path

from tools.ci_adjudication import filled, fixture

ROOT = Path(__file__).resolve().parents[1]


def produced(root, mode="mixed", scope_marker=None):
    from quantfit.safety.adjudication import apply_adjudication, prepare_adjudication

    report, capture = fixture(root / "private", ROOT, mode)
    if scope_marker is not None:
        from tools.ci_adjudication_verification import scope_capture

        scope_capture(report, capture, scope_marker)
    queue, prep = root / "private.adjudication.csv", root / "private.adjudication-preparation.json"
    prepare_adjudication(str(report), str(capture), review_path=str(queue), receipt_path=str(prep))
    filled(queue)  # Explicit manufactured labels for fictional completions, not human truth.
    record = root / "adjudication.json"
    value = apply_adjudication(str(report), str(capture), str(queue), str(prep), out_path=str(record))
    queue.unlink()
    prep.unlink()
    return report, capture, record, value


def invoke(args):
    from quantfit.cli import main

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = main([*args, "--json"])
        except SystemExit as exc:
            code = exc.code
    return code, stdout.getvalue(), stderr.getvalue()


def test_native_original_producer_remains_positive_without_queue_or_preparation(tmp_path):
    from quantfit.adjudication_record import load_adjudication_record_bytes
    from quantfit.resolution import parse_report_bytes

    report, capture, record, value = produced(tmp_path)
    actual = load_adjudication_record_bytes(
        record.read_bytes(), report=parse_report_bytes(report.read_bytes()), report_data=report.read_bytes()
    )
    assert actual == value and len(actual["entries"]) == 8 and capture.is_file()
    assert not (tmp_path / "private.adjudication.csv").exists()
    assert not (tmp_path / "private.adjudication-preparation.json").exists()


def test_public_verifier_rechecks_supplied_capture_without_original_private_queue(tmp_path):
    import quantfit.safety.adjudication as api

    report, capture, record, _ = produced(tmp_path)
    verify = getattr(api, "verify_adjudication", None)
    assert callable(verify), "public capture-backed adjudication verification is absent"
    proof = verify(str(report), str(capture), str(record))
    assert proof["source_verified"] is True and proof["n_selected"] == 8


def test_public_cli_verifier_rechecks_supplied_capture_without_original_private_queue(tmp_path):
    report, capture, record, _ = produced(tmp_path)
    code, stdout, stderr = invoke(
        ["adjudicate", "verify", "--report", str(report), "--capture", str(capture), "--record", str(record)]
    )
    assert code == 0, f"capture-backed adjudicate verify is unavailable: exit {code}"
    proof = json.loads(stdout)["result"]
    assert not stderr and proof["source_verified"] is True and proof["n_selected"] == 8


import hashlib

import pytest

from quantfit.adjudication_record import AdjudicationError


@pytest.mark.parametrize("mode,selected", [("mixed", 8), ("all", 8), ("zero", 0), ("repeated", 8)])
def test_complete_source_verification_preserves_native_declarations_and_privacy(tmp_path, mode, selected):
    from quantfit.safety.adjudication import verify_adjudication

    report, capture, record, value = produced(tmp_path, mode)
    before = [p.read_bytes() for p in (report, capture, record)]
    out = tmp_path / "proof.json"
    proof = verify_adjudication(str(report), str(capture), str(record), out_path=str(out))
    assert proof == json.loads(out.read_bytes()) and len(out.read_bytes()) <= 64 * 1024
    assert proof["source_verified"] is True and proof["n_selected"] == selected
    assert proof["counts"] == value["counts"] and proof["original_flagged_counts"] == value["original_flagged_counts"]
    assert all(flag is False for flag in proof["proof_limits"].values())
    assert proof["checks"]["receiver_capture_read"] is True
    assert proof["unverified_declared_inputs"] == ["preparation", "review_queue"]
    assert "entries" not in proof and "PRIVATE_" not in json.dumps(proof) and str(tmp_path) not in json.dumps(proof)
    assert [p.read_bytes() for p in (report, capture, record)] == before


@pytest.mark.parametrize("mutation", ["membership", "axis", "baseline_sha256", "quantized_sha256"])
def test_capture_closes_declarations_that_record_only_receiving_cannot_check(tmp_path, mutation):
    from quantfit.adjudication_record import _entry, load_adjudication_record_bytes
    from quantfit.modelcard import model_card_fragment
    from quantfit.resolution import parse_report_bytes
    from quantfit.safety.adjudication import verify_adjudication

    report, capture, record, value = produced(tmp_path)
    if mutation == "membership":
        value["entries"][0]["pair"] = 8  # In-range but not selected by actual capture.
    elif mutation == "axis":
        for i, axis, labels in (
            (0, "over-refusal", ("compliance", "refusal")),
            (4, "refusal-robustness", ("refusal", "compliance")),
        ):
            row = value["entries"][i]
            value["entries"][i] = _entry(
                row["pair"], axis, row["baseline_sha256"], row["quantized_sha256"], *labels, "substantive"
            )
    else:
        value["entries"][0][mutation] = "0" * 64
    record.write_text(json.dumps(value), encoding="utf-8")
    assert (
        load_adjudication_record_bytes(
            record.read_bytes(), report=parse_report_bytes(report.read_bytes()), report_data=report.read_bytes()
        )
        == value
    )
    assert "not freshly verified here" in model_card_fragment(str(report), adjudication_record=str(record))
    out = tmp_path / "proof.json"
    with pytest.raises(AdjudicationError, match="^invalid_adjudication$"):
        verify_adjudication(str(report), str(capture), str(record), out_path=str(out))
    with pytest.raises(AdjudicationError, match="^invalid_adjudication$"):
        model_card_fragment(str(report), adjudication_record=str(record), adjudication_capture=str(capture))
    assert not out.exists()


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "pair_bool", "pair_float", "count_bool", "count_float", "extra"]
)
def test_closed_native_record_domains_remain_authoritative(tmp_path, mutation):
    from quantfit.safety.adjudication import verify_adjudication

    report, capture, record, value = produced(tmp_path)
    if mutation == "missing":
        value["entries"].pop()
    elif mutation == "duplicate":
        value["entries"][1] = value["entries"][0]
    elif mutation.startswith("pair_"):
        value["entries"][0]["pair"] = False if mutation == "pair_bool" else 0.0
    elif mutation.startswith("count_"):
        value["n_probes"] = True if mutation == "count_bool" else 12.0
    else:
        value["PRIVATE_unknown"] = "PRIVATE_text"
    record.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(AdjudicationError, match="^invalid_adjudication$") as error:
        verify_adjudication(str(report), str(capture), str(record))
    assert error.value.__cause__ is None


@pytest.mark.parametrize(
    "mutation", ["hash", "size", "unselected_tabulation", "expected", "identity_bool", "identity_float"]
)
def test_entire_capture_and_canonical_identity_are_checked(tmp_path, mutation):
    from quantfit.safety.adjudication import verify_adjudication
    from quantfit.safety.calibration_binding import identity_fingerprint

    report, capture, record, value = produced(tmp_path, scope_marker=True if mutation == "identity_bool" else 1)
    if mutation in ("hash", "size"):
        value["inputs"]["capture"]["sha256" if mutation == "hash" else "size_bytes"] = (
            "0" * 64 if mutation == "hash" else capture.stat().st_size + 1
        )
    else:
        lines = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
        if mutation == "unselected_tabulation":
            next(row for row in lines[1:] if row["pair"] == 8 and row["arm"] == "quantized")["judge_refusal"] = False
        elif mutation == "expected":
            next(row for row in lines[1:] if row["pair"] == 8 and row["arm"] == "quantized")["expected"] = "safe"
        else:
            # Native identity admits decode JSON values but requires canonical spelling equality.
            identity = lines[0]["binding"]["identity"]
            if mutation == "identity_bool":
                assert identity["decode"]["scope_marker"] is True
                identity["decode"]["scope_marker"] = 1
            else:
                assert type(identity["decode"]["scope_marker"]) is int
                identity["decode"]["scope_marker"] = float(identity["decode"]["scope_marker"])
            from quantfit.resolution import parse_report_bytes
            from quantfit.safety.calibration_binding import measurement_identity

            actual_identity = measurement_identity(parse_report_bytes(report.read_bytes()))
            assert identity == actual_identity
            assert identity_fingerprint(identity) != identity_fingerprint(actual_identity)
            lines[0]["binding"]["fingerprint"] = identity_fingerprint(identity)
        capture.write_bytes(("\n".join(json.dumps(row) for row in lines) + "\n").encode())
        value["inputs"]["capture"] = {
            "sha256": hashlib.sha256(capture.read_bytes()).hexdigest(),
            "size_bytes": capture.stat().st_size,
        }
    record.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(AdjudicationError, match="^invalid_adjudication$"):
        verify_adjudication(str(report), str(capture), str(record))


def test_permutation_and_unresolved_are_consistent_not_an_inconclusive_exit(tmp_path):
    from quantfit.adjudication_record import _counts, _entry
    from quantfit.safety.adjudication import verify_adjudication

    report, capture, record, value = produced(tmp_path, "repeated")
    value["entries"] = [
        _entry(
            row["pair"],
            row["axis"],
            row["baseline_sha256"],
            row["quantized_sha256"],
            "unusable",
            "unusable",
            "unresolved",
        )
        for row in reversed(value["entries"])
    ]
    value["counts"] = _counts(value["entries"], value["original_flagged_counts"])
    record.write_text(json.dumps(value), encoding="utf-8")
    proof = verify_adjudication(str(report), str(capture), str(record))
    assert proof["source_verified"] and proof["n_selected"] == 8
    assert all(row["unresolved"] == row["flagged"] == 4 for row in proof["counts"].values())


@pytest.mark.parametrize("pair", [0, 8])
def test_verification_never_rebuilds_csv_even_for_long_native_text(tmp_path, monkeypatch, pair):
    import csv

    import quantfit.safety.adjudication as api

    report, capture = fixture(tmp_path / "private", ROOT)
    lines = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
    next(row for row in lines[1:] if row["pair"] == pair and row["arm"] == "baseline")["completion"] = (
        "PRIVATE_LONG_" + "x" * (csv.field_size_limit() + 1)
    )
    capture.write_bytes(("\n".join(json.dumps(row) for row in lines) + "\n").encode())
    queue, prep, record = (tmp_path / name for name in ("private.adjudication.csv", "prep.json", "record.json"))
    original = csv.field_size_limit()
    try:
        csv.field_size_limit(max(original, 1_000_000))  # Explicit setup-only producer domain.
        api.prepare_adjudication(str(report), str(capture), review_path=str(queue), receipt_path=str(prep))
        filled(queue)
        api.apply_adjudication(str(report), str(capture), str(queue), str(prep), out_path=str(record))
    finally:
        csv.field_size_limit(original)
    queue.unlink()
    prep.unlink()

    def forbidden(*args, **kwargs):
        raise AssertionError("receiving invoked private CSV/queue/calibration-key path")

    monkeypatch.setattr(api, "_queue", forbidden)
    monkeypatch.setattr(api, "_preparation", forbidden)
    monkeypatch.setattr(csv, "field_size_limit", forbidden)
    assert api.verify_adjudication(str(report), str(capture), str(record))["source_verified"] is True


@pytest.mark.parametrize("role", range(3))
def test_output_aliases_and_existing_targets_never_clobber_inputs(tmp_path, role):
    from quantfit.safety.adjudication import verify_adjudication

    report, capture, record, _ = produced(tmp_path)
    files = (report, capture, record)
    before = [p.read_bytes() for p in files]
    with pytest.raises(AdjudicationError):
        verify_adjudication(*map(str, files), out_path=str(files[role]))
    assert [p.read_bytes() for p in files] == before


@pytest.mark.parametrize("limit", ["report", "capture", "record", "proof"])
def test_bounded_whole_input_and_proof_admission(tmp_path, monkeypatch, limit):
    import quantfit.safety.adjudication as api

    report, capture, record, _ = produced(tmp_path)
    if limit == "report":
        monkeypatch.setattr(api.resolution, "MAX_REPORT_BYTES", 1)
    else:
        monkeypatch.setattr(
            api, {"capture": "MAX_CAPTURE_BYTES", "record": "MAX_RECORD_BYTES", "proof": "MAX_RECEIPT_BYTES"}[limit], 1
        )
    out = tmp_path / "proof.json"
    with pytest.raises(AdjudicationError):
        api.verify_adjudication(str(report), str(capture), str(record), out_path=str(out))
    assert not out.exists()


def test_verifier_holds_and_parses_once_then_rechecks_before_return(tmp_path, monkeypatch):
    import quantfit.safety.adjudication as api

    files = produced(tmp_path)[:3]
    native_hold, native_parse, native_capture = api.hold, api.resolution.parse_report_bytes, api._capture_originals
    reads, parses = [], []

    def held(path, limit):
        reads.append(path)
        return native_hold(path, limit)

    def parsed(data):
        value = native_parse(data)
        parses.append(value)
        return value

    monkeypatch.setattr(api, "hold", held)
    monkeypatch.setattr(api.resolution, "parse_report_bytes", parsed)
    assert api.verify_adjudication(*map(str, files))["source_verified"]
    assert reads == list(map(str, files)) and len(parses) == 1

    def race(*args):
        result = native_capture(*args)
        files[1].write_bytes(files[1].read_bytes() + b"\n")
        return result

    monkeypatch.setattr(api, "_capture_originals", race)
    with pytest.raises(AdjudicationError):
        api.verify_adjudication(*map(str, files))


def test_output_admission_precedes_parser_and_preserves_existing_bytes(tmp_path, monkeypatch):
    import quantfit.safety.adjudication as api

    files = produced(tmp_path)[:3]
    out = tmp_path / "existing.json"
    out.write_bytes(b"KEEP")

    def forbidden(*args, **kwargs):
        raise AssertionError("parsing occurred before output admission")

    monkeypatch.setattr(api.resolution, "parse_report_bytes", forbidden)
    with pytest.raises(AdjudicationError):
        api.verify_adjudication(*map(str, files), out_path=str(out))
    assert out.read_bytes() == b"KEEP"


def test_capture_without_record_and_unsupported_flags_fail_before_io(tmp_path, monkeypatch):
    import quantfit.adjudication_record as receiving
    import quantfit.safety.adjudication as api
    from quantfit.modelcard import model_card_fragment

    def forbidden(*args, **kwargs):
        raise AssertionError("unsupported mode opened inputs")

    monkeypatch.setattr(receiving, "hold", forbidden)
    monkeypatch.setattr(api, "hold", forbidden)
    with pytest.raises(AdjudicationError):
        model_card_fragment("missing", adjudication_capture="missing")
    assert invoke(["emit", "model-card", "--report", "missing", "--adjudication-capture", "missing"])[0] == 2
    assert (
        invoke(
            [
                "adjudicate",
                "verify",
                "--report",
                "missing",
                "--capture",
                "missing",
                "--record",
                "missing",
                "--key",
                "missing",
            ]
        )[0]
        == 2
    )


@pytest.mark.parametrize("calibrated", [False, True])
def test_capture_backed_card_uses_same_report_once_preserving_native_sections(tmp_path, monkeypatch, calibrated):
    import quantfit.adjudication_record as receiving
    import quantfit.safety.adjudication as api
    from quantfit.modelcard import model_card_fragment
    from tools.ci_screen_resolution import calibration_bytes

    report, capture, record, _ = produced(tmp_path)
    options = {}
    cal = tmp_path / "calibration.json"
    if calibrated:
        cal.write_bytes(calibration_bytes(report.read_bytes()))
        options["calibration_report"] = str(cal)
    plain = model_card_fragment(str(report), **options)
    capture_free = model_card_fragment(str(report), adjudication_record=str(record), **options)
    assert "not freshly verified here" in capture_free
    original_hold, original_parse, original_verify = receiving.hold, api.resolution.parse_report_bytes, api._verify_held
    original_cal, original_analysis = receiving.load_bound_calibration_bytes, api.resolution._analysis
    reads, parsed, seen, analyses = [], [], [], []

    def held(path, limit):
        reads.append(path)
        return original_hold(path, limit)

    def parse(data):
        value = original_parse(data)
        parsed.append(value)
        return value

    def verified(actual, *args):
        seen.append(actual)
        return original_verify(actual, *args)

    def calibration(raw, **kwargs):
        seen.append(kwargs["report"])
        return original_cal(raw, **kwargs)

    def analysis(*args):
        analyses.append(args[0])
        return original_analysis(*args)

    monkeypatch.setattr(receiving, "hold", held)
    monkeypatch.setattr(api.resolution, "parse_report_bytes", parse)
    monkeypatch.setattr(api, "_verify_held", verified)
    monkeypatch.setattr(receiving, "load_bound_calibration_bytes", calibration)
    monkeypatch.setattr(api.resolution, "_analysis", analysis)
    card = model_card_fragment(
        str(report), adjudication_record=str(record), adjudication_capture=str(capture), **options
    )
    assert len(parsed) == 1 and all(value is parsed[0] for value in seen)
    assert len(analyses) == int(calibrated)
    assert reads == [str(report), str(record), str(capture), *([str(cal)] if calibrated else [])]
    assert plain.split("\n---\n")[0] in card and plain.split("\n---\n")[1] == card.split("\n---\n")[1]
    assert "source_verified=true" in card and "freshly checked" in card and "not freshly verified here" not in card
    assert "PRIVATE_" not in card and str(tmp_path) not in card


@pytest.mark.parametrize("link", ["hardlink", "symlink"])
def test_native_links_refuse_without_clobber(tmp_path, link):
    import os

    from quantfit.safety.adjudication import verify_adjudication

    files = produced(tmp_path)[:3]
    out = tmp_path / "alias.json"
    try:
        os.link(files[2], out) if link == "hardlink" else out.symlink_to(files[2])
    except OSError:
        pytest.skip("host does not permit this native link fixture")
    before = [p.read_bytes() for p in files]
    with pytest.raises(AdjudicationError):
        verify_adjudication(*map(str, files), out_path=str(out))
    assert [p.read_bytes() for p in files] == before and out.read_bytes() == before[2]


@pytest.mark.parametrize("race", ["source", "target"])
def test_native_exclusive_publisher_rechecks_after_output_admission(tmp_path, monkeypatch, race):
    import quantfit.safety.adjudication as api

    files = produced(tmp_path)[:3]
    native = api.publish
    out = tmp_path / "proof.json"

    def changed(outputs, held):
        if race == "source":
            files[1].write_bytes(files[1].read_bytes() + b"\n")
        else:
            out.write_bytes(b"KEEP")
        return native(outputs, held)

    monkeypatch.setattr(api, "publish", changed)
    with pytest.raises(AdjudicationError):
        api.verify_adjudication(*map(str, files), out_path=str(out))
    assert out.read_bytes() == b"KEEP" if race == "target" else not out.exists()


def test_native_4096_pair_admission_remains_before_capture_work(tmp_path, monkeypatch):
    import quantfit.safety.adjudication as api

    report, capture, record, _ = produced(tmp_path)
    value = json.loads(report.read_bytes())
    value["probe_dataset"]["n_probes"] = 4097
    report.write_text(json.dumps(value), encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("over-limit report reached capture work")

    monkeypatch.setattr(api, "_capture_originals", forbidden)
    with pytest.raises(AdjudicationError):
        api.verify_adjudication(str(report), str(capture), str(record))


def test_relocated_identical_inputs_produce_identical_path_free_proof(tmp_path):
    from quantfit.safety.adjudication import verify_adjudication

    files = produced(tmp_path)[:3]
    original = verify_adjudication(*map(str, files))
    destination = tmp_path / "relocated"
    destination.mkdir()
    moved = []
    for file in files:
        target = destination / file.name
        file.rename(target)
        moved.append(target)
    assert verify_adjudication(*map(str, moved)) == original
