"""Two analysis cases and six original native axes; counts derived from the XML."""

from xml.etree import ElementTree as ET

from quantfit.junit import _axis_case, _render


def repeatability_to_junit(result: dict) -> str:
    suite = ET.Element("testsuite", {"name": "quantfit.repeatability"})
    full = ET.SubElement(suite, "testcase", {"name": "full-report-agreement", "classname": "analysis"})
    if not result["full_report_repeatability"]["pass"]:
        ET.SubElement(full, "failure", {"type": "PayloadDifference", "message": "full decoded reports differ"})
    native = ET.SubElement(suite, "testcase", {"name": "native-t0", "classname": "analysis"})
    if result["native_t0"]["status"] == "refused":
        ET.SubElement(native, "error", {"type": "NativeT0Refusal", "message": result["native_t0"]["reason"]})
    elif not result["native_t0"]["result"]["protocol_pass"]:
        ET.SubElement(native, "failure", {"type": "NativeT0Difference", "message": "native T0 disagreement"})
    for i, run in enumerate(result["runs"], 1):
        for name, axis in run["axes"].items():
            _axis_case(
                suite,
                axis=name,
                flips=axis["flagged_flips"],
                at_risk=axis["n_at_risk"],
                unmeasurable=not axis["measurable"],
                classname=f"replicate-{i}",
            )
    cases = list(suite.iter("testcase"))
    counts = {
        "tests": str(len(cases)),
        **{
            label: str(sum(c.find(tag) is not None for c in cases))
            for label, tag in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped"))
        },
    }
    suite.attrib.update(counts)
    ET.SubElement(suite, "system-out").text = (
        "Original flags are unconfirmed; a measured zero means the detector did not fire. " + result["scope"]
    )
    suites = ET.Element("testsuites", counts)
    suites.append(suite)
    return _render(suites)
