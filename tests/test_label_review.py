"""Complete native review workflow, exact preparation binding and private subset validation."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from tools.ci_label_review import FINAL, fill_fixture_review, fixture, read_rows, write_rows

ROOT = Path(__file__).resolve().parents[1]


def prepared(tmp_path, *, mode="mixed", key_kind="bound-v2"):
    from quantfit.safety.label_review import prepare_label_review

    first, second, key = fixture(tmp_path / "private", ROOT, mode=mode, key_kind=key_kind)
    queue, receipt = tmp_path / "private.review.labels.csv", tmp_path / "preparation.json"
    report = prepare_label_review(str(first), str(second), str(key), review_path=str(queue), receipt_path=str(receipt))
    return (first, second, key, queue, receipt), report


def apply(paths, tmp_path):
    from quantfit.safety.label_review import apply_label_review

    a, b, key, review, preparation = paths
    return apply_label_review(
        str(a),
        str(b),
        str(key),
        str(review),
        str(preparation),
        out_path=str(tmp_path / "reviewed.labels.csv"),
        receipt_path=str(tmp_path / "application.json"),
    )


def test_every_unequal_normalized_combination_is_queued_sorted_with_blank_labels(tmp_path):
    paths, report = prepared(tmp_path)
    a, b, key, queue, _ = paths
    ids = json.loads(key.read_bytes())["ids"]
    rows = read_rows(queue)
    assert rows[0] == ["id", "completion", "human_label"]
    assert [row[0] for row in rows[1:]] == sorted(row[0] for row in rows[1:])
    assert all(row[2] == "" for row in rows[1:])
    assert {(ids[row[0]]["pair"], ids[row[0]]["arm"]) for row in rows[1:]} == {
        (i, arm) for i in (1, 2, 3, 5, 6, 7) for arm in ("baseline", "quantized")
    }
    assert (report["n_pairs"], report["n_rows"], report["n_selected"], report["n_agreed"]) == (9, 18, 12, 6)
    assert report["per_arm"] == {
        arm: {"n_rows": 9, "n_selected": 6, "n_agreed": 3} for arm in ("baseline", "quantized")
    }
    rendered = json.dumps(report)
    assert "PRIVATE" not in rendered and str(tmp_path) not in rendered
    assert all(row_id not in rendered for row_id in ids)
    assert all(str(path) not in rendered for path in (a, b, key, queue))


def test_prepare_explicit_fill_apply_and_unchanged_native_ingest(tmp_path):
    from quantfit.safety.calibrate import ingest_labels
    from quantfit.safety.verify import wilson_interval

    paths, _ = prepared(tmp_path)
    before = [p.read_bytes() for p in paths[:3]]
    fill_fixture_review(paths[3], paths[2])
    application = apply(paths, tmp_path)
    assert (
        application["n_rows"],
        application["n_reviewed"],
        application["n_changed_vs_a"],
        application["n_unusable"],
    ) == (18, 12, 10, 4)
    assert application["per_arm"] == {
        arm: {"n_rows": 9, "n_reviewed": 6, "n_changed_vs_a": 5, "n_unusable": 2} for arm in ("baseline", "quantized")
    }
    ids = json.loads(paths[2].read_bytes())["ids"]
    rows = read_rows(tmp_path / "reviewed.labels.csv")
    assert len(rows) == 19 and {row[0] for row in rows[1:]} == set(ids)
    assert all(row[2] == FINAL[ids[row[0]]["pair"]] for row in rows[1:])
    result = ingest_labels(str(tmp_path / "reviewed.labels.csv"), str(paths[2]), str(tmp_path / "calibration.json"))
    assert result["calibration_schema"] == 2
    for arm, expected in {"baseline": (7, 2, 4, 3, 2, 2), "quantized": (7, 2, 4, 3, 1, 2)}.items():
        block = result[arm]
        assert (
            block["n"],
            block["n_unusable"],
            block["human_refusals"],
            block["human_compliances"],
            block["direction"]["judge_refusal_human_compliance"],
            block["direction"]["judge_compliance_human_refusal"],
        ) == expected
        assert block["epsilon_wilson95"] == list(wilson_interval(expected[4] + expected[5], 7))
    assert [p.read_bytes() for p in paths[:3]] == before


def test_zero_selection_header_only_review_still_builds_complete_native_sheet(tmp_path):
    from quantfit.safety.calibrate import CalibrationError, ingest_labels

    paths, report = prepared(tmp_path, mode="zero")
    assert report["n_selected"] == 0 and len(read_rows(paths[3])) == 1
    with pytest.raises(CalibrationError):
        ingest_labels(str(paths[3]), str(paths[2]), str(tmp_path / "invalid.json"))
    application = apply(paths, tmp_path)
    assert application["n_reviewed"] == application["n_changed_vs_a"] == 0
    assert read_rows(tmp_path / "reviewed.labels.csv")[1:] == sorted(read_rows(paths[0])[1:])
    assert (
        ingest_labels(str(tmp_path / "reviewed.labels.csv"), str(paths[2]), str(tmp_path / "valid.json"))["n_labeled"]
        == 18
    )


def test_partial_queue_remains_not_native_ingestible_and_complete_all_u_still_refuses(tmp_path):
    from quantfit.safety.calibrate import CalibrationError, ingest_labels

    paths, _ = prepared(tmp_path / "partial")
    fill_fixture_review(paths[3], paths[2])
    with pytest.raises(CalibrationError):
        ingest_labels(str(paths[3]), str(paths[2]), str(tmp_path / "partial.json"))
    all_u, _ = prepared(tmp_path / "unusable", mode="all-disagree")
    fill_fixture_review(all_u[3], all_u[2], labels=("unusable",) * 9)
    report = apply(all_u, tmp_path / "unusable")
    assert report["n_unusable"] == 18
    with pytest.raises(CalibrationError):
        ingest_labels(str(tmp_path / "unusable/reviewed.labels.csv"), str(all_u[2]), str(tmp_path / "unusable.json"))


@pytest.mark.parametrize(
    "mutation", ["blank", "missing", "duplicate", "extra", "extra-agreed", "unknown-label", "text"]
)
def test_review_subset_must_be_exact_unchanged_and_explicit(tmp_path, mutation):
    from quantfit.safety.label_review import LabelReviewError

    paths, _ = prepared(tmp_path)
    before = [p.read_bytes() for p in paths[:3]]
    fill_fixture_review(paths[3], paths[2])
    rows = read_rows(paths[3])
    if mutation == "blank":
        rows[1][2] = ""
    elif mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows.append(rows[1])
    elif mutation == "extra":
        rows.append(["PRIVATE_UNKNOWN_ID", "PRIVATE_TEXT", "refusal"])
    elif mutation == "extra-agreed":
        selected = {row[0] for row in rows[1:]}
        row = next(row for row in read_rows(paths[0])[1:] if row[0] not in selected)
        rows.append([row[0], row[1], "compliance"])
    elif mutation == "unknown-label":
        rows[1][2] = "PRIVATE_LABEL"
    else:
        rows[1][1] += "PRIVATE_CHANGED"
    write_rows(paths[3], rows)
    with pytest.raises(LabelReviewError, match="^invalid_label_review$"):
        apply(paths, tmp_path)
    assert not (tmp_path / "reviewed.labels.csv").exists() and not (tmp_path / "application.json").exists()
    assert [p.read_bytes() for p in paths[:3]] == before


@pytest.mark.parametrize(
    "mutation",
    [
        "swap",
        "reorder",
        "changed-agreement",
        "key-bytes",
        "schema-bool",
        "schema-float",
        "count-float",
        "zero-count-bool",
        "flag-int",
        "unknown-field",
    ],
)
def test_preparation_exact_roles_and_closed_typed_receipt_are_not_reinterpreted(tmp_path, mutation):
    from quantfit.safety.label_review import LabelReviewError

    paths, _ = prepared(tmp_path, mode="zero" if mutation == "zero-count-bool" else "mixed")
    fill_fixture_review(paths[3], paths[2])
    if mutation == "swap":
        paths = (paths[1], paths[0], *paths[2:])
    elif mutation == "reorder":
        rows = read_rows(paths[1])
        write_rows(paths[1], [rows[0], *reversed(rows[1:])], bom=True)
    elif mutation == "key-bytes":
        paths[2].write_bytes(paths[2].read_bytes() + b"\n")
    elif mutation == "changed-agreement":
        ids = json.loads(paths[2].read_bytes())["ids"]
        for path in paths[:2]:
            rows = read_rows(path)
            for row in rows[1:]:
                if ids[row[0]]["pair"] == 0:
                    row[2] = "compliance"
            write_rows(path, rows)
    else:
        receipt = json.loads(paths[4].read_bytes())
        if mutation == "schema-bool":
            receipt["review_preparation_schema"] = True
        elif mutation == "schema-float":
            receipt["review_preparation_schema"] = 1.0
        elif mutation == "count-float":
            receipt["n_selected"] = float(receipt["n_selected"])
        elif mutation == "zero-count-bool":
            receipt["n_selected"] = False
        elif mutation == "flag-int":
            receipt["limits"]["human_labels_authenticated"] = 0
        else:
            receipt["PRIVATE_EXTRA"] = "PRIVATE"
        paths[4].write_bytes(json.dumps(receipt).encode("utf-8"))
    with pytest.raises(LabelReviewError):
        apply(paths, tmp_path)
    assert not (tmp_path / "reviewed.labels.csv").exists()


@pytest.mark.parametrize("key_kind", ["legacy-v1", "unbound-v2"])
def test_legacy_or_unbound_scope_remains_unbound(tmp_path, key_kind):
    paths, report = prepared(tmp_path, key_kind=key_kind)
    assert report["binding_fingerprint"] is None
    assert (report["capture_sha256_declared"] is None) == (key_kind == "legacy-v1")
    fill_fixture_review(paths[3], paths[2])
    result = apply(paths, tmp_path)
    assert result["binding_fingerprint"] is None


def test_apply_holds_all_five_roles_once_and_does_not_reflect_declared_producer(tmp_path, monkeypatch):
    import quantfit.safety.label_review as review_module
    from quantfit import __version__
    from quantfit.safety import retention_io

    paths, _ = prepared(tmp_path)
    fill_fixture_review(paths[3], paths[2])
    receipt = json.loads(paths[4].read_bytes())
    receipt["quantfit_version"] = "C:/PRIVATE_PRODUCER_VERSION"
    paths[4].write_bytes(json.dumps(receipt).encode("utf-8"))
    seen = []
    opened = retention_io.os.open

    def counted(path, flags, *args, **kwargs):
        if Path(path) in paths:
            seen.append(Path(path))
        return opened(path, flags, *args, **kwargs)

    monkeypatch.setattr(retention_io.os, "open", counted)
    key_validator = review_module._key

    def validated_after_hold(raw):
        assert sorted(map(str, seen)) == sorted(map(str, paths))
        return key_validator(raw)

    monkeypatch.setattr(review_module, "_key", validated_after_hold)
    result = apply(paths, tmp_path)
    assert sorted(map(str, seen)) == sorted(map(str, paths))
    assert result["quantfit_version"] == __version__ and "PRIVATE" not in json.dumps(result)


def test_fresh_preparation_swap_order_bom_and_normalization_preserve_selection_not_stale_receipts(tmp_path):
    from quantfit.safety.label_review import LabelReviewError, prepare_label_review

    paths, _ = prepared(tmp_path)
    a, b, key, queue, _receipt = paths
    blank = queue.read_bytes()
    for path in (a, b):
        rows = read_rows(path)
        for row in rows[1:]:
            row[2] = " " + row[2].upper() + " "
        write_rows(path, [rows[0], *reversed(rows[1:])], bom=True)
    fill_fixture_review(queue, key)
    with pytest.raises(LabelReviewError):
        apply(paths, tmp_path)
    fresh, fresh_receipt = tmp_path / "fresh.labels.csv", tmp_path / "fresh.json"
    swapped, swapped_receipt = tmp_path / "swapped.labels.csv", tmp_path / "swapped.json"
    report = prepare_label_review(str(a), str(b), str(key), review_path=str(fresh), receipt_path=str(fresh_receipt))
    swapped_report = prepare_label_review(
        str(b), str(a), str(key), review_path=str(swapped), receipt_path=str(swapped_receipt)
    )
    assert fresh.read_bytes() == swapped.read_bytes() == blank
    assert report["review_sheet"] == swapped_report["review_sheet"] and report["inputs"] != swapped_report["inputs"]
    for path in (fresh, swapped):
        fill_fixture_review(path, key)
        rows = read_rows(path)
        for row in rows[1:]:
            row[2] = " " + row[2].upper() + " "
        write_rows(path, [rows[0], *reversed(rows[1:])], bom=True)
    apply((a, b, key, fresh, fresh_receipt), tmp_path)
    (tmp_path / "swap-out").mkdir()
    apply((b, a, key, swapped, swapped_receipt), tmp_path / "swap-out")
    assert (tmp_path / "reviewed.labels.csv").read_bytes() == (tmp_path / "swap-out/reviewed.labels.csv").read_bytes()


@pytest.mark.parametrize("mutation", ["duplicate", "nonfinite", "long-number"])
def test_strict_preparation_json_is_checked_on_actual_apply_path(tmp_path, mutation):
    from quantfit.safety.label_review import LabelReviewError

    paths, _ = prepared(tmp_path)
    fill_fixture_review(paths[3], paths[2])
    raw = paths[4].read_bytes().rstrip()
    suffix = {
        "duplicate": b', "n_pairs":9}',
        "nonfinite": b', "unused":NaN}',
        "long-number": b', "unused":' + b"9" * 1000 + b"}",
    }[mutation]
    paths[4].write_bytes(raw[:-1] + suffix)
    with pytest.raises(LabelReviewError):
        apply(paths, tmp_path)
    assert not (tmp_path / "reviewed.labels.csv").exists()


def test_empty_review_still_enforces_logical_csv_record_cap(tmp_path):
    from quantfit.safety.label_review import MAX_CSV_RECORDS, LabelReviewError

    paths, _ = prepared(tmp_path, mode="zero")
    paths[3].write_bytes(paths[3].read_bytes() + b"\n" * MAX_CSV_RECORDS)
    with pytest.raises(LabelReviewError):
        apply(paths, tmp_path)
    assert not (tmp_path / "reviewed.labels.csv").exists()


def test_valid_bound_private_scope_and_legacy_extra_scope_are_never_reflected(tmp_path):
    from quantfit.safety.calibration_binding import identity_fingerprint
    from quantfit.safety.label_review import prepare_label_review

    for legacy in (False, True):
        root = tmp_path / ("legacy" if legacy else "bound")
        a, b, key = fixture(root / "private", ROOT, key_kind="legacy-v1" if legacy else "bound-v2")
        private = json.loads(key.read_bytes())
        model = "C:/PRIVATE_REVIEW_MODEL_PATH/model"
        if legacy:
            private["binding"] = {"PRIVATE_SCOPE": model}
            private["capture_sha256"] = "PRIVATE_CAPTURE_DECLARATION"
        else:
            private["capture"]["baseline"] = model
            private["binding"]["identity"]["baseline"]["model"] = model
            private["binding"]["fingerprint"] = identity_fingerprint(private["binding"]["identity"])
        key.write_bytes(json.dumps(private).encode("utf-8"))
        queue, receipt = root / "queue.labels.csv", root / "preparation.json"
        prep = prepare_label_review(str(a), str(b), str(key), review_path=str(queue), receipt_path=str(receipt))
        fill_fixture_review(queue, key)
        app = apply((a, b, key, queue, receipt), root)
        rendered = json.dumps([prep, app])
        assert "PRIVATE" not in rendered and private["salt"] not in rendered
        if legacy:
            assert prep["binding_fingerprint"] is prep["capture_sha256_declared"] is None
            assert app["binding_fingerprint"] is app["capture_sha256_declared"] is None


def test_second_output_race_is_categorical_failure_without_rollback_or_private_traceback(tmp_path, monkeypatch):
    import os
    import traceback

    from quantfit.safety import retention_io
    from quantfit.safety.label_review import LabelReviewError

    paths, _ = prepared(tmp_path)
    fill_fixture_review(paths[3], paths[2])
    originals = [p.read_bytes() for p in paths]
    receipt = tmp_path / "application.json"
    opened = retention_io.os.open

    def raced(path, flags, *args, **kwargs):
        if Path(path) == receipt and flags & os.O_CREAT:
            receipt.write_bytes(b"PRIVATE_RACER_CONTENT")
        return opened(path, flags, *args, **kwargs)

    monkeypatch.setattr(retention_io.os, "open", raced)
    with pytest.raises(LabelReviewError) as failure:
        apply(paths, tmp_path)
    assert (tmp_path / "reviewed.labels.csv").exists() and receipt.read_bytes() == b"PRIVATE_RACER_CONTENT"
    assert [p.read_bytes() for p in paths] == originals
    assert not list(tmp_path.glob(".quantfit-retain-*"))
    rendered = "".join(traceback.format_exception(failure.value))
    assert "PRIVATE_RACER_CONTENT" not in rendered and str(receipt) not in rendered


@pytest.mark.parametrize("mode", ["private-input", "public-input", "same-target"])
def test_new_review_output_roles_cannot_alias_inputs_or_each_other(tmp_path, mode):
    from quantfit.safety.label_review import LabelReviewError, apply_label_review

    paths, _ = prepared(tmp_path)
    fill_fixture_review(paths[3], paths[2])
    before = [p.read_bytes() for p in paths]
    a, b, key, queue, prep = paths
    out, receipt = tmp_path / "new.labels.csv", tmp_path / "new.json"
    if mode == "private-input":
        out = a
    elif mode == "public-input":
        receipt = prep
    else:
        receipt = out
    with pytest.raises(LabelReviewError):
        apply_label_review(
            str(a), str(b), str(key), str(queue), str(prep), out_path=str(out), receipt_path=str(receipt)
        )
    assert [p.read_bytes() for p in paths] == before
    assert not (tmp_path / "new.labels.csv").exists() and not (tmp_path / "new.json").exists()


def test_oversized_key_is_refused_before_native_key_validation(tmp_path, monkeypatch):
    from unittest.mock import Mock

    import quantfit.safety.label_review as review

    a, b, key = fixture(tmp_path / "private", ROOT)
    with key.open("wb") as stream:
        stream.seek(review.MAX_KEY_BYTES)
        stream.write(b"x")
    validator = Mock(side_effect=AssertionError("native key validator before byte admission"))
    monkeypatch.setattr(review, "_key", validator)
    with pytest.raises(review.LabelReviewError):
        review.prepare_label_review(
            str(a),
            str(b),
            str(key),
            review_path=str(tmp_path / "new.labels.csv"),
            receipt_path=str(tmp_path / "new.json"),
        )
    validator.assert_not_called()


@pytest.mark.parametrize("kind", ["hardlink", "symlink", "fifo"])
def test_unsafe_original_nodes_are_refused_without_output(tmp_path, kind):
    import os

    from quantfit.safety.label_review import LabelReviewError, prepare_label_review

    a, b, key = fixture(tmp_path / "private", ROOT)
    alias = tmp_path / "unsafe.labels.csv"
    if kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("POSIX FIFO unavailable")
        os.mkfifo(alias)
    else:
        try:
            if kind == "hardlink":
                os.link(a, alias)
            else:
                os.symlink(a, alias)
        except OSError as exc:
            pytest.skip(f"link creation unavailable: {exc.errno}")
    with pytest.raises(LabelReviewError):
        prepare_label_review(
            str(alias),
            str(b),
            str(key),
            review_path=str(tmp_path / "new.labels.csv"),
            receipt_path=str(tmp_path / "new.json"),
        )
    assert not (tmp_path / "new.labels.csv").exists() and not (tmp_path / "new.json").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction contract")
def test_windows_junction_original_and_output_parent_are_refused(tmp_path):
    from quantfit.safety.label_review import LabelReviewError, prepare_label_review

    a, b, key = fixture(tmp_path / "private", ROOT)
    junction = tmp_path / "junction"
    quoted_link, quoted_target = [str(path).replace("'", "''") for path in (junction, a.parent)]
    command = f"New-Item -ItemType Junction -Path '{quoted_link}' -Target '{quoted_target}' | Out-Null"
    completed = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    try:
        with pytest.raises(LabelReviewError):
            prepare_label_review(
                str(junction / a.name),
                str(b),
                str(key),
                review_path=str(tmp_path / "refused.labels.csv"),
                receipt_path=str(tmp_path / "refused.json"),
            )
        with pytest.raises(LabelReviewError):
            prepare_label_review(
                str(a),
                str(b),
                str(key),
                review_path=str(junction / "refused.labels.csv"),
                receipt_path=str(tmp_path / "refused.json"),
            )
        assert a.is_file() and not (a.parent / "refused.labels.csv").exists()
    finally:
        junction.rmdir()  # Remove only the owned junction, never the target directory.
