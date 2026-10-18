"""Descriptive synthetic label counts; no human truth, consensus or calibration study."""

import csv
import hashlib
import io
import json
import os

import pytest

from quantfit.safety import calibrate


def fixture(tmp_path, *, n=9, schema=2, all_unusable=False, bom=False, multiline=False):
    salt = "PRIVATE_KEY_SALT_SENTINEL"
    labels = calibrate.HUMAN_LABELS
    ids, a, b = {}, [], []
    for pair in range(n):
        for arm in calibrate.ARMS:
            row_id = calibrate._row_id(salt, pair, arm)
            completion = f"PRIVATE_COMPLETION_SENTINEL {pair} {arm}"
            if multiline:
                completion += '\nquoted, "second line"\r\nthird line'
            ids[row_id] = {
                "pair": pair,
                "arm": arm,
                "judge_refusal": pair % 2 == 0,
                "completion_sha256": calibrate._completion_sha256(completion),
            }
            label_a = labels[(pair // 3) % 3] if arm == "baseline" else "refusal"
            label_b = labels[pair % 3] if arm == "baseline" else "compliance"
            a.append([row_id, completion, "unusable" if all_unusable else label_a])
            b.append([row_id, completion, "unusable" if all_unusable else label_b])
    key = {
        "key_schema": schema,
        "salt": salt,
        "capture": {"n_pairs": n, "baseline": "synthetic/base", "quant": "synthetic/quant"},
        "ids": ids,
    }
    if schema == 2:
        key.update(binding=None, capture_sha256="a" * 64)
    key_path, sheet_a, sheet_b = (tmp_path / name for name in ("private-key.json", "private-a.csv", "private-b.csv"))
    key_path.write_bytes((json.dumps(key, indent=3) + "\r\n").encode())
    write_sheet(sheet_a, a, bom=bom)
    write_sheet(sheet_b, list(reversed(b)), bom=bom)
    return sheet_a, sheet_b, key_path


def write_sheet(path, rows, *, bom=False):
    buffer = io.StringIO(newline="")
    csv.writer(buffer).writerows([calibrate.SHEET_COLUMNS, *rows])
    path.write_bytes(buffer.getvalue().encode("utf-8-sig" if bom else "utf-8"))


def api(*args, **kwargs):
    from quantfit.safety.reconcile import reconcile_labels

    return reconcile_labels(*(str(path) for path in args), **kwargs)


def test_matrices_keep_rater_direction_arm_counts_and_original_byte_bindings(tmp_path):
    a, b, key = fixture(tmp_path)
    originals = {path: path.read_bytes() for path in (a, b, key)}
    result = api(a, b, key, out_path=str(tmp_path / "aggregate.json"))
    assert result["label_order"] == ["refusal", "compliance", "unusable"]
    assert result["n_pairs"] == 9 and result["n_rows"] == 18
    assert result["arms"]["baseline"] == {
        "matrix": [[1, 1, 1], [1, 1, 1], [1, 1, 1]],
        "n_rows": 9,
        "n_both_usable": 4,
        "n_usable_agreement": 2,
        "n_usable_disagreement": 2,
        "n_one_unusable": 4,
        "n_both_unusable": 1,
        "usable_agreement_rate": 0.5,
    }
    assert result["arms"]["quantized"] == {
        "matrix": [[0, 9, 0], [0, 0, 0], [0, 0, 0]],
        "n_rows": 9,
        "n_both_usable": 9,
        "n_usable_agreement": 0,
        "n_usable_disagreement": 9,
        "n_one_unusable": 0,
        "n_both_unusable": 0,
        "usable_agreement_rate": 0.0,
    }
    for role, path in (("sheet_a", a), ("sheet_b", b), ("key", key)):
        assert result["inputs"][role] == {
            "sha256": hashlib.sha256(originals[path]).hexdigest(),
            "size_bytes": len(originals[path]),
        }
    assert all(path.read_bytes() == raw for path, raw in originals.items())
    assert json.loads((tmp_path / "aggregate.json").read_bytes()) == result
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("schema,bom,multiline", [(1, False, False), (2, True, True)])
def test_existing_legacy_bom_and_multiline_rules_are_reused(tmp_path, schema, bom, multiline):
    a, b, key = fixture(tmp_path, schema=schema, bom=bom, multiline=multiline)
    result = api(a, b, key)
    assert result["arms"]["baseline"]["matrix"] == [[1, 1, 1], [1, 1, 1], [1, 1, 1]]


@pytest.mark.parametrize("same", [False, True])
def test_all_unusable_or_identical_sheet_remains_descriptive_with_null_rate(tmp_path, same):
    a, b, key = fixture(tmp_path, all_unusable=True)
    if same:
        b = a
    result = api(a, b, key)
    assert result["identical_sheet_bytes"] is same
    for block in result["arms"].values():
        assert block["matrix"] == [[0, 0, 0], [0, 0, 0], [0, 0, 9]]
        assert block["usable_agreement_rate"] is None and block["n_both_unusable"] == 9
    assert result["independence_verified"] is result["consensus_calibration"] is result["scientific_go"] is False


@pytest.mark.parametrize("mutation", ["negative", "single_arm", "huge_capture", "bool_capture"])
def test_new_population_preflight_refuses_old_unbound_key_gap_before_sdk(tmp_path, monkeypatch, mutation):
    from quantfit.safety.reconcile import LabelReconciliationError

    a, b, key = fixture(tmp_path, n=1, schema=1)
    payload = json.loads(key.read_bytes())
    if mutation == "negative":
        entry = next(iter(payload["ids"].values()))
        entry["pair"] = -1
        payload["ids"] = {calibrate._row_id(payload["salt"], -1, entry["arm"]): entry}
    elif mutation == "single_arm":
        payload["ids"] = {row_id: entry for row_id, entry in payload["ids"].items() if entry["arm"] == "baseline"}
    else:
        payload["capture"]["n_pairs"] = 10**10 if mutation == "huge_capture" else True
    if mutation in ("negative", "single_arm"):
        assert calibrate._read_key("private", data=json.dumps(payload).encode())["ids"]
    key.write_text(json.dumps(payload), encoding="utf-8")
    calls = []
    monkeypatch.setattr(calibrate, "_read_key", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(LabelReconciliationError):
        api(a, b, key)
    assert calls == []


def test_csv_record_guard_stops_before_retaining_or_reading_after_first_excess(monkeypatch):
    visited = []

    def records(*args):
        for record in (list(calibrate.SHEET_COLUMNS), ["id", "private", "refusal"], [], []):
            visited.append(record)
            yield record
        pytest.fail("reader continued after first excess record")

    monkeypatch.setattr(csv, "reader", records)
    with pytest.raises(calibrate.CalibrationError, match="record limit"):
        calibrate._read_sheet("private", data=b"held", max_records=3)
    assert len(visited) == 4


def test_valid_bound_key_uses_existing_binding_and_capture_match(tmp_path):
    from test_calibration_binding import report_fixture

    from quantfit.safety.calibration_binding import identity_fingerprint, measurement_identity

    a, b, key = fixture(tmp_path)
    payload = json.loads(key.read_bytes())
    identity = measurement_identity(report_fixture(n=9))
    payload["binding"] = {"identity": identity, "fingerprint": identity_fingerprint(identity)}
    payload["capture"].update(baseline="base", quant="quant")
    key.write_text(json.dumps(payload), encoding="utf-8")
    assert api(a, b, key)["n_pairs"] == 9
    payload["capture"]["baseline"] = "PRIVATE_WRONG_CAPTURE"
    key.write_text(json.dumps(payload), encoding="utf-8")
    from quantfit.safety.reconcile import LabelReconciliationError

    with pytest.raises(LabelReconciliationError) as error:
        api(a, b, key)
    assert str(error.value) == error.value.category == "invalid_key"


def test_large_stored_bound_population_never_expands_sdk_range(tmp_path, monkeypatch):
    from test_calibration_binding import report_fixture

    from quantfit.safety.calibration_binding import identity_fingerprint, measurement_identity
    from quantfit.safety.reconcile import LabelReconciliationError

    a, b, key = fixture(tmp_path, n=1)
    payload = json.loads(key.read_bytes())
    identity = measurement_identity(report_fixture(n=10**10))
    payload["binding"] = {"identity": identity, "fingerprint": identity_fingerprint(identity)}
    key.write_text(json.dumps(payload), encoding="utf-8")

    def forbidden_range(*args):
        pytest.fail("SDK expanded a mismatched bound population")

    monkeypatch.setattr(calibrate, "range", forbidden_range, raising=False)
    with pytest.raises(LabelReconciliationError, match="invalid_key"):
        api(a, b, key)


@pytest.mark.parametrize("mutation", ["duplicate", "nonfinite", "overflow", "malformed", "array"])
def test_strict_syntax_preflight_rejects_before_sdk_without_aggregate_privacy_filter(tmp_path, monkeypatch, mutation):
    from quantfit.safety.reconcile import LabelReconciliationError

    a, b, key = fixture(tmp_path)
    original = key.read_bytes()
    if mutation == "duplicate":
        raw = original.replace(b'"key_schema": 2', b'"key_schema": 2,"key_schema": 2')
    elif mutation == "nonfinite":
        raw = original[:-3] + b',"PRIVATE":NaN}'
    elif mutation == "overflow":
        raw = original[:-3] + b',"PRIVATE":1e999}'
    else:
        raw = b'{"PRIVATE":' if mutation == "malformed" else b"[]"
    key.write_bytes(raw)
    monkeypatch.setattr(calibrate, "_read_key", lambda *args, **kwargs: pytest.fail("SDK received invalid preflight"))
    with pytest.raises(LabelReconciliationError) as error:
        api(a, b, key)
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "blank", "unknown", "edited", "header", "salt"])
def test_sdk_row_key_and_text_refusals_are_categorical_and_preserve_existing_output(tmp_path, mutation):
    from quantfit.safety.reconcile import LabelReconciliationError

    a, b, key = fixture(tmp_path)
    rows = list(csv.reader(io.StringIO(b.read_text(), newline="")))
    if mutation == "duplicate":
        rows.append(rows[1])
    elif mutation == "missing":
        rows.pop()
    elif mutation in ("blank", "unknown"):
        rows[1][2] = "" if mutation == "blank" else "PRIVATE_UNKNOWN_LABEL"
    elif mutation == "edited":
        rows[1][1] += " PRIVATE_EDIT"
    elif mutation == "header":
        rows[0][1] = "PRIVATE_HEADER"
    else:
        payload = json.loads(key.read_bytes())
        payload["salt"] = "PRIVATE_CHANGED_SALT"
        key.write_text(json.dumps(payload), encoding="utf-8")
    buffer = io.StringIO(newline="")
    csv.writer(buffer).writerows(rows)
    b.write_bytes(buffer.getvalue().encode())
    originals = {path: path.read_bytes() for path in (a, b, key)}
    out = tmp_path / "aggregate.json"
    out.write_bytes(b"old aggregate")
    with pytest.raises(LabelReconciliationError) as error:
        api(a, b, key, out_path=str(out))
    assert str(error.value) == error.value.category and "PRIVATE" not in str(error.value)
    assert out.read_bytes() == b"old aggregate" and all(path.read_bytes() == raw for path, raw in originals.items())


def test_real_csv_field_error_is_private_and_does_not_change_global_field_limit(tmp_path):
    from quantfit.safety.reconcile import LabelReconciliationError

    a, b, key = fixture(tmp_path, n=1)
    field_limit = csv.field_size_limit()
    a.write_bytes(b"id,completion,human_label\r\nid," + b"P" * (field_limit + 1) + b",refusal\r\n")
    with pytest.raises(LabelReconciliationError, match="invalid_sheet"):
        api(a, b, key)
    assert csv.field_size_limit() == field_limit


def test_actual_maximum_population_and_ids_are_bounded_and_accepted(tmp_path):
    a, b, key = fixture(tmp_path, n=4096)
    result = api(a, b, key)
    assert result["n_pairs"] == 4096 and result["n_rows"] == 8192
    assert all(block["n_rows"] == 4096 for block in result["arms"].values())


def test_record_cap_counts_header_and_blank_exports_while_old_default_remains_unbounded(tmp_path):
    from quantfit.safety.reconcile import LabelReconciliationError

    a, b, key = fixture(tmp_path, n=1)
    original = a.read_bytes()
    a.write_bytes(original + b"\r\n" * (16385 - 3))
    assert api(a, b, key)["n_pairs"] == 1
    a.write_bytes(a.read_bytes() + b"\r\n")
    with pytest.raises(LabelReconciliationError, match="invalid_sheet"):
        api(a, b, key)
    ids = calibrate._read_key("key", data=key.read_bytes())["ids"]
    assert len(calibrate._join("a", "key", ids, data=a.read_bytes())) == 2


@pytest.mark.parametrize("bound", ["key", "sheet", "total"])
def test_logical_byte_limits_refuse_without_sdk_or_private_error(tmp_path, monkeypatch, bound):
    from quantfit.safety import reconcile

    a, b, key = fixture(tmp_path)
    sizes = {path: len(path.read_bytes()) for path in (a, b, key)}
    if bound == "key":
        monkeypatch.setattr(reconcile, "MAX_KEY_BYTES", sizes[key] - 1)
    elif bound == "sheet":
        monkeypatch.setattr(reconcile, "MAX_SHEET_BYTES", min(sizes[a], sizes[b]) - 1)
    else:
        monkeypatch.setattr(reconcile, "MAX_TOTAL_INPUT_BYTES", sum(sizes.values()) - 1)
    monkeypatch.setattr(calibrate, "_read_key", lambda *args, **kwargs: pytest.fail("SDK before bounded capture"))
    with pytest.raises(reconcile.LabelReconciliationError) as error:
        api(a, b, key)
    assert "PRIVATE" not in str(error.value)


def test_exact_total_bytes_and_repeated_sheet_occurrences_are_charged_with_one_read(tmp_path, monkeypatch):
    from quantfit.safety import reconcile

    a, _, key = fixture(tmp_path)
    needed = 2 * len(a.read_bytes()) + len(key.read_bytes())
    read, calls = reconcile._read, []

    def once(path, limit):
        assert path not in calls
        calls.append(path)
        return read(path, limit)

    monkeypatch.setattr(reconcile, "_read", once)
    monkeypatch.setattr(reconcile, "MAX_TOTAL_INPUT_BYTES", needed)
    result = api(a, a, key)
    assert result["identical_sheet_bytes"] is True and calls == [a, key]
    monkeypatch.setattr(reconcile, "MAX_TOTAL_INPUT_BYTES", needed - 1)
    calls.clear()
    with pytest.raises(reconcile.LabelReconciliationError):
        api(a, a, key)


@pytest.mark.parametrize("sink", ["a", "b", "key", "hardlink", "missing_parent", "directory"])
def test_output_protection_precedes_any_input_read(tmp_path, monkeypatch, sink):
    from quantfit.safety import reconcile

    a, b, key = fixture(tmp_path)
    out = {
        "a": a,
        "b": b,
        "key": key,
        "hardlink": tmp_path / "alias",
        "missing_parent": tmp_path / "absent/out",
        "directory": tmp_path,
    }[sink]
    if sink == "hardlink":
        os.link(key, out)
    monkeypatch.setattr(reconcile, "_read", lambda *args: pytest.fail("read before unsafe output refusal"))
    with pytest.raises(reconcile.LabelReconciliationError, match="unsafe_output"):
        api(a, b, key, out_path=str(out))


def test_original_buffers_are_held_once_and_published_without_private_source_rereads(tmp_path, monkeypatch):
    from quantfit.safety import reconcile

    a, b, key = fixture(tmp_path)
    originals = {path: path.read_bytes() for path in (a, b, key)}
    read, calls = reconcile._read, []

    def once(path, limit):
        assert path not in calls
        calls.append(path)
        raw = read(path, limit)
        if len(calls) == 3:
            for source in originals:
                source.unlink()
        return raw

    monkeypatch.setattr(reconcile, "_read", once)
    monkeypatch.setattr(calibrate, "_artifact_bytes", lambda *args: pytest.fail("private source reopened"))
    out = tmp_path / "public-aggregate.json"
    result = api(a, b, key, out_path=str(out))
    assert calls == [a, b, key]
    assert json.loads(out.read_bytes()) == result and "PRIVATE" not in out.read_text()
    for role, source in (("sheet_a", a), ("sheet_b", b), ("key", key)):
        assert result["inputs"][role]["sha256"] == hashlib.sha256(originals[source]).hexdigest()


def test_late_output_alias_is_refused_without_overwriting_private_input(tmp_path, monkeypatch):
    from quantfit.safety import reconcile

    a, b, key = fixture(tmp_path)
    out = tmp_path / "aggregate.json"
    out.write_bytes(b"old aggregate")
    original = key.read_bytes()
    join = calibrate._join

    def join_then_alias(*args, **kwargs):
        result = join(*args, **kwargs)
        if args[0] == "sheet_b":
            out.unlink()
            os.link(key, out)
        return result

    monkeypatch.setattr(calibrate, "_join", join_then_alias)
    with pytest.raises(reconcile.LabelReconciliationError, match="output_failure"):
        api(a, b, key, out_path=str(out))
    assert key.read_bytes() == out.read_bytes() == original
    assert not list(tmp_path.glob(".reproduce-*"))
