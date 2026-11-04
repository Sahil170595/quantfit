"""Two-judge diagnostics preserve whole canonical cells and native denominators."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("judges_native_fixture", ROOT / "tools/ci_calibration_judges.py")
assert SPEC and SPEC.loader
fixture_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture_module)


def sources(tmp_path):
    return fixture_module.fixture(tmp_path / "a", ROOT, "a"), fixture_module.fixture(tmp_path / "b", ROOT, "b")


def test_native_producers_and_both_own_receivers_are_positive(tmp_path):
    from quantfit.safety.calibrate import ingest_labels
    from quantfit.safety.calibration_inputs import load_calibration_inputs
    from quantfit.safety.calibration_strata import _group
    from quantfit.safety.retained_labels import ingest_retained_labels

    a, b = sources(tmp_path)
    ka, kb = (json.loads(side["key"].read_bytes()) for side in (a, b))
    assert ka["salt"] != kb["salt"] and set(ka["ids"]).isdisjoint(kb["ids"])
    for index, side in enumerate((a, b)):
        full = load_calibration_inputs(str(side["capture"]), str(side["key"]), sheet_path=str(side["sheet"]))
        retained = load_calibration_inputs(
            str(side["capture"]),
            str(side["key"]),
            retained_labels_path=str(side["retained"]),
            retention_receipt_path=str(side["receipt"]),
        )
        assert full.n_pairs == 8 and full.rows == retained.rows and len(full.rows) == 16
        report = ingest_labels(str(side["sheet"]), str(side["key"]), str(tmp_path / f"full-{index}.json"))
        retained_report = ingest_retained_labels(
            str(side["retained"]),
            str(side["receipt"]),
            str(side["key"]),
            out_path=str(tmp_path / f"retained-{index}.json"),
        )
        for arm, block in _group(full.rows)["arms"].items():
            assert report[arm] == retained_report[arm] == block


def test_public_api_compares_the_complete_two_judge_population(tmp_path):
    from quantfit.safety.calibration_judges import analyze_calibration_judges

    a, b = sources(tmp_path)
    result = analyze_calibration_judges(
        str(a["capture"]),
        str(a["key"]),
        str(b["capture"]),
        str(b["key"]),
        sheet_a=str(a["sheet"]),
        sheet_b=str(b["sheet"]),
        out_path=str(tmp_path / "judges.json"),
    )
    assert result["n_pairs"] == 8 and result["n_rows_per_judge"] == 16


def test_cli_compares_the_complete_two_judge_population(tmp_path):
    a, b = sources(tmp_path)
    argv = [
        sys.executable,
        "-B",
        "-m",
        "quantfit.cli",
        "calibrate",
        "compare-judges",
        "--capture-a",
        str(a["capture"]),
        "--key-a",
        str(a["key"]),
        "--sheet-a",
        str(a["sheet"]),
        "--capture-b",
        str(b["capture"]),
        "--key-b",
        str(b["key"]),
        "--sheet-b",
        str(b["sheet"]),
        "--out",
        str(tmp_path / "cli.json"),
        "--json",
    ]
    child = subprocess.run(argv, cwd=tmp_path, stdin=subprocess.DEVNULL, capture_output=True, check=False)
    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout)["result"]["n_pairs"] == 8


def receive(a, b, out, modes=("full", "full")):
    from quantfit.safety.calibration_judges import analyze_calibration_judges

    kwargs = {}
    for name, side, mode in zip(("a", "b"), (a, b), modes, strict=True):
        if mode == "full":
            kwargs[f"sheet_{name}"] = str(side["sheet"])
        else:
            kwargs[f"retained_labels_{name}"] = str(side["retained"])
            kwargs[f"retention_receipt_{name}"] = str(side["receipt"])
    return analyze_calibration_judges(
        str(a["capture"]), str(a["key"]), str(b["capture"]), str(b["key"]), out_path=str(out), **kwargs
    )


@pytest.mark.parametrize(
    "modes", [("full", "full"), ("retained", "retained"), ("full", "retained"), ("retained", "full")]
)
def test_all_modes_match_native_denominators_and_full_cell_tables(tmp_path, modes):
    from quantfit.safety.calibration_inputs import load_calibration_inputs
    from quantfit.safety.calibration_strata import _group

    a, b = sources(tmp_path)
    result = receive(a, b, tmp_path / "out.json", modes)
    native = {
        name: _group(
            load_calibration_inputs(str(side["capture"]), str(side["key"]), sheet_path=str(side["sheet"])).rows
        )
        for name, side in (("a", a), ("b", b))
    }
    assert result["native_per_judge"] == native
    assert result["truth_coverage"] == {
        "denominator_pairs": 8,
        "both_usable": 3,
        "baseline_only": 2,
        "quantized_only": 2,
        "neither_usable": 1,
    }
    for arm in ("baseline", "quantized"):
        table = result["per_arm"][arm]
        assert sum(map(sum, table["judge_a_by_judge_b"])) == table["whole_n"] == 8
        assert sum(map(sum, table["error_a_by_error_b"])) == table["usable_truth_n"] == 5
        assert table["error_a_margin"] == native["a"]["arms"][arm]["judge_errors"]
        assert table["error_b_margin"] == native["b"]["arms"][arm]["judge_errors"]
    assert result["per_arm"]["baseline"]["judge_a_by_judge_b"] == [[2, 2], [2, 2]]
    assert result["per_arm"]["baseline"]["error_a_by_error_b"] == [[1, 1], [2, 1]]
    assert result["per_arm"]["quantized"]["error_a_by_error_b"] == [[2, 1], [2, 0]]
    assert result["sources"]["a"]["original_sheet"]["held_and_validated"] == (modes[0] == "full")
    assert result["sources"]["b"]["original_sheet"]["held_and_validated"] == (modes[1] == "full")
    raw = json.dumps(result)
    assert fixture_module.MARKER not in raw
    for side in (a, b):
        key = json.loads(side["key"].read_bytes())
        assert key["salt"] not in raw and all(value not in raw for value in key["ids"])
        assert all(str(path) not in raw for path in side.values())
    assert result["scientific_go"] is result["replaces_calibration"] is result["independence_verified"] is False


def test_self_control_keeps_full_flags_and_zero_offdiagonal_errors(tmp_path):
    a, _ = sources(tmp_path)
    result = receive(a, a, tmp_path / "self.json")
    for table in result["per_arm"].values():
        assert table["flag_disagreements"] == 0
        assert table["error_a_by_error_b"][0][1] == table["error_a_by_error_b"][1][0] == 0


def test_all_unusable_is_descriptive_null_but_old_ingest_still_refuses(tmp_path):
    from quantfit.safety.calibrate import CalibrationError, ingest_labels

    sides = [
        fixture_module.fixture(tmp_path / side, ROOT, side, base_truth=("unusable",) * 8, quant_truth=("unusable",) * 8)
        for side in ("a", "b")
    ]
    result = receive(*sides, tmp_path / "unusable.json", modes=("retained", "retained"))
    assert result["truth_coverage"]["neither_usable"] == 8
    for group in result["native_per_judge"].values():
        for block in group["arms"].values():
            assert block["n"] == 0 and block["epsilon"] is None and block["epsilon_wilson95"] == [0, 1]
    for table in result["per_arm"].values():
        assert table["whole_n"] == table["unusable_truth_n"] == 8 and table["usable_truth_n"] == 0
        assert table["error_a_by_error_b"] == [[0, 0], [0, 0]]
    with pytest.raises(CalibrationError):
        ingest_labels(str(sides[0]["sheet"]), str(sides[0]["key"]), str(tmp_path / "not-calibration.json"))


@pytest.mark.parametrize("mutation", ["strings", "truth", "zone", "expected", "bool-int", "float-int"])
def test_individually_valid_sides_cannot_contradict_common_population_or_scope(tmp_path, mutation):
    from quantfit.safety.calibration_judges import CalibrationJudgesError

    a = fixture_module.fixture(tmp_path / "a", ROOT, "a", scope_marker=1)
    options = {"scope_marker": 1}
    if mutation == "strings":
        options["content_suffix"] = "CHANGED_PRIVATE_CONTENT"
    elif mutation == "truth":
        options["base_truth"] = ("refusal", *fixture_module.BASE_TRUTH[1:])
    elif mutation == "zone":
        options["zones"] = ("clear_safe", *("borderline",) * 7)
    elif mutation == "expected":
        options["expected"] = ("safe", *("safe" if i % 2 else "unsafe" for i in range(1, 8)))
    elif mutation == "bool-int":
        options["scope_marker"] = True
    else:
        options["scope_marker"] = 1.0
    b = fixture_module.fixture(tmp_path / "b", ROOT, "b", **options)
    out = tmp_path / "refused.json"
    with pytest.raises(CalibrationJudgesError, match="^invalid_calibration_judges$") as error:
        receive(a, b, out)
    assert error.value.__cause__ is None and not out.exists()


@pytest.mark.parametrize(
    "mutation", ["capture", "key", "receipt", "late_extra_csv", "duplicate_csv", "missing_csv", "input_contract"]
)
def test_native_own_binding_and_every_csv_cell_are_required(tmp_path, mutation):
    from quantfit.safety.calibration_judges import CalibrationJudgesError

    a, b = sources(tmp_path)
    modes = ("full", "full")
    if mutation == "capture":
        a["capture"].write_bytes(a["capture"].read_bytes() + b" ")
    elif mutation == "key":
        a["key"].write_bytes(b["key"].read_bytes())
    elif mutation == "receipt":
        a["receipt"].write_bytes(b["receipt"].read_bytes())
        modes = ("retained", "retained")
    elif mutation == "input_contract":
        from quantfit.safety.calibration_binding import identity_fingerprint

        rows = [json.loads(line) for line in a["capture"].read_bytes().splitlines()]
        rows[0]["binding"]["identity"]["judge"]["input_contract"] = "unsupported full prompt"
        rows[0]["binding"]["fingerprint"] = identity_fingerprint(rows[0]["binding"]["identity"])
        a["capture"].write_bytes(("\n".join(json.dumps(row) for row in rows) + "\n").encode())
    else:
        import csv
        import io

        rows = list(csv.reader(io.StringIO(a["sheet"].read_text(), newline="")))
        if mutation == "late_extra_csv":
            rows.append(["unknown", "PRIVATE_EXTRA", "unusable"])
        elif mutation == "duplicate_csv":
            rows.append(rows[1])
        else:
            rows.pop()
        stream = io.StringIO(newline="")
        csv.writer(stream).writerows(rows)
        a["sheet"].write_bytes(stream.getvalue().encode())
    out = tmp_path / "invalid.json"
    with pytest.raises(CalibrationJudgesError):
        receive(a, b, out, modes)
    assert not out.exists()


def test_cached_physical_hold_still_charges_both_logical_suites(tmp_path, monkeypatch):
    import quantfit.safety.calibration_judges as module

    a, _ = sources(tmp_path)
    original, calls = module.hold, []

    def count(path, limit):
        calls.append(path)
        return original(path, limit)

    monkeypatch.setattr(module, "hold", count)
    total = 2 * sum(a[role].stat().st_size for role in ("capture", "key", "sheet"))
    monkeypatch.setattr(module, "MAX_INPUT_BYTES", total)
    receive(a, a, tmp_path / "exact.json")
    assert len(calls) == 3
    monkeypatch.setattr(module, "MAX_INPUT_BYTES", total - 1)
    monkeypatch.setattr(module, "_group", lambda _: pytest.fail("math before complete admission"))
    with pytest.raises(module.CalibrationJudgesError):
        receive(a, a, tmp_path / "over.json")
    assert not (tmp_path / "over.json").exists()


def test_both_modes_are_admitted_before_any_hold(tmp_path, monkeypatch):
    import quantfit.safety.calibration_judges as module

    monkeypatch.setattr(module, "hold", lambda *_: pytest.fail("IO before both modes admitted"))
    with pytest.raises(module.CalibrationJudgesError):
        module.analyze_calibration_judges(
            "missing",
            "missing",
            "missing",
            "missing",
            sheet_a="a",
            sheet_b="b",
            retained_labels_b="also-b",
            retention_receipt_b="receipt",
            out_path=str(tmp_path / "out.json"),
        )


def test_whole_cli_envelope_is_admitted_before_file_publication(tmp_path, monkeypatch):
    import quantfit.safety.calibration_judges as module

    a, b = sources(tmp_path)
    result = receive(a, b, tmp_path / "first.json")
    monkeypatch.setattr(module, "MAX_JUDGES_BYTES", len(module._encode(result)))
    with pytest.raises(module.CalibrationJudgesError):
        receive(a, b, tmp_path / "envelope-too-large.json")
    assert not (tmp_path / "envelope-too-large.json").exists()


def test_output_alias_and_existing_file_are_never_overwritten(tmp_path):
    from quantfit.safety.calibration_judges import CalibrationJudgesError

    a, b = sources(tmp_path)
    for path in (*a.values(), *b.values()):
        before = path.read_bytes()
        with pytest.raises(CalibrationJudgesError):
            receive(a, b, path)
        assert path.read_bytes() == before
    existing = tmp_path / "existing.json"
    existing.write_bytes(b"KEEP")
    with pytest.raises(CalibrationJudgesError):
        receive(a, b, existing)
    assert existing.read_bytes() == b"KEEP"


def test_retained_long_capture_does_not_enter_csv_but_supplied_csv_keeps_native_limit(tmp_path):
    import csv

    from quantfit.safety.calibration_judges import CalibrationJudgesError

    limit = csv.field_size_limit()
    try:
        csv.field_size_limit(300000)
        a = fixture_module.fixture(tmp_path / "a", ROOT, "a", content_suffix="x" * 131073)
        b = fixture_module.fixture(tmp_path / "b", ROOT, "b", content_suffix="x" * 131073)
    finally:
        csv.field_size_limit(limit)
    receive(a, b, tmp_path / "retained-long.json", ("retained", "retained"))
    with pytest.raises(CalibrationJudgesError):
        receive(a, b, tmp_path / "full-long.json")


def test_two_own_valid_unsupported_input_contracts_are_not_admitted(tmp_path):
    from quantfit.safety.calibration_inputs import load_calibration_inputs
    from quantfit.safety.calibration_judges import CalibrationJudgesError

    sides = [
        fixture_module.fixture(tmp_path / side, ROOT, side, input_contract="fictional other judge inputs")
        for side in ("a", "b")
    ]
    for side in sides:
        assert (
            len(load_calibration_inputs(str(side["capture"]), str(side["key"]), sheet_path=str(side["sheet"])).rows)
            == 16
        )
    with pytest.raises(CalibrationJudgesError):
        receive(*sides, tmp_path / "unsupported.json")


def test_input_changed_after_parsing_refuses_publication_and_removes_owned_stage(tmp_path, monkeypatch):
    from quantfit.safety import calibration_judges as module

    a, b = [fixture_module.fixture(tmp_path / side, ROOT, side) for side in ("a", "b")]
    publish = module.publish

    def changed(outputs, held):
        a["key"].write_bytes(a["key"].read_bytes() + b" ")
        publish(outputs, held)

    monkeypatch.setattr(module, "publish", changed)
    with pytest.raises(module.CalibrationJudgesError, match="^invalid_calibration_judges$"):
        receive(a, b, tmp_path / "not-published.json")
    assert not (tmp_path / "not-published.json").exists()
    assert not list(tmp_path.glob(".quantfit-retain-*"))


def test_hardlinked_private_input_refused_without_modifying_either_name(tmp_path):
    import os

    from quantfit.safety.calibration_judges import CalibrationJudgesError

    a, b = [fixture_module.fixture(tmp_path / side, ROOT, side) for side in ("a", "b")]
    raw = a["key"].read_bytes()
    alias = tmp_path / "hardlink.json"
    os.link(a["key"], alias)
    with pytest.raises(CalibrationJudgesError):
        receive(a, b, tmp_path / "not-published.json")
    assert a["key"].read_bytes() == alias.read_bytes() == raw
