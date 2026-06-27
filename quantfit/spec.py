"""Frozen quantization spec.

One calibration recipe applied to every method, so quants are comparable across
AWQ/GPTQ instead of confounded by differing calibration data. Override per-run on
the CLI, but the default is the contract.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuantSpec:
    bits: int = 4
    group_size: int = 128
    calib_dataset: str = (
        "Salesforce/wikitext"  # HF dataset id (namespaced; bare "wikitext" fails the strict URI parser)
    )
    calib_config: str = "wikitext-103-raw-v1"  # config/subset
    calib_split: str = "train"
    calib_samples: int = 128
    calib_seqlen: int = 2048
    seed: int = 42

    def fingerprint(self) -> str:
        """Compact, stable string for model-card provenance + manifest keys."""
        return (
            f"w{self.bits}g{self.group_size}-"
            f"{self.calib_config}-n{self.calib_samples}-"
            f"L{self.calib_seqlen}-s{self.seed}"
        )


DEFAULT_SPEC = QuantSpec()
