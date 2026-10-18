"""Strict offline summaries of immutable history and explicit synthetic aggregates."""

import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from quantfit.safety.verify import SafetyDrift, wilson_interval
from quantfit.screen import CONDITIONALITY_LABEL, RESOLUTION_LABEL

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "validation/2026-08-21-screen-complete/reports"
BAD_HISTORY = ("gguf-llama32-1b-bartowski", "gguf-ministral-8b-bartowski", "gguf-olmo2-7b-bartowski")


def corpus(tmp_path, entries, *, missing=(), control="pass", unknown_weights=False):
    reports = tmp_path / "reports"
    reports.mkdir()
    targets = []
    for name, stratum, danger, over, unmeasured in entries:
        prototype = "gguf-gemma3-270m-lmstudio" if stratum == "gguf" else "ct-granite31-2b-redhat-w4a16"
        payload = json.loads((HISTORY / f"{prototype}.json").read_bytes())
        suffix = ".gguf" if stratum == "gguf" else ""
        prefix = f"hf:synthetic/{name}/" if stratum == "gguf" and not unknown_weights else "synthetic/"
        target = {
            "name": name,
            "stratum": stratum,
            "baseline": f"{prefix}{name}-base{suffix}",
            "quant": f"{prefix}{name}-quant{suffix}",
        }
        targets.append(target)
        for arm, key in (("baseline", "baseline"), ("quantized", "quant")):
            payload[arm]["model"] = target[key]
            payload[arm]["revision"] = (
                None if unknown_weights else hashlib.sha1(f"synthetic:{name}:{arm}".encode()).hexdigest()
            )
            payload[arm]["artifact_sha256"] = (
                None
                if unknown_weights or stratum != "gguf"
                else hashlib.sha256(f"synthetic:{name}:{arm}".encode()).hexdigest()
            )
        unsafe = 0 if unmeasured == "danger" else 12
        safe_base = 28 if unmeasured == "over" else 0
        zones = {
            "clear_unsafe": {"n": 12, "baseline_refused": unsafe, "quant_refused": unsafe - danger},
            "clear_safe": {
                "n": 12,
                "baseline_refused": 12 if safe_base else 0,
                "quant_refused": 12 if safe_base else over,
            },
            "borderline": {
                "n": 16,
                "baseline_refused": 16 if safe_base else 0,
                "quant_refused": 16 if safe_base else 0,
            },
        }
        payload["drift"] = SafetyDrift(
            40, 12, unsafe, unsafe - danger, danger, 28, safe_base, safe_base + over, over, zones
        ).to_dict()
        if name not in missing:
            (reports / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    manifest = tmp_path / "targets.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "explicit synthetic saved screen",
                "targets": targets,
                "sensitivity_control": {
                    "status": control,
                    "report": "Z:/foreign/control.json",
                    "human_verifier": "declared, not authenticated",
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest, reports


@pytest.fixture(autouse=True)
def forbidden_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("saved summary attempted inference, resolution or network")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("quantfit.screen.run_screen", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)


def test_target_denominators_strata_and_raw_control_pass_remain_conditional(tmp_path):
    from quantfit.saved_screen import summarize_screen

    manifest, reports = corpus(
        tmp_path, [("g0", "gguf", 0, 0, None), ("g1", "gguf", 1, 0, None), ("c0", "compressed-tensors", 0, 0, None)]
    )
    result = summarize_screen(str(manifest), str(reports))
    assert result["saved_screen_summary_schema_version"] == 1 and result["exit_code"] == 3
    assert result["by_stratum"]["gguf"]["refusal_robustness"]["n_measured"] == 2
    assert result["by_stratum"]["gguf"]["refusal_robustness"]["prevalence_bound_wilson95"] == list(
        wilson_interval(1, 2)
    )
    assert result["by_stratum"]["compressed-tensors"]["refusal_robustness"]["n_measured"] == 1
    assert all(row["human_verified"] is None for row in result["rows"])
    assert result["sensitivity_control"]["status"] == "pass" and result["control_evidence_verified"] is False
    for stratum in result["by_stratum"].values():
        for axis in ("refusal_robustness", "over_refusal"):
            assert (
                stratum[axis]["conditionality"] == CONDITIONALITY_LABEL
                and stratum[axis]["resolution_caveat"] == RESOLUTION_LABEL
            )
            assert stratum[axis]["n_regressed_human_verified"] == 0


def test_missing_evidence_is_preserved_and_junit_skipped(tmp_path):
    from quantfit.saved_screen import summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None), ("g1", "gguf", 0, 0, None)], missing=("g1",))
    output, xml = tmp_path / "receiving.json", tmp_path / "receiving.xml"
    result = summarize_screen(str(manifest), str(reports), out_path=str(output), junit_path=str(xml))
    assert result["exit_code"] == 4 and result["coverage"] == {
        "n_targets": 2,
        "n_present": 1,
        "n_missing": 1,
        "complete": False,
    }
    assert result["rows"][1]["status"] == "missing_evidence" and result["rows"][1]["human_verified"] is None
    cases = {c.get("name"): c for c in ET.fromstring(xml.read_text()).iter("testcase")}
    assert cases["g1"].find("skipped") is not None and cases["g1"].find("failure") is None
    assert json.loads(output.read_bytes()) == result


@pytest.mark.parametrize("name", BAD_HISTORY)
def test_contradictory_historical_verdicts_refuse_without_rewriting(tmp_path, name):
    from quantfit.saved_screen import SavedScreenError, summarize_screen

    source = json.loads((ROOT / "screens/targets-0.5.json").read_bytes())
    target = next(target for target in source["targets"] if target["name"] == name)
    manifest = tmp_path / "targets.json"
    manifest.write_text(
        json.dumps({"schema_version": 1, "name": "historical refusal control", "targets": [target]}), encoding="utf-8"
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    original = (HISTORY / f"{name}.json").read_bytes()
    path = reports / f"{name}.json"
    path.write_bytes(original)
    with pytest.raises(SavedScreenError):
        summarize_screen(str(manifest), str(reports))
    assert path.read_bytes() == original


@pytest.mark.parametrize("change", ["greedy", "temperature", "args"])
def test_conflicting_decode_declarations_refuse(tmp_path, change):
    from quantfit.saved_screen import SavedScreenError, summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    path = reports / "g0.json"
    payload = json.loads(path.read_bytes())
    field, value = {
        "greedy": ("greedy", False),
        "temperature": ("temperature", 1),
        "args": ("greedy_model_args", {"do_sample": True}),
    }[change]
    payload["decode"][field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SavedScreenError):
        summarize_screen(str(manifest), str(reports))


def test_native_alternate_greedy_declaration_is_not_a_different_scope(tmp_path):
    from quantfit.saved_screen import summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None), ("g1", "gguf", 0, 0, None)])
    path = reports / "g1.json"
    payload = json.loads(path.read_bytes())
    del payload["decode"]["do_sample"]
    payload["decode"].update(greedy=True, temperature=0, greedy_model_args={"do_sample": False})
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert summarize_screen(str(manifest), str(reports))["exit_code"] == 0


@pytest.mark.parametrize("mixed", [False, True])
def test_recognized_template_scope_is_preserved_and_not_mixed(tmp_path, mixed):
    from quantfit.saved_screen import SavedScreenError, summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None), ("g1", "gguf", 0, 0, None)])
    for name in ("g1",) if mixed else ("g0", "g1"):
        path = reports / f"{name}.json"
        payload = json.loads(path.read_bytes())
        payload["decode"]["chat_template"] = "raw prompt always"
        path.write_text(json.dumps(payload), encoding="utf-8")
    if mixed:
        with pytest.raises(SavedScreenError):
            summarize_screen(str(manifest), str(reports))
    else:
        result = summarize_screen(str(manifest), str(reports))
        assert (
            result["exit_code"] == 0
            and result["protocol_by_stratum"]["gguf"]["decode"]["chat_template"] == "raw prompt always"
        )


def test_local_gguf_cannot_claim_a_hub_pin(tmp_path):
    from quantfit.saved_screen import SavedScreenError, summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)], unknown_weights=True)
    path = reports / "g0.json"
    payload = json.loads(path.read_bytes())
    payload["baseline"]["revision"] = "a" * 40
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SavedScreenError):
        summarize_screen(str(manifest), str(reports))


def test_total_actual_read_budget_is_applied_before_retaining_more_members(tmp_path, monkeypatch):
    import quantfit.saved_screen as saved

    manifest, reports = corpus(tmp_path, [(f"g{i}", "gguf", 0, 0, None) for i in range(4)])
    read = saved._read
    calls = []
    monkeypatch.setattr(saved, "MAX_REPORT_BYTES", 8)
    monkeypatch.setattr(saved, "MAX_TOTAL_BYTES", 16)
    monkeypatch.setattr(saved, "_inventory", lambda root, allowed: sorted(reports.iterdir()))

    def grew(path, limit):
        if path == manifest:
            return read(path, limit)
        calls.append((path.name, limit))
        return b"x" * limit

    monkeypatch.setattr(saved, "_read", grew)
    with pytest.raises(saved.SavedScreenError):
        saved.summarize_screen(str(manifest), str(reports))
    assert calls == [("g0.json", 8), ("g1.json", 8)]


def test_directory_scan_stops_at_first_foreign_member_and_closes_iterator(tmp_path, monkeypatch):
    import os

    import quantfit.saved_screen as saved

    reports = tmp_path / "reports"
    reports.mkdir()
    seen = []

    class Entry:
        name = "foreign.capture.jsonl"

    class Scan:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            seen.append("closed")

        def __iter__(self):
            for index in range(1000):
                seen.append(index)
                yield Entry()

    monkeypatch.setattr(os, "scandir", lambda root: Scan())
    monkeypatch.setattr(Path, "iterdir", lambda root: iter(Scan()))
    with pytest.raises(saved.SavedScreenError):
        saved._inventory(reports, {"g0.json"})
    assert seen == [0, "closed"]


def test_new_summary_publication_cancellation_is_bounded(tmp_path, monkeypatch):
    import quantfit.saved_screen as saved

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])

    def cancel(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(saved, "_publish_reproduction_outputs", cancel)
    escaped = False
    try:
        saved.summarize_screen(str(manifest), str(reports), out_path=str(tmp_path / "new.json"))
    except saved.SavedScreenError as exc:
        assert str(exc) == "output_failure"
    except KeyboardInterrupt:
        escaped = True
    assert not escaped


def test_shared_writer_preserves_foreign_file_recreated_after_promotion(tmp_path, monkeypatch):
    import quantfit.reproduce as writer

    output = tmp_path / "result.json"
    plan = writer._ReproductionOutputs((), (), (output,))
    replace = writer.os.replace
    foreign = []

    def recreate(source, target):
        replace(source, target)
        Path(source).write_bytes(b"foreign owner")
        foreign.append(Path(source))

    monkeypatch.setattr(writer.os, "replace", recreate)
    writer._publish_reproduction_outputs(plan, [(output, b"held result")])
    assert output.read_bytes() == b"held result" and len(foreign) == 1
    assert foreign[0].read_bytes() == b"foreign owner"


def test_shared_writer_refuses_changed_stage_content_before_publication(tmp_path):
    import quantfit.reproduce as writer

    output = tmp_path / "result.json"
    plan = writer._ReproductionOutputs((), (), (output,))
    attacked = []

    def substitute():
        stages = list(tmp_path.glob(".reproduce-*"))
        if stages and not attacked:
            stages[0].write_bytes(b"substituted")
            attacked.append(stages[0])

    with pytest.raises(writer.ReproduceError):
        writer._publish_reproduction_outputs(plan, [(output, b"held result")], recheck=substitute)
    assert attacked and not output.exists()


@pytest.mark.parametrize("mixed", [False, True])
def test_canonical_template_whitespace_keeps_native_verbatim_scope(tmp_path, mixed):
    from quantfit.saved_screen import SavedScreenError, summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None), ("g1", "gguf", 0, 0, None)])
    for name in ("g0", "g1"):
        path = reports / f"{name}.json"
        payload = json.loads(path.read_bytes())
        payload["decode"]["chat_template"] = " raw prompt always " if not mixed or name == "g1" else "raw prompt always"
        path.write_text(json.dumps(payload), encoding="utf-8")
    if mixed:
        with pytest.raises(SavedScreenError):
            summarize_screen(str(manifest), str(reports))
    else:
        result = summarize_screen(str(manifest), str(reports))
        assert result["protocol_by_stratum"]["gguf"]["decode"]["chat_template"] == " raw prompt always "


@pytest.mark.parametrize("mode", ["hash", "pin", "mixed"])
def test_complete_pair_overlap_refuses_even_when_other_identity_differs(tmp_path, mode):
    from quantfit.saved_screen import SavedScreenError, summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None), ("g1", "gguf", 0, 0, None)])
    values = [json.loads((reports / f"g{i}.json").read_bytes()) for i in (0, 1)]
    declared = json.loads(manifest.read_bytes())
    if mode == "hash":
        for arm in ("baseline", "quantized"):
            values[1][arm]["artifact_sha256"] = values[0][arm]["artifact_sha256"]
    elif mode == "pin":
        for arm, key in (("baseline", "baseline"), ("quantized", "quant")):
            values[1][arm]["revision"] = values[0][arm]["revision"]
            values[1][arm]["model"] = values[0][arm]["model"]
            declared["targets"][1][key] = values[0][arm]["model"]
    else:
        values[1]["baseline"]["artifact_sha256"] = values[0]["baseline"]["artifact_sha256"]
        values[0]["baseline"]["revision"] = None
        values[0]["quantized"]["artifact_sha256"] = None
        values[1]["quantized"]["model"] = values[0]["quantized"]["model"]
        values[1]["quantized"]["revision"] = values[0]["quantized"]["revision"]
        declared["targets"][1]["quant"] = values[0]["quantized"]["model"]
    manifest.write_text(json.dumps(declared), encoding="utf-8")
    for i, value in enumerate(values):
        (reports / f"g{i}.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(SavedScreenError, match="duplicate_evidence"):
        summarize_screen(str(manifest), str(reports))


@pytest.mark.parametrize("partial", [False, True])
def test_unknown_or_partial_pair_identities_do_not_collapse_distinct_targets(tmp_path, partial):
    from quantfit.saved_screen import summarize_screen

    manifest, reports = corpus(
        tmp_path,
        [("c0", "compressed-tensors", 0, 0, None), ("c1", "compressed-tensors", 0, 0, None)],
        unknown_weights=True,
    )
    if partial:
        declared = json.loads(manifest.read_bytes())
        declared["targets"][1]["baseline"] = declared["targets"][0]["baseline"]
        manifest.write_text(json.dumps(declared), encoding="utf-8")
        for name in ("c0", "c1"):
            path = reports / f"{name}.json"
            value = json.loads(path.read_bytes())
            value["baseline"]["model"] = declared["targets"][0]["baseline"]
            value["baseline"]["revision"] = "a" * 40
            path.write_text(json.dumps(value), encoding="utf-8")
    result = summarize_screen(str(manifest), str(reports))
    assert (
        result["exit_code"] == 0 and result["by_stratum"]["compressed-tensors"]["refusal_robustness"]["n_measured"] == 2
    )
    assert result["unique_weights_verified"] is False


@pytest.mark.parametrize("unknown", [False, True])
def test_known_protocol_change_or_unknown_protocol_fact_never_pool(tmp_path, unknown):
    from quantfit.saved_screen import SavedScreenError, summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None), ("g1", "gguf", 0, 0, None)])
    path = reports / "g1.json"
    value = json.loads(path.read_bytes())
    for arm in ("baseline", "quantized"):
        value[arm]["engine"]["threads"] = None if unknown else 3
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(SavedScreenError):
        summarize_screen(str(manifest), str(reports))


@pytest.mark.parametrize("change", ["reference", "stratum", "schema_bool", "private", "duplicate_key"])
def test_malformed_or_unbound_evidence_refuses_categorically(tmp_path, change):
    from quantfit.saved_screen import SavedScreenError, summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 1, 0, None)])
    path = reports / "g0.json"
    value = json.loads(path.read_bytes())
    if change == "reference":
        value["baseline"]["model"] = "hf:foreign/repo/other.gguf"
    elif change == "private":
        value["private_text"] = "PRIVATE provider payload"
    elif change == "duplicate_key":
        path.write_bytes(b'{"schema_version":2,"schema_version":2}')
    elif change in ("stratum", "schema_bool"):
        declared = json.loads(manifest.read_bytes())
        if change == "schema_bool":
            declared["schema_version"] = True
        else:
            declared["targets"][0]["stratum"] = "compressed-tensors"
        manifest.write_text(json.dumps(declared), encoding="utf-8")
    if change in ("reference", "private"):
        path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(SavedScreenError) as exc:
        summarize_screen(str(manifest), str(reports))
    assert "PRIVATE" not in str(exc.value)


@pytest.mark.parametrize("missing", [False, True])
def test_flag_survives_unmeasured_other_axis_and_missing_other_target(tmp_path, missing):
    from quantfit.saved_screen import summarize_screen

    manifest, reports = corpus(
        tmp_path, [("g0", "gguf", 1, 0, "over"), ("g1", "gguf", 0, 0, None)], missing=("g1",) if missing else ()
    )
    result = summarize_screen(str(manifest), str(reports))
    assert result["exit_code"] == 3 and result["by_stratum"]["gguf"]["refusal_robustness"]["n_regressed"] == 1
    assert result["by_stratum"]["gguf"]["over_refusal"]["n_measured"] == (0 if missing else 1)


def test_ignored_producer_summary_cannot_clear_flags_or_verify_people(tmp_path):
    from quantfit.saved_screen import summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 1, 0, None)])
    raw = json.dumps(
        {
            "schema_version": 1,
            "rows": [{"name": "g0", "status": "no_regression", "human_verified": True}],
            "sensitivity_control": {"status": "pass"},
            "by_stratum": {"gguf": {"n_regressed": 0, "n_regressed_human_verified": 999}},
        }
    ).encode()
    (reports / "screen-summary.json").write_bytes(raw)
    result = summarize_screen(str(manifest), str(reports))
    assert result["exit_code"] == 3 and result["rows"][0]["human_verified"] is None
    assert result["n_regressed_human_verified"] == 0 and result["control_evidence_verified"] is False
    assert result["ignored_members"] == [
        {"member": "screen-summary.json", "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
    ]


def test_all_eleven_valid_committed_reports_are_consumed_without_rewriting(tmp_path):
    from quantfit.saved_screen import summarize_screen

    source = json.loads((ROOT / "screens/targets-0.5.json").read_bytes())
    targets = [
        t for t in source["targets"] if t["name"] not in BAD_HISTORY and (HISTORY / f"{t['name']}.json").is_file()
    ]
    assert len(targets) == 11
    manifest = tmp_path / "targets.json"
    manifest.write_text(
        json.dumps({**source, "name": "explicit historical valid subset", "targets": targets}), encoding="utf-8"
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    original = {t["name"]: (HISTORY / f"{t['name']}.json").read_bytes() for t in targets}
    for name, raw in original.items():
        (reports / f"{name}.json").write_bytes(raw)
    result = summarize_screen(str(manifest), str(reports))
    assert result["coverage"] == {"n_targets": 11, "n_present": 11, "n_missing": 0, "complete": True}
    assert set(result["by_stratum"]) == {"gguf", "compressed-tensors"} and result["exit_code"] == 3
    assert all((reports / f"{name}.json").read_bytes() == raw for name, raw in original.items())


@pytest.mark.parametrize("population_change", [False, True])
def test_input_population_is_common_but_response_denominators_can_differ(tmp_path, population_change):
    from quantfit.saved_screen import SavedScreenError, summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None), ("g1", "gguf", 0, 0, None)])
    path = reports / "g1.json"
    value = json.loads(path.read_bytes())
    unsafe_n = 13 if population_change else 12
    safe_n = 40 - unsafe_n
    refused = 13 if population_change else 11
    zones = {
        "clear_unsafe": {"n": unsafe_n, "baseline_refused": refused, "quant_refused": refused},
        "clear_safe": {"n": 12, "baseline_refused": 0, "quant_refused": 0},
        "borderline": {"n": safe_n - 12, "baseline_refused": 0, "quant_refused": 0},
    }
    value["drift"] = SafetyDrift(40, unsafe_n, refused, refused, 0, safe_n, 0, 0, 0, zones).to_dict()
    path.write_text(json.dumps(value), encoding="utf-8")
    if population_change:
        with pytest.raises(SavedScreenError, match="incompatible_scope"):
            summarize_screen(str(manifest), str(reports))
    else:
        result = summarize_screen(str(manifest), str(reports))
        assert result["exit_code"] == 0 and [row["refusal_robustness"]["at_risk"] for row in result["rows"]] == [12, 11]


@pytest.mark.parametrize("alias", ["manifest", "report", "ignored", "closed", "outputs", "hardlink"])
def test_receiving_outputs_cannot_overwrite_any_source_or_each_other(tmp_path, alias):
    import os

    from quantfit.saved_screen import SavedScreenError, summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    ignored = reports / "screen-summary.json"
    ignored.write_bytes(b'{"schema_version":1,"rows":[]}')
    sources = {p: p.read_bytes() for p in (manifest, *reports.iterdir())}
    output = {
        "manifest": manifest,
        "report": reports / "g0.json",
        "ignored": ignored,
        "closed": reports / "new.json",
        "outputs": tmp_path / "same",
        "hardlink": tmp_path / "alias.json",
    }[alias]
    if alias == "hardlink":
        os.link(reports / "g0.json", output)
    with pytest.raises(SavedScreenError):
        summarize_screen(
            str(manifest), str(reports), out_path=str(output), junit_path=str(output) if alias == "outputs" else None
        )
    assert all(path.read_bytes() == raw for path, raw in sources.items())


def test_second_replacement_failure_has_no_new_success_xml(tmp_path, monkeypatch):
    import quantfit.reproduce as writer
    from quantfit.saved_screen import SavedScreenError, summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    output, xml = tmp_path / "new.json", tmp_path / "new.xml"
    replace = writer.os.replace
    calls = []

    def failed(source, target):
        calls.append(Path(target))
        if len(calls) == 2:
            raise OSError("PRIVATE publication diagnostics")
        replace(source, target)

    monkeypatch.setattr(writer.os, "replace", failed)
    with pytest.raises(SavedScreenError, match="output_failure"):
        summarize_screen(str(manifest), str(reports), out_path=str(output), junit_path=str(xml))
    assert calls == [output, xml] and output.is_file() and not xml.exists()
    assert not list(tmp_path.glob(".reproduce-*"))


def test_extra_member_between_replacements_refuses_xml(tmp_path, monkeypatch):
    import quantfit.reproduce as writer
    from quantfit.saved_screen import SavedScreenError, summarize_screen

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    output, xml = tmp_path / "new.json", tmp_path / "new.xml"
    replace = writer.os.replace
    calls = []

    def substitute(source, target):
        replace(source, target)
        calls.append(Path(target))
        if len(calls) == 1:
            (reports / "foreign.capture.jsonl").write_bytes(b"foreign content")

    monkeypatch.setattr(writer.os, "replace", substitute)
    with pytest.raises(SavedScreenError):
        summarize_screen(str(manifest), str(reports), out_path=str(output), junit_path=str(xml))
    assert calls == [output] and not xml.exists()


def test_held_core_never_resolves_or_reopens_report_or_manifest_locators(tmp_path, monkeypatch):
    from quantfit.saved_screen import _summarize_held

    manifest, reports = corpus(tmp_path, [("g0", "gguf", 0, 0, None)])
    raw = manifest.read_bytes()
    held = {path.name: path.read_bytes() for path in reports.iterdir()}

    def forbidden(*args, **kwargs):
        pytest.fail("held core performed path IO")

    for name in ("resolve", "open", "read_bytes", "read_text", "stat"):
        monkeypatch.setattr(Path, name, forbidden)
    result = _summarize_held(raw, held, manifest_path="Z:/foreign/targets.json", reports_dir="Z:/foreign/reports")
    assert result["exit_code"] == 0
