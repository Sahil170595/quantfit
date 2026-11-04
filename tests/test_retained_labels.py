"""Retain private labels and consume real native calibration without completion text."""

import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("retention_fixture", ROOT / "tools/ci_label_reconciliation.py")
assert SPEC and SPEC.loader
fixture_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture_module)


def api():
    from quantfit.safety import retained_labels

    return retained_labels


def setup(tmp_path, **kwargs):
    sheet, _, key, _ = fixture_module.fixture(tmp_path / "private", ROOT, **kwargs)
    return sheet, key, tmp_path / "retained.csv", tmp_path / "receipt.json", tmp_path / "calibration.json"


def extract(paths):
    sheet, key, labels, receipt, _ = paths
    return api().extract_labels(str(sheet), str(key), out_path=str(labels), receipt_path=str(receipt))


def ingest(paths):
    _, key, labels, receipt, out = paths
    return api().ingest_retained_labels(str(labels), str(receipt), str(key), out_path=str(out))


def test_native_roundtrip_after_original_sheet_unavailable_preserves_wilson_and_real_resolution(tmp_path):
    from quantfit.resolution import analyze_resolution
    from quantfit.safety.calibrate import CALIBRATION_SCHEMA, ingest_labels

    paths = setup(tmp_path, n=40)
    sheet, key, labels, receipt, out = paths
    original = sheet.read_bytes()
    native = ingest_labels(str(sheet), str(key), str(tmp_path / "legacy.json"))
    retention = extract(paths)
    assert CALIBRATION_SCHEMA == 2 and native["calibration_schema"] == 2
    assert retention["inputs"]["sheet"] == {"sha256": hashlib.sha256(original).hexdigest(), "size_bytes": len(original)}
    with labels.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["id", "human_label"] and len(rows) == 81
    assert rows[1:] == sorted(rows[1:])
    sheet.unlink()
    retained = ingest(paths)
    assert retained["calibration_schema"] == 3
    for field in (
        "baseline",
        "quantized",
        "n_labeled",
        "n_unusable",
        "unmeasured_arms",
        "arm_epsilon_delta",
        "binding",
    ):
        assert retained[field] == native[field]
    assert set(retained["source"]) == {
        "sheet_sha256",
        "key_sha256",
        "retained_labels_sha256",
        "retention_receipt_sha256",
        "capture_sha256_declared",
    }
    assert retained["source"]["sheet_sha256"] == hashlib.sha256(original).hexdigest()
    for field, path in (("key_sha256", key), ("retained_labels_sha256", labels), ("retention_receipt_sha256", receipt)):
        assert retained["source"][field] == hashlib.sha256(path.read_bytes()).hexdigest()
    result = analyze_resolution(str(ROOT / "validation/2026-10-18-screen-bundle/inputs/reports/clean.json"), str(out))
    assert result["human_confirmation_verified"] is result["assumptions_verified"] is False
    private = json.loads(key.read_bytes())
    rendered = json.dumps(retained) + json.dumps(retention)
    assert private["salt"] not in rendered and fixture_module.MARKER not in rendered
    assert all(row_id not in rendered for row_id in private["ids"])


@pytest.mark.parametrize("key_kind", ["bound-v2", "unbound-v2", "legacy-v1"])
def test_all_unusable_extracts_but_native_ingest_refuses_without_output(tmp_path, key_kind):
    paths = setup(tmp_path, mode="unusable", key_kind=key_kind)
    receipt = extract(paths)
    assert receipt["n_unusable"] == receipt["n_rows"] == 18
    with pytest.raises(RuntimeError, match="invalid_retained_labels"):
        ingest(paths)
    assert not paths[-1].exists()


@pytest.mark.parametrize(
    "mutation",
    ["label", "missing", "extra", "duplicate", "receipt-count", "receipt-hash", "key", "receipt-extra", "receipt-bool"],
)
def test_exact_retained_population_and_receipt_bindings_fail_before_output(tmp_path, mutation):
    paths = setup(tmp_path)
    extract(paths)
    _, key, labels, receipt, out = paths
    rows = list(csv.reader(io.StringIO(labels.read_text())))
    document = json.loads(receipt.read_bytes())
    if mutation == "label":
        rows[1][1] = "compliance" if rows[1][1] != "compliance" else "refusal"
    elif mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append(["PRIVATE_EXTRA_ID", "refusal"])
    elif mutation == "duplicate":
        rows.append(rows[1])
    elif mutation == "receipt-count":
        document["n_rows"] -= 1
    elif mutation == "receipt-hash":
        document["inputs"]["sheet"]["sha256"] = "bad"
    elif mutation == "receipt-extra":
        document["PRIVATE_RAW"] = "PRIVATE_RAW"
    elif mutation == "receipt-bool":
        document["n_pairs"] = True
    elif mutation == "key":
        key.write_bytes(key.read_bytes() + b" ")
    if mutation in {"label", "missing", "extra", "duplicate"}:
        buffer = io.StringIO(newline="")
        csv.writer(buffer, lineterminator="\n").writerows(rows)
        labels.write_bytes(buffer.getvalue().encode())
    receipt.write_bytes((json.dumps(document) + "\n").encode())
    with pytest.raises(RuntimeError, match="invalid_retained_labels") as error:
        ingest(paths)
    assert error.value.__cause__ is None and not out.exists()
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("mutation", ["missing-arm", "bool-n", "excess-n", "duplicate-json", "nonfinite", "completion"])
def test_full_source_admission_is_bounded_and_precedes_outputs(tmp_path, mutation):
    paths = setup(tmp_path, key_kind="legacy-v1")
    sheet, key, labels, receipt, _ = paths
    document = json.loads(key.read_bytes())
    if mutation == "missing-arm":
        document["ids"].pop(next(iter(document["ids"])))
    elif mutation == "bool-n":
        document["capture"]["n_pairs"] = True
    elif mutation == "excess-n":
        document["capture"]["n_pairs"] = 4097
    elif mutation == "completion":
        sheet.write_bytes(sheet.read_bytes().replace(b"PRIVATE_SYNTHETIC", b"PRIVATE_CHANGED"))
    if mutation != "completion":
        raw = json.dumps(document).encode()
        if mutation == "duplicate-json":
            raw = raw.replace(b'"key_schema": 1', b'"key_schema": 1, "key_schema": 1')
        if mutation == "nonfinite":
            raw = raw.replace(b'"key_schema": 1', b'"key_schema": 1, "bad": NaN')
        key.write_bytes(raw)
    with pytest.raises(RuntimeError, match="invalid_retained_labels"):
        extract(paths)
    assert not labels.exists() and not receipt.exists()


def test_deterministic_retained_output_for_bom_crlf_reordered_multiline_source(tmp_path):
    paths = setup(tmp_path)
    extract(paths)
    sheet, key, labels, _, _ = paths
    expected = labels.read_bytes()
    with sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\r\n").writerows([rows[0], *reversed(rows[1:])])
    sheet.write_bytes(buffer.getvalue().encode("utf-8-sig"))
    result = api().extract_labels(
        str(sheet), str(key), out_path=str(tmp_path / "other.csv"), receipt_path=str(tmp_path / "other.json")
    )
    assert (tmp_path / "other.csv").read_bytes() == expected
    assert result["inputs"]["sheet"]["sha256"] == hashlib.sha256(sheet.read_bytes()).hexdigest()


@pytest.mark.parametrize("target", ["labels", "receipt", "input", "same"])
def test_write_once_existing_and_alias_outputs_never_replace_bytes(tmp_path, target):
    paths = list(setup(tmp_path))
    if target == "labels":
        paths[2].write_bytes(b"existing")
    elif target == "receipt":
        paths[3].write_bytes(b"existing")
    elif target == "input":
        paths[2] = paths[0]
    else:
        paths[3] = paths[2]
    before = {p: p.read_bytes() for p in paths if p.exists()}
    with pytest.raises(RuntimeError, match="invalid_retained_labels"):
        extract(paths)
    assert all(p.read_bytes() == raw for p, raw in before.items())


@pytest.mark.parametrize("kind", ["hardlink", "symlink"])
def test_link_inputs_are_refused(tmp_path, kind):
    paths = list(setup(tmp_path))
    alias = tmp_path / "alias.csv"
    try:
        (os.link if kind == "hardlink" else os.symlink)(paths[0], alias)
    except OSError:
        pytest.skip("host does not permit requested link")
    paths[0] = alias
    with pytest.raises(RuntimeError, match="invalid_retained_labels"):
        extract(paths)
    assert not paths[2].exists()


def test_schema2_remains_closed_and_schema3_recomputes_counts(tmp_path):
    from quantfit.safety.calibration_binding import CalibrationBindingError, load_bound_calibration_bytes

    paths = setup(tmp_path, n=40)
    extract(paths)
    report = ingest(paths)
    report["baseline"]["n"] -= 1
    with pytest.raises(CalibrationBindingError):
        load_bound_calibration_bytes(json.dumps(report).encode())
    report["calibration_schema"] = 2
    with pytest.raises(CalibrationBindingError):
        load_bound_calibration_bytes(json.dumps(report).encode())


@pytest.mark.parametrize("kind", ["integer-token", "salt"])
def test_numeric_token_and_salt_work_bounds_precede_native_allocation(tmp_path, monkeypatch, kind):
    paths = setup(tmp_path, key_kind="legacy-v1")
    raw = paths[1].read_bytes()
    if kind == "integer-token":
        raw = raw.replace(b'"key_schema": 1', b'"key_schema": 1, "unused": ' + b"9" * 1000)
    else:
        document = json.loads(raw)
        document["salt"] = "x" * 257
        raw = json.dumps(document).encode()
    paths[1].write_bytes(raw)
    monkeypatch.setattr(
        "quantfit.safety.calibrate._read_key", lambda *a, **kw: pytest.fail("native key loop before bounded admission")
    )
    with pytest.raises(RuntimeError, match="invalid_retained_labels"):
        extract(paths)
    assert not paths[2].exists() and not paths[3].exists()


@pytest.mark.parametrize("mode", ["empty-arm", "empty-direction"])
def test_native_partial_and_unmeasured_directions_remain_null_and_unbound_for_decisions(tmp_path, mode):
    from quantfit.safety.calibration_binding import CalibrationBindingError, load_bound_calibration

    paths = setup(tmp_path, n=40)
    sheet, key, _, _, out = paths
    payload = json.loads(key.read_bytes())
    with sheet.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    for row in rows[1:]:
        if mode == "empty-direction":
            row[2] = "refusal"
        elif payload["ids"][row[0]]["arm"] == "baseline":
            row[2] = "unusable"
    fixture_module.write_rows(sheet, rows)
    extract(paths)
    report = ingest(paths)
    assert report["n_labeled"] == 80
    if mode == "empty-arm":
        assert report["baseline"]["epsilon"] is None and report["arm_epsilon_delta"]["delta"] is None
        assert report["unmeasured_arms"] == ["baseline"]
    else:
        assert report["baseline"]["mde_epsilon_upper"] is None
    with pytest.raises(CalibrationBindingError):
        load_bound_calibration(str(out))


def test_legacy_key_injected_provenance_remains_ignored_unbound(tmp_path):
    from quantfit.safety.calibration_binding import CalibrationBindingError, load_bound_calibration

    paths = setup(tmp_path, key_kind="legacy-v1")
    payload = json.loads(paths[1].read_bytes())
    payload.update(binding={"PRIVATE_INVALID": "PRIVATE_INVALID"}, capture_sha256="a" * 64)
    paths[1].write_bytes(fixture_module.encode(payload))
    receipt = extract(paths)
    report = ingest(paths)
    assert receipt["binding_fingerprint"] is receipt["capture_sha256_declared"] is None
    assert report["binding"] is report["source"]["capture_sha256_declared"] is None
    with pytest.raises(CalibrationBindingError):
        load_bound_calibration(str(paths[-1]))


@pytest.mark.parametrize(
    "mutation", ["duplicate", "nonfinite", "huge-int", "huge-float", "fingerprint", "capture", "version-extra"]
)
def test_receipt_strict_json_and_declared_scope_refusals(tmp_path, mutation):
    paths = setup(tmp_path)
    extract(paths)
    document = json.loads(paths[3].read_bytes())
    if mutation == "fingerprint":
        document["binding_fingerprint"] = "0" * 64
    elif mutation == "capture":
        document["capture_sha256_declared"] = "0" * 64
    elif mutation == "version-extra":
        document["retained_labels"]["extra"] = 1
    raw = json.dumps(document).encode()
    if mutation == "duplicate":
        raw = raw.replace(b'"retention_schema": 1', b'"retention_schema": 1, "retention_schema": 1')
    elif mutation == "nonfinite":
        raw = raw.replace(b'"retention_schema": 1', b'"retention_schema": NaN')
    elif mutation == "huge-int":
        raw = raw.replace(b'"retention_schema": 1', b'"retention_schema": ' + b"9" * 1000)
    elif mutation == "huge-float":
        raw = raw.replace(b'"retention_schema": 1', b'"retention_schema": 1.' + b"0" * 1000)
    paths[3].write_bytes(raw)
    with pytest.raises(RuntimeError, match="invalid_retained_labels"):
        ingest(paths)
    assert not paths[-1].exists()


def test_inputs_are_held_once_with_exact_validated_bytes(tmp_path, monkeypatch):
    from quantfit.safety import retention_io

    paths = setup(tmp_path)
    seen = []
    original = retention_io.os.open

    def opened(path, flags, *args, **kwargs):
        if Path(path) in paths[:2]:
            seen.append(Path(path))
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(retention_io.os, "open", opened)
    extract(paths)
    assert sorted(map(str, seen)) == sorted(map(str, paths[:2]))


def test_second_publication_failure_is_error_not_success_or_rollback(tmp_path, monkeypatch):
    from quantfit.safety import retention_io

    paths = setup(tmp_path)
    original = retention_io.os.open

    def opened(path, flags, *args, **kwargs):
        if Path(path) == paths[3] and flags & os.O_EXCL:
            raise OSError("PRIVATE_FILESYSTEM_ERROR")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(retention_io.os, "open", opened)
    with pytest.raises(RuntimeError, match="invalid_retained_labels") as error:
        extract(paths)
    assert error.value.__cause__ is None
    assert paths[2].exists() and not paths[3].exists()
    assert not list(tmp_path.glob(".quantfit-retain-*"))


def test_first_stage_fstat_failure_closes_fd_without_private_write_or_publication(tmp_path, monkeypatch):
    from quantfit.safety import retention_io

    paths = setup(tmp_path)
    original = retention_io.tempfile.mkstemp
    target_fd = None

    def staged(*args, **kwargs):
        nonlocal target_fd
        fd, name = original(*args, **kwargs)
        target_fd = fd
        return fd, name

    real_stat = retention_io.os.fstat

    def statted(fd):
        if fd == target_fd:
            raise OSError("PRIVATE_STAT_ERROR")
        return real_stat(fd)

    monkeypatch.setattr(retention_io.tempfile, "mkstemp", staged)
    monkeypatch.setattr(retention_io.os, "fstat", statted)
    with pytest.raises(RuntimeError, match="invalid_retained_labels"):
        extract(paths)
    assert target_fd is not None
    with pytest.raises(OSError):
        real_stat(target_fd)
    stages = list(tmp_path.glob(".quantfit-retain-*"))
    assert len(stages) == 1 and stages[0].read_bytes() == b""
    assert not paths[2].exists() and not paths[3].exists()


@pytest.mark.parametrize("which,limit", [(0, 8 * 1024 * 1024), (1, 2 * 1024 * 1024)])
def test_oversized_inputs_refuse_before_output(tmp_path, which, limit):
    paths = setup(tmp_path)
    paths[which].write_bytes(b"x" * (limit + 1))
    with pytest.raises(RuntimeError, match="invalid_retained_labels"):
        extract(paths)
    assert not paths[2].exists() and not paths[3].exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows path identity")
@pytest.mark.parametrize("kind", ["extended-alias", "trailing-dot", "ads", "device"])
def test_windows_native_alias_and_unsafe_names_refused_before_outputs(tmp_path, kind):
    paths = list(setup(tmp_path))
    if kind == "extended-alias":
        paths[3] = Path("\\\\?\\" + str(paths[2]))
    elif kind == "trailing-dot":
        paths[3] = Path(str(paths[2]) + ".")
    elif kind == "ads":
        paths[2] = Path(str(paths[0]) + ":labels")
    else:
        paths[2] = tmp_path / "NUL.csv"
    before = paths[0].read_bytes()
    with pytest.raises(RuntimeError, match="invalid_retained_labels"):
        extract(paths)
    assert paths[0].read_bytes() == before and not (tmp_path / "retained.csv").exists()


def test_encoded_retained_calibration_must_fit_real_native_consumer_limit(tmp_path):
    from quantfit.safety.calibration_binding import identity_fingerprint

    paths = setup(tmp_path, n=40)
    payload = json.loads(paths[1].read_bytes())
    payload["binding"]["identity"]["judge"]["id"] = "é" * 360000
    payload["binding"]["fingerprint"] = identity_fingerprint(payload["binding"]["identity"])
    paths[1].write_bytes(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    assert paths[1].stat().st_size < 2 * 1024 * 1024
    extract(paths)
    with pytest.raises(RuntimeError, match="invalid_retained_labels"):
        ingest(paths)
    assert not paths[-1].exists()


def test_clean_schema2_old_source_cannot_be_relabeled_as_retained_schema3(tmp_path):
    from quantfit.safety.calibrate import ingest_labels
    from quantfit.safety.calibration_binding import CalibrationBindingError, load_bound_calibration_bytes

    paths = setup(tmp_path, n=40)
    report = ingest_labels(str(paths[0]), str(paths[1]), str(tmp_path / "legacy.json"))
    load_bound_calibration_bytes(json.dumps(report).encode())
    report["calibration_schema"] = 3
    with pytest.raises(CalibrationBindingError):
        load_bound_calibration_bytes(json.dumps(report).encode())


def test_legacy_full_sheet_mode_still_refuses_two_column_retained_rows(tmp_path):
    from quantfit.safety.calibrate import CalibrationError, ingest_labels

    paths = setup(tmp_path)
    extract(paths)
    with pytest.raises(CalibrationError):
        ingest_labels(str(paths[2]), str(paths[1]), str(paths[-1]))
    assert not paths[-1].exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO support")
def test_fifo_input_is_refused_before_open(tmp_path):
    paths = list(setup(tmp_path))
    fifo = tmp_path / "fifo.csv"
    os.mkfifo(fifo)
    paths[0] = fifo
    with pytest.raises(RuntimeError, match="invalid_retained_labels"):
        extract(paths)
    assert not paths[2].exists() and not paths[3].exists()


def test_failed_first_stage_unlink_still_closes_other_stages_and_never_succeeds(tmp_path, monkeypatch):
    paths = setup(tmp_path)
    original = Path.unlink
    failed = None
    removed = []

    def unlink(path, *args, **kwargs):
        nonlocal failed
        if path.name.startswith(".quantfit-retain-"):
            if failed is None:
                failed = path
                raise OSError("PRIVATE_CLEANUP_ERROR")
            removed.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(RuntimeError, match="invalid_retained_labels"):
        extract(paths)
    assert failed is not None and failed.exists() and len(removed) == 1
    assert paths[2].exists() and paths[3].exists()
