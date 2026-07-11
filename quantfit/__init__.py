"""quantfit — quantize an LLM if it fits your GPU."""

from quantfit.gpufit import FitReport, check_fit
from quantfit.spec import DEFAULT_SPEC, QuantSpec

__version__ = "0.4.0"
__all__ = ["FitReport", "check_fit", "QuantSpec", "DEFAULT_SPEC", "__version__"]
