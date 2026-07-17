"""Drift report schema v1: a verify-safety run as an auditable artifact.

A printed summary is evidence only for whoever watched the terminal. The report
is the durable form: every input that determines the numbers is recorded —
judge + probe-dataset revision pins, decode parameters, the RESOLVED dtype of
each arm (never "auto"), an environment fingerprint, and per-arm runtimes — so a
report can be audited, diffed against a rerun, and cited.

Schema rules (enforced on construction and on parse):
  - `schema_version` must match; a report from a different schema is refused,
    never silently coerced.
  - dtypes are the resolved torch dtypes (e.g. "torch.float16"); the literal
    string "auto" is rejected — "auto" is an input, not a provenance fact.
  - judge/dataset revisions are the pinned commit hashes the run actually used.

The judge's card-reported external accuracy rides along labeled exactly as what
it is — measured on XSTest/GPT-4 responses, NOT calibrated on quantfit's own
probe distribution — so downstream readers cannot mistake it for a measured
error rate of this run (calibration is ROADMAP 0.6, gated on the 0.5 GO).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

SCHEMA_VERSION = 1

_FORBIDDEN_DTYPE = "auto"


class ReportError(RuntimeError):
    """Malformed or wrong-schema report (operational: clean CLI exit, no traceback)."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReportError(message)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass(frozen=True)
class ArmRun:
    """Provenance for one generation arm (baseline or quantized)."""

    model: str  # id or local path, as given
    revision: str | None  # HF commit hash when resolvable; None for local paths
    resolved_dtype: str  # e.g. "torch.float16" — the dtype actually loaded, never "auto"
    runtime_s: float  # wall-clock generation time for this arm

    def __post_init__(self) -> None:
        _require(isinstance(self.model, str) and bool(self.model), "arm model must be a non-empty string")
        _require(self.revision is None or isinstance(self.revision, str), "arm revision must be a string or null")
        _require(isinstance(self.resolved_dtype, str), "arm resolved_dtype must be a string")
        _require(
            self.resolved_dtype.strip().lower() != _FORBIDDEN_DTYPE,
            "resolved_dtype must be the loaded torch dtype, not the 'auto' input",
        )
        _require(_is_number(self.runtime_s), "arm runtime_s must be a number")


@dataclass(frozen=True)
class DriftReport:
    """One verify-safety run, fully reproducible from its own fields."""

    schema_version: int
    quantfit_version: str
    created_utc: str  # ISO 8601, UTC
    judge: dict  # id, revision (pinned), input_contract, card_xstest_accuracy (+ its label)
    probe_dataset: dict  # id, revision (pinned), split, n_probes
    decode: dict  # max_new_tokens, do_sample, chat_template policy
    env: dict  # python / torch / transformers / cuda / device
    baseline: ArmRun
    quantized: ArmRun
    judge_runtime_s: float
    drift: dict  # the SafetyDrift vector: counts, at-risk, CIs, MDE, verdict

    def __post_init__(self) -> None:
        # Structural validation — "validated" must mean more than "the keys exist".
        # A tampered report ("judge": "x", "drift": [], runtime as a string) must be
        # refused here, not crash whatever audit tooling reads the parsed object.
        _require(self.schema_version == SCHEMA_VERSION, f"schema_version must be {SCHEMA_VERSION}")
        for name in ("quantfit_version", "created_utc"):
            _require(isinstance(getattr(self, name), str), f"{name} must be a string")
        for name in ("judge", "probe_dataset", "decode", "env", "drift"):
            _require(isinstance(getattr(self, name), dict), f"{name} must be a JSON object")
        _require(isinstance(self.baseline, ArmRun), "baseline must be an ArmRun object")
        _require(isinstance(self.quantized, ArmRun), "quantized must be an ArmRun object")
        _require(_is_number(self.judge_runtime_s), "judge_runtime_s must be a number")

    def to_json(self, path: str) -> Path:
        """Write the report; returns the path."""
        p = Path(path)
        payload = asdict(self)
        p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return p

    @classmethod
    def from_json(cls, path: str) -> DriftReport:
        """Parse + validate a report file; refuses wrong schema or missing fields."""
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReportError(f"unreadable report {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ReportError(f"report {path} is not a JSON object")
        got = payload.get("schema_version")
        if got != SCHEMA_VERSION:
            raise ReportError(f"report {path} has schema_version {got!r}; this quantfit reads {SCHEMA_VERSION}")
        try:
            baseline = ArmRun(**payload.pop("baseline"))
            quantized = ArmRun(**payload.pop("quantized"))
            return cls(baseline=baseline, quantized=quantized, **payload)
        except TypeError as exc:  # missing/extra keys and non-object arms surface here
            raise ReportError(f"report {path} does not match schema v{SCHEMA_VERSION}: {exc}") from exc
        except ReportError as exc:  # field-level type violations from __post_init__
            raise ReportError(f"report {path}: {exc}") from exc


def environment_fingerprint() -> dict:
    """The runtime that produced the numbers: versions + device, resolved now."""
    import platform

    import torch
    import transformers

    cuda = torch.cuda.is_available()
    return {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "cuda": torch.version.cuda if cuda else None,
        "device": torch.cuda.get_device_name(0) if cuda else "cpu",
    }
