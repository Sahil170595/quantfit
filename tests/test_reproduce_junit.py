"""Native reproduction XML and paired output protection, without model execution."""

import copy
import json
import os
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from test_reproduce_bundles import make_bundle

from quantfit.cli import main
from quantfit.reproduce import compare, compare_bundles, within_hardware_identical
from quantfit.reproduce_junit import reproduction_to_junit

NAMES = ["reference-t0", "candidate-t0", "P0", "P1", "T1", "T2", "T3", "T4", "T5", "overall"]


def assert_counts(xml):
    root = ET.fromstring(xml)
    cases = list(root.iter("testcase"))
    expected = {
        "tests": str(len(cases)),
        **{
            key: str(sum(case.find(tag) is not None for case in cases))
            for key, tag in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped"))
        },
    }
    assert root.attrib == expected
    suite = root.find("testsuite")
    assert suite.attrib == {"name": "quantfit.reproduce", **expected}
    return cases, expected


@pytest.mark.parametrize(
    "kind", ["clean", "breach", "denominator", "negative", "P0", "P1", "T1", "unverified", "short"]
)
def test_ten_native_cases_and_nonpasses_cannot_be_all_green(tmp_path, kind):
    ref, ref_paths, _ = make_bundle(tmp_path, "reference")
    options = {
        "breach": {"flips": 1},
        "denominator": {"unsafe": 11},
        "negative": {"disagreement": True},
        "P0": {"unsafe": 0},
        "T1": {"baseline_model": "synthetic/different-model"},
    }.get(kind, {})
    cand, cand_paths, cand_t0 = make_bundle(tmp_path, "candidate", **options)
    if kind == "P1":
        decision = compare_bundles(str(ref), str(ref))
    elif kind == "unverified":
        decision = compare(ref_paths[0], cand_paths[0])
    elif kind == "short":
        decision = compare(
            ref_paths[0], cand_paths[0], t0_reference=within_hardware_identical(ref_paths[:2]), t0_candidate=cand_t0
        )
    else:
        decision = compare_bundles(str(ref), str(cand))
    original = copy.deepcopy(decision)
    cases, counts = assert_counts(reproduction_to_junit(decision))
    assert [case.get("name") for case in cases] == NAMES
    assert decision == original
    assert cases[-1].find("failure") is None if kind == "clean" else cases[-1].find("failure") is not None
    if kind == "clean":
        assert counts == {"tests": "10", "failures": "0", "errors": "0", "skipped": "0"}
    else:
        assert int(counts["failures"]) >= 1
    if kind == "unverified":
        assert counts["skipped"] == "2" and counts["failures"] == "1"
    if kind == "short":
        assert counts["skipped"] == "1" and "protocol" in cases[0].find("skipped").get("message")
    if kind == "negative":
        assert cases[1].find("failure") is not None and cases[1].find("skipped") is None


@pytest.mark.parametrize("change", ["exit", "bool-exit", "passed", "P1", "T0", "truthy", "summary", "outcome"])
def test_contradictory_or_truthy_native_states_are_rejected(tmp_path, change):
    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    decision = compare_bundles(str(ref), str(cand))
    if change == "exit":
        decision["exit_code"] = 3
    elif change == "bool-exit":
        decision["exit_code"] = False
    elif change == "passed":
        decision["passed"] = 1
    elif change == "P1":
        decision["preconditions"]["P1_distinct_reports"]["pass"] = False
    elif change == "T0":
        decision["preconditions"]["T0_within_hardware_byte_identity"]["reference"]["pass"] = 1
    elif change == "truthy":
        decision["checks"]["T2_verdict_class"]["pass"] = "true"
    elif change == "summary":
        decision["preconditions"]["T0_within_hardware_byte_identity"]["pass"] = None
    else:
        decision["outcome"] = "private-provider-response"
    with pytest.raises(RuntimeError, match="native reproduction decision"):
        reproduction_to_junit(decision)


def test_xml_omits_all_untrusted_paths_prose_and_private_payloads(tmp_path):
    _, paths, _ = make_bundle(tmp_path, "reference")
    _, candidate_paths, _ = make_bundle(tmp_path, "candidate")
    decision = compare(paths[0], candidate_paths[0])
    marker = "private-provider <payload> & 'quoted' /secret/path"
    decision["headline"] = marker
    decision["reports"]["reference"]["path"] = marker
    decision["notes"] = [marker]
    decision["preconditions"]["T0_within_hardware_byte_identity"]["reference"]["note"] = marker
    decision["checks"]["T1_same_measurement"]["predicates"][0]["note"] = marker
    xml = reproduction_to_junit(decision)
    assert_counts(xml)
    assert "private-provider" not in xml and "/secret/path" not in xml and str(tmp_path) not in xml


@pytest.mark.parametrize("change", ["aggregate", "side", "truthy-aggregate", "truthy-side"])
def test_t0_supplied_summaries_cannot_contradict_native_sides(tmp_path, change):
    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    decision = compare_bundles(str(ref), str(cand))
    t0 = decision["preconditions"]["T0_within_hardware_byte_identity"]
    if change in ("aggregate", "truthy-aggregate"):
        t0["supplied"] = False if change == "aggregate" else 1
    else:
        t0["supplied_by_side"]["reference"] = False if change == "side" else 1
    with pytest.raises(RuntimeError, match="native reproduction decision"):
        reproduction_to_junit(decision)


@pytest.mark.parametrize("bundle", [False, True])
def test_cli_json_and_native_exit_unchanged_with_junit(tmp_path, capsys, bundle):
    ref, ref_paths, _ = make_bundle(tmp_path, "reference")
    cand, cand_paths, _ = make_bundle(tmp_path, "candidate", flips=1)
    source = (
        ["--reference-bundle", str(ref), "--candidate-bundle", str(cand)]
        if bundle
        else ["--reference", ref_paths[0], "--candidate", cand_paths[0]]
    )
    out, junit = tmp_path / "decision.json", tmp_path / "decision.xml"
    assert main(["reproduce", *source, "--out", str(out), "--junit", str(junit), "--json"]) == 3
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["exit_code"] == 3 and envelope["result"]["exit_code"] == 3
    assert json.loads(out.read_bytes()) == {
        key: value for key, value in envelope["result"].items() if key != "record_path"
    }
    assert "junit_path" not in envelope["result"]
    cases, counts = assert_counts(junit.read_text(encoding="utf-8"))
    assert len(cases) == 10 and int(counts["failures"]) >= 1


def test_operational_error_writes_one_bounded_error_without_decision(tmp_path, capsys):
    _, paths, _ = make_bundle(tmp_path, "candidate")
    out, junit = tmp_path / "decision.json", tmp_path / "error.xml"
    assert (
        main(
            [
                "reproduce",
                "--reference",
                str(tmp_path / "missing-private-file"),
                "--candidate",
                paths[0],
                "--out",
                str(out),
                "--junit",
                str(junit),
                "--json",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["result"] is None and not out.exists()
    xml = junit.read_text(encoding="utf-8")
    cases, counts = assert_counts(xml)
    assert counts == {"tests": "1", "failures": "0", "errors": "1", "skipped": "0"}
    assert cases[0].get("name") == "operational-error"
    assert str(tmp_path) not in xml and "missing-private-file" not in xml


@pytest.mark.parametrize("bundle", [False, True])
@pytest.mark.parametrize("alias", ["same-output", "hardlink-output", "source", "hardlink-source"])
def test_aliases_between_outputs_and_sources_preserve_all_inputs(tmp_path, bundle, alias):
    ref, ref_paths, _ = make_bundle(tmp_path, "reference")
    cand, cand_paths, _ = make_bundle(tmp_path, "candidate")
    source = (
        ["--reference-bundle", str(ref), "--candidate-bundle", str(cand)]
        if bundle
        else ["--reference", ref_paths[0], "--candidate", cand_paths[0]]
    )
    out, junit = tmp_path / "decision.json", tmp_path / "decision.xml"
    member = cand / "t0.json" if bundle else Path(cand_paths[0])
    original = member.read_bytes()
    if alias == "same-output":
        junit = out
    elif alias == "hardlink-output":
        out.write_bytes(b"existing output")
        os.link(out, junit)
    elif alias == "source":
        junit = member
    else:
        os.link(member, junit)
    assert main(["reproduce", *source, "--out", str(out), "--junit", str(junit), "--json"]) == 2
    assert member.read_bytes() == original
    if alias != "hardlink-output":
        assert not out.exists()
    else:
        assert out.read_bytes() == junit.read_bytes() == b"existing output"


@pytest.mark.parametrize("target", ["artifact", "nested"])
def test_positive_standalone_t0_and_consumed_nested_sources_protected(tmp_path, target):
    _, ref_paths, _ = make_bundle(tmp_path, "reference")
    _, cand_paths, _ = make_bundle(tmp_path, "candidate")
    t0 = tmp_path / "positive-t0.json"
    within_hardware_identical(ref_paths, out_path=str(t0))
    junit = t0 if target == "artifact" else Path(ref_paths[2])
    original = junit.read_bytes()
    assert (
        main(
            [
                "reproduce",
                "--reference",
                ref_paths[0],
                "--candidate",
                cand_paths[0],
                "--t0-reference",
                str(t0),
                "--junit",
                str(junit),
                "--json",
            ]
        )
        == 2
    )
    assert junit.read_bytes() == original


@pytest.mark.parametrize("hardlink", [False, True])
def test_discovered_positive_sources_stay_protected_when_next_t0_parse_fails(tmp_path, hardlink):
    _, ref_paths, _ = make_bundle(tmp_path, "reference")
    _, cand_paths, _ = make_bundle(tmp_path, "candidate")
    positive, malformed = tmp_path / "reference-t0.json", tmp_path / "candidate-t0.json"
    within_hardware_identical(ref_paths, out_path=str(positive))
    malformed.write_bytes(b"not JSON")
    member = Path(ref_paths[1])
    junit = member
    if hardlink:
        junit = tmp_path / "aliased.xml"
        os.link(member, junit)
    original = member.read_bytes()
    assert (
        main(
            [
                "reproduce",
                "--reference",
                ref_paths[0],
                "--candidate",
                cand_paths[0],
                "--t0-reference",
                str(positive),
                "--t0-candidate",
                str(malformed),
                "--junit",
                str(junit),
                "--json",
            ]
        )
        == 2
    )
    assert member.read_bytes() == junit.read_bytes() == original


@pytest.mark.parametrize(
    "value,code",
    [
        ({"pass": False, "reports": [{"path": "/private-unconsumed/negative.json"}]}, 4),
        ({"pass": True, "reports": [{"path": "/private-unconsumed/legacy.json"}]}, 3),
        (
            {
                "pass": True,
                "meets_protocol_replicate_count": False,
                "reports": [{"path": "/private-unconsumed/short.json"}],
            },
            3,
        ),
    ],
)
def test_negative_legacy_and_short_t0_labels_never_resolved(tmp_path, monkeypatch, value, code):
    import quantfit.reproduce as module

    _, ref_paths, _ = make_bundle(tmp_path, "reference")
    _, cand_paths, _ = make_bundle(tmp_path, "candidate")
    t0, junit = tmp_path / "t0.json", tmp_path / "result.xml"
    t0.write_text(json.dumps(value), encoding="utf-8")
    canonical = module._canonical_receiving_path

    def guarded(path):
        assert "private-unconsumed" not in str(path), "followed an unconsumed T0 label"
        return canonical(path)

    monkeypatch.setattr(module, "_canonical_receiving_path", guarded)
    assert (
        main(
            [
                "reproduce",
                "--reference",
                ref_paths[0],
                "--candidate",
                cand_paths[0],
                "--t0-reference",
                str(t0),
                "--junit",
                str(junit),
                "--json",
            ]
        )
        == code
    )
    assert_counts(junit.read_text(encoding="utf-8"))


def test_second_replacement_failure_returns_two_and_no_success_xml(tmp_path, monkeypatch, capsys):
    import quantfit.reproduce as module

    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    out, junit = tmp_path / "result.json", tmp_path / "result.xml"
    replace = module.os.replace
    destinations = []

    def fail_second(source, target):
        destinations.append(Path(target))
        if len(destinations) == 2:
            raise OSError("private-provider-response and path diagnostic")
        return replace(source, target)

    monkeypatch.setattr(module.os, "replace", fail_second)
    assert (
        main(
            [
                "reproduce",
                "--reference-bundle",
                str(ref),
                "--candidate-bundle",
                str(cand),
                "--out",
                str(out),
                "--junit",
                str(junit),
                "--json",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["result"] is None
    assert destinations[:2] == [out, junit]
    # JSON was already atomically published; the pair is not a transaction.
    assert json.loads(out.read_bytes())["exit_code"] == 0
    cases, counts = assert_counts(junit.read_text(encoding="utf-8"))
    assert counts["errors"] == "1" and len(cases) == 1
    assert "private-provider" not in junit.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".reproduce-*"))


def test_between_replacements_alias_substitution_blocks_xml_and_error_fallback(tmp_path, monkeypatch):
    import quantfit.reproduce as module

    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    out, junit = tmp_path / "result.json", tmp_path / "result.xml"
    member = cand / "t0.json"
    original = member.read_bytes()
    replace = module.os.replace
    replaced = []

    def substitute(source, target):
        replace(source, target)
        replaced.append(Path(target))
        if len(replaced) == 1:
            os.link(member, junit)

    monkeypatch.setattr(module.os, "replace", substitute)
    assert (
        main(
            [
                "reproduce",
                "--reference-bundle",
                str(ref),
                "--candidate-bundle",
                str(cand),
                "--out",
                str(out),
                "--junit",
                str(junit),
                "--json",
            ]
        )
        == 2
    )
    assert replaced == [out] and member.read_bytes() == junit.read_bytes() == original
    assert not list(tmp_path.glob(".reproduce-*"))


def test_between_replacements_changed_parent_cannot_write_into_closed_bundle(tmp_path, monkeypatch):
    import quantfit.reproduce as module

    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    probe = tmp_path / "link-probe"
    try:
        probe.symlink_to(ref, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation unavailable")
    probe.unlink()
    parent = tmp_path / "xml-parent"
    parent.mkdir()
    out, junit = tmp_path / "result.json", parent / "result.xml"
    originals = {path: path.read_bytes() for bundle in (ref, cand) for path in bundle.iterdir()}
    replace = module.os.replace
    replaced = []

    def substitute(source, target):
        replace(source, target)
        replaced.append(Path(target))
        if len(replaced) == 1:
            parent.rename(tmp_path / "externally-moved-parent")
            parent.symlink_to(ref, target_is_directory=True)

    monkeypatch.setattr(module.os, "replace", substitute)
    assert (
        main(
            [
                "reproduce",
                "--reference-bundle",
                str(ref),
                "--candidate-bundle",
                str(cand),
                "--out",
                str(out),
                "--junit",
                str(junit),
                "--json",
            ]
        )
        == 2
    )
    assert replaced == [out] and not (ref / "result.xml").exists()
    assert all(path.read_bytes() == raw for path, raw in originals.items())


@pytest.mark.parametrize("fault", ["partial", "short", "flush", "close", "interrupt"])
def test_both_buffers_are_staged_before_any_success_is_published(tmp_path, monkeypatch, fault):
    import quantfit.reproduce as module

    ref, _, _ = make_bundle(tmp_path, "reference")
    cand, _, _ = make_bundle(tmp_path, "candidate")
    out, junit = tmp_path / "result.json", tmp_path / "result.xml"
    factory = module.tempfile.NamedTemporaryFile
    opened = []

    class FaultStream:
        def __init__(self, *args, **kwargs):
            self.stream = factory(*args, **kwargs)
            self.name = self.stream.name
            opened.append(self.name)
            self.fail = len(opened) == 2

        def __enter__(self):
            return self

        def fileno(self):
            return self.stream.fileno()

        def write(self, raw):
            if self.fail and fault in ("partial", "short", "interrupt"):
                self.stream.write(raw[: len(raw) // 2])
                if fault == "interrupt":
                    raise KeyboardInterrupt()
                if fault == "partial":
                    raise OSError("synthetic partial staging")
                return len(raw) // 2
            return self.stream.write(raw)

        def flush(self):
            self.stream.flush()
            if self.fail and fault == "flush":
                raise OSError("synthetic flush")

        def __exit__(self, *args):
            self.stream.close()
            if self.fail and fault == "close":
                raise OSError("synthetic close")

    monkeypatch.setattr(module.tempfile, "NamedTemporaryFile", FaultStream)
    arguments = [
        "reproduce",
        "--reference-bundle",
        str(ref),
        "--candidate-bundle",
        str(cand),
        "--out",
        str(out),
        "--junit",
        str(junit),
        "--json",
    ]
    if fault == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            main(arguments)
        assert not junit.exists()
    else:
        assert main(arguments) == 2
        _, counts = assert_counts(junit.read_text(encoding="utf-8"))
        assert counts["tests"] == counts["errors"] == "1"
    assert not out.exists() and not list(tmp_path.glob(".reproduce-*"))
