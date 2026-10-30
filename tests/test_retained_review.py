"""Capture-backed explicit review after the original filled sheets are unavailable."""

import json
from pathlib import Path

import pytest

from tools.ci_label_review import fill_fixture_review, fixture, read_rows, write_rows

ROOT = Path(__file__).resolve().parents[1]


def retained_inputs(tmp_path, mode="mixed", key_kind="bound-v2"):
    from quantfit.safety.retained_labels import extract_labels

    first, second, key = fixture(tmp_path / "private", ROOT, mode=mode, key_kind=key_kind)
    paths = []
    for name, sheet in (("a", first), ("b", second)):
        labels, receipt = tmp_path / f"{name}.labels.csv", tmp_path / f"{name}-retention.json"
        extract_labels(str(sheet), str(key), out_path=str(labels), receipt_path=str(receipt))
        paths += [labels, receipt]
    first.unlink()
    second.unlink()
    (tmp_path / "private/pristine.labels.csv").unlink()
    return (tmp_path / "private/private.capture.jsonl", key, *paths)


def prepared(tmp_path, mode="mixed"):
    from quantfit.safety.retained_review import prepare_retained_label_review

    originals = retained_inputs(tmp_path, mode)
    queue, preparation = tmp_path / "queue.labels.csv", tmp_path / "preparation.json"
    result = prepare_retained_label_review(*map(str, originals), review_path=str(queue), receipt_path=str(preparation))
    return originals, queue, preparation, result


def apply(tmp_path, originals, queue, preparation):
    from quantfit.safety.retained_review import apply_retained_label_review

    return apply_retained_label_review(
        *map(str, originals),
        str(queue),
        str(preparation),
        out_path=str(tmp_path / "reviewed.labels.csv"),
        receipt_path=str(tmp_path / "application.json"),
    )


@pytest.mark.parametrize(("mode", "selected"), [("mixed", 12), ("zero", 0), ("all-disagree", 18), ("all-unusable", 0)])
def test_complete_review_actual_capture_and_truthful_native_consumers(tmp_path, mode, selected):
    from quantfit.safety import calibrate
    from quantfit.safety.retained_labels import extract_labels, ingest_retained_labels

    originals, queue, preparation, prepared_result = prepared(tmp_path, mode)
    before = [p.read_bytes() for p in originals]
    assert prepared_result["n_selected"] == selected
    assert prepared_result["input_mode"] == "retained_labels"
    assert prepared_result["capture_verification"]["held_and_validated"] is True
    assert all(not v["held_and_validated"] for v in prepared_result["original_sheets_declared"].values())
    fill_fixture_review(queue, originals[1])
    rows = read_rows(queue)
    write_rows(queue, [rows[0], *reversed(rows[1:])], bom=True)
    applied = apply(tmp_path, originals, queue, preparation)
    full = tmp_path / "reviewed.labels.csv"
    assert (
        len(calibrate._join("full", "key", calibrate._read_key(str(originals[1]))["ids"], data=full.read_bytes())) == 18
    )
    assert applied["n_reviewed"] == selected and applied["n_rows"] == 18
    assert [p.read_bytes() for p in originals] == before
    if mode == "all-unusable":
        with pytest.raises(calibrate.CalibrationError):
            calibrate.ingest_labels(str(full), str(originals[1]), str(tmp_path / "native.json"))
    else:
        report = calibrate.ingest_labels(str(full), str(originals[1]), str(tmp_path / "native.json"))
        assert report["calibration_schema"] == 2 and report["n_labeled"] == 18
        labels, receipt = tmp_path / "new.labels.csv", tmp_path / "new-retention.json"
        extracted = extract_labels(str(full), str(originals[1]), out_path=str(labels), receipt_path=str(receipt))
        assert extracted["inputs"]["sheet"] == applied["output_sheet"]
        native = ingest_retained_labels(
            str(labels), str(receipt), str(originals[1]), out_path=str(tmp_path / "native3.json")
        )
        assert native["calibration_schema"] == 3 and native["n_unusable"] == report["n_unusable"]
    public = json.dumps([prepared_result, applied])
    key = json.loads(originals[1].read_bytes())
    assert "PRIVATE_" not in public and key["salt"] not in public and str(tmp_path) not in public
    assert all(ident not in public for ident in key["ids"])


@pytest.mark.parametrize("role", range(6))
def test_every_held_source_role_is_bound(tmp_path, role):
    from quantfit.safety.retained_review import RetainedReviewError

    originals, queue, preparation, _ = prepared(tmp_path)
    fill_fixture_review(queue, originals[1])
    originals[role].write_bytes(originals[role].read_bytes() + b"\n")
    with pytest.raises(RetainedReviewError, match="^invalid_retained_label_review$"):
        apply(tmp_path, originals, queue, preparation)
    assert not (tmp_path / "reviewed.labels.csv").exists()


@pytest.mark.parametrize("kind", ["legacy-v1", "unbound-v2"])
def test_unbound_capture_provenance_refused_without_outputs(tmp_path, kind):
    from quantfit.safety.retained_review import RetainedReviewError, prepare_retained_label_review

    originals = retained_inputs(tmp_path, key_kind=kind)
    with pytest.raises(RetainedReviewError):
        prepare_retained_label_review(
            *map(str, originals), review_path=str(tmp_path / "q.labels.csv"), receipt_path=str(tmp_path / "p.json")
        )
    assert not (tmp_path / "q.labels.csv").exists()


@pytest.mark.parametrize("mutation", ["wrong_receipt", "missing", "extra", "duplicate", "blank", "text", "preparation"])
def test_retained_review_malformed_queue_and_role_refusals(tmp_path, mutation):
    from quantfit.safety.retained_review import RetainedReviewError

    originals, queue, preparation, _ = prepared(tmp_path)
    fill_fixture_review(queue, originals[1])
    originals = list(originals)
    if mutation == "wrong_receipt":
        originals[3] = originals[5]
    elif mutation == "preparation":
        data = json.loads(preparation.read_bytes())
        data["n_selected"] = 12.0
        preparation.write_text(json.dumps(data))
    else:
        rows = read_rows(queue)
        if mutation == "missing":
            rows.pop()
        elif mutation == "extra":
            rows.append(["foreign", "PRIVATE_", "refusal"])
        elif mutation == "duplicate":
            rows[-1] = rows[1]
        elif mutation == "blank":
            rows[-1][2] = ""
        else:
            rows[-1][1] += "changed"
        write_rows(queue, rows)
    with pytest.raises(RetainedReviewError):
        apply(tmp_path, originals, queue, preparation)
    assert not (tmp_path / "reviewed.labels.csv").exists() and not (tmp_path / "application.json").exists()


@pytest.mark.parametrize("mutation", ["judge", "text", "metadata"])
def test_actual_capture_facts_checked_after_rebound_declarations(tmp_path, mutation):
    from quantfit.safety.retained_labels import _binding
    from quantfit.safety.retained_review import RetainedReviewError, prepare_retained_label_review

    originals = retained_inputs(tmp_path)
    capture, key_path = originals[:2]
    values = [json.loads(line) for line in capture.read_text().splitlines()]
    if mutation == "judge":
        values[1]["judge_refusal"] = not values[1]["judge_refusal"]
    elif mutation == "text":
        values[1]["completion"] += "changed"
    else:
        values[1]["expected"] = "unsafe"
    capture.write_text("\n".join(json.dumps(v) for v in values) + "\n")
    key = json.loads(key_path.read_bytes())
    key["capture_sha256"] = _binding(capture.read_bytes())["sha256"]
    key_path.write_text(json.dumps(key))
    for receipt_path in (originals[3], originals[5]):
        receipt = json.loads(receipt_path.read_bytes())
        receipt["capture_sha256_declared"] = key["capture_sha256"]
        receipt["inputs"]["key"] = _binding(key_path.read_bytes())
        receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(RetainedReviewError):
        prepare_retained_label_review(
            *map(str, originals), review_path=str(tmp_path / "q.labels.csv"), receipt_path=str(tmp_path / "p.json")
        )
    assert not (tmp_path / "q.labels.csv").exists()


def test_shared_capture_key_and_each_input_held_once(tmp_path, monkeypatch):
    import quantfit.safety.retained_review as review

    originals = retained_inputs(tmp_path)
    observed = []
    native = review.hold

    def held(path, limit):
        observed.append(Path(path))
        return native(path, limit)

    monkeypatch.setattr(review, "hold", held)
    queue, preparation = tmp_path / "q.labels.csv", tmp_path / "p.json"
    review.prepare_retained_label_review(*map(str, originals), review_path=str(queue), receipt_path=str(preparation))
    assert len(observed) == len(set(observed)) == 6
    observed.clear()
    fill_fixture_review(queue, originals[1])
    review.apply_retained_label_review(
        *map(str, originals),
        str(queue),
        str(preparation),
        out_path=str(tmp_path / "o.labels.csv"),
        receipt_path=str(tmp_path / "a.json"),
    )
    assert len(observed) == len(set(observed)) == 8


@pytest.mark.parametrize("role", range(8))
def test_every_actual_input_is_protected_from_output_alias(tmp_path, role):
    from quantfit.safety.retained_review import RetainedReviewError, apply_retained_label_review

    originals, queue, preparation, _ = prepared(tmp_path)
    fill_fixture_review(queue, originals[1])
    paths = (*originals, queue, preparation)
    before = [p.read_bytes() for p in paths]
    with pytest.raises(RetainedReviewError):
        apply_retained_label_review(
            *map(str, paths), out_path=str(paths[role]), receipt_path=str(tmp_path / "app.json")
        )
    assert [p.read_bytes() for p in paths] == before and not (tmp_path / "app.json").exists()


@pytest.mark.parametrize("kind", ["existing", "same_output", "late_source_change", "late_output_race"])
def test_exclusive_publisher_and_held_revalidation(tmp_path, monkeypatch, kind):
    import quantfit.safety.retained_review as review

    originals, queue, preparation, _ = prepared(tmp_path)
    fill_fixture_review(queue, originals[1])
    out, receipt = tmp_path / "out.labels.csv", tmp_path / "app.json"
    if kind == "existing":
        out.write_bytes(b"existing")
    elif kind == "same_output":
        receipt = out
    else:
        native = review.publish

        def raced(outputs, inputs):
            if kind == "late_source_change":
                originals[0].write_bytes(originals[0].read_bytes() + b"\n")
            else:
                out.write_bytes(b"existing")
            return native(outputs, inputs)

        monkeypatch.setattr(review, "publish", raced)
    with pytest.raises(review.RetainedReviewError):
        review.apply_retained_label_review(
            *map(str, originals), str(queue), str(preparation), out_path=str(out), receipt_path=str(receipt)
        )
    assert not receipt.exists()
    if kind in {"existing", "late_output_race"}:
        assert out.read_bytes() == b"existing"
    else:
        assert not out.exists()


def test_combined_budget_is_admitted_before_capture_reconstruction(tmp_path, monkeypatch):
    import quantfit.safety.retained_review as review

    originals = retained_inputs(tmp_path)
    monkeypatch.setattr(review, "MAX_INPUT_BYTES", 1)

    def forbidden(*args):
        raise AssertionError("capture was reconstructed before byte admission")

    monkeypatch.setattr(review, "_originals", forbidden)
    with pytest.raises(review.RetainedReviewError):
        review.prepare_retained_label_review(
            *map(str, originals), review_path=str(tmp_path / "q.labels.csv"), receipt_path=str(tmp_path / "p.json")
        )
    assert not (tmp_path / "q.labels.csv").exists()
