"""Private whole local probe populations; raw-byte integrity is not curation or authenticity."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from quantfit.safety.retention_io import HeldFile
    from quantfit.safety.verify import Probe

FORMAT = "quantfit-probe-bundle-v1"
MAX_RAW_BYTES = 64 * 1024 * 1024
LOCAL_FIELDS = {"source_kind", "format", "sha256"}
SCOPE = (
    "Whole private operator-supplied population; exact raw-byte integrity only. "
    "No curation, label truth, authorship, source completeness, sensitivity or scientific qualification."
)


class ProbeBundleError(RuntimeError):
    """Categorical errors never include private paths or row values."""


def _require(ok: bool) -> None:
    if not ok:
        raise ProbeBundleError("invalid_probe_bundle")


@dataclass(frozen=True)
class LocalProbeCorpus:
    """An expected whole RAW SHA256 identity, with no path or Hub revision."""

    sha256: str

    def __post_init__(self) -> None:
        _require(type(self.sha256) is str and re.fullmatch(r"[0-9a-f]{64}", self.sha256) is not None)


def _identity(source: Any) -> dict[str, Any]:
    if type(source) is LocalProbeCorpus:
        source.__post_init__()
        return {"source_kind": "local", "format": FORMAT, "sha256": source.sha256}
    return {"id": source.id, "revision": source.revision, "split": source.split}


def _dataset(source: Any, n: int) -> dict[str, Any]:
    return {**_identity(source), "n_probes": n}


def _source_from_context(value: dict[str, Any]) -> Any:
    if "source_kind" in value:
        _require(type(value["source_kind"]) is str and value["source_kind"] == "local")
        _require(type(value.get("format")) is str and value["format"] == FORMAT)
        return LocalProbeCorpus(value["sha256"])
    from quantfit.safety.verify import ProbeCorpus

    return ProbeCorpus(value["id"], value["revision"], value["split"])


def _pin(value: dict[str, Any], *, include_split: bool = False) -> str:
    """Render the declared source without inventing Hub identity for local bytes."""
    if "source_kind" in value:
        source = _source_from_context(value)
        return f"local:{FORMAT}@sha256:{source.sha256}"
    return f"{value['id']}@{value['revision']}" + (f"/{value['split']}" if include_split else "")


def _admit_local_dataset(value: Any) -> dict[str, Any]:
    from quantfit.resolution import MAX_PROBES

    _require(type(value) is dict and set(value) == LOCAL_FIELDS | {"n_probes"})
    _require(type(value["source_kind"]) is str and value["source_kind"] == "local")
    _require(type(value["format"]) is str and value["format"] == FORMAT)
    source = LocalProbeCorpus(value["sha256"])
    n = value["n_probes"]
    _require(type(n) is int and 1 <= n <= MAX_PROBES)
    return _dataset(source, n)


def _json(raw: bytes) -> Any:
    from quantfit.safety.retained_labels import _float, _integer, _nonfinite, _pairs

    text = raw.decode("utf-8")
    _require(not text.startswith("\ufeff"))
    return json.loads(text, object_pairs_hook=_pairs, parse_int=_integer, parse_float=_float, parse_constant=_nonfinite)


def _paths(inputs: tuple[str, ...], outputs: tuple[str | None, ...], cache_dir: str | None = None) -> None:
    from quantfit.corpus_gate import _admit_publication_paths

    try:
        _admit_publication_paths(inputs, tuple(p for p in outputs if p is not None), cache_dir=cache_dir)
    except (OSError, RuntimeError, ValueError, TypeError):
        raise ProbeBundleError("invalid_probe_bundle_paths") from None


def _roots(inputs: tuple[str, ...], roots: tuple[str, ...]) -> None:
    from pathlib import Path

    from quantfit.safety.retention_io import canonical

    try:
        for raw in roots:
            root = canonical(raw)
            _require(all(not p.exists() or p.is_dir() for p in (root, *root.parents)))
            _require(not any(Path(p).resolve().is_relative_to(root) for p in inputs))
    except (OSError, RuntimeError, ValueError, TypeError):
        raise ProbeBundleError("invalid_probe_bundle_paths") from None


def _load(path: str | None, source: LocalProbeCorpus) -> tuple[list[Probe], HeldFile]:
    from quantfit.safety.retention_io import hold
    from quantfit.safety.verify import _admit_probe_rows

    try:
        if not isinstance(path, str) or type(source) is not LocalProbeCorpus:
            raise ProbeBundleError("invalid_probe_bundle")
        _require(type(path) is str and bool(path))
        source.__post_init__()
        held = hold(path, MAX_RAW_BYTES)
        _require(hashlib.sha256(held.data).hexdigest() == source.sha256)
        value = _json(held.data)
        _require(type(value) is dict and set(value) == {"probe_bundle_schema", "probes"})
        _require(type(value["probe_bundle_schema"]) is int and value["probe_bundle_schema"] == 1)
        _require(type(value["probes"]) is list)
        probes = _admit_probe_rows(value["probes"], closed=True)
        held.check()
        return probes, held
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, RecursionError):
        raise ProbeBundleError("invalid_probe_bundle") from None


def prepare_probe_bundle(rows_path: str, *, out_path: str) -> dict[str, Any]:
    """Validate all private input rows, then exclusively publish one complete bundle."""
    from quantfit.safety.retention_io import admit_outputs, hold, publish
    from quantfit.safety.verify import _admit_probe_rows

    try:
        _paths((rows_path,), (out_path,))
        targets = admit_outputs((out_path,), ())
        held = hold(rows_path, MAX_RAW_BYTES)
        values = _json(held.data)
        _require(type(values) is list)
        probes = _admit_probe_rows(values, closed=True)
        raw = (
            json.dumps({"probe_bundle_schema": 1, "probes": values}, ensure_ascii=True, allow_nan=False, indent=2)
            + "\n"
        ).encode("utf-8")
        _require(len(raw) <= MAX_RAW_BYTES)
        source = LocalProbeCorpus(hashlib.sha256(raw).hexdigest())
        receipt = {
            **_dataset(source, len(probes)),
            "expected_unsafe_n": sum(p.expected == "unsafe" for p in probes),
            "expected_safe_n": sum(p.expected == "safe" for p in probes),
            "zone_counts": {z: sum(p.zone == z for p in probes) for z in ("clear_safe", "clear_unsafe", "borderline")},
            "scope": SCOPE,
        }
        held.check()
        publish(((targets[0], raw),), (held,))
        return receipt
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, RecursionError):
        raise ProbeBundleError("invalid_probe_bundle") from None
