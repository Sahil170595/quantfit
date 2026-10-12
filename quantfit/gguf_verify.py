"""Rich GGUF structure/native usability results; never a quantization-quality verdict."""

from __future__ import annotations

import math

from quantfit.gguf_structure import InvalidGguf, UnsupportedGguf, _supported, scan


def verify_gguf(path: str, *, runtime: bool = False, timeout_seconds: float = 120, max_new_tokens: int = 8) -> dict:
    """Validate the supported binary profile, optionally one bounded native CPU request."""
    result = {
        "verify_schema_version": 1,
        "path": path,
        "exit_code": 2,
        "passed": False,
        "structure": {"status": "unverified"},
        "runtime": {
            "requested": runtime if type(runtime) is bool else False,
            "status": "unverified" if runtime else "not_requested",
        },
        "quantization_quality_verified": False,
        "scientific_go": False,
        "scope": "GGUF structure/usability only; tensor contents, quantization quality, safety and scientific GO are not established.",
    }
    try:
        _supported(type(runtime) is bool, "runtime request must be boolean")
        _supported(
            type(timeout_seconds) in (int, float) and math.isfinite(timeout_seconds) and 0 < timeout_seconds <= 1800,
            "native timeout must be finite positive and at most1800seconds",
        )
        _supported(
            type(max_new_tokens) is int and 1 <= max_new_tokens <= 64, "native token budget must be integer1..64"
        )
        structure, selected, file_identity = scan(path)
        result.update(
            path=structure.pop("path"),
            structure=structure,
            exit_code=0,
            passed=True,
            message="GGUF structure OK; payload meaning and native usability unverified",
        )
        if runtime:
            from quantfit.gguf_runtime import verify_runtime

            outcome = verify_runtime(
                result["path"], selected, file_identity, timeout_seconds=timeout_seconds, max_new_tokens=max_new_tokens
            )
            result.update(
                runtime=outcome,
                exit_code=outcome["exit_code"],
                passed=outcome["exit_code"] == 0,
                message="GGUF structure OK; native CPU usability " + outcome["status"],
            )
    except InvalidGguf as exc:
        result.update(exit_code=3, structure={"status": "fail"}, message="GGUF structure FAIL: " + str(exc))
    except (UnsupportedGguf, OSError, RuntimeError, ValueError, TypeError) as exc:
        result.update(
            exit_code=2,
            passed=False,
            message="GGUF verification unverified: "
            + (str(exc) if isinstance(exc, UnsupportedGguf) else "input/capability unavailable"),
        )
        if runtime:
            result["runtime"].update(status="unverified")
    return result
