"""quantfit routing policy.

Detects the hardware (`detect_target`) and routes (model, target, budget) onto a
feasible `EngineConfig` (`route`). The policy never touches quantization logic —
it only chooses which engine config to run, with a legible rationale.
"""

from quantfit.policy.route import route
from quantfit.policy.target import DEFAULT_BUDGET, detect_target

__all__ = ["detect_target", "route", "DEFAULT_BUDGET"]
