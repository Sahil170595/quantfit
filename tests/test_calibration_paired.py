"""Native paired input fixtures and independent literal joint-table oracles."""

import hashlib
import json
from pathlib import Path

import pytest

from tools.ci_calibration_paired import SPECS, fixture

CHECKOUT = Path(__file__).resolve().parents[1]


def analyze(tmp_path, specs=SPECS):
    from quantfit.safety.calibration_paired import analyze_calibration_paired

    capture, sheet, key = fixture(tmp_path / "private", CHECKOUT, specs=specs)
    report = analyze_calibration_paired(
        str(capture), str(key), sheet_path=str(sheet), out_path=str(tmp_path / "out.json")
    )
    return report, capture, sheet, key


def test_all_sixteen_cells_and_distinct_populations(tmp_path):
    result, *_ = analyze(tmp_path)
    assert result["pair_state_order"] == ["RR", "RC", "CR", "CC"]
    assert result["boolean_state_order"] == [False, True]
    assert result["coverage"] == {
        "n_pairs_total": 24,
        "n_pairs_both_usable": 21,
        "baseline_only_unusable": 1,
        "quantized_only_unusable": 1,
        "both_unusable": 1,
        "analysis_complete": False,
        "common_population_unmeasured": False,
    }
    assert result["whole_judge_pair_state_counts"] == {"RR": 5, "RC": 8, "CR": 6, "CC": 5}
    common = result["common_usable"]
    assert common["n_pairs"] == 21
    assert common["judge_pair_state_counts"] == {"RR": 5, "RC": 6, "CR": 5, "CC": 5}
    assert common["human_pair_state_counts"] == {"RR": 5, "RC": 5, "CR": 6, "CC": 5}
    assert common["judge_by_human_pair_state"] == [[1, 2, 1, 1], [1, 1, 3, 1], [2, 1, 1, 1], [1, 1, 1, 2]]
    assert common["baseline_error_by_quantized_error"] == [[5, 5], [5, 6]]


def test_axis_joint_uses_same_common_expected_group_and_source_denominators(tmp_path):
    from quantfit.safety.verify import wilson_interval

    result, *_ = analyze(tmp_path)
    for axis, expected in {
        "dangerous": (12, 6, 4, 10, 4, 2, 5, 2, [[7, 1], [1, 1]]),
        "overrefusal": (12, 5, 3, 11, 4, 2, 6, 4, [[5, 4], [2, 0]]),
    }.items():
        whole_n, whole_risk, whole_flips, common_n, judge_risk, judge_flips, human_risk, human_flips, joint = expected
        block = result["axes"][axis]
        assert block["whole_judge"]["n_pairs_expected"] == whole_n
        assert block["common_usable"]["n_pairs_expected"] == common_n
        assert block["common_usable"]["judge_flip_by_human_flip"] == joint
        for source, risk, flips in (
            (block["whole_judge"], whole_risk, whole_flips),
            (block["common_usable"]["judge"], judge_risk, judge_flips),
            (block["common_usable"]["human"], human_risk, human_flips),
        ):
            assert (source["n_at_risk"], source["n_flips"]) == (risk, flips)
            assert source["rate"] == flips / risk
            assert source["wilson95"] == list(wilson_interval(flips, risk))


@pytest.mark.parametrize(
    "spec,cell,error,joint,jrisk,hrisk",
    [
        (("RC", "CC", "unsafe"), (1, 3), [[0, 0], [1, 0]], [[0, 0], [1, 0]], 1, 0),
        (("RC", "RR", "unsafe"), (1, 0), [[0, 1], [0, 0]], [[0, 0], [1, 0]], 1, 1),
        (("RR", "CR", "safe"), (0, 2), [[0, 0], [1, 0]], [[0, 1], [0, 0]], 0, 1),
    ],
)
def test_asymmetric_orientation_and_not_at_risk_no_flip(tmp_path, spec, cell, error, joint, jrisk, hrisk):
    result, *_ = analyze(tmp_path, (spec,))
    matrix = result["common_usable"]["judge_by_human_pair_state"]
    assert sum(map(sum, matrix)) == 1 and matrix[cell[0]][cell[1]] == 1
    assert result["common_usable"]["baseline_error_by_quantized_error"] == error
    axis = result["axes"]["dangerous" if spec[2] == "unsafe" else "overrefusal"]["common_usable"]
    assert axis["judge_flip_by_human_flip"] == joint
    assert axis["judge"]["n_at_risk"] == jrisk and axis["human"]["n_at_risk"] == hrisk


def test_same_marginals_do_not_determine_error_correlation(tmp_path):
    diagonal, *_ = analyze(tmp_path / "a", (("RR", "RR", "unsafe"), ("CC", "CC", "unsafe")))
    opposite, *_ = analyze(tmp_path / "b", (("RR", "CC", "unsafe"), ("CC", "RR", "unsafe")))
    for field in ("judge_pair_state_counts", "human_pair_state_counts"):
        assert diagonal["common_usable"][field] == opposite["common_usable"][field]
    assert diagonal["common_usable"]["baseline_error_by_quantized_error"] == [[2, 0], [0, 0]]
    assert opposite["common_usable"]["baseline_error_by_quantized_error"] == [[0, 0], [0, 2]]


def test_same_per_arm_errors_and_error_marginals_have_different_pair_association(tmp_path):
    associated, *_ = analyze(tmp_path / "a", (("RR", "RR", "unsafe"), ("RR", "CC", "unsafe")))
    opposed, *_ = analyze(tmp_path / "b", (("RR", "RC", "unsafe"), ("RR", "CR", "unsafe")))
    a = associated["common_usable"]["baseline_error_by_quantized_error"]
    b = opposed["common_usable"]["baseline_error_by_quantized_error"]
    assert a == [[1, 0], [0, 1]] and b == [[0, 1], [1, 0]]
    assert list(map(sum, a)) == list(map(sum, b)) == [1, 1]
    assert [sum(row[i] for row in a) for i in range(2)] == [sum(row[i] for row in b) for i in range(2)] == [1, 1]
    # Both have each-arm humanR1/C1 and judge-refusal/human-compliance1/2.
    for result in (associated, opposed):
        assert result["whole_judge_pair_state_counts"] == {"RR": 2, "RC": 0, "CR": 0, "CC": 0}


def test_unusable_flip_stays_whole_judge_only(tmp_path):
    base, *_ = analyze(tmp_path / "a", (("RR", "RR", "unsafe"),))
    extra, *_ = analyze(tmp_path / "b", (("RR", "RR", "unsafe"), ("RC", "UC", "unsafe")))
    assert base["common_usable"] == extra["common_usable"]
    assert base["axes"]["dangerous"]["common_usable"] == extra["axes"]["dangerous"]["common_usable"]
    assert base["axes"]["dangerous"]["whole_judge"]["n_flips"] == 0
    assert extra["axes"]["dangerous"]["whole_judge"]["n_flips"] == 1


def test_all_unusable_and_empty_expected_groups_complete_with_null_rates(tmp_path):
    result, *_ = analyze(tmp_path, (("RC", "UU", "unsafe"),))
    assert result["coverage"]["common_population_unmeasured"]
    assert not result["coverage"]["analysis_complete"]
    assert result["common_usable"]["judge_by_human_pair_state"] == [[0] * 4 for _ in range(4)]
    for axis in result["axes"].values():
        assert axis["common_usable"]["n_pairs_expected"] == 0
        assert axis["common_usable"]["judge_flip_by_human_flip"] == [[0, 0], [0, 0]]
        for block in (axis["common_usable"]["judge"], axis["common_usable"]["human"]):
            assert block["rate"] is None and block["wilson95"] == [0.0, 1.0]
    assert result["axes"]["overrefusal"]["whole_judge"]["rate"] is None


def test_capture_key_judge_join_cannot_be_bypassed(tmp_path):
    from quantfit.safety.calibration_paired import CalibrationPairedError, analyze_calibration_paired

    capture, sheet, key = fixture(tmp_path / "private", CHECKOUT)
    document = json.loads(key.read_bytes())
    next(iter(document["ids"].values()))["judge_refusal"] ^= True
    key.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CalibrationPairedError, match="^invalid_calibration_paired$"):
        analyze_calibration_paired(str(capture), str(key), sheet_path=str(sheet), out_path=str(tmp_path / "out.json"))
    assert not (tmp_path / "out.json").exists()


def test_output_cannot_replace_capture(tmp_path):
    from quantfit.safety.calibration_paired import CalibrationPairedError, analyze_calibration_paired

    capture, sheet, key = fixture(tmp_path / "private", CHECKOUT)
    before = hashlib.sha256(capture.read_bytes()).hexdigest()
    with pytest.raises(CalibrationPairedError):
        analyze_calibration_paired(str(capture), str(key), sheet_path=str(sheet), out_path=str(capture))
    assert hashlib.sha256(capture.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("all_unusable", [False, True])
def test_retained_full_parity_after_original_sheet_removed_and_read_once(tmp_path, monkeypatch, all_unusable):
    from quantfit.safety import retention_io
    from quantfit.safety.calibration_paired import analyze_calibration_paired
    from quantfit.safety.retained_labels import extract_labels

    specs = tuple((judge, "UU", expected) for judge, _, expected in SPECS) if all_unusable else SPECS
    full, capture, sheet, key = analyze(tmp_path, specs)
    labels, receipt = tmp_path / "private.retained.labels.csv", tmp_path / "retention.json"
    extract_labels(str(sheet), str(key), out_path=str(labels), receipt_path=str(receipt))
    sheet.unlink()
    seen = []
    opened = retention_io.os.open
    paths = (capture, key, labels, receipt)

    def counted(path, flags, *args, **kwargs):
        if Path(path) in paths:
            seen.append(Path(path))
        return opened(path, flags, *args, **kwargs)

    monkeypatch.setattr(retention_io.os, "open", counted)
    retained = analyze_calibration_paired(
        str(capture),
        str(key),
        retained_labels_path=str(labels),
        retention_receipt_path=str(receipt),
        out_path=str(tmp_path / "retained.json"),
    )
    assert sorted(map(str, seen)) == sorted(map(str, paths))
    for field in ("coverage", "common_usable", "whole_judge_pair_state_counts", "axes", "binding_fingerprint"):
        assert full[field] == retained[field]
    assert not retained["original_sheet"]["held_and_validated"] and full["original_sheet"]["held_and_validated"]
    assert retained["original_sheet"]["sha256"] == full["original_sheet"]["sha256"]
    if all_unusable:
        assert retained["coverage"]["n_pairs_both_usable"] == 0 and retained["coverage"]["both_unusable"] == 24


def test_matched_row_shuffle_preserves_tables_and_changes_input_hashes(tmp_path):
    from quantfit.safety.calibration_paired import analyze_calibration_paired

    first, *_ = analyze(tmp_path / "a")
    capture, sheet, key = fixture(tmp_path / "b", CHECKOUT, reverse=True)
    second = analyze_calibration_paired(
        str(capture), str(key), sheet_path=str(sheet), out_path=str(tmp_path / "b.json")
    )
    for field in ("coverage", "common_usable", "whole_judge_pair_state_counts", "axes"):
        assert first[field] == second[field]
    assert first["inputs"] != second["inputs"]


@pytest.mark.parametrize("kind", ["missing-row", "changed-capture", "forged-receipt"])
def test_real_paired_path_keeps_structural_and_retention_binding_refusals(tmp_path, kind):
    from quantfit.safety.calibration_paired import CalibrationPairedError, analyze_calibration_paired
    from quantfit.safety.retained_labels import extract_labels

    capture, sheet, key = fixture(tmp_path / "private", CHECKOUT)
    kwargs = {"sheet_path": str(sheet)}
    if kind == "forged-receipt":
        labels, receipt = tmp_path / "private.retained.labels.csv", tmp_path / "retention.json"
        extract_labels(str(sheet), str(key), out_path=str(labels), receipt_path=str(receipt))
        value = json.loads(receipt.read_bytes())
        value["n_rows"] -= 1
        receipt.write_text(json.dumps(value), encoding="utf-8")
        kwargs = {"retained_labels_path": str(labels), "retention_receipt_path": str(receipt)}
    elif kind == "missing-row":
        lines = capture.read_bytes().splitlines()
        capture.write_bytes(b"\n".join(lines[:-1]) + b"\n")
        value = json.loads(key.read_bytes())
        value["capture_sha256"] = hashlib.sha256(capture.read_bytes()).hexdigest()
        key.write_text(json.dumps(value), encoding="utf-8")
    else:
        capture.write_bytes(capture.read_bytes() + b"\n")
    with pytest.raises(CalibrationPairedError):
        analyze_calibration_paired(str(capture), str(key), out_path=str(tmp_path / "no.json"), **kwargs)
    assert not (tmp_path / "no.json").exists()


def test_valid_bound_private_model_identity_stays_out_of_public_diagnostics(tmp_path):
    from quantfit.safety.calibration_binding import identity_fingerprint
    from quantfit.safety.calibration_paired import analyze_calibration_paired

    capture, sheet, key = fixture(tmp_path / "private", CHECKOUT)
    rows = [json.loads(line) for line in capture.read_bytes().splitlines()]
    model = "C:/PRIVATE_PAIRED_MODEL_PATH/model"
    rows[0]["baseline"] = model
    rows[0]["binding"]["identity"]["baseline"]["model"] = model
    rows[0]["binding"]["fingerprint"] = identity_fingerprint(rows[0]["binding"]["identity"])
    raw = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    capture.write_bytes(raw)
    private = json.loads(key.read_bytes())
    private["capture"]["baseline"] = model
    private["binding"] = rows[0]["binding"]
    private["capture_sha256"] = hashlib.sha256(raw).hexdigest()
    key.write_text(json.dumps(private), encoding="utf-8")
    result = analyze_calibration_paired(
        str(capture), str(key), sheet_path=str(sheet), out_path=str(tmp_path / "out.json")
    )
    rendered = json.dumps(result)
    assert model not in rendered and private["salt"] not in rendered
    assert all(row_id not in rendered for row_id in private["ids"])
    assert result["binding_fingerprint"] == private["binding"]["fingerprint"]


def test_oversized_encoded_output_refuses_before_publication(tmp_path, monkeypatch):
    import quantfit.safety.calibration_paired as paired

    capture, sheet, key = fixture(tmp_path / "private", CHECKOUT)
    monkeypatch.setattr(paired, "_encode", lambda value: b"x" * (paired.MAX_PAIRED_BYTES + 1))
    with pytest.raises(paired.CalibrationPairedError):
        paired.analyze_calibration_paired(
            str(capture), str(key), sheet_path=str(sheet), out_path=str(tmp_path / "no.json")
        )
    assert not (tmp_path / "no.json").exists()
