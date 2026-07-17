"""Safety verification: does quantization preserve refusal behavior?

The differentiator for quantfit — a quant that is faster/smaller but answers
prompts the unquantized baseline refused is a regression, not a win.
`verify_safety` measures that drift over a curated PUBLIC, umbrella-free probe
set (never raw harmbench/advbench), so the check is distributable.
"""

from __future__ import annotations

from quantfit.safety.report import ArmRun, DriftReport, ReportError
from quantfit.safety.verify import SafetyDrift, detectable_flip_rate, verify_safety, wilson_interval

__all__ = [
    "ArmRun",
    "DriftReport",
    "ReportError",
    "SafetyDrift",
    "detectable_flip_rate",
    "verify_safety",
    "wilson_interval",
]
