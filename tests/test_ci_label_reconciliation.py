"""Actual reconciliation CLI consumers; all private fixtures stay in pytest temporary directories."""

import csv
import importlib.util
import json
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "label_reconciliation_consumer", ROOT / "tools/ci_label_reconciliation.py"
)
assert SPEC is not None and SPEC.loader is not None
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


@pytest.fixture(autouse=True)
def no_model_or_calibration_work(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("reconciliation attempted inference, assets or calibration ingestion")

    for name in (
        "quantfit.safety.verify.verify_safety",
        "quantfit.safety.gguf_arm.resolve_pair",
        "huggingface_hub.hf_hub_download",
        "quantfit.safety.calibrate.ingest_labels",
    ):
        monkeypatch.setattr(name, forbidden)


def test_actual_cli_descriptive_disagreement_preserves_asymmetric_per_arm_matrix_and_private_bytes(tmp_path):
    first, second, key, expected = consumer.fixture(tmp_path / "private", ROOT)
    before = {p: p.read_bytes() for p in (first, second, key)}
    out = tmp_path / "aggregate.json"
    document, stderr = consumer.invoke(first, second, key, out)
    compact = consumer.check(document, first, second, key, expected)
    assert compact["arms"]["baseline"]["matrix"] == [[2, 1, 0], [0, 1, 2], [1, 0, 2]]
    assert compact["arms"]["quantized"]["matrix"] == [[0, 1, 2], [2, 0, 1], [1, 2, 0]]
    assert json.loads(out.read_bytes()) == document["result"]
    consumer.assert_private_not_reflected(document, stderr, before[key])
    assert all(p.read_bytes() == raw for p, raw in before.items())


def test_private_fixture_uses_native_blinding_and_fresh_salt_with_no_committed_inputs(tmp_path):
    from quantfit.safety.calibrate import _join, _read_key

    first, second, key, expected = consumer.fixture(tmp_path / "one", ROOT)
    _, _, other_key, _ = consumer.fixture(tmp_path / "two", ROOT)
    payload = _read_key(str(key))
    assert payload["salt"] != json.loads(other_key.read_bytes())["salt"]
    for path in (first, second):
        assert len(_join(str(path), str(key), payload["ids"])) == 18
        assert not path.resolve().is_relative_to(ROOT.resolve())
    assert expected["baseline"]["usable_agreement_rate"] == 0.75
    assert expected["quantized"]["usable_agreement_rate"] == 0.0


@pytest.mark.parametrize("mode", ["agreement", "unusable"])
@pytest.mark.parametrize("key_kind", ["bound-v2", "unbound-v2", "legacy-v1"])
def test_agreement_and_all_unusable_are_descriptive_zero_with_unverified_raters(tmp_path, mode, key_kind):
    first, second, key, expected = consumer.fixture(tmp_path / "private", ROOT, mode=mode, key_kind=key_kind)
    document, stderr = consumer.invoke(first, second, key, tmp_path / "aggregate.json")
    consumer.check(document, first, second, key, expected)
    consumer.assert_private_not_reflected(document, stderr, key.read_bytes())
    for arm in consumer.ARMS:
        assert document["result"]["arms"][arm]["usable_agreement_rate"] == (None if mode == "unusable" else 1.0)


def test_native_bom_quoted_multiline_and_reversed_row_order_preserve_directed_counts(tmp_path):
    first, second, key, expected = consumer.fixture(tmp_path / "private", ROOT, reverse_b=True, bom_b=True)
    assert second.read_bytes().startswith(b"\xef\xbb\xbf")
    document, _ = consumer.invoke(first, second, key, tmp_path / "aggregate.json")
    consumer.check(document, first, second, key, expected)


def test_swapping_sheets_transposes_each_asymmetric_arm_without_pooling(tmp_path):
    first, second, key, _ = consumer.fixture(tmp_path / "private", ROOT)
    expected = {arm: consumer.expected_arm(list(consumer.B[arm]), list(consumer.A[arm])) for arm in consumer.ARMS}
    document, _ = consumer.invoke(second, first, key, tmp_path / "swapped.json")
    consumer.check(document, second, first, key, expected)
    assert document["result"]["arms"]["baseline"]["matrix"] == [[2, 0, 1], [1, 1, 0], [0, 2, 2]]


@pytest.mark.parametrize("same_path", [True, False])
def test_identical_sheet_bytes_are_self_control_with_no_independence_claim(tmp_path, same_path):
    first, _, key, _ = consumer.fixture(tmp_path / "private", ROOT)
    second = first if same_path else tmp_path / "private/copy.labels.csv"
    if not same_path:
        second.write_bytes(first.read_bytes())
    expected = {arm: consumer.expected_arm(list(consumer.A[arm]), list(consumer.A[arm])) for arm in consumer.ARMS}
    document, _ = consumer.invoke(first, second, key, tmp_path / "self-control.json")
    assert consumer.check(document, first, second, key, expected)["identical_sheet_bytes"] is True


def test_maximum_complete_4096_pair_native_key_and_sheets_are_supported(tmp_path):
    first, second, key, expected = consumer.fixture(tmp_path / "private", ROOT, n=4096)
    assert key.stat().st_size <= 2097152 and max(first.stat().st_size, second.stat().st_size) <= 8388608
    document, _ = consumer.invoke(first, second, key, tmp_path / "maximum.json")
    assert consumer.check(document, first, second, key, expected)["n_rows"] == 8192


@pytest.mark.parametrize("key_kind", ["bound-v2", "unbound-v2", "legacy-v1"])
@pytest.mark.parametrize("mutation", ["bool-n", "missing-arm"])
def test_incomplete_population_precedes_sdk_validation_even_for_legacy_unbound_keys(tmp_path, key_kind, mutation):
    first, second, key, _ = consumer.fixture(tmp_path / "private", ROOT, key_kind=key_kind)
    payload = json.loads(key.read_bytes())
    if mutation == "bool-n":
        payload["capture"]["n_pairs"] = True
    else:
        del payload["ids"][next(row_id for row_id, entry in payload["ids"].items() if entry["arm"] == "baseline")]
    key.write_bytes(consumer.encode(payload))
    out = tmp_path / "refused.json"
    with patch(
        "quantfit.safety.calibrate._read_key", side_effect=AssertionError("SDK before population preflight")
    ) as sdk:
        document, _ = consumer.invoke(first, second, key, out)
    sdk.assert_not_called()
    assert document["exit_code"] == 2 and document["result"] is None and not out.exists()


@pytest.mark.parametrize("mutation", ["range", "duplicate-key", "nonfinite"])
def test_key_range_and_strict_json_preflight_refuse_before_sdk_without_private_reflection(tmp_path, mutation):
    from quantfit.safety.calibrate import _row_id

    first, second, key, _ = consumer.fixture(tmp_path / "private", ROOT, key_kind="legacy-v1")
    payload = json.loads(key.read_bytes())
    if mutation == "range":
        row_id, entry = next(iter(payload["ids"].items()))
        del payload["ids"][row_id]
        entry["pair"] = -1
        payload["ids"][_row_id(payload["salt"], entry["pair"], entry["arm"])] = entry
        raw = consumer.encode(payload)
    elif mutation == "duplicate-key":
        raw = consumer.encode(payload).replace(b'"key_schema": 1', b'"key_schema": 1, "key_schema": 1')
    else:
        raw = consumer.encode(payload).replace(b'"key_schema": 1', b'"private_number": NaN, "key_schema": 1')
    key.write_bytes(raw)
    out = tmp_path / "refused.json"
    with patch("quantfit.safety.calibrate._read_key", side_effect=AssertionError("SDK before syntax preflight")) as sdk:
        document, stderr = consumer.invoke(first, second, key, out)
    sdk.assert_not_called()
    assert document["exit_code"] == 2 and not out.exists()
    consumer.assert_private_not_reflected(document, stderr, raw)


def test_bound_capture_scope_contradiction_is_refused_by_authoritative_key_loader(tmp_path):
    from quantfit.safety import calibrate

    first, second, key, _ = consumer.fixture(tmp_path / "private", ROOT)
    payload = json.loads(key.read_bytes())
    payload["capture"]["baseline"] = consumer.MARKER
    key.write_bytes(consumer.encode(payload))
    with patch("quantfit.safety.calibrate._read_key", wraps=calibrate._read_key) as sdk:
        document, stderr = consumer.invoke(first, second, key, tmp_path / "refused.json")
    assert sdk.call_count == 1 and document["exit_code"] == 2
    consumer.assert_private_not_reflected(document, stderr, key.read_bytes())


@pytest.mark.parametrize(
    "mutation",
    [
        "empty-label",
        "bad-label",
        "duplicate-id",
        "missing-id",
        "unknown-id",
        "changed-value",
        "bad-header",
        "bad-utf8",
        "csv-error",
    ],
)
def test_invalid_sheet_identity_hash_labels_or_csv_refuse_without_private_diagnostics(tmp_path, mutation):
    first, second, key, _ = consumer.fixture(tmp_path / "private", ROOT)
    rows = consumer.read_rows(second)
    if mutation == "empty-label":
        rows[1][2] = ""
    elif mutation == "bad-label":
        rows[1][2] = consumer.MARKER
    elif mutation == "duplicate-id":
        rows.append(rows[1])
    elif mutation == "missing-id":
        rows.pop()
    elif mutation == "unknown-id":
        rows[1][0] = consumer.MARKER
    elif mutation == "changed-value":
        rows[1][1] += " changed"
    elif mutation == "bad-header":
        rows[0].append(consumer.MARKER)
    consumer.write_rows(second, rows)
    if mutation == "bad-utf8":
        second.write_bytes(b"\xff")
    elif mutation == "csv-error":
        second.write_bytes(b"id,completion,human_label\n" + b"x" * (csv.field_size_limit() + 1))
    before = {p: p.read_bytes() for p in (first, second, key)}
    out = tmp_path / "refused.json"
    document, stderr = consumer.invoke(first, second, key, out)
    assert document["exit_code"] == 2 and document["result"] is None and not out.exists()
    consumer.assert_private_not_reflected(document, stderr, key.read_bytes())
    assert all(p.read_bytes() == raw for p, raw in before.items())


@pytest.mark.parametrize("alias", ["sheet_a", "sheet_b", "key", "outside-hardlink"])
def test_output_aliases_preserve_private_original_bytes(tmp_path, alias):
    first, second, key, _ = consumer.fixture(tmp_path / "private", ROOT)
    output = {"sheet_a": first, "sheet_b": second, "key": key, "outside-hardlink": tmp_path / "outside.json"}[alias]
    if alias == "outside-hardlink":
        os.link(key, output)
    before = {p: p.read_bytes() for p in (first, second, key)}
    document, stderr = consumer.invoke(first, second, key, output)
    assert document["exit_code"] == 2 and all(p.read_bytes() == raw for p, raw in before.items())
    consumer.assert_private_not_reflected(document, stderr, key.read_bytes())


@pytest.mark.parametrize("input_name", ["key", "sheet_a", "sheet_b"])
def test_actual_input_byte_bounds_refuse_before_sdk_key_parsing(tmp_path, input_name):
    first, second, key, _ = consumer.fixture(tmp_path / "private", ROOT)
    target = {"key": key, "sheet_a": first, "sheet_b": second}[input_name]
    limit = 2097152 if input_name == "key" else 8388608
    raw = target.read_bytes()
    target.write_bytes(raw + b" " * (limit + 1 - len(raw)))
    with patch("quantfit.safety.calibrate._read_key", side_effect=AssertionError("SDK before byte preflight")) as sdk:
        document, _ = consumer.invoke(first, second, key, tmp_path / "refused.json")
    sdk.assert_not_called()
    assert document["exit_code"] == 2


def test_exact_key_byte_limit_uses_original_bytes_and_supports_valid_padding(tmp_path):
    first, second, key, expected = consumer.fixture(tmp_path / "private", ROOT)
    raw = key.read_bytes()
    key.write_bytes(raw + b" " * (2097152 - len(raw)))
    document, _ = consumer.invoke(first, second, key, tmp_path / "aggregate.json")
    assert consumer.check(document, first, second, key, expected)["inputs"]["key"]["size_bytes"] == 2097152


def test_csv_record_budget_counts_header_and_blank_records_while_preserving_multiline_fields(tmp_path):
    first, second, key, expected = consumer.fixture(tmp_path / "private", ROOT)
    records = len(consumer.read_rows(second))
    second.write_bytes(second.read_bytes() + b"\n" * (16385 - records))
    document, _ = consumer.invoke(first, second, key, tmp_path / "boundary.json")
    consumer.check(document, first, second, key, expected)
    second.write_bytes(second.read_bytes() + b"\n")
    refused, stderr = consumer.invoke(first, second, key, tmp_path / "refused.json")
    assert refused["exit_code"] == 2
    consumer.assert_private_not_reflected(refused, stderr, key.read_bytes())


def test_committed_aggregate_record_preserves_matrices_hash_links_and_private_provenance_limits():
    data = ROOT / "validation/2026-10-18-label-reconciliation"
    receipt = json.loads((data / "receipt.json").read_bytes())
    directed = {"baseline": [[2, 1, 0], [0, 1, 2], [1, 0, 2]], "quantized": [[0, 1, 2], [2, 0, 1], [1, 2, 0]]}
    diagonal = [[3, 0, 0], [0, 3, 0], [0, 0, 3]]
    unusable = [[0, 0, 0], [0, 0, 0], [0, 0, 9]]
    cases = {
        "directed": directed,
        "bom-reordered": directed,
        "unbound-v2": directed,
        "legacy-v1": directed,
        "swapped": {arm: [list(row) for row in zip(*matrix, strict=True)] for arm, matrix in directed.items()},
        "agreement": dict.fromkeys(consumer.ARMS, diagonal),
        "self-control": dict.fromkeys(consumer.ARMS, diagonal),
        "all-unusable": dict.fromkeys(consumer.ARMS, unusable),
    }
    for name, matrices in cases.items():
        document = json.loads((data / f"{name}-cli.json").read_bytes())
        result = json.loads((data / f"{name}.json").read_bytes())
        compact = receipt[name]
        assert document["result"] == result and document["exit_code"] == compact["exit_code"] == 0
        assert result["kind"] == "quantfit.label-reconciliation" and result["label_reconciliation_schema_version"] == 1
        assert result["n_pairs"] == compact["n_pairs"] == 9 and result["n_rows"] == compact["n_rows"] == 18
        assert result["label_order"] == ["refusal", "compliance", "unusable"]
        assert result["inputs"] == compact["inputs"] and result["arms"] == compact["arms"]
        assert result["identical_sheet_bytes"] is (name in {"agreement", "self-control", "all-unusable"})
        assert set(result["inputs"]) == {"sheet_a", "sheet_b", "key"}
        for bound in result["inputs"].values():
            assert set(bound) == {"sha256", "size_bytes"} and re.fullmatch("[0-9a-f]{64}", bound["sha256"])
            assert type(bound["size_bytes"]) is int and bound["size_bytes"] > 0
        for arm, matrix in matrices.items():
            counts = result["arms"][arm]
            assert counts["matrix"] == matrix and counts["n_rows"] == sum(map(sum, matrix)) == 9
            usable = sum(matrix[i][j] for i in range(2) for j in range(2))
            agreement = matrix[0][0] + matrix[1][1]
            assert counts["n_both_usable"] == usable and counts["n_usable_agreement"] == agreement
            assert counts["n_usable_disagreement"] == usable - agreement
            assert counts["n_one_unusable"] == sum(matrix[2][j] + matrix[j][2] for j in range(2))
            assert counts["n_both_unusable"] == matrix[2][2]
            assert counts["usable_agreement_rate"] == (agreement / usable if usable else None)
        for field in (
            "rater_identity_verified",
            "human_labels_authenticated",
            "independence_verified",
            "consensus_calibration",
            "scientific_go",
        ):
            assert result[field] is False
    for name in ("missing-id", "changed-value", "invalid-legacy-population", "record-budget", "output-alias"):
        refused = json.loads((data / f"{name}-refusal.json").read_bytes())
        assert refused["exit_code"] == receipt[name]["exit_code"] == 2 and refused["result"] is None
        assert receipt[name]["private_bytes_unchanged"] is True
    assert receipt["invalid-legacy-population"]["sdk_key_parse_calls"] == 0
    assert receipt["limits"]["private_inputs_published"] is receipt["limits"]["per_row_identifiers_published"] is False
    assert receipt["limits"]["private_provenance_limit"] and "Fresh" in receipt["limits"]["reproduction"]
    # The private input buffers are intentionally absent: hashes identify this local run, not their contents.
    assert (
        not list(data.rglob("*.labels.csv"))
        and not list(data.rglob("*.labelkey.json"))
        and not list(data.rglob("*.capture.jsonl"))
    )
    # Recorded source bindings are historical, never compared to the future installed package.
    assert len(receipt["runtime"]["source_files"]) == 6
    assert receipt["runtime"]["source_version"] == receipt["runtime"]["distribution_version"] == "0.36.0"
