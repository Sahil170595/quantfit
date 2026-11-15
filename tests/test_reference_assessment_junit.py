"""Closed XML projection keeps original native assessment criteria and publication behavior."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest
from test_reference_assessment import make_bundle, target_declaration, write_target

from quantfit import reference_assessment as assessment


def scenario(root, name="ready"):
    bundle, _, _ = make_bundle(
        root, "candidate", historical=name in ("historical", "mixed"), unsafe=0 if name == "native4_excluded" else 12
    )
    body = target_declaration()
    if name in ("unknown", "mixed"):
        body["arms"]["baseline"]["size_bytes"] = None
    return bundle, write_target(root, body)


@pytest.mark.parametrize(
    "name,code", [("ready", 0), ("historical", 3), ("unknown", 4), ("mixed", 3), ("native4_excluded", 0)]
)
def test_native_receiving_criteria_and_json_remain_exact_with_requested_xml(tmp_path, name, code):
    bundle, target = scenario(tmp_path, name)
    native = assessment.assess_candidate(str(bundle), str(target))
    out, xml = tmp_path / "receiving.json", tmp_path / "receiving.xml"
    result = assessment.assess_candidate(str(bundle), str(target), out_path=str(out), junit_path=str(xml))
    assert result == native and result["exit_code"] == code and json.loads(out.read_bytes()) == native
    cases = list(ET.fromstring(xml.read_bytes()).iter("testcase"))
    assert len(cases) == 108 and cases[0].get("name") == "overall"
    assert {c.get("name") for c in cases[1:]} == set(native["criteria"])
    assert not any(c.find("skipped") is not None for c in cases)
    if code == 3:
        assert cases[0].find("failure") is not None
    elif code == 4:
        assert cases[0].find("error") is not None
    else:
        assert all(c.find("failure") is None and c.find("error") is None for c in cases)
    if name == "mixed":
        assert any(c.find("failure") is not None for c in cases[1:]) and any(
            c.find("error") is not None for c in cases[1:]
        )
    if name == "native4_excluded":
        assert native["native_exits"] == [4, 4, 4]


def test_pure_renderer_has_original_core_shape_and_no_mutation(tmp_path):
    from quantfit.reference_assessment_junit import assessment_to_junit

    bundle, target = scenario(tmp_path)
    buffers = tuple((bundle / f"report-{i}.json").read_bytes() for i in range(1, 4))
    result = assessment.assess_report_buffers(buffers, target.read_bytes(), source_labels=("one", "two", "three"))
    before = json.dumps(result, sort_keys=True)
    xml = assessment_to_junit(result)
    assert isinstance(xml, str) and len(list(ET.fromstring(xml).iter("testcase"))) == 108
    assert json.dumps(result, sort_keys=True) == before


def test_junit_only_publishes_no_json_output_buffer(tmp_path, monkeypatch):
    bundle, target = scenario(tmp_path, "historical")
    publish = Mock(wraps=assessment._publish_reproduction_outputs)
    monkeypatch.setattr(assessment, "_publish_reproduction_outputs", publish)
    xml = tmp_path / "only.xml"
    result = assessment.assess_candidate(str(bundle), str(target), junit_path=str(xml))
    buffers = publish.call_args.args[1]
    assert result["exit_code"] == 3 and len(buffers) == 1 and buffers[0][0] == xml
    assert buffers[0][1].startswith(b"<?xml") and xml.exists()


def test_actual_os_cli_publishes_native_blocked_json_and_xml_before_exit_three(tmp_path):
    bundle, target = scenario(tmp_path, "historical")
    out, xml = tmp_path / "cli.json", tmp_path / "cli.xml"
    process = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "quantfit.cli",
            "references",
            "assess",
            "--bundle",
            str(bundle),
            "--target",
            str(target),
            "--out",
            str(out),
            "--junit",
            str(xml),
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
        cwd=tmp_path,
    )
    assert process.returncode == 3 and not process.stderr
    assert json.loads(process.stdout)["result"] == json.loads(out.read_bytes()) and xml.exists()


@pytest.fixture(autouse=True)
def receiving_only(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("assessment XML attempted inference, source resolution or Hub work")

    monkeypatch.setattr("quantfit.safety.verify.verify_safety", forbidden)
    monkeypatch.setattr("quantfit.safety.gguf_arm.resolve_pair", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)


@pytest.fixture(scope="module")
def admitted_records(tmp_path_factory):
    root = tmp_path_factory.mktemp("native-reference-assessments")
    records = {}
    for name in ("ready", "historical", "unknown", "mixed", "native4_excluded"):
        here = root / name
        here.mkdir()
        bundle, target = scenario(here, name)
        records[name] = assessment.assess_candidate(str(bundle), str(target))
    return records


def test_all_original_107_criteria_have_fixed_order_even_when_input_keys_are_shuffled(admitted_records):
    from quantfit.reference_assessment_junit import CANONICAL_CRITERIA, assessment_to_junit

    native = copy.deepcopy(admitted_records["mixed"])
    assert len(CANONICAL_CRITERIA) == len(set(CANONICAL_CRITERIA)) == 107 and set(CANONICAL_CRITERIA) == set(
        native["criteria"]
    )
    first = assessment_to_junit(native)
    native["criteria"] = dict(reversed(list(native["criteria"].items())))
    native["target"]["engine"] = dict(reversed(list(native["target"]["engine"].items())))
    native["target"]["judge"] = dict(reversed(list(native["target"]["judge"].items())))
    assert assessment_to_junit(native) == first
    assert [case.get("name") for case in ET.fromstring(first).iter("testcase")] == ["overall", *CANONICAL_CRITERIA]


NULLABLE_FACTS = [
    *(
        ("arms", arm, key)
        for arm in ("baseline", "quantized")
        for key in ("model", "revision", "resolved_dtype", "artifact_sha256")
    ),
    *(
        ("engine", key)
        for key in ("name", "device", "binary_sha256", "threads", "offload_device", "n_gpu_layers", "op_offload")
    ),
    *(
        (group, key)
        for group, keys in (
            ("judge", ("id", "revision", "input_contract")),
            ("probe_dataset", ("id", "revision", "split", "n_probes")),
            ("decode", ("max_new_tokens", "do_sample", "chat_template")),
        )
        for key in keys
    ),
]


@pytest.mark.parametrize("path", NULLABLE_FACTS)
def test_every_native_nullable_target_fact_remains_unestablished_and_xml_error(tmp_path, path):
    from quantfit.reference_assessment_junit import assessment_to_junit

    bundle, _ = scenario(tmp_path)
    target = target_declaration()
    parent = target
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = None
    native = assessment.assess_candidate(str(bundle), str(write_target(tmp_path, target)))
    assert native["exit_code"] == 4 and "target_facts_unestablished" in native["unknown_reasons"]
    root = ET.fromstring(assessment_to_junit(native))
    assert root.get("errors") != "0" and root.get("skipped") == "0"


@pytest.mark.parametrize(
    "mode,code",
    [
        ("full_payload", 3),
        ("t0", 3),
        ("protocol", 3),
        ("unsupported_profile", 4),
        ("none_measured", 4),
        ("over_cap_and_none", 3),
        ("size_at_cap", 0),
    ],
)
def test_original_native_adverse_unknown_and_boundary_decisions_are_only_projected(tmp_path, mode, code):
    from quantfit.reference_assessment_junit import assessment_to_junit
    from quantfit.safety.verify import SafetyDrift

    bundle, _, _ = make_bundle(tmp_path, "candidate", disagreement=mode == "t0")
    values = [json.loads((bundle / f"report-{i}.json").read_bytes()) for i in range(1, 4)]
    target = target_declaration()
    if mode == "full_payload":
        values[2]["baseline"]["engine"]["runtime_scope"] = "PRIVATE extra observation"
    elif mode == "protocol":
        for value in values:
            value["judge"]["id"] = "synthetic/foreign-judge"
        target["judge"]["id"] = "synthetic/foreign-judge"
    elif mode == "unsupported_profile":
        target["profile"] = "unsupported-instrument"
    elif mode in ("none_measured", "over_cap_and_none"):
        zones = {
            "clear_unsafe": {"n": 12, "baseline_refused": 0, "quant_refused": 0},
            "clear_safe": {"n": 12, "baseline_refused": 12, "quant_refused": 12},
            "borderline": {"n": 16, "baseline_refused": 16, "quant_refused": 16},
        }
        for value in values:
            value["drift"] = SafetyDrift(40, 12, 0, 0, 0, 28, 28, 28, 0, zones).to_dict()
        if mode == "over_cap_and_none":
            target["arms"]["baseline"]["size_bytes"] = 16_500_000_001
    elif mode == "size_at_cap":
        target["arms"]["baseline"]["size_bytes"] = 16_500_000_000
    native = assessment.assess_report_buffers(
        tuple(json.dumps(v).encode() for v in values),
        json.dumps(target).encode(),
        source_labels=("one", "two", "three"),
    )
    assert native["exit_code"] == code
    root = ET.fromstring(assessment_to_junit(native))
    cases = {case.get("name"): case for case in root.iter("testcase")}
    assert (cases["overall"].find("failure") is not None) is (code == 3)
    assert (cases["overall"].find("error") is not None) is (code == 4)
    if mode == "over_cap_and_none":
        assert (
            cases["measured_axis"].find("error") is not None
            and cases["baseline_declared_cap"].find("failure") is not None
        )


def test_operational_t0_refusal_remains_native_false_with_its_allowed_reason(tmp_path, monkeypatch):
    from quantfit.reference_assessment_junit import assessment_to_junit
    from quantfit.reproduce import ReproduceError

    bundle, target = scenario(tmp_path)
    buffers = tuple((bundle / f"report-{i}.json").read_bytes() for i in range(1, 4))

    def failed(*args, **kwargs):
        raise ReproduceError("PRIVATE controlled native T0 refusal")

    monkeypatch.setattr(assessment, "_t0_from_views", failed)
    native = assessment.assess_report_buffers(buffers, target.read_bytes(), source_labels=("one", "two", "three"))
    assert native["exit_code"] == 3 and native["criteria"]["native_t0"] == {
        "pass": False,
        "reason": "t0_operational_refusal",
    }
    rendered = assessment_to_junit(native)
    assert "PRIVATE" not in rendered
    assert (
        next(case for case in ET.fromstring(rendered).iter("testcase") if case.get("name") == "native_t0").find(
            "failure"
        )
        is not None
    )


@pytest.mark.parametrize(
    "fault",
    [
        "schema_bool",
        "schema_float",
        "schema_missing",
        "unknown_root",
        "partial_receiving",
        "missing_criterion",
        "extra_criterion",
        "renamed_criterion",
        "pass_zero",
        "pass_one",
        "pass_string",
        "true_reason",
        "false_null_reason",
        "unknown_null_reason",
        "private_reason",
        "false_supported",
        "false_quantized_size",
        "false_measured",
        "none_native_profile",
        "none_full_repeat",
        "none_no_flags",
        "outcome",
        "code_bool",
        "code_float",
        "code_domain",
        "code_mismatch",
        "blockers",
        "unknowns",
        "hash",
        "uppercase_hash",
        "size_bool",
        "size_huge",
        "flag_true",
        "flag_zero",
        "extra_block",
        "native_exits_bool",
    ],
)
def test_forged_or_contradictory_projection_refuses_before_xml(admitted_records, monkeypatch, fault):
    from quantfit import reference_assessment_junit as renderer

    native = copy.deepcopy(admitted_records["ready"])
    key = "run-1.arms.baseline.model"
    if fault == "schema_bool":
        native["receiving_assessment_schema_version"] = True
    elif fault == "schema_float":
        native["receiving_assessment_schema_version"] = 1.0
    elif fault == "schema_missing":
        del native["receiving_assessment_schema_version"]
    elif fault == "unknown_root":
        native["PRIVATE"] = True
    elif fault == "partial_receiving":
        del native["original_t0"]
    elif fault == "missing_criterion":
        del native["criteria"][key]
    elif fault == "extra_criterion":
        native["criteria"]["PRIVATE"] = {"pass": True, "reason": None}
    elif fault == "renamed_criterion":
        native["criteria"]["PRIVATE"] = native["criteria"].pop(key)
    elif fault in ("pass_zero", "pass_one", "pass_string"):
        native["criteria"][key]["pass"] = {"pass_zero": 0, "pass_one": 1, "pass_string": "true"}[fault]
    elif fault == "true_reason":
        native["criteria"][key]["reason"] = "reported_target_facts_mismatch"
    elif fault == "false_null_reason":
        native["criteria"][key] = {"pass": False, "reason": None}
    elif fault == "unknown_null_reason":
        native["criteria"][key] = {"pass": None, "reason": None}
    elif fault == "private_reason":
        native["criteria"][key] = {"pass": False, "reason": "PRIVATE raw diagnostic"}
    elif fault in ("false_supported", "false_quantized_size", "false_measured"):
        name, reason = {
            "false_supported": ("supported_spec", "unsupported_spec"),
            "false_quantized_size": ("quantized_size_declared", "quantized_size_unestablished"),
            "false_measured": ("measured_axis", "no_measured_axis"),
        }[fault]
        native["criteria"][name] = {"pass": False, "reason": reason}
    elif fault in ("none_native_profile", "none_full_repeat", "none_no_flags"):
        name, reason = {
            "none_native_profile": ("run-1.native_profile", "reported_native_profile_mismatch"),
            "none_full_repeat": ("full_report_repeatability", "full_report_repeatability_failed"),
            "none_no_flags": ("no_fresh_flags", "fresh_flags_without_human_adjudication"),
        }[fault]
        native["criteria"][name] = {"pass": None, "reason": reason}
    elif fault == "outcome":
        native["outcome"] = "blocked"
    elif fault == "code_bool":
        native["exit_code"] = False
    elif fault == "code_float":
        native["exit_code"] = 0.0
    elif fault == "code_domain":
        native["exit_code"] = 2
    elif fault == "code_mismatch":
        native["exit_code"] = 3
        native["outcome"] = "blocked"
    elif fault == "blockers":
        native["blocking_reasons"] = ["reported_target_facts_mismatch"]
    elif fault == "unknowns":
        native["unknown_reasons"] = ["target_facts_unestablished"]
    elif fault == "hash":
        native["target_sha256"] = "PRIVATE"
    elif fault == "uppercase_hash":
        native["source_reports"][0]["sha256"] = "A" * 64
    elif fault == "size_bool":
        native["source_reports"][0]["size_bytes"] = True
    elif fault == "size_huge":
        native["source_reports"][0]["size_bytes"] = 10**1000
    elif fault == "flag_true":
        native["scientific_go"] = True
    elif fault == "flag_zero":
        native["human_labels_authenticated"] = 0
    elif fault == "extra_block":
        native["criteria"][key]["PRIVATE"] = True
    else:
        native["native_exits"] = [False, 0, 0]
    trap = lambda *a, **k: pytest.fail("unadmitted projection reached XML construction")
    monkeypatch.setattr(renderer, "ET", SimpleNamespace(Element=trap, SubElement=trap))
    with pytest.raises(renderer.ReferenceAssessmentJUnitError, match="^invalid_reference_assessment_junit$"):
        renderer.assessment_to_junit(native)


def test_opaque_producer_metadata_and_private_canaries_never_enter_xml(admitted_records):
    from quantfit.reference_assessment_junit import assessment_to_junit

    native = copy.deepcopy(admitted_records["historical"])
    original = assessment_to_junit(native)
    native["pair"] = native["scope"] = native["quantfit_version"] = "PRIVATE model/path/name/exception"
    native["target"]["pair_slug"] = "PRIVATE pair"
    native["target"]["arbitrary_metadata"] = {"completion": "PRIVATE raw producer content"}
    native["bundle_path"] = "PRIVATE receiving path"
    for report in native["source_reports"]:
        report["path"] = "PRIVATE producer path"
    for report in native["report_bindings"]:
        report["producer_path"] = report["receiving_path"] = "PRIVATE path"
    native["full_report_repeatability"]["differing_paths"] = ["PRIVATE arbitrary metadata"]
    native["original_t0"]["arbitrary_metadata"] = {"text": "PRIVATE raw T0"}
    before = copy.deepcopy(native)
    rendered = assessment_to_junit(native)
    assert rendered == original and "PRIVATE" not in rendered and native == before
    root = ET.fromstring(rendered)
    assert all(case.get("classname") == "quantfit.references.assess" for case in root.iter("testcase"))
    assert all(len(prop.get("value")) == 64 or prop.get("value").isdecimal() for prop in root.iter("property"))


def test_renderer_is_pure_and_adds_zero_native_calls_or_mutation(admitted_records, monkeypatch):
    from quantfit.reference_assessment_junit import assessment_to_junit

    native = copy.deepcopy(admitted_records["mixed"])
    before = copy.deepcopy(native)

    def forbidden(*args, **kwargs):
        pytest.fail("pure XML projection performed native or path work")

    for name in (
        "_read",
        "_target",
        "_verified_bundle",
        "_assess_bundle_held",
        "assess_report_buffers",
        "_t0_from_views",
    ):
        monkeypatch.setattr(assessment, name, forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    assert len(list(ET.fromstring(assessment_to_junit(native)).iter("testcase"))) == 108 and native == before


def test_actual_native_alias_counts_are_baselined_and_xml_adds_zero(tmp_path, monkeypatch):
    from quantfit import replay_bundle

    bundle, target = scenario(tmp_path)
    names = ("_read", "_verified_bundle", "_assess_bundle_held", "assess_report_buffers", "_target", "_t0_from_views")
    spies = {name: Mock(wraps=getattr(assessment, name)) for name in names}
    replay_t0 = Mock(wraps=replay_bundle._t0_from_views)
    replay_read = Mock(wraps=replay_bundle._read)
    for name, spy in spies.items():
        monkeypatch.setattr(assessment, name, spy)
    monkeypatch.setattr(replay_bundle, "_t0_from_views", replay_t0)
    monkeypatch.setattr(replay_bundle, "_read", replay_read)
    baseline = assessment.assess_candidate(str(bundle), str(target))
    counts = {name: spy.call_count for name, spy in spies.items()}
    counts.update(replay_t0=replay_t0.call_count, replay_read=replay_read.call_count)
    assert counts == {
        "_read": 1,
        "_verified_bundle": 1,
        "_assess_bundle_held": 1,
        "assess_report_buffers": 1,
        "_target": 2,
        "_t0_from_views": 1,
        "replay_t0": 2,
        "replay_read": 5,
    }
    for spy in [*spies.values(), replay_t0, replay_read]:
        spy.reset_mock()
    selected = assessment.assess_candidate(
        str(bundle), str(target), out_path=str(tmp_path / "result.json"), junit_path=str(tmp_path / "result.xml")
    )
    after = {name: spy.call_count for name, spy in spies.items()}
    after.update(replay_t0=replay_t0.call_count, replay_read=replay_read.call_count)
    assert selected == baseline and after == counts


def test_requested_cap_exact_boundary_and_one_over(admitted_records, monkeypatch):
    from quantfit import reference_assessment_junit as renderer

    native = copy.deepcopy(admitted_records["mixed"])
    raw = renderer.assessment_to_junit(native)
    size = len(raw.encode("utf-8"))
    assert size <= 65536
    monkeypatch.setattr(renderer, "MAX_JUNIT_BYTES", size)
    assert renderer.assessment_to_junit(native) == raw
    monkeypatch.setattr(renderer, "MAX_JUNIT_BYTES", size - 1)
    with pytest.raises(renderer.ReferenceAssessmentJUnitError):
        renderer.assessment_to_junit(native)


def test_no_xml_request_has_no_renderer_or_cap_and_failed_cap_never_publishes(tmp_path, monkeypatch):
    from quantfit import reference_assessment_junit as renderer

    bundle, target = scenario(tmp_path, "unknown")
    out, xml = tmp_path / "result.json", tmp_path / "result.xml"
    monkeypatch.setattr(renderer, "MAX_JUNIT_BYTES", 1)
    with pytest.raises(assessment.ReferenceAssessmentError, match="^assessment_output_failure$"):
        assessment.assess_candidate(str(bundle), str(target), out_path=str(out), junit_path=str(xml))
    assert not out.exists() and not xml.exists()
    trap = Mock(side_effect=AssertionError("JSON-only path rendered XML"))
    monkeypatch.setattr(renderer, "assessment_to_junit", trap)
    native = assessment.assess_candidate(str(bundle), str(target), out_path=str(out))
    assert native["exit_code"] == 4 and out.exists()
    trap.assert_not_called()


@pytest.mark.parametrize("json_output,xml_output", [(False, False), (True, False), (False, True), (True, True)])
def test_requested_outputs_use_one_complete_publication_and_no_extra_json_output(
    tmp_path, monkeypatch, json_output, xml_output
):
    bundle, target = scenario(tmp_path, "unknown")
    publish = Mock(wraps=assessment._publish_reproduction_outputs)
    monkeypatch.setattr(assessment, "_publish_reproduction_outputs", publish)
    out, xml = tmp_path / "receiving.json", tmp_path / "receiving.xml"
    result = assessment.assess_candidate(
        str(bundle),
        str(target),
        out_path=str(out) if json_output else None,
        junit_path=str(xml) if xml_output else None,
    )
    assert result["exit_code"] == 4 and out.exists() is json_output and xml.exists() is xml_output
    if json_output or xml_output:
        publish.assert_called_once()
        buffers = publish.call_args.args[1]
        assert len(buffers) == int(json_output) + int(xml_output)
        assert [path for path, _ in buffers] == ([out] if json_output else []) + ([xml] if xml_output else [])
    else:
        publish.assert_not_called()


@pytest.mark.parametrize("sink", ["json", "xml"])
@pytest.mark.parametrize(
    "alias",
    [
        "target",
        "target_hardlink",
        "manifest",
        "report1",
        "report2",
        "report3",
        "t0",
        "inside",
        "missing_role",
        "mutual",
        "mutual_hardlinks",
    ],
)
def test_all_sinks_and_declared_missing_roles_are_protected_before_input_reads(tmp_path, monkeypatch, sink, alias):
    bundle, target = scenario(tmp_path)
    out, xml = tmp_path / "out.json", tmp_path / "out.xml"
    aliases = {
        "target": target,
        "manifest": bundle / "manifest.json",
        "report1": bundle / "report-1.json",
        "report2": bundle / "report-2.json",
        "report3": bundle / "report-3.json",
        "t0": bundle / "t0.json",
        "inside": bundle / "other.xml",
        "missing_role": bundle / "report-2.json",
    }
    if alias == "target_hardlink":
        linked = tmp_path / "linked.xml"
        os.link(target, linked)
        aliases[alias] = linked
    elif alias == "missing_role":
        (bundle / "report-2.json").unlink()
    elif alias == "mutual":
        out = xml = tmp_path / "same"
    elif alias == "mutual_hardlinks":
        out.write_bytes(b"prior output")
        os.link(out, xml)
    if alias not in ("mutual", "mutual_hardlinks"):
        if sink == "json":
            out = aliases[alias]
        else:
            xml = aliases[alias]
    before = {p: p.read_bytes() for p in [target, *bundle.iterdir(), out, xml] if p.exists() and p.is_file()}
    monkeypatch.setattr(assessment, "_read", lambda *a, **k: pytest.fail("unsafe output reached target content read"))
    monkeypatch.setattr(
        assessment, "_verified_bundle", lambda *a, **k: pytest.fail("unsafe output reached bundle content read")
    )
    with pytest.raises(assessment.ReferenceAssessmentError, match="^unsafe_output$"):
        assessment.assess_candidate(str(bundle), str(target), out_path=str(out), junit_path=str(xml))
    assert all(p.read_bytes() == raw for p, raw in before.items())


@pytest.mark.parametrize("mode", ["invalid_projection", "renderer", "cap"])
def test_requested_renderer_refusal_materializes_no_files(tmp_path, monkeypatch, mode):
    from quantfit import reference_assessment_junit as renderer

    bundle, target = scenario(tmp_path)
    out, xml = tmp_path / "prior.json", tmp_path / "prior.xml"
    out.write_bytes(b"prior JSON")
    xml.write_bytes(b"prior XML")
    if mode == "invalid_projection":
        native = assessment._assess_bundle_held

        def malformed(*args, **kwargs):
            result = native(*args, **kwargs)
            result["criteria"]["supported_spec"]["pass"] = 0
            return result

        monkeypatch.setattr(assessment, "_assess_bundle_held", malformed)
    elif mode == "renderer":
        monkeypatch.setattr(renderer, "assessment_to_junit", Mock(side_effect=RuntimeError("PRIVATE renderer error")))
    else:
        monkeypatch.setattr(renderer, "MAX_JUNIT_BYTES", 1)
    with pytest.raises(assessment.ReferenceAssessmentError, match="^assessment_output_failure$"):
        assessment.assess_candidate(str(bundle), str(target), out_path=str(out), junit_path=str(xml))
    assert (
        out.read_bytes() == b"prior JSON"
        and xml.read_bytes() == b"prior XML"
        and not list(tmp_path.glob(".reproduce-*"))
    )


@pytest.mark.parametrize("which", ["first", "second"])
def test_native_per_file_replace_failure_preserves_old_or_first_result_and_closes_stages(tmp_path, monkeypatch, which):
    from quantfit import reproduce as publication

    bundle, target = scenario(tmp_path, "historical")
    out, xml = tmp_path / "result.json", tmp_path / "result.xml"
    out.write_bytes(b"old JSON")
    xml.write_bytes(b"old XML")
    native = publication.os.replace
    replaced = []

    def replace(source, destination):
        if (which == "first" and not replaced) or destination == xml:
            raise OSError("PRIVATE replace fault")
        native(source, destination)
        replaced.append(destination)

    monkeypatch.setattr(publication.os, "replace", replace)
    with pytest.raises(assessment.ReferenceAssessmentError, match="^assessment_output_failure$"):
        assessment.assess_candidate(str(bundle), str(target), out_path=str(out), junit_path=str(xml))
    assert xml.read_bytes() == b"old XML" and not list(tmp_path.glob(".reproduce-*"))
    if which == "first":
        assert out.read_bytes() == b"old JSON" and not replaced
    else:
        assert json.loads(out.read_bytes())["exit_code"] == 3 and replaced == [out]


def test_between_replacements_mutual_alias_substitution_refuses_and_preserves_first(tmp_path, monkeypatch):
    from quantfit import reproduce as publication

    bundle, target = scenario(tmp_path)
    out, xml = tmp_path / "result.json", tmp_path / "result.xml"
    native = publication.os.replace

    def replace(source, destination):
        native(source, destination)
        if destination == out:
            os.link(out, xml)

    monkeypatch.setattr(publication.os, "replace", replace)
    with pytest.raises(assessment.ReferenceAssessmentError, match="^assessment_output_failure$"):
        assessment.assess_candidate(str(bundle), str(target), out_path=str(out), junit_path=str(xml))
    assert (
        json.loads(out.read_bytes())["exit_code"] == 0
        and out.read_bytes() == xml.read_bytes()
        and not list(tmp_path.glob(".reproduce-*"))
    )


def test_post_read_source_mutation_remains_held_snapshot_with_xml(tmp_path, monkeypatch):
    bundle, target = scenario(tmp_path)
    before = target.read_bytes()
    verify, read = assessment._verified_bundle, assessment._read

    def consumed_bundle(path):
        result, held = verify(path)
        for member in Path(path).iterdir():
            member.write_bytes(b"PRIVATE source changed after consumption")
        return result, held

    def consumed_target(path, limit):
        raw = read(path, limit)
        path.write_bytes(b"PRIVATE changed target")
        return raw

    monkeypatch.setattr(assessment, "_verified_bundle", consumed_bundle)
    monkeypatch.setattr(assessment, "_read", consumed_target)
    xml = tmp_path / "held.xml"
    result = assessment.assess_candidate(str(bundle), str(target), junit_path=str(xml))
    import hashlib

    assert result["exit_code"] == 0 and result["target_sha256"] == hashlib.sha256(before).hexdigest() and xml.exists()
    assert "PRIVATE" not in xml.read_text(encoding="utf-8")


@pytest.mark.parametrize("name,code", [("ready", 0), ("unknown", 4), ("mixed", 3), ("native4_excluded", 0)])
def test_actual_os_cli_other_native_outcomes_publish_all_108_original_cases(tmp_path, name, code):
    bundle, target = scenario(tmp_path, name)
    out, xml = tmp_path / "cli.json", tmp_path / "cli.xml"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "quantfit.cli",
            "references",
            "assess",
            "--bundle",
            str(bundle),
            "--target",
            str(target),
            "--out",
            str(out),
            "--junit",
            str(xml),
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
        cwd=tmp_path,
    )
    assert (
        result.returncode == code
        and not result.stderr
        and json.loads(result.stdout)["result"] == json.loads(out.read_bytes())
    )
    assert len(list(ET.fromstring(xml.read_bytes()).iter("testcase"))) == 108


@pytest.mark.parametrize(
    "mode,code,reason",
    [
        ("unsupported_spec", 4, "unsupported_spec"),
        ("quantized_size_unknown", 4, "quantized_size_unestablished"),
        ("declared_model_mismatch", 3, "reported_target_facts_mismatch"),
    ],
)
def test_remaining_native_rule_branches_are_projected_with_no_private_diagnostics(tmp_path, mode, code, reason):
    from quantfit.reference_assessment_junit import assessment_to_junit

    bundle, _ = scenario(tmp_path)
    target = target_declaration()
    if mode == "unsupported_spec":
        target["spec_version"] = "unsupported-spec"
    elif mode == "quantized_size_unknown":
        target["arms"]["quantized"]["size_bytes"] = None
    else:
        target["arms"]["baseline"]["model"] = "PRIVATE unverified model path"
    native = assessment.assess_candidate(str(bundle), str(write_target(tmp_path, target)))
    assert native["exit_code"] == code and reason in native["blocking_reasons"] + native["unknown_reasons"]
    rendered = assessment_to_junit(native)
    assert "PRIVATE" not in rendered and len(list(ET.fromstring(rendered).iter("testcase"))) == 108
