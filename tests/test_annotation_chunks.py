"""Complete private partition/return workflow; no manufactured human-truth claim."""

import json
from pathlib import Path

import pytest

from tools.ci_label_review import fixture, read_rows, write_rows

ROOT = Path(__file__).resolve().parents[1]


def source(tmp_path):
    first, _, key = fixture(tmp_path / "private", ROOT)
    rows = read_rows(first)
    for row in rows[1:]:
        row[2] = ""
    write_rows(first, rows, bom=True)
    directory = tmp_path / "parts"
    directory.mkdir()
    return first, key, directory


def prepare(tmp_path, size=5):
    from quantfit.safety.annotation_chunks import prepare_annotation_chunks

    sheet, key, directory = source(tmp_path)
    summary = prepare_annotation_chunks(str(sheet), str(key), out_dir=str(directory), rows_per_part=size)
    manifest = directory / "annotation.chunkmanifest.json"
    parts = sorted(directory.glob("part-*.labels.csv"))
    return sheet, key, manifest, parts, summary


def fill(parts, label=" ReFuSaL "):
    for part in parts:
        rows = read_rows(part)
        for row in rows[1:]:
            row[2] = label
        write_rows(part, [rows[0], *reversed(rows[1:])], bom=True)


def collect(tmp_path, sheet, key, manifest, parts):
    from quantfit.safety.annotation_chunks import collect_annotation_chunks

    return collect_annotation_chunks(
        str(sheet),
        str(key),
        str(manifest),
        tuple(map(str, parts)),
        out_path=str(tmp_path / "complete.labels.csv"),
        receipt_path=str(tmp_path / "collection.json"),
    )


@pytest.mark.parametrize("label", [" ReFuSaL ", "unusable"])
def test_complete_native_workflow_and_schema3(tmp_path, label):
    from quantfit.safety import calibrate
    from quantfit.safety.retained_labels import extract_labels, ingest_retained_labels

    sheet, key, manifest, parts, prepared = prepare(tmp_path)
    original = (sheet.read_bytes(), key.read_bytes(), manifest.read_bytes())
    with pytest.raises(calibrate.CalibrationError):
        calibrate._join("sheet", "key", calibrate._read_key(str(key))["ids"], data=sheet.read_bytes())
    blank_hashes = [row["blank_sheet"] for row in json.loads(manifest.read_bytes())["parts"]]
    fill(parts, label)
    result = collect(tmp_path, sheet, key, manifest, parts)
    assert result["n_rows"] == prepared["n_rows"] == 18
    assert result["n_parts"] == 4
    assert [row["filled_sheet"] for row in result["parts"]] != blank_hashes
    full = tmp_path / "complete.labels.csv"
    joined = calibrate._join("sheet", "key", calibrate._read_key(str(key))["ids"], data=full.read_bytes())
    assert len(joined) == 18 and {row["human_label"] for row in joined.values()} == {label.strip().lower()}
    retained, receipt, report = (
        tmp_path / name for name in ("retained.labels.csv", "retention.json", "calibration.json")
    )
    if label == "unusable":
        from quantfit.safety.retention_io import RetainedLabelsError

        with pytest.raises(calibrate.CalibrationError, match="every labeled row"):
            calibrate.ingest_labels(str(full), str(key), str(report))
        extract_labels(str(full), str(key), out_path=str(retained), receipt_path=str(receipt))
        with pytest.raises(RetainedLabelsError):
            ingest_retained_labels(str(retained), str(receipt), str(key), out_path=str(report))
        assert not report.exists() and result["n_unusable"] == 18
    else:
        legacy = calibrate.ingest_labels(str(full), str(key), str(tmp_path / "native.json"))
        assert legacy["calibration_schema"] == 2 and legacy["n_labeled"] == 18
        extract_labels(str(full), str(key), out_path=str(retained), receipt_path=str(receipt))
        native = ingest_retained_labels(str(retained), str(receipt), str(key), out_path=str(report))
        assert native["calibration_schema"] == 3 and native["n_labeled"] == 18 and native["n_unusable"] == 0
    assert (sheet.read_bytes(), key.read_bytes(), manifest.read_bytes()) == original
    public = json.dumps([prepared, result])
    private_key = json.loads(key.read_bytes())
    assert private_key["salt"] not in public and "PRIVATE_" not in public
    assert all(row_id not in public for row_id in private_key["ids"])
    assert str(tmp_path) not in public


@pytest.mark.parametrize("mutation", ["partial", "duplicate", "foreign", "text", "header"])
def test_blank_source_refuses_before_any_output(tmp_path, mutation):
    from quantfit.safety.annotation_chunks import AnnotationChunksError, prepare_annotation_chunks

    sheet, key, directory = source(tmp_path)
    rows = read_rows(sheet)
    if mutation == "partial":
        rows[1][2] = "refusal"
    elif mutation == "duplicate":
        rows[-1] = rows[1]
    elif mutation == "foreign":
        rows[-1][0] = "foreign"
    elif mutation == "text":
        rows[-1][1] += "changed"
    else:
        rows[0].append("notes")
    write_rows(sheet, rows)
    with pytest.raises(AnnotationChunksError, match="^invalid_annotation_chunks$"):
        prepare_annotation_chunks(str(sheet), str(key), out_dir=str(directory), rows_per_part=5)
    assert not list(directory.iterdir())


@pytest.mark.parametrize(
    "mutation",
    ["gap", "duplicate_part", "extra", "blank", "text", "foreign", "invalid_label", "manifest", "source", "key"],
)
def test_collect_refuses_whole_population_mutations(tmp_path, mutation):
    from quantfit.safety.annotation_chunks import AnnotationChunksError

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    if mutation == "gap":
        parts.pop()
    elif mutation == "duplicate_part":
        parts[-1] = parts[0]
    elif mutation == "extra":
        parts.append(parts[0])
    elif mutation in {"blank", "text", "foreign", "invalid_label"}:
        rows = read_rows(parts[-1])
        column, value = {
            "blank": (2, ""),
            "text": (1, "private_changed"),
            "foreign": (0, "foreign"),
            "invalid_label": (2, "yes"),
        }[mutation]
        rows[-1][column] = value
        write_rows(parts[-1], rows)
    elif mutation == "manifest":
        data = json.loads(manifest.read_bytes())
        data["parts"][0]["blank_sheet"]["sha256"] = "0" * 64
        manifest.write_text(json.dumps(data))
    elif mutation == "source":
        sheet.write_bytes(sheet.read_bytes() + b"\n")
    else:
        key.write_bytes(key.read_bytes() + b" ")
    with pytest.raises(AnnotationChunksError, match="^invalid_annotation_chunks$"):
        collect(tmp_path, sheet, key, manifest, parts)
    assert not (tmp_path / "complete.labels.csv").exists() and not (tmp_path / "collection.json").exists()


@pytest.mark.parametrize("size", [True, 0, -1, 8193, 1])
def test_prepare_admits_point_and_part_bounds_before_writes(tmp_path, size, monkeypatch):
    import quantfit.safety.annotation_chunks as chunks

    sheet, key, directory = source(tmp_path)
    monkeypatch.setattr(chunks, "MAX_PARTS", 2)
    with pytest.raises(chunks.AnnotationChunksError):
        chunks.prepare_annotation_chunks(str(sheet), str(key), out_dir=str(directory), rows_per_part=size)
    assert not list(directory.iterdir())


def test_multiline_quoted_source_and_output_alias_refusal(tmp_path):
    from quantfit.safety import calibrate
    from quantfit.safety.annotation_chunks import AnnotationChunksError, collect_annotation_chunks

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    # Existing native fixture includes quoted private text; BOM and reordered returns preserve it.
    fill(parts)
    before = sheet.read_bytes()
    with pytest.raises(AnnotationChunksError):
        collect_annotation_chunks(
            str(sheet),
            str(key),
            str(manifest),
            tuple(map(str, parts)),
            out_path=str(sheet),
            receipt_path=str(tmp_path / "receipt.json"),
        )
    assert sheet.read_bytes() == before
    collect(tmp_path, sheet, key, manifest, parts)
    assert calibrate._read_sheet(str(sheet))[0]["human_label"] == ""


def test_cli_prepare_and_collect(tmp_path, capsys):
    from quantfit.cli import main

    sheet, key, directory = source(tmp_path)
    assert (
        main(
            [
                "calibrate",
                "chunks",
                "prepare",
                "--sheet",
                str(sheet),
                "--key",
                str(key),
                "--out-dir",
                str(directory),
                "--rows-per-part",
                "5",
                "--json",
            ]
        )
        == 0
    )
    prepared = json.loads(capsys.readouterr().out)
    parts = sorted(directory.glob("part-*.labels.csv"))
    fill(parts)
    args = [
        "calibrate",
        "chunks",
        "collect",
        "--sheet",
        str(sheet),
        "--key",
        str(key),
        "--manifest",
        str(directory / "annotation.chunkmanifest.json"),
        "--out",
        str(tmp_path / "complete.labels.csv"),
        "--receipt",
        str(tmp_path / "receipt.json"),
        "--json",
    ]
    for part in parts:
        args += ["--part", str(part)]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert prepared["command"] == "calibrate chunks prepare" and result["result"]["n_rows"] == 18


def test_each_input_is_held_once_and_duplicate_parts_are_not_reread(tmp_path, monkeypatch):
    import quantfit.safety.annotation_chunks as chunks

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    held = []
    native = chunks.hold

    def tracked(path, limit):
        held.append(Path(path))
        return native(path, limit)

    monkeypatch.setattr(chunks, "hold", tracked)
    collect(tmp_path, sheet, key, manifest, parts)
    assert len(held) == len(set(held)) == 3 + len(parts)
    held.clear()
    with pytest.raises(chunks.AnnotationChunksError):
        collect(tmp_path, sheet, key, manifest, [parts[0]] * len(parts))
    assert held == []


def test_combined_byte_budget_refuses_before_returned_allocation(tmp_path, monkeypatch):
    import quantfit.safety.annotation_chunks as chunks

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    monkeypatch.setattr(chunks, "MAX_INPUT_BYTES", sum(path.stat().st_size for path in (sheet, key, manifest)) + 1)
    with pytest.raises(chunks.AnnotationChunksError):
        collect(tmp_path, sheet, key, manifest, parts)
    assert not (tmp_path / "complete.labels.csv").exists()


@pytest.mark.parametrize("mutation", ["bool", "float", "extra_key", "duplicate_json_key", "missing_row", "overlap"])
def test_manifest_types_and_returned_membership_are_exact(tmp_path, mutation):
    from quantfit.safety.annotation_chunks import AnnotationChunksError

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    document = json.loads(manifest.read_bytes())
    if mutation in {"bool", "float"}:
        document["annotation_chunk_schema"] = True if mutation == "bool" else 1.0
    elif mutation == "extra_key":
        document["extra"] = "PRIVATE_"
    elif mutation == "duplicate_json_key":
        raw = manifest.read_text()
        manifest.write_text(
            raw.replace('"annotation_chunk_schema": 1', '"annotation_chunk_schema": 1, "annotation_chunk_schema": 1')
        )
    else:
        rows = read_rows(parts[-1])
        if mutation == "missing_row":
            rows.pop()
        else:
            rows[-1] = read_rows(parts[0])[1]
        write_rows(parts[-1], rows)
    if mutation in {"bool", "float", "extra_key"}:
        manifest.write_text(json.dumps(document))
    with pytest.raises(AnnotationChunksError):
        collect(tmp_path, sheet, key, manifest, parts)
    assert not (tmp_path / "complete.labels.csv").exists()


def test_manifest_last_failure_preserves_new_parts_and_closes_stages(tmp_path, monkeypatch):
    import os

    from quantfit.safety import retention_io
    from quantfit.safety.annotation_chunks import MANIFEST_NAME, AnnotationChunksError, prepare_annotation_chunks

    sheet, key, directory = source(tmp_path)
    native = os.open

    def fail_manifest(path, flags, *args, **kwargs):
        if Path(path).name == MANIFEST_NAME and flags & os.O_EXCL:
            raise OSError("PRIVATE_native_cause")
        return native(path, flags, *args, **kwargs)

    monkeypatch.setattr(retention_io.os, "open", fail_manifest)
    with pytest.raises(AnnotationChunksError, match="^invalid_annotation_chunks$"):
        prepare_annotation_chunks(str(sheet), str(key), out_dir=str(directory), rows_per_part=5)
    assert len(list(directory.glob("*.labels.csv"))) == 4
    assert not (directory / MANIFEST_NAME).exists() and not list(directory.glob(".quantfit-retain-*"))


@pytest.mark.parametrize("race", ["output", "source"])
def test_publication_races_never_overwrite_existing_or_stale_inputs(tmp_path, monkeypatch, race):
    import quantfit.safety.annotation_chunks as chunks

    sheet, key, manifest, parts, _ = prepare(tmp_path)
    fill(parts)
    native = chunks.publish

    def raced(outputs, inputs):
        if race == "output":
            outputs[0][0].path.write_bytes(b"existing PRIVATE operator work")
        else:
            sheet.write_bytes(sheet.read_bytes() + b"\n")
        return native(outputs, inputs)

    monkeypatch.setattr(chunks, "publish", raced)
    with pytest.raises(chunks.AnnotationChunksError):
        collect(tmp_path, sheet, key, manifest, parts)
    out = tmp_path / "complete.labels.csv"
    assert (out.read_bytes() == b"existing PRIVATE operator work") if race == "output" else not out.exists()
    assert not (tmp_path / "collection.json").exists()


def test_named_second_attribution_is_explicit_not_authenticated(tmp_path):
    from quantfit.safety.annotation_chunks import AnnotationChunksError, prepare_annotation_chunks

    sheet, key, directory = source(tmp_path)
    with pytest.raises(AnnotationChunksError):
        prepare_annotation_chunks(str(sheet), str(key), out_dir=str(directory), annotator_role="named_second")
    result = prepare_annotation_chunks(
        str(sheet),
        str(key),
        out_dir=str(directory),
        annotator_role="named_second",
        annotator_name="Fictional fixture annotator",
    )
    assert result["annotator_declared"] == {"role": "named_second", "name": "Fictional fixture annotator"}
    assert result["limits"]["rater_identity_verified"] is False
