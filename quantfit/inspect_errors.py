"""Shared lightweight Inspect/native protocol error identity."""


class InspectTaskError(RuntimeError):
    """Protocol violation or missing optional provider; operational CLI exit 2."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InspectTaskError(message)
