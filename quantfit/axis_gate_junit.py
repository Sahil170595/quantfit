"""Opted per-axis resolution/detection cases and an explicit aggregate CI outcome."""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET


def axis_gate_to_junit(decision: dict[str, Any], *, baseline: str, quant: str) -> str:
    from quantfit.junit import GATE_SUITE_NAME, _case, _finalise

    suite = ET.Element("testsuite")
    classname = f"{baseline}->{quant}"
    for name, row in decision["axis_results"].items():
        resolution = _case(suite, f"{name} resolution", classname)
        if row["exit_code"] == 5:
            ET.SubElement(
                resolution,
                "failure",
                {"type": "ThresholdUnresolvable", "message": "native MDE cannot resolve declared effect"},
            )
        elif not row["observed"] or row["exit_code"] == 4 or not row["resolution"]["resolution_proven"]:
            ET.SubElement(
                resolution,
                "skipped",
                {"message": "unobserved/unmeasured or perfect-judge floor; resolution not proven"},
            )
        detection = _case(suite, f"{name} detection (gated)", classname)
        if row["exit_code"] == 3:
            ET.SubElement(
                detection,
                "failure",
                {"type": "NativeDetection", "message": "flagged flips reached native k*; human verification required"},
            )
        elif row["exit_code"] != 0:
            ET.SubElement(
                detection, "skipped", {"message": "no passing detection verdict: unobserved/unmeasurable/unresolved"}
            )
    for name in decision["diagnostic_axes"]:
        diagnostic = _case(suite, f"{name} (ungated)", classname)
        ET.SubElement(diagnostic, "skipped", {"message": "diagnostic only; does not govern selected policy"})
    overall = _case(suite, "selected-axis overall", classname)
    code = decision["exit_code"]
    if code != 0:
        kind = {3: "NativeDetection", 4: "SelectedAxisUnmeasurable", 5: "ThresholdUnresolvable"}[code]
        ET.SubElement(overall, "failure", {"type": kind, "message": decision["verdict"]})
    ET.SubElement(suite, "system-out").text = decision["message"] + "\n" + "\n".join(decision["notes"])
    return _finalise(suite, GATE_SUITE_NAME)
