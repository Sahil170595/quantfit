"""Frozen quantization spec.

One calibration recipe applied to every method, so quants are comparable across
AWQ/GPTQ instead of confounded by differing calibration data. Override per-run
via the Python API (`quantize(..., spec=QuantSpec(...))`); the CLI always uses
the frozen default — that is the contract.
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
    # The dataset commit. Until 0.14.2 the dataset loaded at `main`, unpinned, though a
    # calibration set is as much a measurement input as the probe set verify-safety pins.
    # Pinned 2026-10-01 to the commit `main` already resolved to (last modified 2024-01-04),
    # so no number moves (validation/2026-10-01-probe-at-n64/). Not in fingerprint(): the
    # pin is what keeps the fingerprint sufficient, and adding it would rename every key.
    calib_revision: str = "b08601e04326c79dfdd32d625aee71d232d685c3"
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
