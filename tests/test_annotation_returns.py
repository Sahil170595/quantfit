"""Inspect indexed private returns before complete native collection."""

import json
import os
import subprocess
import sys

import pytest
from test_annotation_chunks import collect, fill, prepare, read_rows, write_rows


def test_original_complete_collection_remains_native(tmp_path):
    from quantfit.safety.calibrate import ingest_labels

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    assert collect(tmp_path, sheet, key, manifest, parts)["n_rows"] == 18
    result = ingest_labels(str(tmp_path / "complete.labels.csv"), str(key), str(tmp_path / "calibration.json"))
    assert result["n_labeled"] == 18 and result["calibration_schema"] == 2


def test_indexed_subset_is_complete_per_supplied_part_and_explicitly_incomplete(tmp_path):
    from quantfit.safety import annotation_chunks

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    result = annotation_chunks.validate_annotation_returns(
        str(sheet), str(key), str(manifest), ((4, str(parts[3])), (2, str(parts[1])))
    )
    assert result["expected_part_indices"] == [1, 2, 3, 4]
    assert result["received_part_indices"] == [2, 4] and result["missing_part_indices"] == [1, 3]
    assert result["complete"] is False and result["n_received_rows"] == 8


def test_actual_cli_indexed_subset_does_not_collect_or_ingest(tmp_path):
    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    out = tmp_path / "inspection.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "quantfit.cli",
            "calibrate",
            "chunks",
            "validate",
            "--sheet",
            str(sheet),
            "--key",
            str(key),
            "--manifest",
            str(manifest),
            "--part",
            f"2={parts[1]}",
            "--out",
            str(out),
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1"),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    document = json.loads(completed.stdout)
    assert document["command"] == "calibrate chunks validate"
    assert document["result"] == json.loads(out.read_bytes())
    assert document["result"]["complete"] is False
    assert not (tmp_path / "complete.labels.csv").exists() and not (tmp_path / "calibration.json").exists()


def test_complete_out_of_order_inspection_preserves_originals_and_collects(tmp_path):
    from quantfit.safety.annotation_chunks import validate_annotation_returns

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    inputs = [sheet, key, manifest, *parts]
    before = [path.read_bytes() for path in inputs]
    result = validate_annotation_returns(
        str(sheet),
        str(key),
        str(manifest),
        tuple((i + 1, str(part)) for i, part in reversed(list(enumerate(parts)))),
        out_path=str(tmp_path / "inspection.json"),
    )
    assert result["complete"] is True and result["missing_part_indices"] == []
    assert result["n_received_rows"] == 18 and result["n_missing_rows"] == 0
    assert result == json.loads((tmp_path / "inspection.json").read_bytes())
    public = json.dumps(result)
    private = json.loads(key.read_bytes())
    assert private["salt"] not in public and "PRIVATE_" not in public and str(tmp_path) not in public
    assert all(ident not in public for ident in private["ids"])
    assert [path.read_bytes() for path in inputs] == before
    assert collect(tmp_path, sheet, key, manifest, parts)["n_rows"] == 18


@pytest.mark.parametrize("index", [True, 1.0, "1", 0, -1, 5, 129])
def test_index_domain_is_strict_and_publication_is_unchanged(tmp_path, index):
    from quantfit.safety.annotation_chunks import AnnotationChunksError, validate_annotation_returns

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    out = tmp_path / "inspection.json"
    with pytest.raises(AnnotationChunksError, match="^invalid_annotation_returns$"):
        validate_annotation_returns(str(sheet), str(key), str(manifest), ((index, str(parts[0])),), out_path=str(out))
    assert not out.exists()


@pytest.mark.parametrize("fault", ["duplicate_index", "same_file", "substituted", "empty", "not_tuple"])
def test_explicit_roles_reject_ambiguity(tmp_path, fault):
    from quantfit.safety.annotation_chunks import AnnotationChunksError, validate_annotation_returns

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    roles = {
        "duplicate_index": ((1, str(parts[0])), (1, str(parts[1]))),
        "same_file": ((1, str(parts[0])), (2, str(parts[0]))),
        "substituted": ((2, str(parts[0])),),
        "empty": (),
        "not_tuple": {1: str(parts[0])},
    }[fault]
    with pytest.raises(AnnotationChunksError, match="^invalid_annotation_returns$"):
        validate_annotation_returns(str(sheet), str(key), str(manifest), roles)


@pytest.mark.parametrize("fault", ["blank", "text", "label", "missing", "duplicate", "schema", "source", "key"])
def test_late_bad_rows_and_tampered_originals_do_not_publish(tmp_path, fault):
    from quantfit.safety.annotation_chunks import AnnotationChunksError, validate_annotation_returns

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    if fault in {"schema", "source", "key"}:
        if fault == "schema":
            data = json.loads(manifest.read_bytes())
            data["annotation_chunk_schema"] = 1.0
            manifest.write_text(json.dumps(data), encoding="utf-8")
        else:
            path = sheet if fault == "source" else key
            path.write_bytes(path.read_bytes() + b" ")
    else:
        rows = read_rows(parts[-1])
        if fault == "missing":
            rows.pop()
        elif fault == "duplicate":
            rows[-1] = rows[1]
        else:
            column, value = {"blank": (2, ""), "text": (1, "PRIVATE_CHANGED"), "label": (2, "PRIVATE_LABEL")}[fault]
            rows[-1][column] = value
        write_rows(parts[-1], rows)
    out = tmp_path / "inspection.json"
    with pytest.raises(AnnotationChunksError, match="^invalid_annotation_returns$"):
        validate_annotation_returns(
            str(sheet), str(key), str(manifest), ((1, str(parts[0])), (4, str(parts[-1]))), out_path=str(out)
        )
    assert not out.exists()


@pytest.mark.parametrize("role", ["sheet", "key", "manifest", "part", "existing", "directory", "parent_file"])
def test_sink_roles_are_exclusive(tmp_path, role):
    from quantfit.safety.annotation_chunks import AnnotationChunksError, validate_annotation_returns

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    existing = tmp_path / "existing"
    existing.write_bytes(b"operator sentinel")
    outputs = {
        "sheet": sheet,
        "key": key,
        "manifest": manifest,
        "part": parts[0],
        "existing": existing,
        "directory": tmp_path,
        "parent_file": existing / "receipt.json",
    }
    before = [path.read_bytes() for path in (sheet, key, manifest, parts[0], existing)]
    with pytest.raises(AnnotationChunksError, match="^invalid_annotation_returns$"):
        validate_annotation_returns(
            str(sheet), str(key), str(manifest), ((1, str(parts[0])),), out_path=str(outputs[role])
        )
    assert [path.read_bytes() for path in (sheet, key, manifest, parts[0], existing)] == before


def test_hold_once_and_native_budgets(tmp_path, monkeypatch):
    import quantfit.safety.annotation_chunks as chunks

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    calls = []
    native = chunks.hold

    def tracked(path, limit):
        calls.append(path)
        return native(path, limit)

    monkeypatch.setattr(chunks, "hold", tracked)
    chunks.validate_annotation_returns(str(sheet), str(key), str(manifest), ((4, str(parts[-1])), (1, str(parts[0]))))
    assert len(calls) == len(set(calls)) == 5
    calls.clear()
    with pytest.raises(chunks.AnnotationChunksError):
        chunks.validate_annotation_returns(
            str(sheet), str(key), str(manifest), ((1, str(parts[0])), (2, str(parts[0])))
        )
    assert calls == []
    monkeypatch.setattr(chunks, "MAX_INPUT_BYTES", sum(path.stat().st_size for path in (sheet, key, manifest)) + 1)
    with pytest.raises(chunks.AnnotationChunksError):
        chunks.validate_annotation_returns(str(sheet), str(key), str(manifest), ((1, str(parts[0])),))


def test_unusable_labels_validate_without_inventing_calibration(tmp_path):
    from quantfit.safety.annotation_chunks import validate_annotation_returns

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts, "unusable")
    result = validate_annotation_returns(str(sheet), str(key), str(manifest), ((1, str(parts[0])),))
    assert result["n_received_rows"] == 5 and result["limits"]["human_labels_authenticated"] is False
    assert "epsilon" not in json.dumps(result)


@pytest.mark.parametrize("part", ["01=unused", "1.0=unused", "true=unused", "0=unused", "1=", "1", "129=unused"])
def test_actual_cli_categorical_refusal_does_not_expose_paths(tmp_path, part):
    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    out = tmp_path / "receipt.json"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "quantfit.cli",
            "calibrate",
            "chunks",
            "validate",
            "--sheet",
            str(sheet),
            "--key",
            str(key),
            "--manifest",
            str(manifest),
            "--part",
            part,
            "--out",
            str(out),
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1"),
    )
    assert result.returncode == 2 and not result.stderr
    assert json.loads(result.stdout)["error"]["message"] == "invalid_annotation_returns"
    assert str(tmp_path) not in result.stdout and not out.exists()


def test_changed_input_and_receipt_budget_refuse_before_publication(tmp_path, monkeypatch):
    import quantfit.safety.annotation_chunks as chunks

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    out = tmp_path / "receipt.json"
    monkeypatch.setattr(chunks, "MAX_RECEIPT_BYTES", 1)
    with pytest.raises(chunks.AnnotationChunksError):
        chunks.validate_annotation_returns(
            str(sheet), str(key), str(manifest), ((1, str(parts[0])),), out_path=str(out)
        )
    assert not out.exists()
    monkeypatch.undo()
    native = chunks.calibrate._join

    def changed(*args, **kwargs):
        result = native(*args, **kwargs)
        parts[0].write_bytes(parts[0].read_bytes() + b"\n")
        return result

    monkeypatch.setattr(chunks.calibrate, "_join", changed)
    with pytest.raises(chunks.AnnotationChunksError):
        chunks.validate_annotation_returns(
            str(sheet), str(key), str(manifest), ((1, str(parts[0])),), out_path=str(out)
        )
    assert not out.exists()
