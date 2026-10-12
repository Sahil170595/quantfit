"""Offline full-payload agreement, native T0 and original per-run outcomes, separately."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import tempfile
from pathlib import Path

from quantfit import __version__
from quantfit.bundle import _json, _no_links, _read, _report
from quantfit.modelcard import _check_original_statistics
from quantfit.replay_bundle import ROLES, _verified_bundle
from quantfit.report_comparison import ALLOWED_VOLATILE_PATHS, differences, normalized
from quantfit.reproduce import ReproduceError, _t0_from_views, _view_from_report
from quantfit.resolution import MAX_REPORT_BYTES, _axes

SCOPE = (
    "Offline saved-aggregate comparison only. Counts are not pooled; agreement authenticates neither "
    "execution, physical hosts nor human labels. No sensitivity, scientific GO or reproduction qualification."
)


class RepeatabilityError(RuntimeError):
    """Malformed evidence, unsupported input or output failure; CLI exit 2."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RepeatabilityError(message)


def _sources(report_paths: list[str] | None, bundle_path: str | None) -> list[Path]:
    _require((report_paths is None) != (bundle_path is None), "supply exactly one of reports or bundle")
    if bundle_path is not None:
        root = Path(bundle_path).absolute()
        return [root / name for name in (*ROLES.values(), "manifest.json")]
    _require(isinstance(report_paths, (list, tuple)) and len(report_paths) == 3, "exactly three reports required")
    return [Path(p).absolute() for p in report_paths]


def validate_outputs(report_paths: list[str] | None, bundle_path: str | None, outputs: list[str | None]) -> None:
    """Validate all aliases/links before any output; never reopen source bytes."""
    sources = _sources(report_paths, bundle_path)
    targets = [Path(p).absolute() for p in outputs if p is not None]
    for path in [*sources, *targets]:
        _no_links(path)
    closed = Path(bundle_path).resolve() if bundle_path is not None else None
    for i, target in enumerate(targets):
        _require(target.parent.is_dir(), "output parent must already exist")
        if target.exists():
            _require(stat.S_ISREG(target.lstat().st_mode), "output must be a regular file")
        resolved = target.resolve()
        _require(closed is None or not resolved.is_relative_to(closed), "outputs cannot be inside a closed bundle")
        for source in [*sources, *targets[:i]]:
            _require(resolved != source.resolve(), "output aliases an input or another output")
            _require(
                not (target.exists() and source.exists() and target.samefile(source)),
                "hard-linked output aliases input/output",
            )


def publish_outputs(report_paths: list[str] | None, bundle_path: str | None, outputs: list[tuple[str, bytes]]) -> None:
    """Stage complete buffers first; each replacement is atomic, not a multi-file transaction."""
    temporary = []
    try:
        validate_outputs(report_paths, bundle_path, [path for path, _ in outputs])
        for name, raw in outputs:
            target = Path(name)
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".repeatability-", delete=False) as stream:
                path = Path(stream.name)
                temporary.append((path, target))
                _require(stream.write(raw) == len(raw), "incomplete repeatability output write")
                stream.flush()
        validate_outputs(report_paths, bundle_path, [path for path, _ in outputs])
        for path, target in temporary:
            os.replace(path, target)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        if isinstance(exc, RepeatabilityError):
            raise
        raise RepeatabilityError(f"cannot publish repeatability output: {exc}") from exc
    finally:
        for path, _ in temporary:
            path.unlink(missing_ok=True)


def _analyze_held(buffers: list[bytes], paths: list[str], *, source_identity_refusal: str | None = None) -> dict:
    """Current analysis over exactly consumed bytes/receiving labels; no filesystem IO."""
    _require(len(buffers) == len(paths) == 3, "exactly three held reports required")
    values, views, runs = [], [], []
    for i, (path, raw) in enumerate(zip(paths, buffers, strict=True)):
        value, report = _json(raw), _report(raw)
        _require(
            all(
                type(number) in (int, float) and math.isfinite(number) and number >= 0
                for number in (
                    value["judge_runtime_s"],
                    value["baseline"]["runtime_s"],
                    value["quantized"]["runtime_s"],
                )
            ),
            "recorded runtimes must be finite nonnegative numbers before volatile-field removal",
        )
        canonical = _check_original_statistics(report)
        _require(
            type(report.drift["regression_detected"]) is bool
            and report.drift["regression_detected"] is canonical["regression_detected"]
            and report.drift["unmeasurable_axes"] == canonical["unmeasurable_axes"],
            "original report flags contradict validated counts",
        )
        axes = _axes(report)
        for name, field in (("refusal-robustness", "refusal_robustness"), ("over-refusal", "over_refusal")):
            axes[name].update(
                original_counts=report.drift[field],
                human_confirmed_flips=None,
                null_interpretation="nothing was measured on this axis"
                if not axes[name]["measurable"]
                else "the detector did not fire"
                if axes[name]["flagged_flips"] == 0
                else None,
            )
        native_exit = 3 if canonical["regression_detected"] else 4 if canonical["unmeasurable_axes"] else 0
        runs.append(
            {
                "path": str(path),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
                "verdict": report.drift["verdict"],
                "native_exit_code": native_exit,
                "unmeasurable_axes": canonical["unmeasurable_axes"],
                "axes": axes,
            }
        )
        values.append(normalized(value))
        views.append(_view_from_report(report, raw, str(path), f"replicate[{i}]"))
    diffs = [
        {"replicate": str(paths[i]), "against": str(paths[0]), "pointer": pointer}
        for i in range(1, 3)
        for pointer in differences(values[0], values[i])
    ]
    try:
        if source_identity_refusal is not None:
            raise ReproduceError(source_identity_refusal)
        t0 = _t0_from_views(views)
        native = {"status": "computed", "exit_code": 0 if t0["protocol_pass"] else 3, "result": t0, "reason": None}
    except ReproduceError as exc:
        native = {"status": "refused", "exit_code": 2, "result": None, "reason": str(exc)}
    if native["status"] == "refused":
        code, outcome = 2, "t0_refused"
    elif diffs or not native["result"]["protocol_pass"]:
        code, outcome = 3, "disagreement"
    elif any(run["native_exit_code"] == 3 for run in runs):
        code, outcome = 3, "native_flags"
    elif any(run["native_exit_code"] == 4 for run in runs):
        code, outcome = 4, "unmeasured"
    else:
        code, outcome = 0, "repeatable"
    result = {
        "repeatability_schema_version": 1,
        "quantfit_version": __version__,
        "evidence_valid": True,
        "exit_code": code,
        "outcome": outcome,
        "full_report_repeatability": {
            "pass": not diffs,
            "ignored_paths": list(ALLOWED_VOLATILE_PATHS),
            "differences": diffs,
        },
        "native_t0": native,
        "runs": runs,
        "scientific_claims_verified": False,
        "independent_execution_verified": False,
        "scope": SCOPE,
    }
    return result


def analyze_replicates(
    report_paths: list[str] | None = None, *, bundle_path: str | None = None, out_path: str | None = None
) -> dict:
    """Analyze exactly three held reports; native refusal retains valid comparison facts."""
    try:
        paths = _sources(report_paths, bundle_path)
        validate_outputs(report_paths, bundle_path, [out_path])
        input_aliases = False
        if bundle_path is not None:
            verified, held = _verified_bundle(bundle_path)
            _require(verified["integrity_verified"], "replay bundle bytes differ from their manifest")
            paths = paths[:3]
            buffers = [held[f"replicate-{i}"] for i in range(1, 4)]
        else:
            # These are owned receiving paths, never producer locators. Byte
            # hashes alone cannot detect aliases if a file changes between reads.
            paths = [p.resolve() for p in paths]
            input_aliases = any(
                path == earlier or path.samefile(earlier) for i, path in enumerate(paths) for earlier in paths[:i]
            )
            buffers = [_read(path, MAX_REPORT_BYTES) for path in paths]
        result = _analyze_held(
            buffers,
            list(map(str, paths)),
            source_identity_refusal="T0 requires three distinct input files; canonical paths or file identities alias"
            if input_aliases
            else None,
        )
        if out_path is not None:
            publish_outputs(report_paths, bundle_path, [(out_path, encode_result(result))])
        return result
    except (OSError, RuntimeError, RecursionError, TypeError, ValueError, KeyError) as exc:
        if isinstance(exc, RepeatabilityError):
            raise
        raise RepeatabilityError(str(exc)) from exc


def encode_result(result: dict) -> bytes:
    return (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
