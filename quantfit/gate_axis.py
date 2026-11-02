"""The native single-axis resolution/detection criterion, shared by both gate modes."""

from __future__ import annotations

from typing import Any


def evaluate_axis(
    n: int, flips: int | None, threshold: float, eps: dict[str, Any], best_case_n: int, *, stage: str
) -> dict[str, Any]:
    from quantfit import gate

    block = gate._block(eps, n)
    resolution = gate._resolution(stage, threshold, block, eps, best_case_n)
    if stage == gate.STAGE_PRE_RUN:
        code = None if resolution["not_refused"] else gate.EXIT_UNRESOLVABLE
    elif n == 0:
        code = gate.EXIT_UNMEASURABLE
    elif (
        flips is not None
        and flips >= resolution["detection_threshold_flips"]
        and not resolution["no_reachable_rejection"]
    ):
        code = gate.EXIT_FAIL
    elif not resolution["not_refused"]:
        code = gate.EXIT_UNRESOLVABLE
    else:
        code = gate.EXIT_PASS
    return {"block": block, "resolution": resolution, "exit_code": code}
