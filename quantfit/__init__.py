"""quantfit — quantize an LLM if it fits your GPU, and check it still refuses what it should."""

from quantfit.spec import DEFAULT_SPEC, QuantSpec

__version__ = "0.12.12"

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
    "run_screen": ("quantfit.screen", "run_screen"),
    "ScreenError": ("quantfit.screen", "ScreenError"),
    "model_card_fragment": ("quantfit.modelcard", "model_card_fragment"),
    "build_labeling_sheet": ("quantfit.safety.calibrate", "build_labeling_sheet"),
    "ingest_labels": ("quantfit.safety.calibrate", "ingest_labels"),
    "CalibrationError": ("quantfit.safety.calibrate", "CalibrationError"),
    "mde_block": ("quantfit.safety.mde", "mde_block"),
    "effective_mde": ("quantfit.safety.mde", "effective_mde"),
    "run_gate": ("quantfit.gate", "run_gate"),
    "GateError": ("quantfit.gate", "GateError"),
}

__all__ = ["DEFAULT_SPEC", "QuantSpec", "__version__", *sorted(_LAZY)]  # noqa: PLE0604 — _LAZY keys are str literals


def __getattr__(name: str):
    if name in _LAZY:
        import importlib

        module, attr = _LAZY[name]
        return getattr(importlib.import_module(module), attr)
    raise AttributeError(f"module 'quantfit' has no attribute {name!r}")
