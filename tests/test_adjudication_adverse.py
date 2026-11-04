"""Producer exact selection versus capture-free receiver declaration boundaries."""

import csv
import io
import json

import pytest
from test_adjudication import filled, fixture, prepared


@pytest.mark.parametrize("declared,actual", [(1, True), (1.0, 1)])
def test_capture_binding_preserves_json_numeric_and_boolean_types(tmp_path, declared, actual):
    from quantfit import resolution
    from quantfit.adjudication_record import AdjudicationError
    from quantfit.safety.adjudication import prepare_adjudication
    from quantfit.safety.calibration_binding import identity_fingerprint, measurement_identity

    report, capture = fixture(tmp_path / "private")
    raw = json.loads(report.read_bytes())
    raw["decode"]["scope_marker"] = actual
    report.write_text(json.dumps(raw), encoding="utf-8")
    lines = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
    identity = measurement_identity(resolution.parse_report_bytes(report.read_bytes()))
    identity["decode"]["scope_marker"] = declared
    lines[0]["binding"] = {"identity": identity, "fingerprint": identity_fingerprint(identity)}
    capture.write_text("\n".join(json.dumps(row) for row in lines) + "\n", encoding="utf-8")
    with pytest.raises(AdjudicationError, match="^invalid_adjudication$"):
        prepare_adjudication(
            str(report),
            str(capture),
            review_path=str(tmp_path / "review.adjudication.csv"),
            receipt_path=str(tmp_path / "private.adjudication-preparation.json"),
        )
    assert not (tmp_path / "review.adjudication.csv").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "duplicate",
        "text",
        "metadata",
        "blank_label",
        "blank_class",
        "unusable_substantive",
        "wrong_nonflip",
        "preparation",
    ],
)
def test_all_selected_pairs_and_explicit_class_are_required(tmp_path, mutation):
    from quantfit.adjudication_record import AdjudicationError
    from quantfit.safety.adjudication import apply_adjudication

    report, capture, queue, preparation, _ = prepared(tmp_path)
    filled(queue)
    rows = list(csv.reader(io.StringIO(queue.read_text(encoding="utf-8"), newline="")))
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append(["11", *rows[1][1:]])
    elif mutation == "duplicate":
        rows[-1] = rows[1]
    elif mutation == "text":
        rows[1][4] += "PRIVATE_CHANGED"
    elif mutation == "metadata":
        rows[1][2] = "borderline"
    elif mutation == "blank_label":
        rows[1][-3] = ""
    elif mutation == "blank_class":
        rows[1][-1] = ""
    elif mutation == "unusable_substantive":
        rows[4][-1] = "substantive"
    elif mutation == "wrong_nonflip":
        rows[3][-1] = "degenerate"
    else:
        value = json.loads(preparation.read_bytes())
        value["n_selected"] = 8.0
        preparation.write_text(json.dumps(value), encoding="utf-8")
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    queue.write_bytes(stream.getvalue().encode())
    out = tmp_path / "adjudication.json"
    with pytest.raises(AdjudicationError, match="^invalid_adjudication$"):
        apply_adjudication(str(report), str(capture), str(queue), str(preparation), out_path=str(out))
    assert not out.exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "native_count_type",
        "native_zone",
        "native_interval",
        "native_verdict",
        "capture_judge",
        "capture_zone",
        "capture_expected",
        "capture_crossarm",
        "unbound",
        "legacy",
    ],
)
def test_actual_native_correspondence_not_identity_alone(tmp_path, mutation):
    from quantfit.adjudication_record import AdjudicationError
    from quantfit.safety.adjudication import prepare_adjudication

    report, capture = fixture(tmp_path / "private")
    raw = json.loads(report.read_bytes())
    lines = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
    if mutation == "native_count_type":
        raw["drift"]["refusal_robustness"]["at_risk"] = 6.0
    elif mutation == "native_zone":
        raw["drift"]["by_zone"]["clear_unsafe"]["baseline_refused"] -= 1
    elif mutation == "native_interval":
        raw["drift"]["refusal_robustness"]["flip_rate_wilson95"][0] = False
    elif mutation == "native_verdict":
        raw["drift"]["verdict"] = "CONFIRMED SAFE"
    elif mutation == "capture_judge":
        lines[1]["judge_refusal"] = not lines[1]["judge_refusal"]
    elif mutation == "capture_zone":
        lines[1]["zone"] = "foreign"
    elif mutation == "capture_expected":
        lines[1]["expected"] = "foreign"
    elif mutation == "capture_crossarm":
        lines[1]["expected"] = "safe"
    elif mutation == "unbound":
        lines[0]["binding"] = None
    else:
        lines[0]["capture_schema"] = 1
    report.write_text(json.dumps(raw), encoding="utf-8")
    capture.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    queue = tmp_path / "refused.adjudication.csv"
    with pytest.raises(AdjudicationError):
        prepare_adjudication(str(report), str(capture), review_path=str(queue), receipt_path=str(tmp_path / "p.json"))
    assert not queue.exists()


def applied(tmp_path):
    from quantfit.safety.adjudication import apply_adjudication

    report, capture, queue, preparation, _ = prepared(tmp_path)
    filled(queue)
    record = tmp_path / "adjudication.json"
    value = apply_adjudication(str(report), str(capture), str(queue), str(preparation), out_path=str(record))
    return report, capture, record, value


@pytest.mark.parametrize(
    "mutation",
    [
        "report_bytes",
        "pair_type",
        "duplicate_pair",
        "out_of_bounds",
        "axis_count",
        "hash",
        "correct_type",
        "class",
        "counts",
        "limits",
        "notes",
        "row_text",
        "capture_binding_shape",
    ],
)
def test_closed_receiver_refuses_forged_declarations(tmp_path, mutation):
    from quantfit.adjudication_record import AdjudicationError
    from quantfit.modelcard import model_card_fragment

    report, _capture, path, value = applied(tmp_path)
    if mutation == "report_bytes":
        report.write_bytes(report.read_bytes() + b"\n")
    elif mutation == "pair_type":
        value["entries"][0]["pair"] = False
    elif mutation == "duplicate_pair":
        value["entries"][1]["pair"] = value["entries"][0]["pair"]
    elif mutation == "out_of_bounds":
        value["entries"][0]["pair"] = 12
    elif mutation == "axis_count":
        value["original_flagged_counts"]["refusal-robustness"] = 3
    elif mutation == "hash":
        value["entries"][0]["baseline_sha256"] = "not-a-hash"
    elif mutation == "correct_type":
        value["entries"][0]["baseline_judge_correct"] = 1
    elif mutation == "class":
        value["entries"][0]["flip_class"] = "not-a-flip"
    elif mutation == "counts":
        value["counts"]["refusal-robustness"]["substantive"] = 2
    elif mutation == "limits":
        value["proof_limits"]["human_confirmation_verified"] = True
    elif mutation == "notes":
        value["notes"] = "PRIVATE arbitrary text"
    elif mutation == "row_text":
        value["entries"][0]["completion"] = "PRIVATE text"
    else:
        value["inputs"]["capture"]["size_bytes"] = True
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(AdjudicationError):
        model_card_fragment(str(report), adjudication_record=str(path))


def test_capture_free_receiver_honestly_reports_membership_hash_declarations(tmp_path):
    from quantfit.modelcard import model_card_fragment

    report, capture, path, value = applied(tmp_path)
    capture.unlink()  # ONLY freshly generated fictional fixture, no product deletion.
    value["entries"][0]["pair"] = 10
    value["entries"][0]["baseline_sha256"] = "f" * 64
    path.write_text(json.dumps(value), encoding="utf-8")
    card = model_card_fragment(str(report), adjudication_record=str(path))
    assert "not freshly verified here" in card and "Unauthenticated operator declarations" in card


def test_optional_calibration_and_record_share_same_held_report_without_adapter_reopen(tmp_path, monkeypatch):
    import quantfit.adjudication_record as receiving
    from quantfit import resolution
    from quantfit.modelcard import model_card_fragment
    from tools.ci_screen_resolution import calibration_bytes

    report, _capture, path, _ = applied(tmp_path)
    calibration = tmp_path / "calibration.json"
    calibration.write_bytes(calibration_bytes(report.read_bytes()))
    observations = []
    reads = []
    native_record = receiving.load_adjudication_record_bytes
    native_cal = receiving.load_bound_calibration_bytes
    native_hold = receiving.hold

    def record(raw, **kwargs):
        observations.append(kwargs["report"])
        return native_record(raw, **kwargs)

    def cal(raw, **kwargs):
        observations.append(kwargs["report"])
        return native_cal(raw, **kwargs)

    def held(name, limit):
        reads.append(name)
        return native_hold(name, limit)

    def forbidden(*args, **kwargs):
        raise AssertionError("reopening/reparsing resolution adapter used")

    monkeypatch.setattr(receiving, "load_adjudication_record_bytes", record)
    monkeypatch.setattr(receiving, "load_bound_calibration_bytes", cal)
    monkeypatch.setattr(receiving, "hold", held)
    monkeypatch.setattr(resolution, "analyze_resolution_inputs", forbidden)
    monkeypatch.setattr(resolution, "analyze_resolution_bytes", forbidden)
    card = model_card_fragment(str(report), calibration_report=str(calibration), adjudication_record=str(path))
    assert observations[0] is observations[1] and reads == [str(report), str(path), str(calibration)]
    assert "### Conditional resolution from bound calibration" in card and "### Operator-declared adjudication" in card


def test_calibrated_work_admission_precedes_conditional_math(tmp_path, monkeypatch):
    import quantfit.adjudication_record as receiving
    from quantfit.modelcard import model_card_fragment
    from tools.ci_screen_resolution import calibration_bytes

    report, _capture, path, _ = applied(tmp_path)
    cal = tmp_path / "calibration.json"
    cal.write_bytes(calibration_bytes(report.read_bytes()))
    monkeypatch.setattr(receiving, "MAX_ANALYSIS_WORK_UNITS", 1)

    def forbidden(*args, **kwargs):
        raise AssertionError("math before admitted work")

    monkeypatch.setattr("quantfit.resolution._analysis", forbidden)
    with pytest.raises(receiving.AdjudicationError):
        model_card_fragment(str(report), calibration_report=str(cal), adjudication_record=str(path))
