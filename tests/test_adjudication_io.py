"""Native held-once, private IO, bounded outputs and explicit CLI admission."""

import csv
import io
import json

import pytest


@pytest.mark.parametrize("extra", [0, 1])
def test_prepare_refuses_completion_beyond_native_csv_field_domain(tmp_path, extra):
    import csv
    import json

    from test_adjudication import filled, fixture

    from quantfit.adjudication_record import AdjudicationError
    from quantfit.safety.adjudication import apply_adjudication, prepare_adjudication

    report, capture = fixture(tmp_path / "private")
    lines = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
    lines[1]["completion"] = "x" * (csv.field_size_limit() + extra)
    capture.write_text("\n".join(json.dumps(row) for row in lines) + "\n", encoding="utf-8")
    queue, receipt = tmp_path / "review.adjudication.csv", tmp_path / "private.adjudication-preparation.json"
    if extra == 0:
        prepare_adjudication(str(report), str(capture), review_path=str(queue), receipt_path=str(receipt))
        filled(queue)
        result = apply_adjudication(
            str(report), str(capture), str(queue), str(receipt), out_path=str(tmp_path / "adjudication.json")
        )
        assert len(result["entries"]) == 8
        return
    with pytest.raises(AdjudicationError, match="^invalid_adjudication$"):
        prepare_adjudication(str(report), str(capture), review_path=str(queue), receipt_path=str(receipt))
    assert not queue.exists() and not receipt.exists()


from test_adjudication import filled, fixture, prepared
from test_adjudication_adverse import applied


@pytest.mark.parametrize("role", range(4))
def test_every_actual_apply_input_is_protected_from_output_alias(tmp_path, role):
    from quantfit.adjudication_record import AdjudicationError
    from quantfit.safety.adjudication import apply_adjudication

    report, capture, queue, preparation, _ = prepared(tmp_path)
    filled(queue)
    paths = (report, capture, queue, preparation)
    before = [p.read_bytes() for p in paths]
    with pytest.raises(AdjudicationError):
        apply_adjudication(*map(str, paths), out_path=str(paths[role]))
    assert [p.read_bytes() for p in paths] == before


@pytest.mark.parametrize("mutation", ["source", "target"])
def test_late_source_change_or_target_race_never_overwrites(tmp_path, monkeypatch, mutation):
    import quantfit.safety.adjudication as producer
    from quantfit.adjudication_record import AdjudicationError

    report, capture, queue, preparation, _ = prepared(tmp_path)
    filled(queue)
    out = tmp_path / "record.json"
    native = producer.publish

    def race(outputs, inputs):
        if mutation == "source":
            capture.write_bytes(capture.read_bytes() + b"\n")
        else:
            out.write_bytes(b"existing")
        return native(outputs, inputs)

    monkeypatch.setattr(producer, "publish", race)
    with pytest.raises(AdjudicationError):
        producer.apply_adjudication(str(report), str(capture), str(queue), str(preparation), out_path=str(out))
    assert out.read_bytes() == b"existing" if mutation == "target" else not out.exists()


def test_producer_holds_each_original_role_once_per_operation(tmp_path, monkeypatch):
    import quantfit.safety.adjudication as producer

    report, capture = fixture(tmp_path / "private")
    native = producer.hold
    calls = []

    def held(path, limit):
        calls.append(path)
        return native(path, limit)

    monkeypatch.setattr(producer, "hold", held)
    queue, preparation = tmp_path / "private.adjudication.csv", tmp_path / "p.json"
    producer.prepare_adjudication(str(report), str(capture), review_path=str(queue), receipt_path=str(preparation))
    assert calls == [str(report), str(capture)]
    calls.clear()
    filled(queue)
    producer.apply_adjudication(
        str(report), str(capture), str(queue), str(preparation), out_path=str(tmp_path / "record.json")
    )
    assert calls == [str(report), str(capture), str(queue), str(preparation)]


def test_bom_reordered_multiline_queue_retains_exact_text_and_selection(tmp_path):
    from quantfit.safety.adjudication import apply_adjudication

    report, capture, queue, preparation, blank = prepared(tmp_path)
    filled(queue)
    rows = list(csv.reader(io.StringIO(queue.read_text(encoding="utf-8"), newline="")))
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\r\n").writerows([rows[0], *reversed(rows[1:])])
    queue.write_bytes(b"\xef\xbb\xbf" + stream.getvalue().encode())
    record = apply_adjudication(
        str(report), str(capture), str(queue), str(preparation), out_path=str(tmp_path / "record.json")
    )
    assert [r["pair"] for r in record["entries"]] == list(range(8))
    assert record["inputs"]["review_queue"] != blank["review_queue"]


@pytest.mark.parametrize("bound", ["capture", "queue", "record"])
def test_named_byte_caps_refuse_before_publication(tmp_path, monkeypatch, bound):
    import quantfit.safety.adjudication as producer
    from quantfit.adjudication_record import AdjudicationError

    if bound == "capture":
        report, capture = fixture(tmp_path / "private")
        monkeypatch.setattr(producer, "MAX_CAPTURE_BYTES", 1)
        with pytest.raises(AdjudicationError):
            producer.prepare_adjudication(
                str(report), str(capture), review_path=str(tmp_path / "q.csv"), receipt_path=str(tmp_path / "p.json")
            )
        assert not (tmp_path / "q.csv").exists()
    else:
        report, capture, queue, preparation, _ = prepared(tmp_path)
        filled(queue)
        monkeypatch.setattr(producer, "MAX_QUEUE_BYTES" if bound == "queue" else "MAX_RECORD_BYTES", 1)
        with pytest.raises(AdjudicationError):
            producer.apply_adjudication(
                str(report), str(capture), str(queue), str(preparation), out_path=str(tmp_path / "record.json")
            )
        assert not (tmp_path / "record.json").exists()


def test_modelcard_no_file_output_still_has_a_byte_cap(tmp_path, monkeypatch):
    import quantfit.adjudication_record as receiving
    from quantfit.modelcard import model_card_fragment

    report, _capture, path, _ = applied(tmp_path)
    monkeypatch.setattr(receiving, "MAX_CARD_BYTES", 1)
    with pytest.raises(receiving.AdjudicationError):
        model_card_fragment(str(report), adjudication_record=str(path))


@pytest.mark.parametrize("args", [[], ["prepare"], ["apply"], ["prepare", "--report", "missing"]])
def test_complete_adjudication_cli_leaves_required(args):
    from quantfit.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["adjudicate", *args])
    assert exc.value.code == 2


def test_modelcard_has_no_invented_out_flag():
    from quantfit.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["emit", "model-card", "--report", "missing", "--adjudication", "missing", "--out", "wrong"])
    assert exc.value.code == 2


def test_invalid_cli_emits_categorical_error_and_no_private_text(tmp_path, capsys):
    from quantfit.cli import main

    assert (
        main(
            [
                "adjudicate",
                "prepare",
                "--report",
                str(tmp_path / "PRIVATE_missing"),
                "--capture",
                "missing",
                "--review",
                str(tmp_path / "q.csv"),
                "--receipt",
                str(tmp_path / "p.json"),
                "--json",
            ]
        )
        == 2
    )
    emitted = capsys.readouterr()
    value = json.loads(emitted.out)
    assert value["error"]["message"] == "invalid_adjudication" and value["result"] is None
    assert "PRIVATE_" not in emitted.out + emitted.err
