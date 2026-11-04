"""Full-population recipient packets over unchanged native collection."""

import csv
import importlib
import io
import json
import os
import re
import subprocess
import sys

import pytest
from test_annotation_chunks import prepare


def packet_payload(path):
    raw = path.read_bytes()
    match = re.search(rb'<script type="application/json" id="annotation-data">(.*?)</script>', raw, re.DOTALL)
    assert match is not None
    return json.loads(match[1])


def test_native_complete_blind_and_chunks_positive(tmp_path):
    _sheet, key, _manifest, parts, result = prepare(tmp_path)
    ids = json.loads(key.read_bytes())["ids"]
    assert result["n_pairs"] == 9 and result["n_rows"] == 18 and result["n_parts"] == 4
    allrows = []
    for part in parts:
        allrows.extend(list(csv.reader(io.StringIO(part.read_bytes().decode("utf-8-sig"), newline="")))[1:])
    assert len(allrows) == 18 and {row[0] for row in allrows} == set(ids)
    assert all(row[2] == "" for row in allrows)
    assert {(entry["pair"], entry["arm"]) for entry in ids.values()} == {
        (i, arm) for i in range(9) for arm in ("baseline", "quantized")
    }


def test_private_packets_retain_every_assigned_row_without_unblinding(tmp_path):
    sheet, key, manifest, parts, native = prepare(tmp_path)
    output = tmp_path / "recipient"
    output.mkdir()
    api = importlib.import_module("quantfit.safety.annotation_packets")
    result = api.prepare_annotation_packets(str(sheet), str(key), str(manifest), out_dir=str(output))
    pages = sorted(output.glob("*.annotation.html"))
    assert len(pages) == native["n_parts"] == 4 and result["n_rows"] == 18
    expected = []
    for part in parts:
        expected.extend(
            [row[:2] for row in list(csv.reader(io.StringIO(part.read_bytes().decode("utf-8-sig"), newline="")))[1:]]
        )
    actual = []
    for index, page in enumerate(pages, 1):
        data = packet_payload(page)
        assert set(data) == {"annotation_packet_schema", "rows", "filename", "max_csv_bytes"}
        assert data["annotation_packet_schema"] == 1 and data["filename"] == f"part-{index:04d}.labels.csv"
        assert data["max_csv_bytes"] == 8 * 1024 * 1024
        actual.extend(data["rows"])
    assert actual == expected and len({row[0] for row in actual}) == 18
    salt = json.loads(key.read_bytes())["salt"]
    assert all(salt.encode() not in page.read_bytes() for page in pages)


def test_actual_os_cli_packet_producer(tmp_path):
    sheet, key, manifest, _parts, _native = prepare(tmp_path)
    output = tmp_path / "recipient"
    output.mkdir()
    argv = [
        sys.executable,
        "-B",
        "-X",
        "utf8",
        "-m",
        "quantfit.cli",
        "calibrate",
        "chunks",
        "packets",
        "--sheet",
        str(sheet),
        "--key",
        str(key),
        "--manifest",
        str(manifest),
        "--out-dir",
        str(output),
        "--json",
    ]
    child = subprocess.run(
        argv, capture_output=True, cwd=tmp_path, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), check=False
    )
    (tmp_path / "cli.stdout.log").write_bytes(child.stdout)
    (tmp_path / "cli.stderr.log").write_bytes(child.stderr)
    assert child.returncode == 0, child.stderr.decode(errors="replace")
    data = json.loads(child.stdout)
    assert data["result"]["annotation_packets_schema"] == 1 and data["result"]["n_rows"] == 18
    assert len(list(output.glob("*.annotation.html"))) == 4


@pytest.mark.parametrize("completion", ["plain", "left\nright", "left\rright"])
def test_native_chunk_collection_preserves_exact_control_text(tmp_path, completion):
    from quantfit.safety import calibrate
    from quantfit.safety.annotation_chunks import collect_annotation_chunks, prepare_annotation_chunks

    capture = tmp_path / "fictional.capture.jsonl"
    sheet = tmp_path / "blank.labels.csv"
    key = tmp_path / "private.labelkey.json"
    header = {
        "capture_schema": 1,
        "created_utc": "2026-11-02T00:00:00Z",
        "baseline": "fictional/base",
        "quant": "fictional/quant",
        "n_pairs": 1,
    }
    rows = [{"pair": 0, "arm": arm, "judge_refusal": False, "completion": completion} for arm in calibrate.ARMS]
    capture.write_text("\n".join(json.dumps(value) for value in (header, *rows)) + "\n", encoding="utf-8")
    calibrate.build_labeling_sheet(str(capture), str(sheet), str(key))
    directory = tmp_path / "parts"
    directory.mkdir()
    prepare_annotation_chunks(str(sheet), str(key), out_dir=str(directory), rows_per_part=2)
    original = list(csv.reader(io.StringIO(sheet.read_bytes().decode("utf-8-sig"), newline="")))
    filled = tmp_path / "returned.labels.csv"
    buf = io.StringIO(newline="")
    csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
        [original[0], *[[*row[:2], "refusal"] for row in original[1:]]]
    )
    filled.write_bytes(buf.getvalue().encode())
    out = tmp_path / "collected.labels.csv"
    receipt = tmp_path / "collection.json"
    result = collect_annotation_chunks(
        str(sheet),
        str(key),
        str(directory / "annotation.chunkmanifest.json"),
        (str(filled),),
        out_path=str(out),
        receipt_path=str(receipt),
    )
    assert result["n_rows"] == 2
    assert [row["completion"] for row in calibrate._read_sheet(str(out))] == [completion] * 2


def native_source(tmp_path, *, completions=None, judges=None, size=3):
    """Native salted blind from a complete fictional capture; no judge/model work."""
    from quantfit.safety import calibrate
    from quantfit.safety.annotation_chunks import prepare_annotation_chunks

    completion_values = completions or ["same completion"] * 8
    n = len(completion_values) // 2
    decisions = judges or [False] * len(completion_values)
    capture = tmp_path / "fictional.capture.jsonl"
    sheet = tmp_path / "blank.labels.csv"
    key = tmp_path / "private.labelkey.json"
    header = {
        "capture_schema": 1,
        "created_utc": "2026-11-02T00:00:00Z",
        "baseline": "fictional/base",
        "quant": "fictional/quant",
        "n_pairs": n,
    }
    records = [
        {"pair": i, "arm": arm, "judge_refusal": decisions[2 * i + j], "completion": completion_values[2 * i + j]}
        for i in range(n)
        for j, arm in enumerate(calibrate.ARMS)
    ]
    capture.write_text("\n".join(json.dumps(value) for value in (header, *records)) + "\n", encoding="utf-8")
    calibrate.build_labeling_sheet(str(capture), str(sheet), str(key))
    parts = tmp_path / "parts"
    parts.mkdir()
    prepare_annotation_chunks(str(sheet), str(key), out_dir=str(parts), rows_per_part=size)
    out = tmp_path / "recipient"
    out.mkdir()
    return sheet, key, parts / "annotation.chunkmanifest.json", out


def returned_from_packets(pages, destination, label="refusal"):
    destination.mkdir()
    result = []
    for page in pages:
        data = packet_payload(page)
        path = destination / data["filename"]
        buf = io.StringIO(newline="")
        csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
            [["id", "completion", "human_label"], *[[*row, label] for row in data["rows"]]]
        )
        path.write_bytes(buf.getvalue().encode())
        result.append(str(path))
    return tuple(result)


@pytest.mark.parametrize("judges", [[False] * 8, [True, True, False, False, True, False, False, True]])
def test_zero_flags_concordant_and_duplicate_text_are_not_filtered(tmp_path, judges):
    from quantfit.safety.annotation_chunks import collect_annotation_chunks
    from quantfit.safety.annotation_packets import prepare_annotation_packets
    from quantfit.safety.calibrate import ingest_labels

    sheet, key, manifest, out = native_source(tmp_path, judges=judges)
    entries = json.loads(key.read_bytes())["ids"]
    bypair = {i: {} for i in range(4)}
    for row in entries.values():
        bypair[row["pair"]][row["arm"]] = row["judge_refusal"]
    assert sum(p["baseline"] != p["quantized"] for p in bypair.values()) == (0 if len(set(judges)) == 1 else 2)
    result = prepare_annotation_packets(str(sheet), str(key), str(manifest), out_dir=str(out))
    payloadrows = [row for page in sorted(out.glob("*.annotation.html")) for row in packet_payload(page)["rows"]]
    assert result["n_rows"] == 8 and len(payloadrows) == len({row[0] for row in payloadrows}) == 8
    assert {row[1] for row in payloadrows} == {"same completion"}
    filled = returned_from_packets(sorted(out.glob("*.annotation.html")), tmp_path / "returned")
    full = tmp_path / "full.labels.csv"
    collect_annotation_chunks(
        str(sheet), str(key), str(manifest), filled, out_path=str(full), receipt_path=str(tmp_path / "collection.json")
    )
    calibrated = ingest_labels(str(full), str(key), str(tmp_path / "calibration.json"))
    assert calibrated["n_labeled"] == 8 and calibrated["n_unusable"] == 0


HOSTILE = [
    "bare\rreturn",
    "crlf\r\ntext",
    "nul\x00text",
    "emoji 😀 漢字",
    "</script><script>throw 1</script>",
    '"quoted",=HYPERLINK("https://invalid")',
]


@pytest.mark.parametrize("text", HOSTILE)
def test_exact_hostile_strings_through_native_collection_and_both_ingests(tmp_path, text):
    from quantfit.safety.annotation_chunks import collect_annotation_chunks
    from quantfit.safety.annotation_packets import prepare_annotation_packets
    from quantfit.safety.calibrate import _read_sheet, ingest_labels
    from quantfit.safety.retained_labels import extract_labels, ingest_retained_labels

    sheet, key, manifest, out = native_source(tmp_path, completions=[text] * 8)
    originals = {p: p.read_bytes() for p in (sheet, key, manifest)}
    prepare_annotation_packets(str(sheet), str(key), str(manifest), out_dir=str(out))
    pages = sorted(out.glob("*.annotation.html"))
    assert all(row[1] == text for p in pages for row in packet_payload(p)["rows"])
    assert all(b"</script><script>throw 1" not in p.read_bytes() for p in pages)
    parts = returned_from_packets(pages, tmp_path / "returned")
    full = tmp_path / "full.labels.csv"
    collect_annotation_chunks(
        str(sheet), str(key), str(manifest), parts, out_path=str(full), receipt_path=str(tmp_path / "collection.json")
    )
    assert [row["completion"] for row in _read_sheet(str(full))] == [text] * 8
    direct = ingest_labels(str(full), str(key), str(tmp_path / "direct.json"))
    retained = tmp_path / "retained.labels.csv"
    receipt = tmp_path / "retention.json"
    extract_labels(str(full), str(key), out_path=str(retained), receipt_path=str(receipt))
    stripped = ingest_retained_labels(str(retained), str(receipt), str(key), out_path=str(tmp_path / "retained.json"))
    assert (
        direct["calibration_schema"] == 2
        and stripped["calibration_schema"] == 3
        and direct["n_labeled"] == stripped["n_labeled"] == 8
    )
    assert all(p.read_bytes() == raw for p, raw in originals.items())


@pytest.mark.parametrize(
    "mutation",
    [
        "partial",
        "foreign",
        "duplicate",
        "text",
        "header",
        "manifest_bool",
        "manifest_float",
        "manifest_extra",
        "wrong_key",
        "nonempty",
        "missingdir",
    ],
)
def test_whole_invalid_sources_refuse_before_any_packet(tmp_path, mutation):
    from quantfit.safety.annotation_packets import AnnotationPacketsError, prepare_annotation_packets

    sheet, key, manifest, out = native_source(tmp_path)
    if mutation in ("partial", "foreign", "duplicate", "text", "header"):
        rows = list(csv.reader(io.StringIO(sheet.read_bytes().decode("utf-8-sig"), newline="")))
        if mutation == "partial":
            rows[-1][2] = "refusal"
        elif mutation == "foreign":
            rows[-1][0] = "foreign"
        elif mutation == "duplicate":
            rows[-1] = rows[1]
        elif mutation == "text":
            rows[-1][1] += "changed"
        else:
            rows[0].append("extra")
        buf = io.StringIO(newline="")
        csv.writer(buf).writerows(rows)
        sheet.write_bytes(buf.getvalue().encode())
    elif mutation.startswith("manifest_"):
        d = json.loads(manifest.read_bytes())
        if mutation == "manifest_bool":
            d["annotation_chunk_schema"] = True
        elif mutation == "manifest_float":
            d["rows_per_part"] = float(d["rows_per_part"])
        else:
            d["extra"] = "forbidden"
        manifest.write_text(json.dumps(d))
    elif mutation == "wrong_key":
        d = json.loads(key.read_bytes())
        d["salt"] += "x"
        key.write_text(json.dumps(d))
    elif mutation == "nonempty":
        (out / "sentinel").write_bytes(b"held")
    else:
        out = out / "absent"
    before = {p.name: p.read_bytes() for p in out.iterdir()} if out.exists() else None
    with pytest.raises(AnnotationPacketsError, match="^invalid_annotation_packets$"):
        prepare_annotation_packets(str(sheet), str(key), str(manifest), out_dir=str(out))
    assert ({p.name: p.read_bytes() for p in out.iterdir()} if out.exists() else None) == before


def test_stored_preparation_version_is_not_current_producer_requirement(tmp_path):
    from quantfit.safety import annotation_chunks as chunks
    from quantfit.safety.annotation_packets import prepare_annotation_packets
    from quantfit.safety.retained_labels import _encode

    sheet, key, manifest, out = native_source(tmp_path)
    inputs = chunks._held((str(sheet), str(key)), (chunks.MAX_SHEET_BYTES, chunks.MAX_KEY_BYTES))
    prior, _, _ = chunks._preparation(inputs, 3, {"role": "maintainer", "name": None}, "0.42.0")
    manifest.write_bytes(_encode(prior))
    result = prepare_annotation_packets(str(sheet), str(key), str(manifest), out_dir=str(out))
    assert result["n_rows"] == 8 and result["quantfit_version"] != "0.42.0"


@pytest.mark.parametrize(
    "boundary",
    ["part", "remaining", "fullsheet", "collection_receipt", "collection_output", "page", "all_output", "receipt"],
)
def test_whole_roundtrip_and_render_bounds_refuse_without_partial_pages(tmp_path, monkeypatch, boundary):
    from quantfit.safety import annotation_chunks as chunks
    from quantfit.safety import annotation_packets as packets

    sheet, key, manifest, out = native_source(tmp_path)
    if boundary == "part":
        monkeypatch.setattr(packets, "_worst_part", lambda rows, label: chunks.MAX_SHEET_BYTES + 1)
    elif boundary == "remaining":
        monkeypatch.setattr(chunks, "MAX_INPUT_BYTES", sum(p.stat().st_size for p in (sheet, key, manifest)) + 1)
    elif boundary == "fullsheet":

        def refuse(rows):
            raise RuntimeError("native full sheet limit")

        monkeypatch.setattr(packets, "_csv", refuse)
    elif boundary == "collection_receipt":
        monkeypatch.setattr(packets, "MAX_RECEIPT_BYTES", 1)
    elif boundary == "collection_output":
        monkeypatch.setattr(chunks, "MAX_OUTPUT_BYTES", 1)
    elif boundary == "page":
        monkeypatch.setattr(packets, "MAX_PAGE_BYTES", 1)
    elif boundary == "all_output":
        monkeypatch.setattr(packets, "MAX_OUTPUT_BYTES", 1)
    else:
        monkeypatch.setattr(packets, "MAX_RECEIPT_BYTES", 1)
    with pytest.raises(packets.AnnotationPacketsError):
        packets.prepare_annotation_packets(str(sheet), str(key), str(manifest), out_dir=str(out))
    assert not list(out.iterdir())


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_exact_complete_filled_parts_fit_actual_remaining_collector_budget(tmp_path, monkeypatch, delta):
    from quantfit.safety import annotation_chunks as chunks
    from quantfit.safety.annotation_packets import AnnotationPacketsError, prepare_annotation_packets

    sheet, key, manifest, out = native_source(tmp_path)
    values = json.loads(manifest.read_bytes())
    total = 0
    for part in values["parts"]:
        rows = list(csv.reader(io.StringIO((manifest.parent / part["filename"]).read_bytes().decode(), newline="")))
        buf = io.StringIO(newline="")
        csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
            [rows[0], *[[*row[:2], "compliance"] for row in rows[1:]]]
        )
        total += len(buf.getvalue().encode())
    held = sum(p.stat().st_size for p in (sheet, key, manifest))
    monkeypatch.setattr(chunks, "MAX_INPUT_BYTES", held + total + delta)
    if delta < 0:
        with pytest.raises(AnnotationPacketsError):
            prepare_annotation_packets(str(sheet), str(key), str(manifest), out_dir=str(out))
        assert not list(out.iterdir())
    else:
        result = prepare_annotation_packets(str(sheet), str(key), str(manifest), out_dir=str(out))
        assert result["native_roundtrip_bounds"]["worst_all_filled_parts_bytes"] == total
        assert result["native_roundtrip_bounds"]["remaining_collector_input_bytes"] == total + delta
        returned = returned_from_packets(sorted(out.glob("*.annotation.html")), tmp_path / "returned", "compliance")
        native = chunks.collect_annotation_chunks(
            str(sheet),
            str(key),
            str(manifest),
            returned,
            out_path=str(tmp_path / "full.labels.csv"),
            receipt_path=str(tmp_path / "collection.json"),
        )
        assert native["n_rows"] == 8


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_actual_native_fullsheet_8MiB_boundary_is_admitted_before_pages(tmp_path, delta):
    from quantfit.safety import annotation_chunks as chunks
    from quantfit.safety.annotation_packets import AnnotationPacketsError, prepare_annotation_packets

    measure = tmp_path / "measure"
    measure.mkdir()
    small, _, _, _ = native_source(measure, completions=[""] * 128, size=64)
    # Native source writer uses CRLF; full collection uses LF.128longest labels
    # add1280bytes and129record terminators save129: full output is source+1151.
    target_source_bytes = chunks.MAX_SHEET_BYTES - 1151 + delta
    text_bytes = target_source_bytes - small.stat().st_size
    work = tmp_path / "boundary"
    work.mkdir()
    sheet, key, manifest, out = native_source(
        work, completions=["x" * (text_bytes // 128 + (i < text_bytes % 128)) for i in range(128)], size=64
    )
    assert sheet.stat().st_size == target_source_bytes
    rows = list(csv.reader(io.StringIO(sheet.read_bytes().decode(), newline="")))
    full = io.StringIO(newline="")
    csv.writer(full, lineterminator="\n").writerows([rows[0], *[[*row[:2], "compliance"] for row in rows[1:]]])
    assert len(full.getvalue().encode()) == chunks.MAX_SHEET_BYTES + delta
    assert all(
        (manifest.parent / p["filename"]).stat().st_size < chunks.MAX_SHEET_BYTES
        for p in json.loads(manifest.read_bytes())["parts"]
    )
    if delta > 0:
        with pytest.raises(AnnotationPacketsError):
            prepare_annotation_packets(str(sheet), str(key), str(manifest), out_dir=str(out))
        assert not list(out.iterdir())
    else:
        result = prepare_annotation_packets(str(sheet), str(key), str(manifest), out_dir=str(out))
        assert result["native_roundtrip_bounds"]["worst_reconstructed_sheet_bytes"] == chunks.MAX_SHEET_BYTES + delta
        assert len(list(out.glob("*.annotation.html"))) == 2
