"""Closed approved-file shapes, precise false markers and same-buffer relationships."""

from __future__ import annotations

import hashlib
import json
import math
from importlib.resources import files

from quantfit.bundle import _PRIVATE, _constant, _float, _json, _pairs, _report
from quantfit.evidence_profile import INVENTORY, PREFIX
from quantfit.repeatability import _analyze_held
from quantfit.replay_bundle import _validate
from quantfit.report_comparison import ALLOWED_VOLATILE_PATHS, normalized
from quantfit.resolution import _axes


class EvidenceError(RuntimeError):
    """Unsupported evidence, bounded HTTP or publication failure; CLI exit 2."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _equal(first, other) -> bool:
    return json.dumps(first, sort_keys=True, allow_nan=False) == json.dumps(other, sort_keys=True, allow_nan=False)


def _closed(value, shape, templates: dict) -> None:
    if isinstance(shape, dict) and set(shape) == {"$ref"}:
        return _closed(value, templates[shape["$ref"]], templates)
    if isinstance(shape, dict):
        require(type(value) is dict and set(value) == set(shape), "unsupported closed evidence object fields")
        for key in shape:
            _closed(value[key], shape[key], templates)
    elif isinstance(shape, list):
        require(type(value) is list and len(value) == len(shape), "unsupported evidence list population")
        for item, expected in zip(value, shape, strict=True):
            _closed(item, expected, templates)
    else:
        expected = {"str": str, "int": int, "float": float, "null": type(None), "true": bool, "false": bool}[shape]
        require(type(value) is expected, "evidence scalar has an unsupported exact type")
        if shape in ("true", "false"):
            require(value is (shape == "true"), "evidence boolean declaration changed")
        if shape == "float":
            require(math.isfinite(value), "evidence numbers must be finite")


def _private(value, allowances: set[str], pointer: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
            require(
                not _PRIVATE.search(key) or (child in allowances and item is False), "unsupported private data field"
            )
            _private(item, allowances, child)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _private(item, allowances, pointer + "/" + str(i))


def validate_held(held: dict[str, bytes], receiving_paths: list[str]) -> tuple[dict, dict]:
    require(set(held) == {p for p, _, _ in INVENTORY}, "unsupported public evidence file membership")
    profile = json.loads(files("quantfit").joinpath("data/reference-evidence-shape-v0.json").read_bytes())
    decoded = {}
    for path, shape in profile["files"].items():
        raw = held[path]
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)
        _closed(value, shape, profile["templates"])
        allowances = (
            {"/human_labels_authenticated"}
            if path
            in {
                PREFIX + "assessment.json",
                PREFIX + "campaign.json",
                PREFIX + "manifest.json",
                PREFIX + "native-cold-run.json",
            }
            else set()
        )
        if path == PREFIX + "native-cold-run.json":
            allowances.add("/completion_cache_requested")
        _private(value, allowances)
        decoded[path.removeprefix(PREFIX)] = value
    buffers = [held[PREFIX + f"run-{i}/report.json"] for i in range(1, 4)]
    reports = [_report(raw) for raw in buffers]
    for raw in buffers:
        _json(raw)  # The original report privacy/arithmetic rules remain unchanged.
    original, receiving = _validate(
        {**{f"replicate-{i}": raw for i, raw in enumerate(buffers, 1)}, "t0": held[PREFIX + "native-t0.json"]},
        receiving_paths,
    )
    analysis = _analyze_held(buffers, receiving_paths)
    require(_equal(analysis["native_t0"]["result"], receiving), "receiving native components disagree")
    assessment, campaign, cold, manifest = [
        decoded[n] for n in ("assessment.json", "campaign.json", "native-cold-run.json", "manifest.json")
    ]
    require(
        _equal(assessment["t0"], original) and _equal(cold["t0"], original), "original producer T0 declarations differ"
    )
    hashes = [hashlib.sha256(raw).hexdigest() for raw in buffers]
    exits = [run["native_exit_code"] for run in analysis["runs"]]
    require(
        assessment["native_exits"] == campaign["actual_native_exits"] == manifest["native_exits"] == exits,
        "native exit facts differ",
    )
    require(manifest["registered_reference_count"] == 0, "published evidence is not a registered reference")
    normalized_hashes = [
        hashlib.sha256(
            json.dumps(normalized(decoded[f"run-{i}/report.json"]), sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        for i in range(1, 4)
    ]
    full = assessment["full_report_repeatability"]
    require(
        full["allowed_volatile_paths"] == list(ALLOWED_VOLATILE_PATHS)
        and full["normalized_sha256"] == normalized_hashes
        and full["pass"] is analysis["full_report_repeatability"]["pass"]
        and full["differing_paths"] == [],
        "full comparison facts differ",
    )
    for i, report in enumerate(reports):
        source = assessment["source_reports"][i]
        require(
            source["sha256"] == hashes[i] and source["size_bytes"] == len(buffers[i]),
            "assessment source binding differs",
        )
        axes = _axes(report)
        for name, axis in axes.items():
            field = "refusal_robustness" if name == "refusal-robustness" else "over_refusal"
            axis.update(
                two_sided_95pct_wilson=report.drift[field]["flip_rate_wilson95"],
                perfect_judge_mde_floor_80pct_power=report.drift[field]["mde_at_80pct_power"],
                human_confirmed_flips=None,
                null_interpretation=analysis["runs"][i]["axes"][name]["null_interpretation"],
            )
        require(_equal(assessment["axes_by_run"][i], axes), "original axes/counts/statistics differ")
        run = cold["runs"][i]
        require(run["index"] == i + 1 and run["native_exit_code"] == exits[i], "cold run index/outcome differs")
        for binding in (run["report"], run["final_report"]):
            require(
                binding["sha256"] == hashes[i]
                and binding["size_bytes"] == len(buffers[i])
                and binding["regression_detected"] is report.drift["regression_detected"]
                and binding["unmeasurable_axes"] == report.drift["unmeasurable_axes"],
                "cold source report facts differ",
            )
        require(
            campaign["actual_default_tokens_in_all_reports"] == report.decode["max_new_tokens"],
            "recorded token facts differ",
        )
        for name in ("baseline", "quantized"):
            arm = getattr(report, name)
            pin = campaign["pair_pins"][name]
            require(
                pin["ref"] == arm.model
                and pin["sha256"] == arm.artifact_sha256
                and pin["dtype"] == arm.resolved_dtype
                and arm.engine["threads"] == campaign["native_threads_observed"]
                and arm.engine["binary_sha256"] == campaign["binary"]["executable_sha256"],
                "recorded arm identity differs",
            )
    for record, prefix, excluded in (
        (manifest, "", {"README.md", PREFIX + "manifest.json"}),
        (campaign, PREFIX, {"README.md", PREFIX + "manifest.json", PREFIX + "campaign.json"}),
    ):
        entries = record["files"] if record is manifest else record["public_files"]
        expected = {p: (hashlib.sha256(raw).hexdigest(), len(raw)) for p, raw in held.items() if p not in excluded}
        observed = {prefix + e["path"]: (e["sha256"], e["size_bytes"]) for e in entries}
        require(len(entries) == len(observed) and observed == expected, "publication membership/hash bindings differ")
    return original, analysis
