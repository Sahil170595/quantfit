"""Descriptive cohort denominators and exact native capture/key admission."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("strata_fixture", ROOT / "tools/ci_calibration_strata.py")
assert SPEC and SPEC.loader
fixture_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture_module)


def api():
    from quantfit.safety.calibration_strata import analyze_calibration_strata

    return analyze_calibration_strata


def run(paths, out, **kwargs):
    capture, sheet, key = paths
    return api()(str(capture), str(key), sheet_path=str(sheet), out_path=str(out), **kwargs)


def test_independent_zone_and_at_risk_cell_counts_preserve_native_wilson_denominators(tmp_path):
    from quantfit.safety.verify import wilson_interval

    paths = fixture_module.fixture(tmp_path / "private", ROOT)
    result = run(paths, tmp_path / "strata.json")
    assert result["n_pairs"] == 8 and result["n_rows"] == 16
    # Independently enumerated n, unusable, humanR, humanC, JRhC, JChR.
    expected = {
        "all": ((6, 2, 3, 3, 2, 2), (6, 2, 3, 3, 2, 1)),
        "clear_safe": ((2, 0, 1, 1, 0, 0), (1, 1, 1, 0, 0, 0)),
        "clear_unsafe": ((2, 0, 1, 1, 1, 1), (2, 0, 1, 1, 0, 0)),
        "borderline": ((2, 2, 1, 1, 1, 1), (3, 1, 1, 2, 2, 1)),
    }
    for zone, arms in expected.items():
        group = result["all_rows"] if zone == "all" else result["all_rows"]["zones"][zone]
        for arm, counts in zip(("baseline", "quantized"), arms, strict=True):
            n, _unusable, refusal, compliance, rhc, chr_ = counts
            block = group["arms"][arm]
            assert (
                block["n"],
                block["n_unusable"],
                block["human_refusals"],
                block["human_compliances"],
                block["direction"]["judge_refusal_human_compliance"],
                block["direction"]["judge_compliance_human_refusal"],
            ) == counts
            assert block["epsilon_wilson95"] == list(wilson_interval(rhc + chr_, n))
            assert block["directional"]["false_compliance"]["n"] == refusal
            assert block["directional"]["false_refusal"]["n"] == compliance
    dangerous = result["observed_at_risk"]["dangerous"]
    over = result["observed_at_risk"]["overrefusal"]
    assert dangerous["n_pairs_selected"] == over["n_pairs_selected"] == 2
    assert (dangerous["arms"]["baseline"]["n"], dangerous["arms"]["baseline"]["n_unusable"]) == (1, 1)
    assert (dangerous["arms"]["quantized"]["n"], dangerous["arms"]["quantized"]["n_unusable"]) == (2, 0)
    assert (over["arms"]["baseline"]["n"], over["arms"]["quantized"]["n_unusable"]) == (2, 1)
    assert dangerous["zones"]["clear_safe"]["n_pairs_selected"] == 0
    assert dangerous["zones"]["borderline"]["n_pairs_selected"] == 1  # expected unsafe remains valid
    assert over["zones"]["borderline"]["n_pairs_selected"] == 1  # expected safe, same zone
    assert json.loads((tmp_path / "strata.json").read_bytes()) == result
    assert result["scientific_go"] is result["replaces_calibration"] is False
    rendered = json.dumps(result)
    private = json.loads(paths[2].read_bytes())
    assert fixture_module.MARKER not in rendered and private["salt"] not in rendered
    assert all(row_id not in rendered for row_id in private["ids"])
    assert all(str(path) not in rendered for path in paths)


@pytest.mark.parametrize("mode", ["unusable", "empty-cohorts"])
def test_empty_or_all_unusable_diagnostics_complete_with_null_and_native_full_interval(tmp_path, mode):
    paths = fixture_module.fixture(
        tmp_path / "private", ROOT, all_unusable=mode == "unusable", no_at_risk=mode == "empty-cohorts"
    )
    result = run(paths, tmp_path / "strata.json")
    group = result["all_rows"] if mode == "unusable" else result["observed_at_risk"]["dangerous"]
    for block in group["arms"].values():
        assert block["n"] == 0 and block["epsilon"] is None and block["epsilon_wilson95"] == [0, 1]
    assert group["unmeasured_arms"] == ["baseline", "quantized"]


def test_retained_and_full_inputs_have_equal_statistics_and_honest_different_provenance(tmp_path):
    from quantfit.safety.retained_labels import extract_labels

    paths = fixture_module.fixture(tmp_path / "private", ROOT)
    full = run(paths, tmp_path / "full.json")
    capture, sheet, key = paths
    labels, receipt = tmp_path / "private.retained.labels.csv", tmp_path / "retention.json"
    extract_labels(str(sheet), str(key), out_path=str(labels), receipt_path=str(receipt))
    sheet.unlink()
    retained = api()(
        str(capture),
        str(key),
        retained_labels_path=str(labels),
        retention_receipt_path=str(receipt),
        out_path=str(tmp_path / "retained.json"),
    )
    for field in ("n_pairs", "n_rows", "all_rows", "observed_at_risk", "binding_fingerprint"):
        assert full[field] == retained[field]
    assert full["original_sheet"]["held_and_validated"] is True
    assert retained["original_sheet"]["held_and_validated"] is False
    assert full["original_sheet"]["sha256"] == retained["original_sheet"]["sha256"]


@pytest.mark.parametrize(
    "mutation",
    [
        "key-judge",
        "capture-sha",
        "header",
        "binding",
        "text",
        "zone",
        "expected",
        "cross-arm",
        "missing-row",
        "duplicate-row",
        "legacy-key",
        "huge-n",
        "duplicate-json",
        "huge-token",
    ],
)
def test_full_capture_key_and_metadata_admission_refuses_before_output(tmp_path, mutation):
    paths = fixture_module.fixture(tmp_path / "private", ROOT)
    capture, _, key = paths
    k = json.loads(key.read_bytes())
    rows = [json.loads(line) for line in capture.read_bytes().splitlines()]
    if mutation == "key-judge":
        k["ids"][next(iter(k["ids"]))]["judge_refusal"] ^= True
    elif mutation == "capture-sha":
        k["capture_sha256"] = "0" * 64
    elif mutation == "header":
        k["capture"]["created_utc"] = "different"
    elif mutation == "binding":
        k["binding"] = None
    elif mutation == "legacy-key":
        k["key_schema"] = 1
    elif mutation == "huge-n":
        rows[0]["n_pairs"] = 10**12
    elif mutation == "text":
        rows[1]["completion"] += "PRIVATE_CHANGED"
    elif mutation == "zone":
        rows[1]["zone"] = "PRIVATE_ZONE"
    elif mutation == "expected":
        rows[1]["expected"] = "PRIVATE_EXPECTED"
    elif mutation == "cross-arm":
        rows[1]["zone"] = "borderline"
    elif mutation == "missing-row":
        rows.pop()
    elif mutation == "duplicate-row":
        rows.append(rows[-1])
    raw = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    if mutation == "duplicate-json":
        raw = raw.replace(b'"capture_schema": 2', b'"capture_schema": 2, "capture_schema": 2')
    elif mutation == "huge-token":
        raw = raw.replace(b'"capture_schema": 2', b'"capture_schema": 2, "unused": ' + b"9" * 1000)
    if mutation not in {"key-judge", "capture-sha", "header", "binding", "legacy-key"}:
        import hashlib

        k["capture_sha256"] = hashlib.sha256(raw).hexdigest()  # test inner admission, not only SHA refusal
    capture.write_bytes(raw)
    key.write_bytes(json.dumps(k).encode())
    out = tmp_path / "must-not-exist.json"
    with pytest.raises(RuntimeError, match="invalid_calibration_strata") as error:
        run(paths, out)
    assert not out.exists() and error.value.__cause__ is None and "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("schema,bound", [(1, True), (2, False)])
def test_native_unbound_capture_combinations_remain_explicitly_unbound(tmp_path, schema, bound):
    paths = fixture_module.fixture(tmp_path / "private", ROOT, capture_schema=schema, bound=bound)
    result = run(paths, tmp_path / "strata.json")
    assert result["binding_fingerprint"] is None and result["n_rows"] == 16


def test_regenerated_capture_bytes_refuse_old_key_even_when_rows_identical(tmp_path):
    paths = fixture_module.fixture(tmp_path / "private", ROOT)
    paths[0].write_bytes(paths[0].read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="invalid_calibration_strata"):
        run(paths, tmp_path / "no.json")


def test_row_shuffle_changes_bindings_but_not_descriptive_statistics(tmp_path):
    a = run(fixture_module.fixture(tmp_path / "one", ROOT), tmp_path / "a.json")
    b = run(fixture_module.fixture(tmp_path / "two", ROOT, reverse=True), tmp_path / "b.json")
    assert a["all_rows"] == b["all_rows"] and a["observed_at_risk"] == b["observed_at_risk"]
    assert a["inputs"] != b["inputs"]


@pytest.mark.parametrize("kind", ["huge-n", "blank-lf", "blank-unicode"])
def test_capture_work_caps_precede_native_population_allocation(tmp_path, monkeypatch, kind):
    import hashlib
    from unittest.mock import Mock

    paths = fixture_module.fixture(tmp_path / "private", ROOT)
    raw = paths[0].read_bytes()
    if kind == "huge-n":
        rows = [json.loads(line) for line in raw.splitlines()]
        rows[0]["n_pairs"] = 10**12
        raw = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    else:
        raw += (("\n" if kind == "blank-lf" else "\u2028") * 16385).encode()
    paths[0].write_bytes(raw)
    key = json.loads(paths[2].read_bytes())
    key["capture_sha256"] = hashlib.sha256(raw).hexdigest()
    paths[2].write_bytes(json.dumps(key).encode())
    sdk = Mock(side_effect=AssertionError("native parser before bounded admission"))
    monkeypatch.setattr("quantfit.safety.calibrate._read_capture", sdk)
    with pytest.raises(RuntimeError, match="invalid_calibration_strata"):
        run(paths, tmp_path / "no.json")
    sdk.assert_not_called()


@pytest.mark.parametrize("token", ['{"x":1,"x":2}', "NaN", "1." + "0" * 1000])
def test_every_capture_body_is_strictly_validated_even_when_all_labels_unusable(tmp_path, monkeypatch, token):
    import hashlib
    from unittest.mock import Mock

    paths = fixture_module.fixture(tmp_path / "private", ROOT, all_unusable=True)
    lines = paths[0].read_bytes().splitlines()
    lines[1] = lines[1][:-1] + b', "unused_nested": ' + token.encode() + b"}"
    raw = b"\n".join(lines) + b"\n"
    paths[0].write_bytes(raw)
    key = json.loads(paths[2].read_bytes())
    key["capture_sha256"] = hashlib.sha256(raw).hexdigest()
    paths[2].write_bytes(json.dumps(key).encode())
    sdk = Mock(side_effect=AssertionError("native parser before strict body admission"))
    monkeypatch.setattr("quantfit.safety.calibrate._read_capture", sdk)
    with pytest.raises(RuntimeError, match="invalid_calibration_strata"):
        run(paths, tmp_path / "no.json")
    sdk.assert_not_called()


def test_complete_at_risk_count_tuples_and_directional_wilson_use_only_selected_pairs(tmp_path):
    from quantfit.safety.verify import wilson_interval

    result = run(fixture_module.fixture(tmp_path / "private", ROOT), tmp_path / "out.json")
    expected = {
        "dangerous": ((1, 1, 0, 1, 1, 0), (2, 0, 0, 2, 1, 0)),
        "overrefusal": ((2, 0, 1, 1, 0, 1), (1, 1, 1, 0, 0, 0)),
    }
    for cohort, arms in expected.items():
        for arm, counts in zip(("baseline", "quantized"), arms, strict=True):
            n, _u, r, c, rhc, chr_ = counts
            block = result["observed_at_risk"][cohort]["arms"][arm]
            assert (
                block["n"],
                block["n_unusable"],
                block["human_refusals"],
                block["human_compliances"],
                block["direction"]["judge_refusal_human_compliance"],
                block["direction"]["judge_compliance_human_refusal"],
            ) == counts
            assert block["epsilon_wilson95"] == list(wilson_interval(rhc + chr_, n))
            assert block["directional"]["false_refusal"]["epsilon_wilson95"] == list(wilson_interval(rhc, c))
            assert block["directional"]["false_compliance"]["epsilon_wilson95"] == list(wilson_interval(chr_, r))


def test_each_private_input_is_held_once_and_existing_output_alias_is_preserved(tmp_path, monkeypatch):
    from quantfit.safety import retention_io

    paths = fixture_module.fixture(tmp_path / "private", ROOT)
    seen = []
    original = retention_io.os.open

    def opened(path, flags, *args, **kwargs):
        if Path(path) in paths:
            seen.append(Path(path))
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(retention_io.os, "open", opened)
    run(paths, tmp_path / "out.json")
    assert sorted(map(str, seen)) == sorted(map(str, paths))
    before = paths[0].read_bytes()
    with pytest.raises(RuntimeError, match="invalid_calibration_strata"):
        run(paths, paths[0])
    assert paths[0].read_bytes() == before


def test_public_diagnostic_never_echoes_valid_bound_private_model_identity(tmp_path):
    import hashlib

    from quantfit.safety.calibration_binding import identity_fingerprint

    paths = fixture_module.fixture(tmp_path / "private", ROOT)
    rows = [json.loads(line) for line in paths[0].read_bytes().splitlines()]
    model = "C:/PRIVATE_STRATA_MODEL_PATH/model"
    rows[0]["baseline"] = model
    rows[0]["binding"]["identity"]["baseline"]["model"] = model
    rows[0]["binding"]["fingerprint"] = identity_fingerprint(rows[0]["binding"]["identity"])
    raw = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    paths[0].write_bytes(raw)
    key = json.loads(paths[2].read_bytes())
    key["capture"]["baseline"] = model
    key["binding"] = rows[0]["binding"]
    key["capture_sha256"] = hashlib.sha256(raw).hexdigest()
    paths[2].write_bytes(json.dumps(key).encode())
    result = run(paths, tmp_path / "out.json")
    assert model not in json.dumps(result) and result["binding_fingerprint"] == key["binding"]["fingerprint"]


def test_retained_all_unusable_after_sheet_removal_is_complete_diagnostic_not_ingest_refusal(tmp_path):
    from quantfit.safety.retained_labels import extract_labels

    paths = fixture_module.fixture(tmp_path / "private", ROOT, all_unusable=True)
    capture, sheet, key = paths
    labels = tmp_path / "retained.labels.csv"
    receipt = tmp_path / "retention.json"
    extract_labels(str(sheet), str(key), out_path=str(labels), receipt_path=str(receipt))
    sheet.unlink()
    result = api()(
        str(capture),
        str(key),
        retained_labels_path=str(labels),
        retention_receipt_path=str(receipt),
        out_path=str(tmp_path / "strata.json"),
    )
    assert result["n_rows"] == 16 and result["all_rows"]["n_pairs_selected"] == 8
    for block in result["all_rows"]["arms"].values():
        assert (
            block["n"] == 0
            and block["n_unusable"] == 8
            and block["epsilon"] is None
            and block["epsilon_wilson95"] == [0, 1]
        )


@pytest.mark.parametrize("field", ["created_utc", "baseline", "quant"])
def test_missing_native_header_metadata_is_not_accepted_as_none_equals_none(tmp_path, field):
    import hashlib

    paths = fixture_module.fixture(tmp_path / "private", ROOT, bound=False)
    rows = [json.loads(line) for line in paths[0].read_bytes().splitlines()]
    del rows[0][field]
    raw = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    paths[0].write_bytes(raw)
    key = json.loads(paths[2].read_bytes())
    key["capture"][field] = None
    key["capture_sha256"] = hashlib.sha256(raw).hexdigest()
    paths[2].write_bytes(json.dumps(key).encode())
    with pytest.raises(RuntimeError, match="invalid_calibration_strata"):
        run(paths, tmp_path / "no.json")


def test_forged_retention_receipt_is_refused_by_actual_diagnostic_path(tmp_path):
    from quantfit.safety.retained_labels import extract_labels

    capture, sheet, key = fixture_module.fixture(tmp_path / "private", ROOT)
    labels = tmp_path / "retained.labels.csv"
    receipt = tmp_path / "retention.json"
    extract_labels(str(sheet), str(key), out_path=str(labels), receipt_path=str(receipt))
    document = json.loads(receipt.read_bytes())
    document["n_rows"] -= 1
    receipt.write_bytes(json.dumps(document).encode())
    out = tmp_path / "no.json"
    with pytest.raises(RuntimeError, match="invalid_calibration_strata"):
        api()(
            str(capture),
            str(key),
            retained_labels_path=str(labels),
            retention_receipt_path=str(receipt),
            out_path=str(out),
        )
    assert not out.exists()
