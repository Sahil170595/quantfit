"""Safety verification: does quantization preserve refusal behavior?

The differentiator for quantfit — a quant that is faster/smaller but answers
prompts the fp16 baseline refused is a regression, not a win. `verify_safety`
measures that drift over a curated PUBLIC, umbrella-free probe set (never raw
harmbench/advbench), so the check is distributable.
"""
from __future__ import annotations

from quantfit.safety.verify import SafetyTax, verify_safety

__all__ = ["SafetyTax", "verify_safety"]
