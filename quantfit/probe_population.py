"""Private holding of the native loader's rows; public contexts contain counts only.

Source pins and these structural checks authenticate neither remote completeness
nor curation. Saved contexts describe consumed native reports, without Hub I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from quantfit.probe_bundle import LOCAL_FIELDS, LocalProbeCorpus, _dataset, _identity, _load, _source_from_context
from quantfit.resolution import MAX_PROBES
from quantfit.safety.calibration_binding import BoundCalibration
from quantfit.safety.verify import Probe, ProbeCorpus, _corpus

if TYPE_CHECKING:
    from quantfit.safety.retention_io import HeldFile

ZONES = ("clear_safe", "clear_unsafe", "borderline")
FIELDS = {
    "id",
    "revision",
    "split",
    "n_probes",
    "expected_unsafe_n",
    "expected_safe_n",
    "zone_counts",
    "population_basis",
}
BASES = {"resolved_native_population", "saved_report_native_counts", "unavailable_no_reports"}


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


@dataclass(frozen=True, slots=True)
class _PreparedPopulation:
    source: ProbeCorpus | LocalProbeCorpus
    probes: tuple[Probe, ...]
    held_file: HeldFile | None = None
    publication_inputs: tuple[str, ...] = ()
    publication_outputs: tuple[str, ...] = ()


def prepare(
    token: str | None, source: ProbeCorpus | LocalProbeCorpus, *, probe_bundle_path: str | None = None
) -> _PreparedPopulation:
    from quantfit.safety import verify

    source = _corpus(source)
    if type(source) is LocalProbeCorpus:
        probes, held = _load(probe_bundle_path, source)
        return _PreparedPopulation(source, tuple(probes), held)
    if probe_bundle_path is not None:
        raise RuntimeError("invalid_probe_corpus_options")
    held_source, probes = verify._prepare_probes(token, source)
    return _PreparedPopulation(held_source, tuple(probes))


def context(population: _PreparedPopulation) -> dict[str, Any]:
    source, probes = population.source, population.probes
    return {
        **_identity(source),
        "n_probes": len(probes),
        "expected_unsafe_n": sum(p.expected == "unsafe" for p in probes),
        "expected_safe_n": sum(p.expected == "safe" for p in probes),
        "zone_counts": {z: sum(p.zone == z for p in probes) for z in ZONES},
        "population_basis": "resolved_native_population",
    }


def unavailable(source: ProbeCorpus | LocalProbeCorpus) -> dict[str, Any]:
    source = _corpus(source)
    return {
        **_identity(source),
        "n_probes": None,
        "expected_unsafe_n": None,
        "expected_safe_n": None,
        "zone_counts": None,
        "population_basis": "unavailable_no_reports",
    }


def admit_context(value: Any, *, allow_missing: bool = False) -> dict[str, Any]:
    _require(type(value) is dict, "invalid_probe_corpus_context")
    fields = (FIELDS - {"id", "revision", "split"}) | LOCAL_FIELDS if "source_kind" in value else FIELDS
    _require(set(value) == fields, "invalid_probe_corpus_context")
    _source_from_context(value)
    _require(type(value["population_basis"]) is str and value["population_basis"] in BASES, "invalid_population_basis")
    if value["population_basis"] == "unavailable_no_reports":
        _require(
            allow_missing
            and all(value[k] is None for k in ("n_probes", "expected_unsafe_n", "expected_safe_n", "zone_counts")),
            "unavailable_population_requires_all_missing",
        )
    else:
        n, u, s, zones = (value[k] for k in ("n_probes", "expected_unsafe_n", "expected_safe_n", "zone_counts"))
        _require(
            type(n) is int
            and 1 <= n <= MAX_PROBES
            and type(u) is int
            and type(s) is int
            and min(u, s) >= 0
            and u + s == n,
            "invalid_native_population_census",
        )
        _require(
            type(zones) is dict
            and set(zones) == set(ZONES)
            and all(type(z) is int and z >= 0 for z in zones.values())
            and sum(zones.values()) == n,
            "invalid_native_zone_census",
        )
    return {**value, "zone_counts": None if value["zone_counts"] is None else dict(value["zone_counts"])}


def report_context(report: Any, source: ProbeCorpus | LocalProbeCorpus) -> dict[str, Any]:
    from quantfit.resolution import _axes
    from quantfit.safety.calibration_binding import _same_numbers

    source = _corpus(source)
    _axes(report)
    n = report.drift["n_probes"]
    _same_numbers(
        report.probe_dataset,
        _dataset(source, n),
        "expected pinned native probe dataset",
    )
    zones = report.drift["by_zone"]
    _require(set(zones) <= set(ZONES), "unsupported_native_probe_zone")
    return admit_context(
        {
            **_identity(source),
            "n_probes": n,
            "expected_unsafe_n": report.drift["refusal_robustness"]["expected_unsafe_n"],
            "expected_safe_n": report.drift["over_refusal"]["expected_safe_n"],
            "zone_counts": {z: zones[z]["n"] if z in zones else 0 for z in ZONES},
            "population_basis": "saved_report_native_counts",
        }
    )


def match_report(report: Any, expected: dict[str, Any]) -> None:
    from quantfit.safety.calibration_binding import _same_numbers

    expected = admit_context(expected)
    actual = report_context(report, _source_from_context(expected))
    _same_numbers(
        {k: v for k, v in actual.items() if k != "population_basis"},
        {k: v for k, v in expected.items() if k != "population_basis"},
        "held native population/report census",
    )


def preflight_calibration(
    path: str, source: ProbeCorpus | LocalProbeCorpus, baseline: str, quant: str, max_tokens: int
) -> BoundCalibration:
    from quantfit.safety import verify as v
    from quantfit.safety.calibration_binding import _same_numbers, load_bound_calibration

    bound = load_bound_calibration(path)
    _same_numbers(
        bound.identity["judge"],
        {"id": v.JUDGE_MODEL_ID, "revision": v.JUDGE_REVISION, "input_contract": v.JUDGE_INPUT_CONTRACT},
        "requested calibration judge",
    )
    dataset = bound.identity["probe_dataset"]
    _same_numbers(
        {k: v for k, v in dataset.items() if k != "n_probes"},
        _identity(source),
        "requested calibration corpus",
    )
    _require(
        bound.identity["baseline"]["model"] == baseline and bound.identity["quantized"]["model"] == quant,
        "calibration requested arms mismatch",
    )
    _same_numbers(
        bound.identity["decode"],
        {"max_new_tokens": max_tokens, "greedy": True, "chat_template": v.DECODE_CHAT_TEMPLATE_POLICY},
        "requested calibration decode",
    )
    return bound
