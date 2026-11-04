from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("review_page_fixtures", ROOT / "tools/ci_adjudication_review.py")
assert spec and spec.loader
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.mark.parametrize("text", [None, "left\rright", "left\0right"], ids=["ordinary", "bare-cr", "nul"])
def test_unchanged_native_prepare_blank_read_regeneration_and_apply(tmp_path, text):
    result = helper.native_roundtrip(ROOT, tmp_path, text)
    assert result["original_n"] == 12 and result["selected"] == 8
    assert result["blank_read_exact"] and result["regeneration_byte_exact"] and result["native_apply_completed"]


def test_actual_public_page_api_gap(tmp_path):
    paths = helper.fixture(tmp_path, ROOT)
    from quantfit.safety.adjudication_review import render_adjudication_review

    receipt = render_adjudication_review(
        str(paths["queue"]), str(paths["preparation"]), out_path=str(tmp_path / "private.adjudication.html")
    )
    assert receipt["n_selected"] == 8


def test_actual_os_cli_page_workflow_gap(tmp_path):
    paths = helper.fixture(tmp_path, ROOT)
    child = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "quantfit.cli",
            "adjudicate",
            "review-page",
            "--review",
            str(paths["queue"]),
            "--preparation",
            str(paths["preparation"]),
            "--out",
            str(tmp_path / "private.adjudication.html"),
            "--json",
        ],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    assert child.returncode == 0


def page(paths, out):
    from quantfit.safety.adjudication_review import render_adjudication_review

    return render_adjudication_review(str(paths["queue"]), str(paths["preparation"]), out_path=str(out))


def write_queue(paths, rows):
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    paths["queue"].write_bytes(stream.getvalue().encode())
    preparation = json.loads(paths["preparation"].read_bytes())
    preparation["review_queue"] = {
        "sha256": hashlib.sha256(paths["queue"].read_bytes()).hexdigest(),
        "size_bytes": len(paths["queue"].read_bytes()),
    }
    paths["preparation"].write_text(json.dumps(preparation))


@pytest.mark.parametrize("mode", ["mixed", "all", "zero"])
def test_complete_private_json_and_native_quote_all_bound(tmp_path, mode):
    from quantfit.safety.adjudication import COLUMNS
    from quantfit.safety.adjudication_review import _triplets

    text = 'PRIVATE_ </script><img src="https://invalid.example">\r\nLF\nCR\rNUL\0 astral \U0001f600'
    paths = helper.fixture(tmp_path, ROOT, text, mode)
    before = {name: p.read_bytes() for name, p in paths.items()}
    out = tmp_path / "private.adjudication.html"
    receipt = page(paths, out)
    raw = out.read_bytes()
    encoded = raw.split(b'id="review-data">', 1)[1].split(b"</script>", 1)[0]
    payload = json.loads(encoded)
    assert b"<" not in encoded and b"\0" not in raw and raw.isascii()
    assert len(payload["rows"]) == receipt["n_selected"] == (0 if mode == "zero" else 8)
    assert all(row[4] == text for row in payload["rows"])
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for row in payload["rows"]:
        choice = max(_triplets()[row[1]], key=lambda values: sum(len(v.encode()) + v.count('"') + 2 for v in values))
        writer.writerow([*row, *choice])
    assert len(stream.getvalue().encode()) == receipt["worst_filled_csv_bytes"]
    assert receipt["source_verified"] is receipt["human_confirmation_verified"] is receipt["scientific_go"] is False
    assert text not in json.dumps(receipt) and all(str(p) not in json.dumps(receipt) for p in paths.values())
    assert all(p.read_bytes() == before[name] for name, p in paths.items())


@pytest.mark.parametrize(
    "mutation",
    [
        "schema-bool",
        "n-bool",
        "n-large",
        "selected-float",
        "selected-negative",
        "count-bool",
        "count-float",
        "count-sum",
        "count-extra",
        "producer-int",
        "proof-int",
        "scope",
        "extra",
        "hash",
    ],
)
def test_closed_typed_preparation_refusals(tmp_path, mutation):
    from quantfit.safety.adjudication_review import AdjudicationReviewError

    paths = helper.fixture(tmp_path, ROOT)
    value = json.loads(paths["preparation"].read_bytes())
    axis = "refusal-robustness"
    if mutation == "schema-bool":
        value["adjudication_preparation_schema"] = True
    if mutation == "n-bool":
        value["n_probes"] = True
    if mutation == "n-large":
        value["n_probes"] = 4097
    if mutation == "selected-float":
        value["n_selected"] = 8.0
    if mutation == "selected-negative":
        value["n_selected"] = -1
    if mutation == "count-bool":
        value["original_flagged_counts"][axis] = True
    if mutation == "count-float":
        value["original_flagged_counts"][axis] = 4.0
    if mutation == "count-sum":
        value["original_flagged_counts"][axis] = 3
    if mutation == "count-extra":
        value["original_flagged_counts"]["extra"] = 0
    if mutation == "producer-int":
        value["producer_checks"]["capture_held"] = 1
    if mutation == "proof-int":
        value["proof_limits"]["receiver_capture_read"] = 0
    if mutation == "scope":
        value["scope"] = "source authenticated"
    if mutation == "extra":
        value["extra"] = "PRIVATE_"
    if mutation == "hash":
        value["review_queue"]["sha256"] = "0" * 64
    paths["preparation"].write_text(json.dumps(value))
    out = tmp_path / "refused.adjudication.html"
    with pytest.raises(AdjudicationReviewError, match="^invalid_adjudication_review$"):
        page(paths, out)
    assert not out.exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "header",
        "width",
        "pair-spelling",
        "pair-range",
        "duplicate",
        "missing",
        "nonblank",
        "whitespace",
        "zone",
        "axis",
        "expected",
        "late-records",
    ],
)
def test_all_blank_csv_rows_checked_after_fresh_hash_binding(tmp_path, mutation):
    from quantfit.safety.adjudication_review import AdjudicationReviewError

    paths = helper.fixture(tmp_path, ROOT)
    rows = list(csv.reader(io.StringIO(paths["queue"].read_bytes().decode(), newline="")))
    if mutation == "header":
        rows[0][0] = "bad"
    if mutation == "width":
        rows[-1].append("PRIVATE_")
    if mutation == "pair-spelling":
        rows[-1][0] = "07"
    if mutation == "pair-range":
        rows[-1][0] = "12"
    if mutation == "duplicate":
        rows[-1][0] = rows[1][0]
    if mutation == "missing":
        rows.pop()
    if mutation == "nonblank":
        rows[-1][6] = "refusal"
    if mutation == "whitespace":
        rows[-1][8] = " "
    if mutation == "zone":
        rows[-1][2] = "unknown"
    if mutation == "axis":
        rows[-1][1] = "unknown"
    if mutation == "expected":
        rows[-1][3] = "unsafe"
    if mutation == "late-records":
        rows.extend([[]] * 8193)
    write_queue(paths, rows)
    with pytest.raises(AdjudicationReviewError):
        page(paths, tmp_path / "refused.adjudication.html")


def test_preparation_consistency_does_not_invent_actual_membership(tmp_path):
    from quantfit.adjudication_record import AdjudicationError
    from quantfit.safety.adjudication import apply_adjudication

    paths = helper.fixture(tmp_path, ROOT)
    rows = list(csv.reader(io.StringIO(paths["queue"].read_bytes().decode(), newline="")))
    rows[1][0] = "8"  # Actual original capture pair8 is not selected; page has no capture.
    write_queue(paths, rows)
    assert page(paths, tmp_path / "consistent.adjudication.html")["source_verified"] is False
    for row in rows[1:]:
        row[6:] = ["unusable", "unusable", "unresolved"]
    stream = io.StringIO(newline="")
    csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(rows)
    filled = tmp_path / "filled.adjudication.csv"
    filled.write_bytes(stream.getvalue().encode())
    with pytest.raises(AdjudicationError):
        apply_adjudication(
            str(paths["report"]),
            str(paths["capture"]),
            str(filled),
            str(paths["preparation"]),
            out_path=str(tmp_path / "record.json"),
        )


def test_exact_html_and_worst_filled_limits_refuse_whole_publication(tmp_path, monkeypatch):
    from quantfit.safety import adjudication_review as module

    paths = helper.fixture(tmp_path, ROOT)
    out = tmp_path / "first.adjudication.html"
    receipt = page(paths, out)
    raw = out.read_bytes()
    monkeypatch.setattr(module, "MAX_PAGE_BYTES", len(raw))
    page(paths, tmp_path / "exact.adjudication.html")
    monkeypatch.setattr(module, "MAX_PAGE_BYTES", len(raw) - 1)
    with pytest.raises(module.AdjudicationReviewError):
        page(paths, tmp_path / "too-large.adjudication.html")
    monkeypatch.setattr(module, "MAX_PAGE_BYTES", 32 * 1024 * 1024)
    cap = receipt["worst_filled_csv_bytes"] - 1
    assert len(paths["queue"].read_bytes()) <= cap
    monkeypatch.setattr(module, "MAX_QUEUE_BYTES", cap)
    with pytest.raises(module.AdjudicationReviewError):
        page(paths, tmp_path / "csv-too-large.adjudication.html")
    assert (
        not (tmp_path / "too-large.adjudication.html").exists()
        and not (tmp_path / "csv-too-large.adjudication.html").exists()
    )


def test_roles_once_target_before_parse_and_private_suffix_before_io(tmp_path, monkeypatch):
    from quantfit.safety import adjudication_review as module

    paths = helper.fixture(tmp_path, ROOT)
    actual_hold = module.hold
    calls = []

    def held(path, limit):
        calls.append((str(path), limit))
        return actual_hold(path, limit)

    monkeypatch.setattr(module, "hold", held)
    page(paths, tmp_path / "good.adjudication.html")
    assert calls == [(str(paths["queue"]), 16 * 1024 * 1024), (str(paths["preparation"]), 64 * 1024)]
    calls.clear()
    with pytest.raises(module.AdjudicationReviewError):
        page(paths, tmp_path / "wrong.html")
    assert calls == []
    occupied = tmp_path / "existing.adjudication.html"
    occupied.write_bytes(b"KEEP")

    def forbidden(*args):
        raise AssertionError("parse before output admission")

    monkeypatch.setattr(module, "_preparation_structure", forbidden)
    with pytest.raises(module.AdjudicationReviewError):
        page(paths, occupied)
    assert occupied.read_bytes() == b"KEEP"


def test_input_changed_before_publish_refuses_and_closes_stage(tmp_path, monkeypatch):
    from quantfit.safety import adjudication_review as module

    paths = helper.fixture(tmp_path, ROOT)
    publish = module.publish

    def changed(outputs, held):
        paths["queue"].write_bytes(paths["queue"].read_bytes() + b" ")
        publish(outputs, held)

    monkeypatch.setattr(module, "publish", changed)
    out = tmp_path / "refused.adjudication.html"
    with pytest.raises(module.AdjudicationReviewError):
        page(paths, out)
    assert not out.exists() and not list(tmp_path.glob(".quantfit-retain-*"))


def test_old_declared_preparation_version_remains_loadable(tmp_path):
    paths = helper.fixture(tmp_path, ROOT)
    value = json.loads(paths["preparation"].read_bytes())
    value["quantfit_version"] = "0.46.0"
    paths["preparation"].write_text(json.dumps(value))
    assert page(paths, tmp_path / "old.adjudication.html")["preparation_consistent"] is True
