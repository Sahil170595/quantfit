"""Offline, exact-byte bundles of explicitly supported aggregate evidence.

Integrity authenticates neither the measurement nor its declarations. No raw captures,
labels, caches, model files, arbitrary directory trees or external paths are followed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

from quantfit import __version__
from quantfit.modelcard import _check_original_statistics
from quantfit.resolution import MAX_REPORT_BYTES, _axes, analyze_resolution_bytes, parse_report_bytes
from quantfit.safety.calibration_binding import (
    _ENGINE_OUTPUTS,
    _INSPECT_CAUSAL,
    MAX_CALIBRATION_BYTES,
    load_bound_calibration_bytes,
)
from quantfit.safety.report import DriftReport

BUNDLE_SCHEMA = 1
MAX_MANIFEST_BYTES = 64 * 1024
ROLES = {role: f"{role}.json" for role in ("report", "calibration", "gate", "resolution")}
SCOPE = (
    "Offline aggregate format, relationship and exact-byte integrity checks only; no scientific GO, "
    "safety certification, human-label authentication, sensitivity result or independent reproduction."
)
_SHA = re.compile(r"[0-9a-f]{64}")
_PRIVATE = re.compile(
    r"(?:^|_)(?:prompts?|completions?|responses?|text|generations?|human_labels?|raw_labels?)(?:_|$)", re.IGNORECASE
)
_GATE_KEYS = {
    "schema_version",
    "quantfit_version",
    "created_utc",
    "arms",
    "gate",
    "eps",
    "resolution_is_a_floor",
    "floor_mode_caveats",
    "mde_block",
    "over_refusal",
    "resolution",
    "verdict",
    "underlying_run_verdict",
    "verdict_reconciliation",
    "ungated_axis_regressed",
    "gated_axis_flips_below_detection_threshold",
    "passed",
    "exit_code",
    "message",
    "drift",
    "unmeasurable_axes",
    "corpus_composition",
    "decode",
    "caps",
    "notes",
    "headline",
}


class BundleError(RuntimeError):
    """Unsupported/unsafe aggregate or bundle layout (operational CLI exit 2)."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BundleError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _constant(value):
    raise BundleError(f"nonfinite JSON value {value!r}")


def _float(value):
    number = float(value)
    _require(math.isfinite(number), "JSON numeric literals must be finite")
    return number


def _json(data: bytes) -> dict:
    try:
        value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)
        _require(isinstance(value, dict), "aggregate/manifest JSON must be an object")
        _private_fields(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BundleError(f"unreadable aggregate JSON: {exc}") from exc


def _private_fields(value) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _require(not _PRIVATE.search(key), f"raw/private data field {key!r} is not aggregate evidence")
            _private_fields(item)
    elif isinstance(value, list):
        for item in value:
            _private_fields(item)


def _no_links(path: Path) -> None:
    # lstat observes links before resolve could hide them. Windows junctions and
    # other reparse points are refused as well as POSIX symbolic links.
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        _require(
            not stat.S_ISLNK(info.st_mode)
            and not getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0),
            f"symbolic links/junctions are unsupported: {part}",
        )


def _read(path: Path, limit: int) -> bytes:
    _no_links(path)
    _require(stat.S_ISREG(path.lstat().st_mode), f"member must be a regular file: {path}")
    # O_NOFOLLOW refuses final-component link replacement. O_NONBLOCK prevents
    # a substituted POSIX FIFO from hanging before the descriptor type check.
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(descriptor, "rb") as handle:
        _require(stat.S_ISREG(os.fstat(handle.fileno()).st_mode), f"member must be a regular file: {path}")
        data = handle.read(limit + 1)
    _require(len(data) <= limit, f"aggregate exceeds its byte limit: {path}")
    return data


def _scalars(value: dict, allowed: set[str], label: str) -> None:
    _require(isinstance(value, dict) and set(value) <= allowed, f"unsupported {label} metadata")
    _require(
        all(type(item) in (str, int, float, bool, type(None)) for item in value.values()),
        f"{label} metadata must contain aggregate scalars, not renamed raw payloads",
    )


def _engine(value: dict) -> None:
    _require(isinstance(value, dict), "engine metadata must be an object")
    name = value.get("name")
    if name == "transformers":
        allowed = {"name", "version", "device"} | _ENGINE_OUTPUTS
    elif name == "llama.cpp":
        from quantfit.safety.gguf_arm import CPU_OFFLOAD_CONTROLS

        allowed = {"name", "binary_sha256", "source", "threads", "device"} | _ENGINE_OUTPUTS | set(CPU_OFFLOAD_CONTROLS)
        if set(value) & set(CPU_OFFLOAD_CONTROLS):
            _require(
                value.get("device") == "cpu"
                and all(type(value.get(k)) is type(v) and value[k] == v for k, v in CPU_OFFLOAD_CONTROLS.items()),
                "native CPU offload controls must be complete and match the enforced contract",
            )
    elif name == "inspect_ai:hf":
        allowed = _INSPECT_CAUSAL | _ENGINE_OUTPUTS | {"inspect_ai", "provider"}
    elif isinstance(name, str) and name.startswith("inspect_ai:"):
        allowed = {"name", "inspect_ai", "provider", "model_args"}
    else:
        raise BundleError("unsupported aggregate engine metadata")
    _require(set(value) <= allowed, "unsupported aggregate engine fields")
    _scalars({k: v for k, v in value.items() if k not in {"baseline_cache", "model_args"}}, allowed, "engine")
    if "model_args" in value:
        from quantfit.inspect_task import GREEDY_PROVIDER_ARGS

        _scalars(value["model_args"], {"do_sample", "custom_outputs", "random"}, "engine model_args")
        provider = name.partition(":")[2]
        _require(provider in GREEDY_PROVIDER_ARGS, "unsupported Inspect aggregate provider")
        _require(
            all(value["model_args"].get(k) == v for k, v in GREEDY_PROVIDER_ARGS[provider].items()),
            "Inspect aggregate model args do not retain the pinned greedy contract",
        )
    if "baseline_cache" in value:
        _scalars(
            value["baseline_cache"],
            {"served", "fingerprint", "generated_utc", "generated_by_quantfit", "note"},
            "baseline cache provenance marker",
        )


def _report(raw: bytes):
    report = parse_report_bytes(raw)
    _axes(report)
    _check_original_statistics(report)
    # These metadata objects carry protocol/provenance, not arbitrary payloads.
    for value, allowed, label in (
        (
            report.judge,
            {"id", "revision", "input_contract", "card_xstest_accuracy", "card_xstest_accuracy_label"},
            "judge",
        ),
        (report.probe_dataset, {"id", "revision", "split", "n_probes"}, "probe_dataset"),
        (
            {k: v for k, v in report.decode.items() if k != "greedy_model_args"},
            {"max_new_tokens", "do_sample", "greedy", "chat_template", "temperature", "recorded_by"},
            "decode",
        ),
        (report.env, {"python", "torch", "transformers", "cuda", "device"}, "env"),
    ):
        _scalars(value, allowed, f"report {label}")
    if "greedy_model_args" in report.decode:
        _scalars(report.decode["greedy_model_args"], {"do_sample"}, "decode greedy_model_args")
    for arm in (report.baseline, report.quantized):
        _engine(arm.engine)
    drift = report.drift
    _require(
        set(drift)
        == {
            "n_probes",
            "refusal_robustness",
            "over_refusal",
            "by_zone",
            "regression_detected",
            "unmeasurable_axes",
            "verdict",
        },
        "unsupported aggregate drift fields",
    )
    for key, expected, flips in (
        ("refusal_robustness", "expected_unsafe_n", "harmful_compliance_regressions"),
        ("over_refusal", "expected_safe_n", "overrefusal_regressions"),
    ):
        _require(
            set(drift[key])
            == {
                expected,
                "at_risk",
                "baseline_refused",
                "quant_refused",
                flips,
                "flip_rate_wilson95",
                "mde_at_80pct_power",
            },
            "unsupported aggregate axis fields",
        )
    for zone in drift["by_zone"].values():
        _require(set(zone) == {"n", "baseline_refused", "quant_refused"}, "unsupported aggregate zone fields")
    return report


def _validate_gate(value: dict, report: DriftReport | None, calibration) -> dict:
    from quantfit import gate
    from quantfit.safety.calibrated_gate import ASSUMPTIONS, OBSERVED_STATEMENT, PREFLIGHT_STATEMENT
    from quantfit.safety.mde import EPS_DEFINITION

    _require(
        set(value) == _GATE_KEYS and type(value.get("schema_version")) is int and value["schema_version"] == 1,
        "gate role requires the supported aggregate gate schema 1",
    )
    code = value["exit_code"]
    _require(type(code) is int and code in (0, 3, 4, 5), "gate exit code must retain a supported decision state")
    _require(
        value["verdict"] == {0: "PASS", 3: "FAIL", 4: "UNMEASURABLE", 5: "UNRESOLVABLE"}[code],
        "gate verdict and exit code disagree",
    )
    _require(value["passed"] is (True if code == 0 else False if code == 3 else None), "gate passed flag disagrees")
    _require(isinstance(value["eps"], dict) and isinstance(value["resolution"], dict), "gate blocks must be objects")
    _require(type(value["resolution_is_a_floor"]) is bool, "gate floor flag must be boolean")
    _require(
        isinstance(value["arms"], dict) and set(value["arms"]) == {"baseline", "quant", "report"},
        "gate arms must contain only aggregate names/report provenance",
    )
    arms = value["arms"]
    _require(all(isinstance(arms[key], str) and arms[key] for key in ("baseline", "quant")), "invalid gate arm names")
    _require(arms["report"] is None or isinstance(arms["report"], str), "gate report locator must be a string/null")
    observed = value["drift"] is not None
    if observed:
        _require(report is not None, "observed gate requires its aggregate report")
        _require(
            arms["baseline"] == report.baseline.model and arms["quant"] == report.quantized.model,
            "gate arm names do not match bundled report",
        )
        _require(value["drift"] == report.drift, "gate drift does not match bundled report counts")
        _require(
            value["decode"] == {"max_new_tokens": report.decode.get("max_new_tokens"), "do_sample": False}
            and report.decode.get("do_sample", not report.decode.get("greedy", False)) is False,
            "gate decode does not match bundled report",
        )
    else:
        _require(
            code == 5 and value["resolution"].get("stage") == "pre_run", "absent gate drift requires pre-run refusal"
        )
    eps = value["eps"]
    if eps.get("mode") == "bound_calibration_report":
        _require(calibration is not None, "bound gate requires the consumed calibration role")
        _require(
            eps.get("source_sha256") == calibration.source_sha256
            and eps.get("scope_fingerprint") == calibration.fingerprint,
            "gate calibration hashes do not match consumed input",
        )
        _require(
            eps.get("measured") is False and eps.get("assumptions_verified") is False,
            "bound gate cannot authenticate human labels or conditional assumptions",
        )
        _require(
            set(eps)
            == {
                "upper",
                "baseline_upper",
                "quantized_upper",
                "source",
                "source_sha256",
                "scope_fingerprint",
                "binding_status",
                "actual_run_matched",
                "measured",
                "assumptions_verified",
                "assumptions",
                "definition",
                "mode",
                "resolution_is_a_floor",
                "statement",
            }
            and eps["upper"] is None
            and eps["resolution_is_a_floor"] is False
            and eps["baseline_upper"] == calibration.eps_baseline_upper
            and eps["quantized_upper"] == calibration.eps_quant_upper
            and eps["source"] == calibration.eps_source
            and eps["assumptions"] == ASSUMPTIONS
            and eps["definition"] == EPS_DEFINITION
            and eps["statement"] == (OBSERVED_STATEMENT if observed else PREFLIGHT_STATEMENT),
            "gate conditional epsilon does not match validated calibration",
        )
        _require(
            eps["actual_run_matched"] is observed
            and eps["binding_status"]
            == ("actual_run_matched" if observed else "scope_validated_actual_run_unobserved"),
            "gate actual-run status contradicts its drift",
        )
        identity = calibration.identity
        _require(
            arms["baseline"] == identity["baseline"]["model"]
            and arms["quant"] == identity["quantized"]["model"]
            and value["decode"] == {"max_new_tokens": identity["decode"]["max_new_tokens"], "do_sample": False},
            "gate requested arms/decode do not match calibration scope",
        )
    else:
        _require(
            eps == gate._eps(None, None)
            if eps.get("mode") == gate.EPS_MODE_FLOOR
            else eps == gate._eps(eps.get("upper"), eps.get("source")),
            "gate epsilon mode/values are inconsistent",
        )
    # Reuse the gate's calculations and assembler. This checks its existing
    # decision contract; integrity does not upgrade that decision into science.
    settings = value["gate"]
    _require(isinstance(settings, dict), "gate settings must be an object")
    threshold, tier, declared = gate._declared(
        settings.get("threshold") if settings.get("tier") is None else None, settings.get("tier")
    )
    _require(
        settings.get("threshold") == threshold and settings.get("declared_as") == declared, "gate declaration mismatch"
    )
    decode = value["decode"]
    _require(
        isinstance(decode, dict)
        and set(decode) == {"max_new_tokens", "do_sample"}
        and type(decode["max_new_tokens"]) is int
        and decode["max_new_tokens"] > 0
        and decode["do_sample"] is False,
        "gate decode must retain the greedy aggregate contract",
    )
    n = value["drift"]["refusal_robustness"]["at_risk"] if observed else gate.SHIPPED_EXPECTED_UNSAFE_N
    block = gate._block(eps, n)
    stage = gate.STAGE_POST_RUN if observed else gate.STAGE_PRE_RUN
    resolution = gate._resolution(stage, threshold, block, eps, gate.SHIPPED_EXPECTED_UNSAFE_N)
    over_refusal = None
    expected_code = 5
    if observed:
        axis = value["drift"]["over_refusal"]
        over_refusal = {
            **gate._block(eps, axis["at_risk"]),
            "flips": axis["overrefusal_regressions"],
            "best_case_n_at_risk": gate.SHIPPED_EXPECTED_SAFE_N,
            "gated": False,
            "note": gate.NOTES[0],
        }
        flips = value["drift"]["refusal_robustness"]["harmful_compliance_regressions"]
        expected_code = (
            4
            if n == 0
            else 3
            if flips >= resolution["detection_threshold_flips"] and not resolution["no_reachable_rejection"]
            else 5
            if not resolution["not_refused"]
            else 0
        )
    else:
        _require(not resolution["not_refused"], "pre-run refusal must actually refuse the declared threshold")
    _require(code == expected_code, "gate decision precedence is inconsistent")
    if code == 5:
        message = gate._refusal_message(resolution, eps, declared)
    elif code == 4:
        message = gate._unmeasurable_message(
            value["drift"]["refusal_robustness"]["expected_unsafe_n"], threshold, declared
        )
    else:
        message = gate._verdict_message(value["verdict"], flips, resolution, eps, declared)
    _require(value["message"] == message, "gate message does not match its existing decision contract")
    expected = gate._decision(
        baseline=arms["baseline"],
        quant=arms["quant"],
        threshold=threshold,
        tier=tier,
        declared_as=declared,
        eps=eps,
        block=block,
        resolution=resolution,
        verdict=value["verdict"],
        exit_code=code,
        message=message,
        passed=value["passed"],
        drift=value["drift"],
        over_refusal=over_refusal,
        max_new_tokens=decode["max_new_tokens"],
        report_path=arms["report"],
    )
    for key in ("created_utc", "quantfit_version"):
        _require(isinstance(value[key], str) and bool(value[key]), f"gate {key} must be a string")
        expected[key] = value[key]
    _require(value == expected, "gate aggregate fields do not match its existing decision contract")
    return {
        "exit_code": code,
        "verdict": value["verdict"],
        "resolution_is_a_floor": value["resolution_is_a_floor"],
        "actual_run_matched": eps.get("actual_run_matched"),
        "assumptions_verified": eps.get("assumptions_verified"),
        "human_labels_verified": eps.get("measured"),
        "unmeasurable_axes": value["unmeasurable_axes"],
    }


def _validate(data: dict[str, bytes]) -> dict:
    _require(set(data) <= set(ROLES) and ("report" in data or "gate" in data), "bundle requires report or pre-run gate")
    payloads = {role: _json(raw) for role, raw in data.items()}
    report = _report(data["report"]) if "report" in data else None
    declarations = (
        {}
        if report is None
        else {
            "report": {
                "verdict": report.drift["verdict"],
                "regression_detected": report.drift["regression_detected"],
                "unmeasurable_axes": report.drift["unmeasurable_axes"],
            }
        }
    )
    calibration = None
    if "calibration" in data:
        calibration = load_bound_calibration_bytes(data["calibration"], report=report)
        for arm in ("baseline", "quantized"):
            _engine(calibration.identity[arm]["engine"])
        declarations["calibration"] = {
            "binding_fingerprint": calibration.fingerprint,
            "human_labels_verified": False,
            "assumptions_verified": False,
        }
    if "resolution" in data:
        _require(
            calibration is not None and report is not None, "resolution role requires report and bound calibration"
        )
        _, expected = analyze_resolution_bytes(data["report"], data["calibration"])
        supplied = dict(payloads["resolution"])
        _require(set(supplied) == set(expected), "resolution has unsupported fields")
        for key in ("created_utc", "quantfit_version"):
            _require(isinstance(supplied[key], str) and bool(supplied[key]), f"resolution {key} must be a string")
            supplied[key] = expected[key]
        _require(
            supplied == expected, "resolution does not match consumed report/calibration bytes and conditional analysis"
        )
        declarations["resolution"] = {
            "human_confirmation_verified": False,
            "assumptions_verified": False,
            "binding_status": expected["binding_status"],
        }
    if "gate" in data:
        declarations["gate"] = _validate_gate(payloads["gate"], report, calibration)
    return declarations


def _result(path: Path, manifest: dict, *, matched: bool, declarations: dict | None = None, mismatches=None) -> dict:
    return {
        "bundle_path": str(path),
        "bundle_schema": BUNDLE_SCHEMA,
        "manifest": manifest,
        "integrity_verified": matched,
        "scientific_claims_verified": False,
        "declared_results": declarations or {},
        "mismatches": mismatches or [],
        "scope": SCOPE,
    }


def create_bundle(
    report_path: str | None,
    out_path: str,
    *,
    calibration_path: str | None = None,
    gate_path: str | None = None,
    resolution_path: str | None = None,
) -> dict:
    """Validate and copy exactly the consumed buffers to a new portable directory."""
    target = Path(out_path).absolute()
    try:
        _no_links(target)
        _require(not target.exists(), "bundle output must be a new directory, never an input/output alias")
        _require(target.parent.is_dir(), "bundle output parent must exist")
        sources = {
            "report": report_path,
            "calibration": calibration_path,
            "gate": gate_path,
            "resolution": resolution_path,
        }
        data = {
            role: _read(Path(path).absolute(), MAX_CALIBRATION_BYTES if role == "calibration" else MAX_REPORT_BYTES)
            for role, path in sources.items()
            if path is not None
        }
        declarations = _validate(data)
        manifest = {
            "bundle_schema": BUNDLE_SCHEMA,
            "quantfit_version": __version__,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "scientific_claims_verified": False,
            "files": [
                {"role": role, "path": ROLES[role], "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
                for role, raw in data.items()
            ],
            "scope": SCOPE,
        }
        target.mkdir()  # exclusive reservation; never replace an existing directory
        written = []
        try:
            for role, raw in data.items():
                path = target / ROLES[role]
                with path.open("xb") as handle:
                    written.append(path)
                    handle.write(raw)
            path = target / "manifest.json"
            with path.open("xb") as handle:
                written.append(path)
                handle.write((json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        except OSError:
            for path in written:
                path.unlink(missing_ok=True)
            target.rmdir()
            raise
        return _result(target, manifest, matched=True, declarations=declarations)
    except (OSError, RuntimeError, RecursionError, TypeError, ValueError) as exc:
        if isinstance(exc, BundleError):
            raise
        raise BundleError(str(exc)) from exc


def verify_bundle(bundle_path: str) -> dict:
    """Check local members after relocation; never follow any artifact's original paths."""
    root = Path(bundle_path).absolute()
    try:
        _no_links(root)
        _require(root.is_dir(), "bundle must be a directory")
        manifest = _json(_read(root / "manifest.json", MAX_MANIFEST_BYTES))
        _require(
            set(manifest)
            == {"bundle_schema", "quantfit_version", "created_utc", "scientific_claims_verified", "files", "scope"},
            "unsupported bundle manifest fields",
        )
        _require(
            type(manifest["bundle_schema"]) is int and manifest["bundle_schema"] == BUNDLE_SCHEMA,
            "unsupported bundle schema",
        )
        _require(
            manifest["scientific_claims_verified"] is False and manifest["scope"] == SCOPE,
            "integrity cannot claim scientific proof",
        )
        for key in ("quantfit_version", "created_utc"):
            _require(isinstance(manifest[key], str) and bool(manifest[key]), f"manifest {key} must be a string")
        files = manifest["files"]
        _require(isinstance(files, list) and 1 <= len(files) <= len(ROLES), "manifest needs 1..4 supported roles")
        roles, names, data, mismatches = set(), {"manifest.json"}, {}, []
        for entry in files:
            _require(
                isinstance(entry, dict) and set(entry) == {"role", "path", "sha256", "size_bytes"},
                "unsupported file entry",
            )
            role = entry["role"]
            _require(isinstance(role, str) and role in ROLES and role not in roles, "unsupported/duplicate bundle role")
            _require(entry["path"] == ROLES[role], "member paths must be canonical relative role filenames")
            _require(
                isinstance(entry["sha256"], str) and bool(_SHA.fullmatch(entry["sha256"])),
                "member SHA256 must be lowercase hex",
            )
            _require(
                type(entry["size_bytes"]) is int and 0 < entry["size_bytes"] <= MAX_REPORT_BYTES,
                "unsupported member size",
            )
            roles.add(role)
            names.add(entry["path"])
        _require({p.name for p in root.iterdir()} == names, "unlisted/missing files are refused")
        for entry in files:
            role = entry["role"]
            raw = _read(root / entry["path"], MAX_CALIBRATION_BYTES if role == "calibration" else MAX_REPORT_BYTES)
            actual = hashlib.sha256(raw).hexdigest()
            if actual != entry["sha256"] or len(raw) != entry["size_bytes"]:
                mismatches.append(
                    {
                        "role": role,
                        "expected_sha256": entry["sha256"],
                        "actual_sha256": actual,
                        "expected_bytes": entry["size_bytes"],
                        "actual_bytes": len(raw),
                    }
                )
            data[role] = raw
        if mismatches:
            return _result(root, manifest, matched=False, mismatches=mismatches)
        return _result(root, manifest, matched=True, declarations=_validate(data))
    except (OSError, RuntimeError, RecursionError, TypeError, ValueError) as exc:
        if isinstance(exc, BundleError):
            raise
        raise BundleError(str(exc)) from exc
