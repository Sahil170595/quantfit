"""Axis-specific XML never turns old flags or missing measurements into green."""

import copy
from xml.etree import ElementTree as ET

import pytest
from test_screen_compare import compare, pair


def render(record):
    from quantfit.screen_compare_junit import screen_comparison_to_junit

    return ET.fromstring(screen_comparison_to_junit(record))


def test_axis_and_overall_flags_precede_missing_or_incompatible(tmp_path):
    reference, candidate = pair(tmp_path, (1, None), (0, None), missing_cand=("g0",))
    record = compare(reference, candidate)
    root = render(record)
    cases = {case.attrib["name"]: case for case in root.iter("testcase")}
    assert set(cases) == {"g0.refusal_robustness", "g0.over_refusal", "overall"}
    assert cases["g0.refusal_robustness"].find("failure") is not None
    assert cases["g0.over_refusal"].find("skipped") is not None
    assert cases["overall"].find("failure") is not None
    assert root.attrib["failures"] == "2" and root.attrib["tests"] == "3"


@pytest.mark.parametrize(
    "mutation",
    ["code", "flag", "count", "transition", "status", "basis", "identity", "protocol", "path", "screen_flag"],
)
def test_contradictory_decisions_are_categorical_refusals(tmp_path, mutation):
    from quantfit.screen_compare import ScreenComparisonError

    reference, candidate = pair(tmp_path, (1, None), (0, None))
    record = copy.deepcopy(compare(reference, candidate))
    row = record["rows"][0]
    axis = row["axes"]["refusal_robustness"]
    if mutation == "code":
        record["exit_code"] = 0
    elif mutation == "flag":
        axis["reference"]["flagged"] = False
    elif mutation == "count":
        axis["reference"]["flips"] = False
    elif mutation == "transition":
        axis["transition"] = "no_flag"
    elif mutation == "status":
        axis["status"] = "missing_reference"
    elif mutation == "basis":
        axis["comparison_basis"] = None
    elif mutation == "identity":
        row["identity"]["same_weights_established"] = True
    elif mutation == "protocol":
        row["protocol_match"] = False
    elif mutation == "path":
        row["name"] = "/PRIVATE/provider/path"
    else:
        record["screens"]["reference"]["rows"][0]["refusal_robustness"]["flips"] = 0
    with pytest.raises(ScreenComparisonError) as error:
        render(record)
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("contradiction", ["native_status", "native_exit", "native_regression_boolean"])
def test_original_screen_adverse_metadata_cannot_contradict_zero_axis_flags(tmp_path, contradiction):
    from quantfit.screen_compare import ScreenComparisonError

    reference, candidate = pair(tmp_path)
    record = compare(reference, candidate)
    screen = record["screens"]["reference"]
    if contradiction == "native_status":
        screen["rows"][0]["status"] = "regression"
    elif contradiction == "native_exit":
        screen["exit_code"] = 3
    else:
        screen["rows"][0]["regression_detected"] = True
    with pytest.raises(ScreenComparisonError):
        render(record)


@pytest.mark.parametrize("unmeasured,code,skipped", [(None, 0, 0), ("danger", 4, 2)])
def test_clean_and_unmeasured_xml_keep_overall_state(tmp_path, unmeasured, code, skipped):
    reference, candidate = pair(tmp_path, (0, unmeasured), (0, unmeasured))
    record = compare(reference, candidate)
    root = render(record)
    assert record["exit_code"] == code and root.attrib["failures"] == "0"
    assert len(list(root.iter("skipped"))) == skipped and root.attrib["tests"] == "3"


@pytest.mark.parametrize("kind", ["protocol", "identity"])
def test_incompatible_axis_still_fails_on_original_native_flag(tmp_path, kind):
    mutate = (
        (lambda payload: payload["env"].__setitem__("python", "other runtime"))
        if kind == "protocol"
        else (lambda payload: payload["quantized"].__setitem__("artifact_sha256", "b" * 64))
    )
    reference, candidate = pair(tmp_path, (1, None), (0, None), mutate=mutate)
    root = render(compare(reference, candidate))
    cases = {case.attrib["name"]: case for case in root.iter("testcase")}
    assert cases["g0.refusal_robustness"].find("failure") is not None
    assert cases["g0.over_refusal"].find("skipped") is not None
    assert cases["overall"].find("failure") is not None
