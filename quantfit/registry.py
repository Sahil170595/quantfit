"""Catalog of quantization methods + schemes.

Single source of truth for `quantfit list`, CLI validation, and which backend
handles a request. Recipe construction itself lives in the backend; this module
only describes *what* is offered and *whether* a (method, scheme) combo is valid.
"""
from __future__ import annotations

from dataclasses import dataclass

# compressed-tensors scheme presets quantfit exposes (a validated subset of what
# llm-compressor installs). Weight-only and weight+activation, down to FP4.
SCHEMES = (
    "W4A16",        # 4-bit weight, symmetric
    "W4A16_ASYM",   # 4-bit weight, asymmetric (AWQ default)
    "W8A16",        # 8-bit weight-only
    "W8A8",         # 8-bit weight + 8-bit activation
    "INT8",         # 8-bit integer weight+activation
    "W4A8",         # 4-bit weight, 8-bit activation
    "FP8_DYNAMIC",  # FP8 E4M3, dynamic activations (no calibration)
    "NVFP4",        # NVIDIA FP4 (Blackwell-native)
    "MXFP4",        # OCP microscaling FP4
)

# Backends.
BACKEND_CT = "compressed-tensors"  # llm-compressor -> vLLM
BACKEND_GGUF = "gguf"              # llama.cpp -> Ollama / llama.cpp


@dataclass(frozen=True)
class Method:
    name: str
    backend: str
    default_scheme: str
    needs_calibration: bool
    summary: str


METHODS: dict[str, Method] = {
    "awq": Method(
        "awq", BACKEND_CT, "W4A16_ASYM", True,
        "Activation-aware weight quant (4-bit); best 4-bit quality for instruct models",
    ),
    "gptq": Method(
        "gptq", BACKEND_CT, "W4A16", True,
        "Hessian/OBQ weight quant (4-bit, symmetric)",
    ),
    "autoround": Method(
        "autoround", BACKEND_CT, "W4A16", True,
        "Intel AutoRound sign-gradient weight quant; often beats GPTQ/AWQ",
    ),
    "smoothquant": Method(
        "smoothquant", BACKEND_CT, "W8A8", True,
        "SmoothQuant activation smoothing + W8A8 (8-bit weight+activation)",
    ),
    "fp8": Method(
        "fp8", BACKEND_CT, "FP8_DYNAMIC", False,
        "FP8 E4M3 dynamic; ~FP16 quality, 50% memory, no calibration (H100/Ada)",
    ),
    "rtn": Method(
        "rtn", BACKEND_CT, "W4A16", False,
        "Round-to-nearest; no calibration; the honest baseline",
    ),
}

# Methods that constrain their scheme to weight+activation presets.
_ACT_QUANT_METHODS = {"smoothquant"}
_ACT_SCHEMES = {"W8A8", "INT8", "W4A8"}
# FP8/FP4 presets pair with the dedicated fp8/scheme path, not weight-only algos.
_FLOAT_SCHEMES = {"FP8_DYNAMIC", "NVFP4", "MXFP4"}
_WEIGHT_ONLY_METHODS = {"awq", "gptq", "autoround", "rtn"}


class UnsupportedCombo(ValueError):
    """Raised for an unknown method or an invalid (method, scheme) pairing."""


def resolve(method: str, scheme: str | None) -> tuple[Method, str]:
    """Validate a method (+ optional scheme override) and return (Method, scheme)."""
    if method not in METHODS:
        raise UnsupportedCombo(
            f"unknown method {method!r}; choose from {sorted(METHODS)}"
        )
    m = METHODS[method]
    chosen = scheme or m.default_scheme
    if chosen not in SCHEMES:
        raise UnsupportedCombo(f"unknown scheme {chosen!r}; choose from {list(SCHEMES)}")
    if method in _ACT_QUANT_METHODS and chosen not in _ACT_SCHEMES:
        raise UnsupportedCombo(
            f"{method} requires a weight+activation scheme {sorted(_ACT_SCHEMES)}, got {chosen}"
        )
    if method in _WEIGHT_ONLY_METHODS and chosen in _FLOAT_SCHEMES:
        raise UnsupportedCombo(
            f"{method} is a weight-only algorithm; use --method fp8 for {chosen}"
        )
    return m, chosen


def catalog() -> str:
    """Human-readable table for `quantfit list`."""
    lines = ["methods:"]
    for m in METHODS.values():
        calib = "calibrated" if m.needs_calibration else "no-calib"
        lines.append(f"  {m.name:<12} [{m.backend}] default={m.default_scheme:<12} ({calib})  {m.summary}")
    lines.append("\nschemes (override with --scheme): " + ", ".join(SCHEMES))
    return "\n".join(lines)
