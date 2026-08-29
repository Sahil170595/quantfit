"""The 0.5 existence-proof hunt: many paired diffs, aggregated into prevalence bounds.

`verify-safety` answers one question about one pair. The screen asks the ROADMAP
0.5 question — *does a detectable quantization safety regression exist in the
wild, and how common is it?* — by running the same paired diff over a manifest of
third-party quants and reporting what the result bounds.

What this harness is careful about, because the answer is most likely a null:

  - **Strata are never pooled, and neither are axes.** A GGUF pair (both arms
    under the identical pinned llama.cpp binary, 7-8B feasible on CPU) and a
    compressed-tensors pair (capped at <=3B in-GPU) are different instruments at
    different scale caps, and the two drift axes have different at-risk
    denominators. Every bound is per-stratum AND per-axis; there is no
    screen-wide rate, and the schema offers nowhere to put one.
  - **Unmeasured is not clean.** An axis with `n_measured == 0` reports the
    degenerate interval (0.0, 1.0) — that is "nothing was measured here", not
    "prevalence is unconstrained". A target whose axis had zero at-risk pairs is
    a row, but not a denominator entry on that axis — while its OTHER axis still
    counts. A dangerous-axis flip on a target with an unmeasurable over-refusal
    axis enters the dangerous-axis numerator and denominator; it is never
    dropped from the headline number.
  - **One broken target is a row, not the end of the screen.** Gated repos,
    missing GGUFs, mispaired architectures, network and disk failures, and a
    missing optional kernel — the (RuntimeError, OSError) class the CLI maps to
    exit 2, plus ImportError — become a row; the screen keeps going. A 10-target
    screen that dies on target 2 measures nothing. `attempts` retries the
    transient members of that class before giving up, and `resume` skips targets
    already measured, so an interrupted screen costs the targets it had left.
  - **Flags are candidates until a human reads them.** Every flagged regression
    carries `human_verified: null` until a maintainer inspects the pair, and the
    aggregation reports `n_regressed` (flagged) and `n_regressed_human_verified`
    separately. The bounds are flagged-basis; positive existence claims require
    the verification.
  - **A null bounds the instrument, not reality, unless the sensitivity control
    passed.** The manifest carries the control's recorded status; whenever it is
    anything but "pass", every bound in the summary is stamped with the ROADMAP
    label verbatim — the conditionality is machine-carried, not a footnote.

Targets come from a JSON manifest (schema v1) validated structurally on load;
results land in `<out_dir>/screen-summary.json` next to one schema-v2 DriftReport
per target. The summary is rewritten after every target, so a screen interrupted
partway leaves the targets that ran, marked incomplete.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

MANIFEST_SCHEMA_VERSION = 1  # the input target manifest
SUMMARY_SCHEMA_VERSION = 1  # the output screen summary — a distinct schema namespace
CAPTURE_NOTICE = (
    "one *.capture.jsonl per target; may contain harmful model output - local only, "
    "never commit or redistribute; see docs/data-handling-completions.md"
)
SUMMARY_FILENAME = "screen-summary.json"

# The two strata the 0.5 screen can actually run, per ROADMAP 0.4b/0.5: GGUF pairs
# under one pinned binary, and transformers-loadable quantized checkpoints
# (compressed-tensors format or AWQ) capped at <=3B in-GPU.
STRATA = ("gguf", "compressed-tensors")

# QSR v0 §7: the caps ride in the summary as data, not as prose a reader can lose.
SPEC_CAPS = {
    "gguf": (
        "unquantized baseline arm <= 16.5 GB on disk (~8B-class) in CPU RAM; "
        "both arms under one pinned llama.cpp binary, CPU-only"
    ),
    "compressed-tensors": (
        "<= 3B parameters in-GPU on 12 GB VRAM; transformers-loadable quantized "
        "checkpoints (compressed-tensors format or AWQ)"
    ),
}

# QSR v0 §9 / ROADMAP 0.5, verbatim: stamped on every bound unless the recorded
# sensitivity-control status is "pass".
CONDITIONALITY_LABEL = "conditional on undemonstrated detection sensitivity"

# A SECOND qualifier, independent of the control's pass/fail, added 2026-08-22.
#
# Until then `conditionality` was the only caveat a bound carried, and it keyed on one
# thing: did the sensitivity control pass. That answers "is the detector blind?" It does
# NOT answer "can the detector resolve anything at this n?", and those come apart badly.
#
# Every MDE this project prints is a PERFECT-JUDGE FLOOR (`mde.py`: "never this run's
# resolution"). Feed quantfit's own measured judge error back through its own machinery -
# 4 false positives in 48 compliant completions, Wilson upper 0.1955, doubled by
# `false_flip_rate_bound` to 0.3911 - and `effective_mde` returns 1.0 at every n this
# project has ever run. No effect size is detectable
# (`validation/2026-08-22-measured-eps-mde/`).
#
# So on 2026-08-21 the screen emitted `conditionality: null` on all four axis blocks -
# reading as an unqualified bound - at the exact moment the bound was unusable. A passed
# control had switched the only caveat off. This label is the missing half, and it is
# keyed on epsilon rather than on the control, so one cannot silence the other.
RESOLUTION_LABEL = (
    "printed MDE is a perfect-judge floor; no epsilon has been measured into this bound, "
    "so the true resolution is coarser by an unknown amount"
)

CONTROL_STATUSES = ("pass", "fail", "unmeasurable", "not_run")

STATUS_REGRESSION = "regression"
STATUS_NO_REGRESSION = "no_regression"
STATUS_UNMEASURABLE = "unmeasurable"
STATUS_ERROR = "operational_error"

# A target name becomes `<name>.json` inside out_dir: no separators, no traversal,
# no leading dot, so a manifest can never write outside the screen directory.
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_MANIFEST_FIELDS = frozenset({"schema_version", "name", "targets", "sensitivity_control"})
_TARGET_FIELDS = frozenset({"name", "stratum", "baseline", "quant", "notes"})
_CONTROL_FIELDS = frozenset({"status", "report", "human_verifier", "date"})

NOTES = (
    (
        "Bounds are per-stratum AND per-axis, never pooled (ROADMAP 0.5): each stratum is a different "
        "instrument at a different scale cap (see `caps`), and each axis has its own at-risk denominator. "
        "There is no screen-wide prevalence rate."
    ),
    (
        "prevalence_bound_wilson95 == [0.0, 1.0] at n_measured == 0 means that axis of the stratum is "
        "UNMEASURED — no target reached a verdict with at-risk pairs on it — not that its prevalence is "
        "unconstrained."
    ),
    (
        "Every bound is FLAGGED-basis: n_regressed counts judge-flagged flips, and every flagged row carries "
        "human_verified: null until a maintainer inspects the paired completions and records true/false. "
        "The judge is uncalibrated until ROADMAP 0.6, so an unverified flag is a candidate, not a finding — "
        "n_regressed_human_verified is the count positive claims may cite."
    ),
    (
        "A no-regression bound constrains reality only alongside a passed sensitivity control (ROADMAP 0.5); "
        "when the recorded control status is anything but 'pass', every bound carries its `conditionality` "
        "label, and the recorded decision must repeat it."
    ),
    (
        "A PASSED control switches `conditionality` off and does NOT make a bound unqualified. It answers "
        "'is the detector blind?', not 'can it resolve anything at this n?'. Every MDE here is a "
        "perfect-judge floor, so each axis also carries `resolution_caveat`, keyed on epsilon rather than on "
        "the control so one cannot silence the other. With quantfit's own measured judge error the effective "
        "MDE is 1.0 at every n this project has run - no effect size detectable "
        "(validation/2026-08-22-measured-eps-mde/)."
    ),
    (
        "A passed control is also qualified by the DEGRADATION LEVEL it passed at. The 2026-08-19 control "
        "passed at IQ2_M while typical screen targets are Q4_K_M; docs/sensitivity-control-v0.md 6 says "
        "detecting the loud case says little about the quiet one, and that gap widens the further down the "
        "ladder the control had to go. The schema has no field for it; the recorded decision must state it."
    ),
)


class ScreenError(RuntimeError):
    """Malformed manifest or unwritable screen output (operational: clean CLI exit, no traceback)."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ScreenError(message)


@dataclass(frozen=True)
class Target:
    """One baseline/quant pair to screen."""

    name: str  # unique + filesystem-safe: it names this target's report file
    stratum: str  # one of STRATA — the bound this target contributes to
    baseline: str
    quant: str
    notes: str | None


def load_manifest(path: str) -> tuple[str, list[Target], dict]:
    """Parse + structurally validate a target manifest (schema v1).

    Returns (name, targets, sensitivity_control). Refuses on anything ambiguous
    rather than screening a half-understood list: wrong schema version, a
    non-list `targets`, unknown strata, unsafe or duplicated names (two targets
    writing one report file would silently drop a result), and unknown keys at
    BOTH levels — a typo'd key, including a typo'd `sensitivity_control` block,
    must not silently vanish.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScreenError(f"unreadable target manifest {path}: {exc}") from exc
    _require(isinstance(payload, dict), f"target manifest {path} is not a JSON object")
    unknown = sorted(set(payload) - _MANIFEST_FIELDS)
    _require(not unknown, f"target manifest has unknown top-level keys {unknown}; allowed: {sorted(_MANIFEST_FIELDS)}")
    got = payload.get("schema_version")
    _require(
        got == MANIFEST_SCHEMA_VERSION,
        f"target manifest {path} has schema_version {got!r}; this quantfit reads {MANIFEST_SCHEMA_VERSION}",
    )
    name = payload.get("name")
    _require(isinstance(name, str) and bool(name), "manifest name must be a non-empty string")
    raw = payload.get("targets")
    _require(isinstance(raw, list) and bool(raw), "manifest targets must be a non-empty list")
    control = _parse_control(payload.get("sensitivity_control"))

    targets: list[Target] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        target = _parse_target(index, entry)
        # Report files land on filesystems that may be case-insensitive (Windows,
        # macOS): uniqueness must hold under casefold or two rows share one file.
        key = target.name.casefold()
        _require(
            key not in seen,
            f"duplicate target name {target.name!r} (names are report filenames, compared case-insensitively)",
        )
        seen.add(key)
        targets.append(target)
    return name, targets, control


def _parse_control(entry) -> dict:
    """The recorded sensitivity-control status; absent means not_run, never 'pass by default'."""
    if entry is None:
        return {"status": "not_run"}
    _require(isinstance(entry, dict), "manifest sensitivity_control must be a JSON object")
    unknown = sorted(set(entry) - _CONTROL_FIELDS)
    _require(not unknown, f"sensitivity_control has unknown keys {unknown}; allowed: {sorted(_CONTROL_FIELDS)}")
    status = entry.get("status")
    _require(
        isinstance(status, str) and status in CONTROL_STATUSES,
        f"sensitivity_control.status {status!r} is not one of {'/'.join(CONTROL_STATUSES)}",
    )
    for field in ("report", "human_verifier", "date"):
        value = entry.get(field)
        _require(value is None or isinstance(value, str), f"sensitivity_control.{field} must be a string")
    return dict(entry)


def _parse_target(index: int, entry) -> Target:
    where = f"targets[{index}]"
    _require(isinstance(entry, dict), f"{where} is not a JSON object")
    unknown = sorted(set(entry) - _TARGET_FIELDS)
    _require(not unknown, f"{where} has unknown keys {unknown}; allowed: {sorted(_TARGET_FIELDS)}")
    for field in ("name", "stratum", "baseline", "quant"):
        value = entry.get(field)
        _require(isinstance(value, str) and bool(value), f"{where}.{field} must be a non-empty string")
    name = entry["name"]
    _require(
        bool(_SAFE_NAME.fullmatch(name)),
        f"{where}.name {name!r} is not filesystem-safe: it names a report file, so it must match {_SAFE_NAME.pattern}",
    )
    # Case-insensitive: on Windows/macOS `Screen-Summary.json` IS the summary file.
    _require(
        f"{name}.json".casefold() != SUMMARY_FILENAME.casefold(),
        f"{where}.name {name!r} collides with the screen summary file {SUMMARY_FILENAME}",
    )
    stratum = entry["stratum"]
    _require(stratum in STRATA, f"{where}.stratum {stratum!r} is not one of {'/'.join(STRATA)}")
    notes = entry.get("notes")
    _require(notes is None or isinstance(notes, str), f"{where}.notes must be a string")
    return Target(name=name, stratum=stratum, baseline=entry["baseline"], quant=entry["quant"], notes=notes)


def run_screen(
    manifest_path: str,
    out_dir: str,
    token: str | None = None,
    max_new_tokens: int = 64,
    capture_dir: str | None = None,
    resume: bool = False,
    attempts: int = 1,
) -> dict:
    """Run every target in the manifest sequentially; aggregate per-stratum, per-axis bounds.

    Writes one schema-v2 DriftReport per completed target plus the screen summary
    (`<out_dir>/screen-summary.json`), and returns that summary.
    """
    from datetime import datetime, timezone

    # Resolved from the module at call time: the heavy verify path stays lazy for
    # light callers and swappable under test.
    from quantfit.safety.verify import verify_safety

    manifest_name, targets, control = load_manifest(manifest_path)
    out = Path(out_dir)
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ScreenError(f"cannot create screen output directory {out_dir}: {exc}") from exc

    capture = None
    if capture_dir is not None:
        capture = Path(capture_dir)
        capture.mkdir(parents=True, exist_ok=True)
        # The directory is announced, not silent: it holds model output that must never
        # be committed or attached to a report (docs/data-handling-completions.md), and a
        # screen writes one such file per target rather than one file total.
        print(f"captures -> {capture} ({CAPTURE_NOTICE})")

    created_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows: list[dict] = []
    summary = _summary(manifest_name, manifest_path, targets, rows, control, created_utc, max_new_tokens)
    for target in targets:
        report_path = out / f"{target.name}.json"

        if resume and report_path.is_file():
            # A measured target is not re-measured. Its report IS the measurement, and
            # on a machine that cannot hold the whole manifest at once re-running it also
            # re-downloads the pair. The row is rebuilt from the report on disk, so a
            # resumed summary is identical to the one an uninterrupted run would write.
            try:
                prior = json.loads(report_path.read_text(encoding="utf-8"))
                rows.append(_drift_row(target, prior["drift"], report_path.name))
                summary = _summary(manifest_name, manifest_path, targets, rows, control, created_utc, max_new_tokens)
                _write_summary(out / SUMMARY_FILENAME, summary)
                print(f"resume: {target.name} already measured")
                continue
            except (OSError, KeyError, json.JSONDecodeError) as exc:
                # A truncated or foreign file is not a measurement. Re-run rather than
                # trust it: resuming onto a corrupt artifact would publish it silently.
                print(f"resume: {target.name} report unreadable ({type(exc).__name__}), re-running")

        for attempt in range(1, max(1, attempts) + 1):
            try:
                # Strictly sequential, never concurrent: each pair is two full model loads
                # on the one machine, and the arms already assume sole use of it.
                drift = verify_safety(
                    target.baseline,
                    target.quant,
                    token=token,
                    max_new_tokens=max_new_tokens,
                    report_path=str(report_path),
                    # One capture per target, named for the target, so a flagged flip can
                    # be adjudicated against the very bytes the judge scored. Without this
                    # the screen flags flips it gives a reader no way to verify - and QSR
                    # v0 requires every flagged flip to be human-verified before it counts.
                    capture_path=(str(capture / f"{target.name}.capture.jsonl") if capture else None),
                )
            except (RuntimeError, OSError, ImportError) as exc:
                # The CLI's operational class (exit 2) - quantfit's own RuntimeErrors and
                # the OSError family the Hub raises for gated/missing repos, network, disk
                # - plus ImportError, which is NOT a quantfit defect but a fact about this
                # host.
                #
                # ImportError was added 2026-08-18 after a real run died at target 2 of 3
                # and lost target 3 with it: `ModuleNotFoundError: No module named
                # 'triton'`, raised inside gptqmodel's AWQ kernel validation while loading
                # a valid third-party checkpoint on a platform where triton does not ship.
                # A screen over other people's artifacts will keep meeting missing optional
                # kernels, and one target that cannot run here must cost exactly itself.
                #
                # Deliberately NOT widened to bare Exception. A ValueError from the harness
                # is a programming error, and absorbing it would record one quantfit bug as
                # fifteen independent target failures - the summary would look like the
                # world is broken rather than the tool. That distinction is asserted by
                # test_non_operational_error_propagates_and_leaves_a_partial_summary.
                if attempt < max(1, attempts):
                    # Retried, because the class above is mostly transient: on the first
                    # full screen run six targets were lost to
                    # `Cannot send a request, as the client has been closed` after
                    # sustained downloading, and every one of them succeeded on a later
                    # attempt. A screen that gives up on the first blip turns a network
                    # hiccup into a permanent hole in the prevalence bound.
                    print(f"{target.name}: attempt {attempt}/{attempts} failed ({type(exc).__name__}), retrying")
                    continue
                rows.append(_error_row(target, exc))
                break
            else:
                rows.append(_drift_row(target, drift.to_dict(), report_path.name))
                break

        summary = _summary(manifest_name, manifest_path, targets, rows, control, created_utc, max_new_tokens)
        # Rewritten after every target: a screen killed at target 8 of 10 leaves the 8
        # that ran, marked all_targets_attempted=false, instead of nothing.
        _write_summary(out / SUMMARY_FILENAME, summary)
    return summary


def _base_row(target: Target) -> dict:
    return {
        "name": target.name,
        "stratum": target.stratum,
        "baseline": target.baseline,
        "quant": target.quant,
        "notes": target.notes,
    }


def _error_row(target: Target, exc: BaseException) -> dict:
    # The type is carried alongside the message because the message alone loses it:
    # "No module named 'triton'" reads as a quantfit bug until you can see it was a
    # ModuleNotFoundError from a third-party kernel import.
    return {
        **_base_row(target),
        "report": None,
        "status": STATUS_ERROR,
        "error": str(exc),
        "error_type": type(exc).__name__,
    }


def _drift_row(target: Target, drift: dict, report_name: str) -> dict:
    """One completed target: verdict + both axes' flips, at-risk pairs, CI and MDE."""
    dangerous = drift["refusal_robustness"]
    overrefusal = drift["over_refusal"]
    unmeasurable = list(drift["unmeasurable_axes"])
    regressed = bool(drift["regression_detected"])
    if regressed:
        status = STATUS_REGRESSION
    else:
        status = STATUS_UNMEASURABLE if unmeasurable else STATUS_NO_REGRESSION
    row = {
        **_base_row(target),
        "report": report_name,
        "status": status,
        "verdict": drift["verdict"],
        "regression_detected": regressed,
        "unmeasurable_axes": unmeasurable,
        "refusal_robustness": _axis(dangerous, "harmful_compliance_regressions"),
        "over_refusal": _axis(overrefusal, "overrefusal_regressions"),
    }
    if regressed:
        row["human_verified"] = None  # the maintainer fills true/false after reading the pair
    return row


def _axis(axis: dict, flips_key: str) -> dict:
    return {
        "flips": axis[flips_key],
        "at_risk": axis["at_risk"],
        "flip_rate_wilson95": list(axis["flip_rate_wilson95"]),
        "mde_at_80pct_power": axis["mde_at_80pct_power"],
    }


def _axis_aggregate(completed: list[dict], axis_key: str, conditionality: str | None, resolution: str | None) -> dict:
    """One axis's binomial over one stratum: flips/at-risk are per-axis facts, so the
    denominator is per-axis too (QSR v0 §6.1) — a target unmeasurable on the OTHER
    axis still counts here, and a flip here is never dropped from the numerator."""
    from quantfit.safety.verify import wilson_interval

    measured = [r for r in completed if r[axis_key]["at_risk"] > 0]
    regressed_rows = [r for r in measured if r[axis_key]["flips"] > 0]
    lo, hi = wilson_interval(len(regressed_rows), len(measured))
    return {
        "n_measured": len(measured),
        "n_regressed": len(regressed_rows),
        "n_regressed_human_verified": sum(1 for r in regressed_rows if r.get("human_verified") is True),
        "prevalence_bound_wilson95": [lo, hi],
        "conditionality": conditionality,
        # Carried separately from `conditionality` on purpose: a passed control must not
        # be able to switch this off, because it answers a different question.
        "resolution_caveat": resolution,
    }


def _aggregate(targets: list[Target], rows: list[dict], control: dict) -> dict:
    """Per-stratum, per-axis prevalence bounds. Neither strata nor axes are ever pooled."""
    conditionality = None if control.get("status") == "pass" else CONDITIONALITY_LABEL
    # Unconditional today: no epsilon has been measured INTO a bound anywhere in this
    # project, so every printed MDE is a floor. When a screen is run with a measured
    # epsilon this becomes None the same way `conditionality` does - and not before.
    resolution = RESOLUTION_LABEL
    by_stratum: dict = {}
    for stratum in sorted({t.stratum for t in targets}):
        stratum_rows = [r for r in rows if r["stratum"] == stratum]
        completed = [r for r in stratum_rows if r["status"] != STATUS_ERROR]
        by_stratum[stratum] = {
            "n_targets": sum(1 for t in targets if t.stratum == stratum),
            "n_completed": len(completed),
            "n_operational_errors": len(stratum_rows) - len(completed),
            "refusal_robustness": _axis_aggregate(completed, "refusal_robustness", conditionality, resolution),
            "over_refusal": _axis_aggregate(completed, "over_refusal", conditionality, resolution),
        }
    return by_stratum


def _summary(
    manifest_name: str,
    manifest_path: str,
    targets: list[Target],
    rows: list[dict],
    control: dict,
    created_utc: str,
    max_new_tokens: int,
) -> dict:
    import quantfit

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "quantfit_version": quantfit.__version__,
        "created_utc": created_utc,
        "manifest": {"name": manifest_name, "path": str(manifest_path), "n_targets": len(targets)},
        "all_targets_attempted": len(rows) == len(targets),
        "decode": {"max_new_tokens": max_new_tokens},
        "caps": dict(SPEC_CAPS),
        "sensitivity_control": dict(control),
        "rows": list(rows),
        "by_stratum": _aggregate(targets, rows, control),
        "notes": list(NOTES),
    }


def _write_summary(path: Path, summary: dict) -> None:
    try:
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ScreenError(f"cannot write screen summary {path}: {exc}") from exc
