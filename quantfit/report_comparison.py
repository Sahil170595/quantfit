"""Strict decoded aggregate comparison with the four predeclared volatile fields."""

import copy

ALLOWED_VOLATILE_PATHS = ("/created_utc", "/judge_runtime_s", "/baseline/runtime_s", "/quantized/runtime_s")


def normalized(value: dict) -> dict:
    result = copy.deepcopy(value)
    del result["created_utc"], result["judge_runtime_s"]
    for arm in ("baseline", "quantized"):
        del result[arm]["runtime_s"]
    return result


def _token(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def differences(first, other, path: str = "") -> list[str]:
    """Strict types/values, list order and missing/null; RFC6901 pointers, no tolerance."""
    if type(first) is not type(other):
        return [path]
    if isinstance(first, dict):
        missing = set(first) ^ set(other)
        return sorted(
            [path + "/" + _token(key) for key in missing]
            + [
                item
                for key in set(first) & set(other)
                for item in differences(first[key], other[key], path + "/" + _token(key))
            ]
        )
    if isinstance(first, list):
        if len(first) != len(other):
            return [path]
        return sorted(
            item
            for i, (left, right) in enumerate(zip(first, other, strict=True))
            for item in differences(left, right, path + "/" + str(i))
        )
    return [] if first == other else [path]
