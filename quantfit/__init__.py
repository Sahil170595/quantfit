"""quantfit — quantize an LLM if it fits your GPU, and check it still refuses what it should."""

from quantfit.spec import DEFAULT_SPEC, QuantSpec

__version__ = "0.4.0"

# Heavy surfaces are re-exported lazily (PEP 562) so `import quantfit` stays
# dependency-light: nothing here drags torch, transformers, or huggingface_hub
# until the attribute is actually touched.
_LAZY = {
    "verify_safety": ("quantfit.safety.verify", "verify_safety"),
    "SafetyDrift": ("quantfit.safety.verify", "SafetyDrift"),
    "DriftReport": ("quantfit.safety.report", "DriftReport"),
    "quantize": ("quantfit.quantize", "quantize"),
    "capacity_plan": ("quantfit.fit", "capacity_plan"),
    "CapacityPlan": ("quantfit.fit", "CapacityPlan"),
}

__all__ = ["DEFAULT_SPEC", "QuantSpec", "__version__", *sorted(_LAZY)]


def __getattr__(name: str):
    if name in _LAZY:
        import importlib

        module, attr = _LAZY[name]
        return getattr(importlib.import_module(module), attr)
    raise AttributeError(f"module 'quantfit' has no attribute {name!r}")
