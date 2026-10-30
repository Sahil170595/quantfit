"""Actual installed-origin capture-backed review and separate native consumers."""

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("retained_review_consumer", ROOT / "tools/ci_retained_review.py")
assert SPEC and SPEC.loader
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def test_actual_installed_capture_backed_retained_review_cli_and_api(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("retained review attempted inference or asset resolution")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    result = consumer.run(ROOT, tmp_path)
    assert set(result["interfaces"]) == {"cli", "api"}
    for record in result["interfaces"].values():
        assert record["preparation"]["n_selected"] == 12
        assert record["application"]["n_reviewed"] == 12
        assert record["native_counts"]["n_labeled"] == 18
        assert record["native_counts"]["n_unusable"] == 4
        assert record["separate_truthful_extract_and_schema3"]
        assert record["original_retained_inputs_unchanged"] and record["original_synthetic_sheets_unavailable"]


@pytest.mark.parametrize("interface", ["api", "cli"])
@pytest.mark.parametrize(("extra", "mode"), [(0, "all-disagree"), (1, "all-disagree"), (1, "zero")])
def test_retained_review_respects_native_csv_field_domain(tmp_path, monkeypatch, interface, extra, mode):
    from quantfit.safety import calibrate, retained_review, verify
    from quantfit.safety.retained_labels import extract_labels, ingest_retained_labels

    helper = consumer._fixture_module(ROOT)
    limit = csv.field_size_limit()
    assert limit == 131072
    native_writer = verify._write_capture
    calls = []

    def long_capture(*args, **kwargs):
        values = list(args)
        values[4] = list(values[4])
        values[4][0] = "x" * (limit + extra)
        calls.append(1)
        return native_writer(*values, **kwargs)

    monkeypatch.setattr(verify, "_write_capture", long_capture)
    retained = []
    try:
        csv.field_size_limit(limit + 1)
        a, b, key = helper.fixture(tmp_path / "private", ROOT, mode=mode)
        for name, sheet in (("a", a), ("b", b)):
            labels, receipt = tmp_path / f"{name}.labels.csv", tmp_path / f"{name}-retention.json"
            extract_labels(str(sheet), str(key), out_path=str(labels), receipt_path=str(receipt))
            retained += [labels, receipt]
    finally:
        csv.field_size_limit(limit)
    assert calls == [1] and csv.field_size_limit() == limit
    capture = tmp_path / "private/private.capture.jsonl"
    captured = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
    assert len(captured[1]["completion"]) == limit + extra
    for path in (a, b, tmp_path / "private/pristine.labels.csv"):
        path.unlink()
    inputs = (capture, key, *retained)
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs]
    queue, preparation = tmp_path / "queue.labels.csv", tmp_path / "preparation.json"
    common = [
        "--input-mode",
        "retained",
        "--capture",
        str(capture),
        "--key",
        str(key),
        "--retained-labels-a",
        str(retained[0]),
        "--retention-receipt-a",
        str(retained[1]),
        "--retained-labels-b",
        str(retained[2]),
        "--retention-receipt-b",
        str(retained[3]),
    ]
    assert csv.field_size_limit() == limit
    if interface == "api":
        try:
            retained_review.prepare_retained_label_review(
                *map(str, inputs), review_path=str(queue), receipt_path=str(preparation)
            )
        except retained_review.RetainedReviewError as exc:
            assert str(exc) == "invalid_retained_label_review"
            code = 2
        else:
            code = 0
    else:
        code, document, stderr = helper.invoke(
            ["calibrate", "review", "prepare", *common, "--sheet", str(queue), "--receipt", str(preparation)]
        )
        assert not stderr
        if code == 2:
            assert document["error"]["message"] == "invalid_retained_label_review"
    assert csv.field_size_limit() == limit
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs] == before
    evidence = {
        "interface": interface,
        "mode": mode,
        "field_characters": limit + extra,
        "native_field_limit": limit,
        "setup_only_field_limit": limit + 1,
        "native_capture_writes": len(calls),
        "native_retention_extractions": 2,
        "input_sha256s": before,
        "original_sheets_unavailable": True,
        "prepare_exit_code": code,
        "queue_created": queue.exists(),
        "preparation_created": preparation.exists(),
        "global_limit_restored": True,
        "synthetic": True,
        "human_labels_authenticated": False,
        "scientific_go": False,
    }
    evidence_path = tmp_path / "field-domain-evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    if extra:
        assert code == 2
        assert not queue.exists() and not preparation.exists()
        return
    assert code == 0
    helper.fill_fixture_review(queue, key)
    full, application = tmp_path / "full.labels.csv", tmp_path / "application.json"
    if interface == "api":
        retained_review.apply_retained_label_review(
            *map(str, inputs), str(queue), str(preparation), out_path=str(full), receipt_path=str(application)
        )
    else:
        code, _, stderr = helper.invoke(
            [
                "calibrate",
                "review",
                "apply",
                *common,
                "--review",
                str(queue),
                "--preparation",
                str(preparation),
                "--out",
                str(full),
                "--receipt",
                str(application),
            ]
        )
        assert code == 0 and not stderr
    joined = calibrate._join("new sheet", "key", calibrate._read_key(str(key))["ids"], data=full.read_bytes())
    labels, receipt = tmp_path / "new.labels.csv", tmp_path / "new-retention.json"
    extract_labels(str(full), str(key), out_path=str(labels), receipt_path=str(receipt))
    native = ingest_retained_labels(str(labels), str(receipt), str(key), out_path=str(tmp_path / "native3.json"))
    assert len(joined) == native["n_labeled"] == 18 and native["calibration_schema"] == 3
    assert csv.field_size_limit() == limit
    evidence.update({"native_full_rows": len(joined), "separate_schema3_ingest": True})
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
