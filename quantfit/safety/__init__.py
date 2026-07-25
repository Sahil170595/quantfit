"""Safety verification: does quantization preserve refusal behavior?

The differentiator for quantfit — a quant that is faster/smaller but answers
prompts the unquantized baseline refused is a regression, not a win.
`verify_safety` measures that drift over a curated PUBLIC, umbrella-free probe
set (never raw harmbench/advbench), so the check is distributable.
"""

from __future__ import annotations

from quantfit.safety.calibrate import CalibrationError, build_labeling_sheet, ingest_labels
from quantfit.safety.mde import MdeError, effective_mde, mde_block
from quantfit.safety.report import ArmRun, DriftReport, ReportError
from quantfit.safety.verify import SafetyDrift, detectable_flip_rate, verify_safety, wilson_interval

__all__ = [
    "ArmRun",
    "CalibrationError",
    "DriftReport",
    "MdeError",
    "ReportError",
    "SafetyDrift",
    "build_labeling_sheet",
    "detectable_flip_rate",
    "effective_mde",
    "ingest_labels",
    "mde_block",
    "verify_safety",
    "wilson_interval",
]
