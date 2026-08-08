"""Completion capture + judge-calibration harness (hermetic: no network, no model load).

The capture tests drive the real `verify_safety` with `_load_probes`,
`_generate_completions` and `_classify_refusals` monkeypatched, so the plumbing
under test is the shipped path and not a re-implementation. The calibration tests
craft tiny captures by hand, because the point there is arithmetic on known counts.

None of this starts ROADMAP 0.6: it exercises machinery, on fabricated
completions, that the 0.5 GO decision gates the use of.
"""

import csv
import hashlib
import json
import re
from pathlib import Path

import pytest

from quantfit.safety.calibrate import (
    CALIBRATION_LABEL,
    CALIBRATION_SCHEMA,
    DIR_FALSE_COMPLIANCE,
    DIR_FALSE_REFUSAL,
    HUMAN_LABELS,
    KEY_SCHEMA,
    SHEET_COLUMNS,
    CalibrationError,
    build_labeling_sheet,
    ingest_labels,
)
from quantfit.safety.verify import ARM_BASELINE, ARM_QUANTIZED, CAPTURE_SCHEMA, CAPTURE_WARNING, wilson_interval

# Ids carry a leading "r" so a spreadsheet cannot read one as a number.
_ID_PATTERN = re.compile(r"r[0-9a-f]{16}")
_TIMESTAMP = re.compile(r'"created_utc": "[^"]*"')


# --- fixtures ----------------------------------------------------------------------


def _probes():
    from quantfit.safety.verify import Probe

    return [
        Probe("u1", "clear_unsafe", "unsafe"),
        Probe("u2", "clear_unsafe", "unsafe"),
        Probe("s1", "clear_safe", "safe"),
    ]


def _install_fake_run(monkeypatch, probes, baseline_completions, quant_completions, flags):
    """Swap the three heavy steps of verify_safety for fakes; everything else is real."""
    import quantfit.safety.report as report_mod
    import quantfit.safety.verify as sv
    from quantfit.safety.report import ArmRun

    def arm(model_id, runtime_s):
        return ArmRun(
            model=model_id,
            revision=f"rev-{model_id}",
            resolved_dtype="torch.bfloat16",
            runtime_s=runtime_s,
            engine={"name": "transformers", "version": "5.10.1", "device": "cpu"},
            artifact_sha256=None,
        )

    def fake_generate(model_id, prompts, max_new_tokens, token):
        if model_id == "base":
            return list(baseline_completions), arm("base", 1.5)
        return list(quant_completions), arm("quant", 0.8)

    monkeypatch.setattr(sv, "_load_probes", lambda token: list(probes))
    monkeypatch.setattr(sv, "_generate_completions", fake_generate)
    monkeypatch.setattr(sv, "_classify_refusals", lambda completions, token: (list(flags), 0.25))
    monkeypatch.setattr(
        report_mod,
        "environment_fingerprint",
        lambda: {"python": "3.13.0", "torch": "x", "transformers": "y", "cuda": None, "device": "cpu"},
    )
    return sv


def _read_capture_lines(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return json.loads(lines[0]), [json.loads(line) for line in lines[1:]]


def _minus_timestamps(path):
    """A report is reproducible 'minus timestamps' — the repo's own standing rule."""
    return _TIMESTAMP.sub('"created_utc": "<t>"', Path(path).read_text(encoding="utf-8"))


# The hand-computed calibration fixture. Baseline: 5 usable rows, 1 judge error
# (eps = 0.200). Quantized: 4 usable rows, 2 judge errors, one in each direction
# (eps = 0.500), plus 1 unusable row that must leave every denominator alone.
_N_PAIRS = 5
_JUDGE = {
    ARM_BASELINE: [True, True, False, False, True],
    ARM_QUANTIZED: [True, False, False, True, True],
}
_HUMAN = {
    (0, ARM_BASELINE): "refusal",  # agree
    (1, ARM_BASELINE): "compliance",  # judge said refusal -> error
    (2, ARM_BASELINE): "compliance",  # agree
    (3, ARM_BASELINE): "compliance",  # agree
    (4, ARM_BASELINE): "refusal",  # agree
    (0, ARM_QUANTIZED): "compliance",  # judge said refusal -> error
    (1, ARM_QUANTIZED): "refusal",  # judge said compliance -> error
    (2, ARM_QUANTIZED): "compliance",  # agree
    (3, ARM_QUANTIZED): "refusal",  # agree
    (4, ARM_QUANTIZED): "unusable",  # excluded from n, counted separately
}


def _capture(tmp_path, name="capture.jsonl", header_overrides=None, rows=None):
    header = {
        "capture_schema": CAPTURE_SCHEMA,
        "created_utc": "2026-07-24T00:00:00+00:00",
        "baseline": "base",
        "quant": "quant",
        "n_pairs": _N_PAIRS,
        "warning": CAPTURE_WARNING,
    }
    header.update(header_overrides or {})
    if rows is None:
        rows = [
            {
                "pair": pair,
                "arm": arm,
                "zone": "clear_unsafe" if pair < 2 else "clear_safe",
                "expected": "unsafe" if pair < 2 else "safe",
                "judge_refusal": _JUDGE[arm][pair],
                "completion": f"text for row {pair} on side {arm[0]}{pair}",
            }
            for arm in (ARM_BASELINE, ARM_QUANTIZED)
            for pair in range(_N_PAIRS)
        ]
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in [header, *rows]) + "\n", encoding="utf-8")
    return str(path)


def _build(tmp_path, capture_path=None, stem="sheet"):
    capture_path = capture_path or _capture(tmp_path)
    sheet = tmp_path / f"{stem}.csv"
    key = tmp_path / f"{stem}-key.json"
    build_labeling_sheet(capture_path, str(sheet), str(key))
    return str(sheet), str(key)


def _sheet_rows(sheet_path):
    with Path(sheet_path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def _fill(sheet_path, key_path, labels=None, mutate=None):
    """Write the human labels into a sheet the way a labeler's spreadsheet would."""
    labels = _HUMAN if labels is None else labels
    ids = json.loads(Path(key_path).read_text(encoding="utf-8"))["ids"]
    table = _sheet_rows(sheet_path)
    filled = [table[0]]
    for row_id, completion, _ in table[1:]:
        entry = ids[row_id]
        filled.append([row_id, completion, labels[(entry["pair"], entry["arm"])]])
    if mutate:
        filled = mutate(filled)
    with Path(sheet_path).open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(filled)
    return sheet_path


def _ingest(tmp_path, sheet, key, name="calibration.json"):
    out = tmp_path / name
    return ingest_labels(sheet, key, str(out)), out


def _add_bom(sheet_path):
    """Re-save a sheet the way Excel does: same bytes, three of them in front."""
    data = Path(sheet_path).read_bytes()
    Path(sheet_path).write_bytes(b"\xef\xbb\xbf" + data)
    return sheet_path


# --- part 1: capture ---------------------------------------------------------------


def test_capture_writes_a_header_then_one_row_per_completion(tmp_path, monkeypatch):
    probes = _probes()
    sv = _install_fake_run(
        monkeypatch,
        probes,
        ["b0", "b1", "b2"],
        ["q0", "q1", "q2"],
        [True, True, False, True, False, False],  # baseline block, then quantized block
    )
    capture = tmp_path / "capture.jsonl"

    sv.verify_safety("base", "quant", capture_path=str(capture))

    header, rows = _read_capture_lines(capture)
    assert header["capture_schema"] == CAPTURE_SCHEMA
    assert (header["baseline"], header["quant"], header["n_pairs"]) == ("base", "quant", 3)
    assert header["created_utc"].endswith("+00:00")
    assert header["warning"] == CAPTURE_WARNING
    for phrase in ("harmful model output", "never commit", "redistribute", "attach to a report"):
        assert phrase in header["warning"]

    assert len(rows) == 6
    assert [(r["pair"], r["arm"]) for r in rows] == [(i, ARM_BASELINE) for i in range(3)] + [
        (i, ARM_QUANTIZED) for i in range(3)
    ]
    assert [r["completion"] for r in rows] == ["b0", "b1", "b2", "q0", "q1", "q2"]
    assert [r["judge_refusal"] for r in rows] == [True, True, False, True, False, False]
    assert [r["zone"] for r in rows[:3]] == [p.zone for p in probes]
    assert [r["expected"] for r in rows[:3]] == [p.expected for p in probes]
    assert set(rows[0]) == {"pair", "arm", "zone", "expected", "judge_refusal", "completion"}


def test_no_capture_file_unless_the_caller_opts_in(tmp_path, monkeypatch):
    sv = _install_fake_run(monkeypatch, _probes(), ["b0", "b1", "b2"], ["q0", "q1", "q2"], [True] * 3 + [False] * 3)
    sv.verify_safety("base", "quant")
    assert list(tmp_path.iterdir()) == []


def test_report_and_drift_are_identical_with_and_without_capture(tmp_path, monkeypatch):
    # The capture is an extra local file, never an input: turning it on must not
    # move a single digit of what the run computes or publishes.
    flags = [True, True, False, False, True, True]
    sv = _install_fake_run(monkeypatch, _probes(), ["b0", "b1", "b2"], ["q0", "q1", "q2"], flags)

    plain = tmp_path / "plain.json"
    captured = tmp_path / "captured.json"
    drift_plain = sv.verify_safety("base", "quant", report_path=str(plain))
    drift_captured = sv.verify_safety(
        "base", "quant", report_path=str(captured), capture_path=str(tmp_path / "capture.jsonl")
    )

    assert drift_plain == drift_captured
    assert drift_plain.to_dict() == drift_captured.to_dict()
    assert drift_plain.summary() == drift_captured.summary()
    assert _minus_timestamps(plain) == _minus_timestamps(captured)
    assert (tmp_path / "capture.jsonl").exists()


def test_capture_survives_completions_with_newlines_and_unicode(tmp_path, monkeypatch):
    # JSONL is one row per line; a completion containing newlines must not become
    # two rows, and a non-ASCII completion must survive the round trip.
    weird = ["line one\nline two", "café — nope", ""]
    sv = _install_fake_run(monkeypatch, _probes(), weird, ["q0", "q1", "q2"], [True] * 3 + [False] * 3)
    capture = tmp_path / "capture.jsonl"

    sv.verify_safety("base", "quant", capture_path=str(capture))

    header, rows = _read_capture_lines(capture)
    assert header["n_pairs"] == 3
    assert len(rows) == 6
    assert [r["completion"] for r in rows[:3]] == weird


def test_an_unwritable_capture_warns_and_does_not_cost_the_run(tmp_path, monkeypatch, capsys):
    # The capture is an opt-in local scratch file; the drift is the run's result.
    # An OSError from the capture write escaped verify_safety AFTER the report was on
    # disk, so a REGRESSION run and a full disk would have exited 2 for opposite
    # reasons — the exit contract cannot carry two meanings for one code.
    flags = [True, True, False, False, True, True]
    sv = _install_fake_run(monkeypatch, _probes(), ["b0", "b1", "b2"], ["q0", "q1", "q2"], flags)
    report = tmp_path / "report.json"
    doomed = tmp_path / "no-such-dir" / "capture.jsonl"  # the parent does not exist

    drift = sv.verify_safety("base", "quant", report_path=str(report), capture_path=str(doomed))

    assert drift == sv.verify_safety("base", "quant")  # the result is untouched
    assert drift.to_dict() == sv.verify_safety("base", "quant").to_dict()
    assert report.exists()  # ...and the artifact the run owed the world is on disk
    assert not doomed.exists()
    assert f"warning: capture not written to {doomed}" in capsys.readouterr().out


def test_a_capture_write_failure_is_reported_not_raised(tmp_path, monkeypatch, capsys):
    # Same contract against a writer that fails for a reason no fixture can stage
    # (a read-only mount, a quota): OSError in, warning out, drift returned.
    sv = _install_fake_run(monkeypatch, _probes(), ["b0", "b1", "b2"], ["q0", "q1", "q2"], [True] * 3 + [False] * 3)

    def refuse(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(sv, "_write_capture", refuse)
    drift = sv.verify_safety("base", "quant", capture_path=str(tmp_path / "capture.jsonl"))

    assert drift.n == 3
    assert "warning: capture not written to" in capsys.readouterr().out


def test_a_failed_capture_does_not_flip_the_cli_exit_contract(tmp_path, monkeypatch, capsys):
    # What the exit codes mean: 3 = regression detected, 2 = operational error. An
    # escaping capture OSError turned the first into the second — with the summary
    # never printed — so a full disk on an opt-in scratch file erased the verdict.
    from quantfit.cli import main

    # Baseline refuses both unsafe probes; the quant complies on one -> a regression.
    _install_fake_run(
        monkeypatch, _probes(), ["b0", "b1", "b2"], ["q0", "q1", "q2"], [True, True, False, False, True, False]
    )
    doomed = tmp_path / "no-such-dir" / "capture.jsonl"

    code = main(["verify-safety", "--baseline", "base", "--quant", "quant", "--capture", str(doomed)])

    out = capsys.readouterr().out
    assert code == 3  # the drift verdict, not 2 (operational failure)
    assert "warning: capture not written to" in out
    # ...and the summary the run owed its caller was still printed.
    assert "safety drift over 3 probes" in out and "harmful-compliance regressions" in out


# --- part 2: the blinded sheet ------------------------------------------------------


def test_sheet_is_blinded(tmp_path):
    sheet, _key = _build(tmp_path)
    table = _sheet_rows(sheet)

    assert tuple(table[0]) == SHEET_COLUMNS  # no arm, no judge label, no zone/expected
    assert all(len(row) == 3 for row in table[1:])
    assert all(row[2] == "" for row in table[1:])  # human_label starts empty

    text = Path(sheet).read_text(encoding="utf-8")
    for leak in (ARM_BASELINE, ARM_QUANTIZED, "judge_refusal", "true", "false"):
        assert leak not in text

    ids = [row[0] for row in table[1:]]
    assert all(_ID_PATTERN.fullmatch(row_id) for row_id in ids)
    # An opaque token, not the row's identity in disguise.
    raw = {str(pair) for pair in range(_N_PAIRS)} | {f"{pair}:{arm}" for pair in range(_N_PAIRS) for arm in ("b", "q")}
    assert not (set(ids) & raw)


def test_two_builds_of_one_capture_share_no_ids(tmp_path):
    # The salt is DRAWN per build, not derived from the capture. Deriving it made the
    # blind brute-forceable: the only unknown in a capture header is a one-second
    # timestamp, so a few hundred thousand guesses re-derive every id. Byte-identical
    # rebuilds paid for that; the write-once guards below are what protect a sheet now.
    capture = _capture(tmp_path)
    first_sheet, first_key = _build(tmp_path, capture_path=capture, stem="a")
    second_sheet, second_key = _build(tmp_path, capture_path=capture, stem="b")

    ids_a = json.loads(Path(first_key).read_text(encoding="utf-8"))["ids"]
    ids_b = json.loads(Path(second_key).read_text(encoding="utf-8"))["ids"]
    assert not (set(ids_a) & set(ids_b))
    assert Path(first_sheet).read_bytes() != Path(second_sheet).read_bytes()
    salts = [json.loads(Path(path).read_text(encoding="utf-8"))["salt"] for path in (first_key, second_key)]
    assert salts[0] != salts[1] and all(len(salt) == 64 for salt in salts)
    # Each key still validates its own ids and unblinds its own sheet.
    for stem, sheet, key in (("a", first_sheet, first_key), ("b", second_sheet, second_key)):
        report, _ = _ingest(tmp_path, _fill(sheet, key), key, name=f"calibration-{stem}.json")
        assert report[ARM_BASELINE]["judge_errors"] == 1


def test_two_captures_never_mint_the_same_ids(tmp_path):
    # Ids from different runs cannot be aligned against each other — one sheet's key
    # never unblinds another's sheet.
    _, key_a = _build(tmp_path, stem="a")
    other = _capture(tmp_path, name="other.jsonl", header_overrides={"quant": "quant-b"})
    _, key_b = _build(tmp_path, capture_path=other, stem="b")
    ids_a = set(json.loads(Path(key_a).read_text(encoding="utf-8"))["ids"])
    ids_b = set(json.loads(Path(key_b).read_text(encoding="utf-8"))["ids"])
    assert not (ids_a & ids_b)


def test_row_order_is_a_shuffle_not_the_capture_order(tmp_path):
    """The sheet order must be randomised, which is a property of the SHUFFLE, not of one draw.

    Asserted across several independent builds on purpose. A fair shuffle can reproduce the
    capture order by chance, so a single draw cannot distinguish "randomised" from "lucky":
    with `_N_PAIRS` = 5 the arm sequence lands back on the capture's own order with
    probability 1/C(10,5), and lands with one arm filling the first block with probability
    2/C(10,5) = 0.79% — which is precisely the rate at which this test used to fail, roughly
    one CI run in 126 across a five-job matrix.

    The blinding salt comes from `secrets`, so it cannot be seeded for the test without
    weakening the thing being tested. Repeating instead makes a false failure require every
    draw to coincide: (1/252)**_DRAWS, which is about 2e-15 here.

    Each individual draw is still checked for the property that must hold every time — the
    order is a permutation of the capture, nothing added, nothing dropped.
    """
    _DRAWS = 6
    capture_order = [ARM_BASELINE] * _N_PAIRS + [ARM_QUANTIZED] * _N_PAIRS

    orders = []
    for i in range(_DRAWS):
        sheet, key = _build(tmp_path, stem=f"draw{i}")
        ids = json.loads(Path(key).read_text(encoding="utf-8"))["ids"]
        order = [ids[row[0]] for row in _sheet_rows(sheet)[1:]]
        # Holds on every draw, lucky or not: a shuffle rearranges, it never adds or drops.
        assert sorted((e["pair"], e["arm"]) for e in order) == sorted(
            (pair, arm) for pair in range(_N_PAIRS) for arm in (ARM_BASELINE, ARM_QUANTIZED)
        )
        orders.append(order)

    arm_orders = [[e["arm"] for e in order] for order in orders]
    assert any(arms != capture_order for arms in arm_orders), (
        f"all {_DRAWS} draws reproduced the capture's own arm order; the sheet is not being shuffled"
    )
    assert any(len(set(arms[:_N_PAIRS])) == 2 for arms in arm_orders), (
        f"in all {_DRAWS} draws one arm filled the first block; the arms are not interleaved"
    )
    assert any([e["pair"] for e in order] != sorted(e["pair"] for e in order) for order in orders), (
        f"all {_DRAWS} draws came out in pair order; the sheet is not being shuffled"
    )


def test_both_arms_and_both_judge_labels_are_in_the_sheet(tmp_path):
    # ROADMAP 0.6: concordant pairs included — labeling only the flips is
    # verification bias, so the sheet carries every captured completion.
    sheet, key = _build(tmp_path)
    ids = json.loads(Path(key).read_text(encoding="utf-8"))["ids"]

    assert len(_sheet_rows(sheet)) - 1 == len(ids) == 2 * _N_PAIRS
    assert {(e["pair"], e["arm"]) for e in ids.values()} == {
        (pair, arm) for pair in range(_N_PAIRS) for arm in (ARM_BASELINE, ARM_QUANTIZED)
    }
    assert {e["judge_refusal"] for e in ids.values()} == {True, False}
    # Pairs the two arms were judged identically on are in the sheet too — those
    # are the ones a flips-only sheet would have dropped.
    concordant = {
        (pair, arm)
        for pair in range(_N_PAIRS)
        for arm in (ARM_BASELINE, ARM_QUANTIZED)
        if _JUDGE[ARM_BASELINE][pair] == _JUDGE[ARM_QUANTIZED][pair]
    }
    assert concordant and concordant <= {(e["pair"], e["arm"]) for e in ids.values()}


def test_key_records_the_capture_provenance_and_schema(tmp_path):
    _, key_path = _build(tmp_path)
    key = json.loads(Path(key_path).read_text(encoding="utf-8"))
    assert key["key_schema"] == KEY_SCHEMA
    assert key["capture"]["baseline"] == "base" and key["capture"]["n_pairs"] == _N_PAIRS
    assert len(key["salt"]) == 64
    assert set(next(iter(key["ids"].values()))) == {"pair", "arm", "judge_refusal", "completion_sha256"}
    # The completion digest is the capture's text, so a mangled sheet is catchable.
    rows = {(e["pair"], e["arm"]): e["completion_sha256"] for e in key["ids"].values()}
    expected = hashlib.sha256(f"text for row 0 on side {ARM_BASELINE[0]}0".encode()).hexdigest()
    assert rows[(0, ARM_BASELINE)] == expected


def test_rebuild_refuses_to_eat_filled_labels(tmp_path):
    sheet, key = _build(tmp_path)
    _fill(sheet, key)
    with pytest.raises(CalibrationError, match="already carries"):
        build_labeling_sheet(_capture(tmp_path), sheet, str(tmp_path / "other-key.json"))
    # ...but an untouched sheet is regenerable — to a key path of its own, since the
    # rebuild mints a new salt and the old key would no longer join it.
    fresh = str(tmp_path / "fresh.csv")
    build_labeling_sheet(_capture(tmp_path), fresh, str(tmp_path / "fresh-key.json"))
    build_labeling_sheet(_capture(tmp_path), fresh, str(tmp_path / "fresh-key-2.json"))


def test_rebuild_refuses_a_filled_sheet_that_came_back_with_a_bom(tmp_path):
    # Excel writes a BOM on save. Reading the sheet as plain utf-8 made the header
    # unparseable, the guard read that as "not a sheet this module wrote" and returned,
    # and the rebuild ate the labeling. Two fixes meet here: utf-8-sig on read, and a
    # guard whose only silent pass is a path that does not exist.
    sheet, key = _build(tmp_path)
    _fill(sheet, key)
    _add_bom(sheet)
    before = Path(sheet).read_bytes()

    with pytest.raises(CalibrationError, match="already carries"):
        build_labeling_sheet(_capture(tmp_path), sheet, str(tmp_path / "other-key.json"))
    assert Path(sheet).read_bytes() == before  # the labeling is untouched


def test_rebuild_refuses_a_sheet_it_cannot_prove_is_pristine(tmp_path):
    # A labeler's spreadsheet added a notes column, so the sheet no longer parses —
    # which is exactly why it may not be assumed to hold nothing.
    sheet, key = _build(tmp_path)
    _fill(sheet, key)
    table = _sheet_rows(sheet)
    widened = [[*table[0], "notes"], *[[*row, "asked a colleague"] for row in table[1:]]]
    with Path(sheet).open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(widened)
    before = Path(sheet).read_bytes()

    with pytest.raises(CalibrationError, match="is not a sheet this module can read") as excinfo:
        build_labeling_sheet(_capture(tmp_path), sheet, str(tmp_path / "other-key.json"))
    assert "move it aside" in str(excinfo.value)
    assert Path(sheet).read_bytes() == before


def test_a_sheet_saved_with_a_bom_still_ingests(tmp_path):
    # Fail-closed must not mean fail-useless: the BOM alone is not corruption.
    sheet, key = _build(tmp_path)
    _fill(sheet, key)
    report, _ = _ingest(tmp_path, _add_bom(sheet), key)
    assert report[ARM_BASELINE]["judge_errors"] == 1
    assert report[ARM_QUANTIZED]["judge_errors"] == 2


def test_rebuild_refuses_to_overwrite_a_key(tmp_path):
    # The key holds the ONLY copy of its sheet's salt now, so a silent overwrite
    # strands the sheet it unblinds — and this write was unguarded.
    sheet, key = _build(tmp_path)
    second_sheet = tmp_path / "second.csv"

    with pytest.raises(CalibrationError, match="already exists") as excinfo:
        build_labeling_sheet(_capture(tmp_path), str(second_sheet), key)
    message = str(excinfo.value)
    assert "unblinds capture" in message  # the refusal names what the existing key is for
    assert '"baseline": "base"' in message and f'"n_pairs": {_N_PAIRS}' in message
    assert not second_sheet.exists()
    # The pair that key belongs to is intact.
    report, _ = _ingest(tmp_path, _fill(sheet, key), key)
    assert report["n_labeled"] == 2 * _N_PAIRS


# --- part 2: ingestion arithmetic ---------------------------------------------------


def test_epsilon_digits_match_the_hand_computation_and_wilson(tmp_path):
    sheet, key = _build(tmp_path)
    report, out = _ingest(tmp_path, _fill(sheet, key), key)

    # Both intervals are `wilson_interval`'s own output AND the literal digits
    # scipy's binomtest(...).proportion_ci(method="wilson") returns for the same
    # counts — the same closed form tests/test_stats_scipy.py pins to 1e-9.
    baseline, quantized = report[ARM_BASELINE], report[ARM_QUANTIZED]
    assert (baseline["n"], baseline["judge_errors"]) == (5, 1)
    assert baseline["epsilon"] == pytest.approx(0.2)
    assert baseline["epsilon_wilson95"] == list(wilson_interval(1, 5))
    assert baseline["epsilon_wilson95"] == pytest.approx([0.0362241086, 0.6244653702], abs=1e-9)

    assert (quantized["n"], quantized["judge_errors"]) == (4, 2)
    assert quantized["epsilon"] == pytest.approx(0.5)
    assert quantized["epsilon_wilson95"] == list(wilson_interval(2, 4))
    assert quantized["epsilon_wilson95"] == pytest.approx([0.1500389892, 0.8499610108], abs=1e-9)

    assert report["arm_epsilon_delta"]["delta"] == pytest.approx(0.3)
    assert "never averaged" in report["arm_epsilon_delta"]["note"]
    assert out.exists()


def test_direction_split_is_recorded_per_arm(tmp_path):
    sheet, key = _build(tmp_path)
    report, _ = _ingest(tmp_path, _fill(sheet, key), key)

    assert report[ARM_BASELINE]["direction"] == {
        "judge_refusal_human_compliance": 1,
        "judge_compliance_human_refusal": 0,
    }
    assert report[ARM_QUANTIZED]["direction"] == {
        "judge_refusal_human_compliance": 1,
        "judge_compliance_human_refusal": 1,
    }
    for arm in (ARM_BASELINE, ARM_QUANTIZED):
        block = report[arm]
        assert sum(block["direction"].values()) == block["judge_errors"]


def test_unusable_rows_are_excluded_from_n_and_counted(tmp_path):
    sheet, key = _build(tmp_path)
    report, _ = _ingest(tmp_path, _fill(sheet, key), key)

    assert report["n_labeled"] == 2 * _N_PAIRS
    assert report["n_unusable"] == 1
    # The identity that proves nothing was silently dropped.
    assert report["n_labeled"] - report["n_unusable"] == report[ARM_BASELINE]["n"] + report[ARM_QUANTIZED]["n"]


def test_unusable_rows_are_counted_on_the_arm_they_came_from(tmp_path):
    # Pooling them hid WHICH side went dark, which is the one thing an unusable count
    # is for: 20 unreadable completions all on the quantized arm is a different fact
    # from 10 on each.
    sheet, key = _build(tmp_path)
    report, _ = _ingest(tmp_path, _fill(sheet, key), key)

    assert report[ARM_BASELINE]["n_unusable"] == 0
    assert report[ARM_QUANTIZED]["n_unusable"] == 1
    assert report["n_unusable"] == report[ARM_BASELINE]["n_unusable"] + report[ARM_QUANTIZED]["n_unusable"]


def test_directional_rates_use_their_own_denominators(tmp_path):
    # A false compliance is only possible where a human saw a refusal, so its
    # denominator is human_refusals, not n. Dividing by n understates it by exactly
    # the compliant mass of the sample.
    sheet, key = _build(tmp_path)
    report, _ = _ingest(tmp_path, _fill(sheet, key), key)

    baseline = report[ARM_BASELINE]
    assert (baseline["human_refusals"], baseline["human_compliances"]) == (2, 3)
    false_compliance = baseline["directional"][DIR_FALSE_COMPLIANCE]
    assert (false_compliance["errors"], false_compliance["n"]) == (0, 2)
    assert false_compliance["epsilon"] == 0.0
    assert false_compliance["epsilon_wilson95"] == list(wilson_interval(0, 2))
    assert false_compliance["epsilon_wilson95"] == pytest.approx([0.0, 0.6576197725], abs=1e-9)
    false_refusal = baseline["directional"][DIR_FALSE_REFUSAL]
    assert (false_refusal["errors"], false_refusal["n"]) == (1, 3)
    assert false_refusal["epsilon"] == pytest.approx(1 / 3)
    assert false_refusal["epsilon_wilson95"] == list(wilson_interval(1, 3))
    assert false_refusal["epsilon_wilson95"] == pytest.approx([0.0614919447, 0.7923403992], abs=1e-9)
    # The marginal epsilon still divides by n and is neither directional rate.
    assert baseline["epsilon"] == pytest.approx(0.2)

    quantized = report[ARM_QUANTIZED]
    assert (quantized["human_refusals"], quantized["human_compliances"]) == (2, 2)
    for direction in (DIR_FALSE_COMPLIANCE, DIR_FALSE_REFUSAL):
        block = quantized["directional"][direction]
        assert (block["errors"], block["n"]) == (1, 2)
        assert block["epsilon"] == pytest.approx(0.5)
        assert block["epsilon_wilson95"] == list(wilson_interval(1, 2))
        assert block["epsilon_wilson95"] == pytest.approx([0.0945312057, 0.9054687943], abs=1e-9)
    # Each arm's directional errors are its marginal judge errors, re-cut by direction.
    for arm in (ARM_BASELINE, ARM_QUANTIZED):
        block = report[arm]
        assert sum(d["errors"] for d in block["directional"].values()) == block["judge_errors"]
        assert block["human_refusals"] + block["human_compliances"] == block["n"]


def test_mde_epsilon_upper_is_the_max_of_the_two_directional_uppers(tmp_path):
    # The MDE module consumes the MAX: a judge excellent in one direction and blind in
    # the other must not average its way into looking adequate.
    sheet, key = _build(tmp_path)
    report, _ = _ingest(tmp_path, _fill(sheet, key), key)

    for arm in (ARM_BASELINE, ARM_QUANTIZED):
        block = report[arm]
        uppers = [block["directional"][d]["epsilon_wilson95"][1] for d in (DIR_FALSE_COMPLIANCE, DIR_FALSE_REFUSAL)]
        assert block["mde_epsilon_upper"] == max(uppers)

    baseline = report[ARM_BASELINE]
    assert baseline["mde_epsilon_upper"] == pytest.approx(wilson_interval(1, 3)[1])
    # ...which is the WORSE direction, not the better one and not the marginal upper.
    assert baseline["mde_epsilon_upper"] > baseline["directional"][DIR_FALSE_COMPLIANCE]["epsilon_wilson95"][1]
    assert baseline["mde_epsilon_upper"] > baseline["epsilon_wilson95"][1]
    assert report[ARM_QUANTIZED]["mde_epsilon_upper"] == pytest.approx(wilson_interval(1, 2)[1])


def test_a_direction_with_no_denominator_is_null_and_stops_the_mde(tmp_path):
    # Every usable baseline row labeled refusal: nothing in that arm COULD have been a
    # false refusal, so the rate has no denominator. Null, never 0.0 — and a direction
    # that was never measured must not license an MDE.
    labels = {k: ("refusal" if k[1] == ARM_BASELINE else v) for k, v in _HUMAN.items()}
    sheet, key = _build(tmp_path)
    report, _ = _ingest(tmp_path, _fill(sheet, key, labels), key)

    baseline = report[ARM_BASELINE]
    assert (baseline["human_refusals"], baseline["human_compliances"]) == (5, 0)
    false_refusal = baseline["directional"][DIR_FALSE_REFUSAL]
    assert (false_refusal["errors"], false_refusal["n"]) == (0, 0)
    assert false_refusal["epsilon"] is None
    assert false_refusal["epsilon_wilson95"] == [0.0, 1.0]  # the degenerate interval
    assert baseline["mde_epsilon_upper"] is None

    false_compliance = baseline["directional"][DIR_FALSE_COMPLIANCE]
    assert (false_compliance["errors"], false_compliance["n"]) == (2, 5)
    assert false_compliance["epsilon"] == pytest.approx(0.4)
    assert false_compliance["epsilon_wilson95"] == list(wilson_interval(2, 5))
    assert false_compliance["epsilon_wilson95"] == pytest.approx([0.1176207742, 0.7692757187], abs=1e-9)
    # The arm is still measured marginally, and the other arm is untouched.
    assert baseline["epsilon"] == pytest.approx(0.4)
    assert report[ARM_QUANTIZED]["mde_epsilon_upper"] == pytest.approx(wilson_interval(1, 2)[1])
    assert report["unmeasured_arms"] == []


def test_an_arm_with_no_usable_rows_reports_null_epsilon(tmp_path):
    # Everything on one arm unusable: eps is unmeasured, and a printed 0.0 would
    # read as a flawless judge. Same rule as an unmeasurable drift axis.
    labels = {k: ("unusable" if k[1] == ARM_QUANTIZED else v) for k, v in _HUMAN.items()}
    sheet, key_path = _build(tmp_path)
    report, _ = _ingest(tmp_path, _fill(sheet, key_path, labels), key_path)

    assert report[ARM_QUANTIZED]["n"] == 0
    assert report[ARM_QUANTIZED]["epsilon"] is None
    assert report[ARM_QUANTIZED]["epsilon_wilson95"] == [0.0, 1.0]  # the degenerate interval
    assert report[ARM_QUANTIZED]["mde_epsilon_upper"] is None
    assert report[ARM_QUANTIZED]["n_unusable"] == _N_PAIRS
    assert report["arm_epsilon_delta"]["delta"] is None
    assert report["n_unusable"] == _N_PAIRS


def test_an_unmeasured_arm_qualifies_the_scope_label(tmp_path):
    # A calibration that measured one arm cannot carry the label of one that measured
    # the pair: arm-correlated judge error is the whole reason the arms are separate.
    labels = {k: ("unusable" if k[1] == ARM_QUANTIZED else v) for k, v in _HUMAN.items()}
    sheet, key_path = _build(tmp_path)
    report, _ = _ingest(tmp_path, _fill(sheet, key_path, labels), key_path)

    assert report["unmeasured_arms"] == [ARM_QUANTIZED]
    label = report["label"]
    assert label != CALIBRATION_LABEL
    assert ARM_QUANTIZED in label and "PARTIAL" in label
    assert "unmeasured — not zero" in label
    assert "does NOT stand in for" in label
    # The measured arm is still reported in full.
    assert report[ARM_BASELINE]["epsilon"] == pytest.approx(0.2)


def test_a_wholly_unusable_sheet_is_not_a_calibration(tmp_path):
    # Both arms at n == 0 measured nothing. Stamping a schema and the scope label on
    # that would publish "the judge was calibrated" over an empty sample.
    labels = dict.fromkeys(_HUMAN, "unusable")
    sheet, key_path = _build(tmp_path)
    out = tmp_path / "calibration.json"

    with pytest.raises(CalibrationError, match="nothing was measured") as excinfo:
        ingest_labels(_fill(sheet, key_path, labels), key_path, str(out))
    assert "every labeled row" in str(excinfo.value)
    assert not out.exists()


def test_calibration_report_round_trips(tmp_path):
    import quantfit

    sheet, key = _build(tmp_path)
    report, out = _ingest(tmp_path, _fill(sheet, key), key)

    assert json.loads(out.read_text(encoding="utf-8")) == report
    assert report["calibration_schema"] == CALIBRATION_SCHEMA
    assert report["quantfit_version"] == quantfit.__version__
    assert report["created_utc"].endswith("+00:00")
    assert set(report) == {
        "calibration_schema",
        "quantfit_version",
        "created_utc",
        "n_labeled",
        "n_unusable",
        "unmeasured_arms",
        ARM_BASELINE,
        ARM_QUANTIZED,
        "arm_epsilon_delta",
        "label",
    }
    assert report["unmeasured_arms"] == []
    for arm in (ARM_BASELINE, ARM_QUANTIZED):
        assert set(report[arm]) == {
            "n",
            "n_unusable",
            "judge_errors",
            "epsilon",
            "epsilon_wilson95",
            "human_refusals",
            "human_compliances",
            "direction",
            "directional",
            "mde_epsilon_upper",
        }
        assert set(report[arm]["directional"]) == {DIR_FALSE_COMPLIANCE, DIR_FALSE_REFUSAL}
        for block in report[arm]["directional"].values():
            assert set(block) == {"errors", "n", "epsilon", "epsilon_wilson95"}


def test_label_scopes_the_replacement_to_this_capture_only(tmp_path):
    sheet, key = _build(tmp_path)
    report, _ = _ingest(tmp_path, _fill(sheet, key), key)
    label = report["label"]
    assert label == CALIBRATION_LABEL
    assert "REPLACES" in label and "§2.7" in label
    assert "that run only" in label
    assert report["unmeasured_arms"] == []  # the unqualified label is only for a full sample


def test_labels_are_case_insensitive(tmp_path):
    sheet, key = _build(tmp_path)
    shouted = {k: v.upper() for k, v in _HUMAN.items()}
    report, _ = _ingest(tmp_path, _fill(sheet, key, shouted), key)
    assert report[ARM_BASELINE]["judge_errors"] == 1


# --- part 2: refusals ---------------------------------------------------------------


def test_calibration_error_is_a_runtime_error():
    # The CLI's exit-2 handler catches RuntimeError; anything else is a traceback.
    assert issubclass(CalibrationError, RuntimeError)


def test_unlabeled_row_refused_by_row_and_id(tmp_path):
    sheet, key = _build(tmp_path)

    def blank_one(rows):
        rows[3][2] = ""
        return rows

    _fill(sheet, key, mutate=blank_one)
    blanked = _sheet_rows(sheet)[3][0]
    with pytest.raises(CalibrationError, match="unlabeled") as excinfo:
        _ingest(tmp_path, sheet, key)
    assert "row 4" in str(excinfo.value) and blanked in str(excinfo.value)


def test_unknown_label_refused(tmp_path):
    sheet, key = _build(tmp_path)

    def bad_label(rows):
        rows[2][2] = "maybe"
        return rows

    _fill(sheet, key, mutate=bad_label)
    with pytest.raises(CalibrationError, match="'maybe' is not one of") as excinfo:
        _ingest(tmp_path, sheet, key)
    assert "row 3" in str(excinfo.value)
    assert all(label in str(excinfo.value) for label in HUMAN_LABELS)


def test_id_missing_from_the_sheet_refused(tmp_path):
    sheet, key = _build(tmp_path)

    def drop_one(rows):
        return rows[:-1]

    _fill(sheet, key, mutate=drop_one)
    dropped = json.loads(Path(key).read_text(encoding="utf-8"))
    with pytest.raises(CalibrationError, match="missing 1 id") as excinfo:
        _ingest(tmp_path, sheet, key)
    assert any(row_id in str(excinfo.value) for row_id in dropped["ids"])


def test_extra_id_in_the_sheet_refused(tmp_path):
    sheet, key = _build(tmp_path)

    def add_one(rows):
        return [*rows, ["r" + "f" * 16, "smuggled completion", "refusal"]]

    _fill(sheet, key, mutate=add_one)
    with pytest.raises(CalibrationError, match="not in labeling key") as excinfo:
        _ingest(tmp_path, sheet, key)
    assert "r" + "f" * 16 in str(excinfo.value)


def test_an_edited_completion_is_refused_naming_the_row(tmp_path):
    # The sheet's completion column was never checked against the capture, so a sheet
    # whose text had been re-typed, truncated by a spreadsheet or "tidied" produced a
    # byte-identical calibration report about text the judge never saw.
    sheet, key = _build(tmp_path)

    def tidy_one(rows):
        rows[2][1] = rows[2][1].upper() + "  "
        return rows

    _fill(sheet, key, mutate=tidy_one)
    edited = _sheet_rows(sheet)[2][0]
    with pytest.raises(CalibrationError, match="does not match the capture") as excinfo:
        _ingest(tmp_path, sheet, key)
    message = str(excinfo.value)
    assert "row 3" in message and edited in message
    assert "cannot be attributed to the text the judge scored" in message


def test_a_completion_with_newlines_and_quotes_round_trips(tmp_path):
    # Authenticating the text is only fail-CLOSED if the sheet round trip is lossless;
    # otherwise the guard refuses honest labelers over CSV quoting.
    rows = [
        {
            "pair": pair,
            "arm": arm,
            "zone": "clear_safe",
            "expected": "safe",
            "judge_refusal": False,
            "completion": f'line one\nline two, with a comma "and quotes" [{arm[0]}{pair}]',
        }
        for arm in (ARM_BASELINE, ARM_QUANTIZED)
        for pair in range(_N_PAIRS)
    ]
    sheet, key = _build(tmp_path, capture_path=_capture(tmp_path, rows=rows))
    report, _ = _ingest(tmp_path, _fill(sheet, key, dict.fromkeys(_HUMAN, "compliance")), key)

    assert report[ARM_BASELINE]["n"] == report[ARM_QUANTIZED]["n"] == _N_PAIRS
    assert report[ARM_BASELINE]["judge_errors"] == 0


def test_duplicated_id_refused(tmp_path):
    sheet, key = _build(tmp_path)

    def duplicate(rows):
        return [*rows, list(rows[1])]

    _fill(sheet, key, mutate=duplicate)
    with pytest.raises(CalibrationError, match="duplicated") as excinfo:
        _ingest(tmp_path, sheet, key)
    assert _sheet_rows(sheet)[1][0] in str(excinfo.value)


def test_tampered_key_refused(tmp_path):
    # Re-pointing an entry at another row is how a key would be edited to launder a
    # judge error; the id no longer hashes to its own (pair, arm) under the salt.
    sheet, key_path = _build(tmp_path)
    _fill(sheet, key_path)
    key = json.loads(Path(key_path).read_text(encoding="utf-8"))
    victim = next(row_id for row_id, entry in key["ids"].items() if entry["arm"] == ARM_BASELINE)
    key["ids"][victim]["arm"] = ARM_QUANTIZED
    Path(key_path).write_text(json.dumps(key), encoding="utf-8")

    with pytest.raises(CalibrationError, match="does not hash to its own") as excinfo:
        _ingest(tmp_path, sheet, key_path)
    assert victim in str(excinfo.value)


def test_flipped_judge_label_in_the_key_is_not_caught_by_the_hash(tmp_path):
    # Stated, not hidden: the id binds (pair, arm) only. A key whose judge_refusal
    # was edited still verifies — the capture is the record that contradicts it.
    sheet, key_path = _build(tmp_path)
    _fill(sheet, key_path)
    key = json.loads(Path(key_path).read_text(encoding="utf-8"))
    victim = next(row_id for row_id, e in key["ids"].items() if (e["pair"], e["arm"]) != (_N_PAIRS - 1, ARM_QUANTIZED))
    key["ids"][victim]["judge_refusal"] = not key["ids"][victim]["judge_refusal"]
    Path(key_path).write_text(json.dumps(key), encoding="utf-8")

    report, _ = _ingest(tmp_path, sheet, key_path)
    assert report[ARM_BASELINE]["judge_errors"] + report[ARM_QUANTIZED]["judge_errors"] in (2, 4)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ({"key_schema": 2}, "key_schema"),
        ({"key_schema": None}, "key_schema"),
        ({"salt": ""}, "records no salt"),
        ({"ids": {}}, "no non-empty 'ids' map"),
        ({"ids": {"r" + "a" * 16: {"pair": 0, "arm": "baseline"}}}, "judge_refusal"),
        (
            {"ids": {"r" + "a" * 16: {"pair": "0", "arm": "baseline", "judge_refusal": True}}},
            "'pair' must be an integer",
        ),
        ({"ids": {"r" + "a" * 16: {"pair": 0, "arm": "fp16", "judge_refusal": True}}}, "is not one of"),
        ({"ids": {"r" + "a" * 16: "baseline"}}, "not a JSON object"),
        # No completion digest: the sheet's text could not be authenticated at all.
        ({"ids": {"r" + "a" * 16: {"pair": 0, "arm": "baseline", "judge_refusal": True}}}, "completion_sha256"),
        (
            {
                "ids": {
                    "r" + "a" * 16: {"pair": 0, "arm": "baseline", "judge_refusal": True, "completion_sha256": "beef"}
                }
            },
            "64-char hex digest",
        ),
    ],
)
def test_malformed_key_refused(tmp_path, mutation, match):
    sheet, key_path = _build(tmp_path)
    _fill(sheet, key_path)
    key = json.loads(Path(key_path).read_text(encoding="utf-8"))
    key.update(mutation)
    Path(key_path).write_text(json.dumps(key), encoding="utf-8")
    with pytest.raises(CalibrationError, match=match):
        _ingest(tmp_path, sheet, key_path)


def test_unreadable_key_refused(tmp_path):
    sheet, key_path = _build(tmp_path)
    _fill(sheet, key_path)
    Path(key_path).write_text("{not json", encoding="utf-8")
    with pytest.raises(CalibrationError, match="unreadable labeling key"):
        _ingest(tmp_path, sheet, key_path)


def test_missing_sheet_refused(tmp_path):
    _, key_path = _build(tmp_path)
    with pytest.raises(CalibrationError, match="unreadable labeling sheet"):
        _ingest(tmp_path, str(tmp_path / "nope.csv"), key_path)


def test_wrong_sheet_header_refused(tmp_path):
    sheet, key_path = _build(tmp_path)
    _fill(sheet, key_path)
    table = _sheet_rows(sheet)
    table[0] = ["id", "completion", "arm", "human_label"]  # an "improved" sheet is not this sheet
    with Path(sheet).open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(table)
    with pytest.raises(CalibrationError, match="header is"):
        _ingest(tmp_path, sheet, key_path)


@pytest.mark.parametrize(
    ("overrides", "rows", "match"),
    [
        ({"capture_schema": 2}, None, "capture_schema"),
        ({"capture_schema": None}, None, "capture_schema"),
        ({"n_pairs": 0}, None, "n_pairs 0"),
        ({"n_pairs": "5"}, None, "n_pairs '5'"),
        (None, [], "no completion rows"),
        (None, [{"pair": 0, "arm": "baseline", "judge_refusal": True}], "'completion' must be a string"),
        (None, [{"pair": "0", "arm": "baseline", "judge_refusal": True, "completion": "x"}], "'pair' must be"),
        (None, [{"pair": 0, "arm": "fp16", "judge_refusal": True, "completion": "x"}], "is not one of"),
        (None, [{"pair": 0, "arm": "baseline", "judge_refusal": "yes", "completion": "x"}], "judge_refusal"),
    ],
)
def test_malformed_capture_refused(tmp_path, overrides, rows, match):
    capture = _capture(tmp_path, header_overrides=overrides, rows=rows)
    with pytest.raises(CalibrationError, match=match):
        build_labeling_sheet(capture, str(tmp_path / "s.csv"), str(tmp_path / "k.json"))


def test_capture_with_a_broken_line_names_the_line(tmp_path):
    capture = Path(_capture(tmp_path))
    lines = capture.read_text(encoding="utf-8").splitlines()
    lines[3] = "{not json"
    capture.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(CalibrationError, match="line 4 is not valid JSON"):
        build_labeling_sheet(str(capture), str(tmp_path / "s.csv"), str(tmp_path / "k.json"))


def test_truncated_capture_refused_with_the_shortfall_named(tmp_path):
    # A run killed mid-write leaves a header promising n_pairs and rows that stop.
    # Nothing checked the two against each other, so the sheet would have been blinded
    # over whatever survived and ε measured against a denominator no one could see.
    capture = Path(_capture(tmp_path))
    lines = capture.read_text(encoding="utf-8").splitlines()
    capture.write_text("\n".join(lines[:-3]) + "\n", encoding="utf-8")  # 3 quantized rows lost

    with pytest.raises(CalibrationError, match=f"declares n_pairs {_N_PAIRS}") as excinfo:
        build_labeling_sheet(str(capture), str(tmp_path / "s.csv"), str(tmp_path / "k.json"))
    message = str(excinfo.value)
    assert f"but carries {2 * _N_PAIRS - 3}" in message
    assert "3 (pair, arm) missing" in message
    assert f"(2, '{ARM_QUANTIZED}')" in message  # the shortfall itself, not just a count
    assert not (tmp_path / "s.csv").exists() and not (tmp_path / "k.json").exists()


def test_capture_with_an_unexpected_pair_index_refused(tmp_path):
    # The other direction: rows the header never promised (a re-run appended to an old
    # capture) would silently widen the sample.
    rows = [
        {"pair": pair, "arm": arm, "zone": "clear_safe", "expected": "safe", "judge_refusal": False, "completion": "x"}
        for arm in (ARM_BASELINE, ARM_QUANTIZED)
        for pair in range(_N_PAIRS + 1)
    ]
    capture = _capture(tmp_path, rows=rows)
    with pytest.raises(CalibrationError, match="2 unexpected") as excinfo:
        build_labeling_sheet(capture, str(tmp_path / "s.csv"), str(tmp_path / "k.json"))
    assert f"(5, '{ARM_BASELINE}')" in str(excinfo.value)


def test_duplicate_row_identity_in_a_capture_refused(tmp_path):
    row = {"pair": 0, "arm": ARM_BASELINE, "zone": "clear_unsafe", "expected": "unsafe", "judge_refusal": True}
    capture = _capture(tmp_path, rows=[{**row, "completion": "first"}, {**row, "completion": "second"}])
    with pytest.raises(CalibrationError, match="two rows for pair 0"):
        build_labeling_sheet(capture, str(tmp_path / "s.csv"), str(tmp_path / "k.json"))


def test_missing_capture_refused(tmp_path):
    with pytest.raises(CalibrationError, match="unreadable capture"):
        build_labeling_sheet(str(tmp_path / "nope.jsonl"), str(tmp_path / "s.csv"), str(tmp_path / "k.json"))


def test_empty_capture_refused(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(CalibrationError, match="is empty"):
        build_labeling_sheet(str(empty), str(tmp_path / "s.csv"), str(tmp_path / "k.json"))


# --- end to end ---------------------------------------------------------------------


def test_capture_to_calibration_end_to_end(tmp_path, monkeypatch):
    # The whole chain on the shipped path: verify_safety writes a capture, the
    # capture blinds into a sheet, a labeler fills it, ingestion unblinds it.
    probes = _probes()
    sv = _install_fake_run(
        monkeypatch,
        probes,
        ["I can't help with that.", "Sure, here you go.", "Sure, here you go."],
        ["Sure, here you go.", "Sure, here you go.", "I can't help with that."],
        [True, False, False, False, False, True],
    )
    capture = tmp_path / "capture.jsonl"
    sv.verify_safety("base", "quant", capture_path=str(capture))

    sheet, key_path = _build(tmp_path, capture_path=str(capture))
    ids = json.loads(Path(key_path).read_text(encoding="utf-8"))["ids"]
    # A perfectly accurate labeler: agree with the judge everywhere -> eps 0 on both arms.
    labels = {(e["pair"], e["arm"]): ("refusal" if e["judge_refusal"] else "compliance") for e in ids.values()}
    report, _ = _ingest(tmp_path, _fill(sheet, key_path, labels), key_path)

    for arm in (ARM_BASELINE, ARM_QUANTIZED):
        assert report[arm] == {
            "n": 3,
            "n_unusable": 0,
            "judge_errors": 0,
            "epsilon": 0.0,
            "epsilon_wilson95": list(wilson_interval(0, 3)),
            # One probe of the three drew a refusal on each arm, so the two directions
            # have denominators 1 and 2 — not 3, and not each other's.
            "human_refusals": 1,
            "human_compliances": 2,
            "direction": {"judge_refusal_human_compliance": 0, "judge_compliance_human_refusal": 0},
            "directional": {
                DIR_FALSE_COMPLIANCE: {
                    "errors": 0,
                    "n": 1,
                    "epsilon": 0.0,
                    "epsilon_wilson95": list(wilson_interval(0, 1)),
                },
                DIR_FALSE_REFUSAL: {
                    "errors": 0,
                    "n": 2,
                    "epsilon": 0.0,
                    "epsilon_wilson95": list(wilson_interval(0, 2)),
                },
            },
            "mde_epsilon_upper": max(wilson_interval(0, 1)[1], wilson_interval(0, 2)[1]),
        }
    assert report["arm_epsilon_delta"]["delta"] == 0.0
    assert report["n_labeled"] == 6 and report["n_unusable"] == 0
    assert report["unmeasured_arms"] == [] and report["label"] == CALIBRATION_LABEL
