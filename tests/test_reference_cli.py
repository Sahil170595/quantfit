"""Offline reference-byte checks; all supplied registry entries here are synthetic."""

import hashlib
import json

import pytest

from quantfit.cli import main


def registry(tmp_path, *, revision="a" * 40):
    report = tmp_path / "fixture-report.json"
    report.write_text('{"fixture_only":true,"count":1}\n', encoding="utf-8")
    entry = {
        "slug": "fixture",
        "baseline": "fixture/baseline",
        "quant": "fixture/quant",
        "stratum": "gguf",
        "spec_version": "v0",
        "quantfit_version": "0.15.1",
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "hf_repo_type": "dataset",
        "hf_repo": "fixture/references",
        "hf_path": "fixture.json",
        "hf_revision": revision,
    }
    path = tmp_path / "fixture-registry.json"
    path.write_text(json.dumps({"refreport_schema_version": 1, "reports": [entry]}), encoding="utf-8")
    return path, report, entry


def test_official_registry_list_is_empty_without_loading_models(capsys):
    assert main(["references", "list", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["n_registered"] == 0 and result["official_registry"]
    assert "screen has not run" not in result["registry_state"]


def test_external_registry_is_explicit_and_checks_exact_bytes(tmp_path, capsys):
    path, report, entry = registry(tmp_path)
    assert main(["references", "list", "--registry", str(path), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)["result"]
    assert not result["official_registry"] and not result["publication_verified"]
    assert result["reports"][0]["entry"]["slug"] == "fixture"
    record = result["reports"][0]
    assert record["publication_verified"] is False
    assert record["citable"] is False
    assert "declared_spec_validity" in record
    assert "still_citable_at_its_own_spec_version" not in record
    assert result["reports"][0]["hf_url"].endswith("/blob/" + "a" * 40 + "/fixture.json")
    assert (
        main(["references", "verify", "--registry", str(path), "--slug", "fixture", "--report", str(report), "--json"])
        == 0
    )
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["matches"] and result["expected_sha256"] == entry["report_sha256"]
    assert result["declared_reference_citable"] is True and result["citable"] is False
    assert "authenticates" not in result["statement"]
    report.write_text('{"fixture_only":true,"count":2}\n', encoding="utf-8")
    assert (
        main(["references", "verify", "--registry", str(path), "--slug", "fixture", "--report", str(report), "--json"])
        == 3
    )
    result = json.loads(capsys.readouterr().out)["result"]
    assert not result["matches"] and result["citable"] is False


@pytest.mark.parametrize(
    "mutation", ["unknown", "duplicate", "nan", "bool_version", "extra_entry", "mutable_revision", "cap"]
)
def test_external_registry_rejects_untrusted_shapes(tmp_path, capsys, mutation):
    path, _, entry = registry(tmp_path)
    payload = json.loads(path.read_text())
    if mutation == "unknown":
        payload["unknown"] = 1
    elif mutation == "duplicate":
        path.write_text('{"refreport_schema_version":1,"refreport_schema_version":1,"reports":[]}', encoding="utf-8")
    elif mutation == "nan":
        entry["report_sha256"] = float("nan")
    elif mutation == "bool_version":
        payload["refreport_schema_version"] = True
    elif mutation == "extra_entry":
        entry["extra"] = "ignored?"
    elif mutation == "mutable_revision":
        entry["hf_revision"] = "main"
    elif mutation == "cap":
        payload["reports"] *= 4
    if mutation in {"nan", "extra_entry", "mutable_revision"}:
        payload["reports"] = [entry]
    if mutation != "duplicate":
        path.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["references", "list", "--registry", str(path), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]


def test_missing_reference_and_unpinned_manifest_are_explicit(tmp_path, capsys):
    assert main(["references", "verify", "--slug", "none", "--report", "none.json", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]
    path, _, _ = registry(tmp_path, revision=None)
    assert main(["references", "list", "--registry", str(path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["reports"][0]["hf_url"] is None
