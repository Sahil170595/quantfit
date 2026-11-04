"""Strict resume over one bounded, held native screen population.

Holding authenticates neither weights nor execution. New measurements are sequential;
their files are retained even if receiving refuses them. Publication is atomic per file,
not a transaction covering execution, captures, native reports and summaries.
"""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from quantfit import saved_screen as saved
from quantfit.bundle import _no_links, _read
from quantfit.junit import screen_to_junit
from quantfit.probe_bundle import LocalProbeCorpus
from quantfit.reproduce import (
    _canonical_receiving_path,
    _publish_reproduction_outputs,
    _ReproductionOutputs,
    _validate_reproduction_outputs,
)
from quantfit.safety.verify import DECODE_CHAT_TEMPLATE_POLICY, ProbeCorpus
from quantfit.screen import (
    CAPTURE_NOTICE,
    CONDITIONALITY_LABEL,
    SUMMARY_FILENAME,
    ScreenError,
    Target,
    _base_row,
    _summary,
)

if TYPE_CHECKING:
    from quantfit.probe_population import _PreparedPopulation


class _SourceOptions(TypedDict, total=False):
    probe_corpus: ProbeCorpus | LocalProbeCorpus
    _prepared_population: _PreparedPopulation | None


RESUME_NOTES = (
    (
        "Prevalence counts measured targets per stratum and axis, never pooled probes. Flags remain "
        "unconfirmed; dangerous zeros mean the detector did not fire. Existing native reports are held "
        "and validated; only missing target reports execute. Content checks do not authenticate "
        "controls, hosts, weights, human labels or independent execution, and establish no scientific GO."
    ),
    (
        "Strict resume retains detection-sensitivity conditionality for every axis, including a recorded "
        "control pass: that declaration remains unverified. Every printed MDE remains a perfect-judge floor; "
        "the per-axis resolution caveat is unchanged and no measured epsilon is folded into these bounds."
    ),
)


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise ScreenError(category)


def _exists(path: Path) -> bool:
    """Only actual absence is missing; unreadable and nonregular paths are errors."""
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _same(left: Path, right: Path) -> bool:
    return left == right or (_exists(left) and _exists(right) and left.samefile(right))


@dataclass(frozen=True)
class _Prepared:
    manifest_path: Path
    manifest: bytes
    name: str
    targets: list[Target]
    control: dict[str, Any]
    root: Path
    capture: Path | None
    junit: Path | None
    held: dict[str, bytes]
    received: dict[str, Any]
    local_model_inputs: tuple[Path, ...] = ()
    corpus_input: Path | None = None

    @property
    def reports(self) -> tuple[Path, ...]:
        return tuple(self.root / f"{target.name}.json" for target in self.targets)

    @property
    def captures(self) -> tuple[Path, ...]:
        if self.capture is None:
            return ()
        return tuple(self.capture / f"{target.name}.capture.jsonl" for target in self.targets)

    @property
    def summary(self) -> Path:
        return self.root / SUMMARY_FILENAME

    def output_plan(self) -> _ReproductionOutputs:
        return _ReproductionOutputs(
            (
                self.manifest_path,
                *self.reports,
                *self.captures,
                *self.local_model_inputs,
                *((self.junit,) if self.junit else ()),
            ),
            (),
            (self.summary,),
        )

    def junit_plan(self) -> _ReproductionOutputs:
        return _ReproductionOutputs(
            (self.manifest_path, *self.reports, self.summary, *self.captures, *self.local_model_inputs),
            (self.root, *((self.capture,) if self.capture else ())),
            (self.junit,) if self.junit else (),
        )


def _paths(prepared: _Prepared) -> None:
    """Check future output paths before mkdir, then again before each contact/write."""
    if prepared.corpus_input is not None:
        from quantfit.corpus_gate import _admit_publication_paths
        from quantfit.gate import validate_replay_outputs

        sources = (prepared.manifest_path, prepared.corpus_input, *prepared.local_model_inputs)
        targets = (*prepared.reports, prepared.summary, *prepared.captures, prepared.junit)
        # The native screen admits future directory parents before mkdir. Native
        # reproduction publication requires existing parents, so use its alias
        # projection now and its complete publication check once parents exist.
        validate_replay_outputs(sources, targets)
        if all(p is None or p.parent.is_dir() for p in targets):
            _admit_publication_paths(sources, targets)
    directories = (prepared.root, *((prepared.capture,) if prepared.capture else ()))
    for directory in directories:
        _no_links(directory)
        _require(not _exists(directory) or stat.S_ISDIR(directory.lstat().st_mode), "unsafe_output")
        # A missing parent may be created; an existing non-directory may not.
        for parent in directory.parents:
            _require(not _exists(parent) or stat.S_ISDIR(parent.lstat().st_mode), "unsafe_output")
    if prepared.capture is not None:
        _require(not prepared.capture.is_relative_to(prepared.root), "unsafe_output")
    sources = (prepared.manifest_path, *prepared.reports, *prepared.local_model_inputs)
    outputs = (prepared.summary, *prepared.captures, *((prepared.junit,) if prepared.junit else ()))
    for path in (*sources, *outputs):
        _no_links(path)
        _require(not _exists(path) or stat.S_ISREG(path.lstat().st_mode), "unsafe_output")
    for index, path in enumerate(outputs):
        _require(not any(_same(path, other) for other in (*sources, *outputs[:index])), "unsafe_output")
    if prepared.junit is not None:
        _validate_reproduction_outputs(prepared.junit_plan())


def _current_protocol(received: dict[str, Any], max_new_tokens: int) -> None:
    for protocol in received["protocol_by_stratum"].values():
        _require(
            protocol["decode"]["max_new_tokens"] == max_new_tokens
            and protocol["decode"]["chat_template"] == DECODE_CHAT_TEMPLATE_POLICY,
            "incompatible_resume_decode",
        )


def _receive(
    prepared: _Prepared,
    held: dict[str, bytes],
    max_new_tokens: int,
    *,
    probe_corpus: ProbeCorpus | LocalProbeCorpus | None = None,
) -> dict[str, Any]:
    received = saved._summarize_held(
        prepared.manifest,
        held,
        manifest_path=str(prepared.manifest_path),
        reports_dir=str(prepared.root),
        probe_corpus=probe_corpus,
    )
    _current_protocol(received, max_new_tokens)
    return received


def _prepare(
    manifest_path: str,
    out_dir: str,
    capture_dir: str | None,
    junit_path: str | None,
    cap: int,
    *,
    probe_corpus: ProbeCorpus | LocalProbeCorpus | None = None,
    probe_bundle_path: str | None = None,
) -> _Prepared:
    _require(type(cap) is int and cap > 0, "invalid_max_new_tokens")
    manifest_path, out_dir = (_canonical_receiving_path(path) for path in (manifest_path, out_dir))
    manifest = _read(Path(manifest_path), saved.MAX_MANIFEST_BYTES)
    name, targets, control = saved._manifest(manifest)
    root = Path(out_dir)
    capture = Path(_canonical_receiving_path(capture_dir)) if capture_dir is not None else None
    junit = Path(_canonical_receiving_path(junit_path)) if junit_path is not None else None
    models: tuple[Path, ...] = ()
    if probe_corpus is not None:
        from quantfit.corpus_gate import _local_model_inputs

        models = _local_model_inputs([ref for target in targets for ref in (target.baseline, target.quant)])
    prepared = _Prepared(
        Path(manifest_path),
        manifest,
        name,
        targets,
        control,
        root,
        capture,
        junit,
        {},
        {},
        models,
        Path(probe_bundle_path) if probe_bundle_path is not None else None,
    )
    _paths(prepared)
    allowed = {path.name for path in prepared.reports} | {SUMMARY_FILENAME}
    members = saved._inventory(root, allowed) if _exists(root) else []
    remaining = saved.MAX_TOTAL_BYTES
    held: dict[str, bytes] = {}
    for path in members:
        _require(remaining > 0, "report_byte_limit")
        raw = _read(path, min(saved.MAX_REPORT_BYTES, remaining))
        held[path.name] = raw
        remaining -= len(raw)
    received = _receive(prepared, held, cap, probe_corpus=probe_corpus)
    return _Prepared(
        Path(manifest_path),
        manifest,
        name,
        targets,
        control,
        root,
        capture,
        junit,
        held,
        received,
        models,
        prepared.corpus_input,
    )


def _receipt(prepared: _Prepared, entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "quantfit.screen-resume",
        "manifest": {"sha256": hashlib.sha256(prepared.manifest).hexdigest(), "size_bytes": len(prepared.manifest)},
        "targets": list(entries),
        "initial_missing": [target.name for target in prepared.targets if f"{target.name}.json" not in prepared.held],
        "n_skipped": sum(entry["action"] == "skipped" for entry in entries),
        "n_executed": sum(entry["action"] == "executed" for entry in entries),
        "n_operational_errors": sum(entry["action"] == "operational_error" for entry in entries),
        "control_evidence_verified": False,
        "independent_execution_verified": False,
        "limits": {
            "manifest_bytes": saved.MAX_MANIFEST_BYTES,
            "report_bytes": saved.MAX_REPORT_BYTES,
            "total_report_bytes": saved.MAX_TOTAL_BYTES,
            "max_targets": saved.MAX_TARGETS,
        },
    }


def _exit_code(summary: dict[str, Any]) -> int:
    statuses = {row["status"] for row in summary["rows"]}
    if "regression" in statuses:
        return 3
    axes = [block[axis] for block in summary["by_stratum"].values() for axis in ("refusal_robustness", "over_refusal")]
    if (
        not summary["all_targets_attempted"]
        or statuses & {"operational_error", "unmeasurable"}
        or any(axis["n_measured"] == 0 for axis in axes)
    ):
        return 4
    return 0


def _entry(target: Target, binding: dict[str, Any], row: dict[str, Any], action: str) -> dict[str, Any]:
    return {
        **{key: value for key, value in _base_row(target).items() if key != "notes"},
        "member": f"{target.name}.json",
        "action": action,
        "sha256": binding["sha256"],
        "size_bytes": binding["size_bytes"],
        "producer_quantfit_version": binding["producer_quantfit_version"],
        "status": row["status"],
    }


def run_resumed_screen(
    manifest_path: str,
    out_dir: str,
    *,
    token: str | None,
    max_new_tokens: int,
    capture_dir: str | None,
    attempts: int,
    junit_path: str | None,
    probe_corpus: ProbeCorpus | LocalProbeCorpus | None = None,
    probe_bundle_path: str | None = None,
    _fresh: bool = False,
) -> dict[str, Any]:
    """Admit all present evidence once; execute only absent native report members."""
    phase = "invalid_resume_input"
    try:
        source_options: _SourceOptions = {}
        corpus_context = None
        held_population = None
        if probe_corpus is not None:
            from quantfit import probe_population as population
            from quantfit.safety import verify
            from quantfit.safety.calibration_binding import _same_numbers

            probe_corpus = verify._corpus(probe_corpus)
        prepared = _prepare(
            manifest_path,
            out_dir,
            capture_dir,
            junit_path,
            max_new_tokens,
            probe_corpus=probe_corpus,
            probe_bundle_path=probe_bundle_path,
        )
        if probe_corpus is not None:
            _require(type(attempts) is int and attempts >= 1, "invalid_attempts")
            for target in prepared.targets:
                from quantfit.safety.gguf_arm import is_gguf_ref

                _require(
                    all(is_gguf_ref(ref) == (target.stratum == "gguf") for ref in (target.baseline, target.quant)),
                    "target_stratum_mismatch",
                )
                verify._admit_verify_options(
                    target.baseline, target.quant, probe_corpus=probe_corpus, max_new_tokens=max_new_tokens
                )
            if _fresh:
                _require(
                    not any(f"{target.name}.json" in prepared.held for target in prepared.targets),
                    "existing_reports_require_resume",
                )
            missing = [t for t in prepared.targets if f"{t.name}.json" not in prepared.held]
            corpus_context = prepared.received["probe_corpus"]
            if missing:
                held_population = population.prepare(token, probe_corpus, probe_bundle_path=probe_bundle_path)
                resolved_context = population.context(held_population)
                if corpus_context["population_basis"] != "unavailable_no_reports":
                    _same_numbers(
                        {k: v for k, v in corpus_context.items() if k != "population_basis"},
                        {k: v for k, v in resolved_context.items() if k != "population_basis"},
                        "resolved resume population",
                    )
                corpus_context = resolved_context
                source_options = {"probe_corpus": probe_corpus, "_prepared_population": held_population}
            elif probe_bundle_path is not None:
                raise ScreenError("complete_resume_requires_identity_only")

        def current_paths() -> None:
            _paths(prepared)
            if held_population is not None and held_population.held_file is not None:
                held_population.held_file.check()

        # No filesystem mutation or model call occurs before the complete preflight.
        from quantfit.safety.verify import verify_safety

        phase = "unsafe_output"
        prepared.root.mkdir(parents=True, exist_ok=True)
        if prepared.capture is not None:
            prepared.capture.mkdir(parents=True, exist_ok=True)
            print(f"captures -> {prepared.capture} ({CAPTURE_NOTICE})")
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows: list[dict[str, Any]] = []
        entries: list[dict[str, Any]] = []
        held = dict(prepared.held)
        received = prepared.received
        for index, target in enumerate(prepared.targets):
            current_paths()
            member = f"{target.name}.json"
            path = prepared.root / member
            if member in prepared.held:
                row = received["rows"][index]
                entries.append(_entry(target, received["report_bindings"][index], row, "skipped"))
                print(f"resume: {target.name} already measured")
            else:
                for attempt in range(1, max(1, attempts) + 1):
                    current_paths()
                    _require(not _exists(path), "unexpected_report_member")
                    phase = "execution_failed"
                    try:
                        verify_safety(
                            target.baseline,
                            target.quant,
                            token=token,
                            max_new_tokens=max_new_tokens,
                            report_path=str(path),
                            capture_path=str(prepared.captures[index]) if prepared.capture else None,
                            **source_options,
                        )
                    except (RuntimeError, OSError, ImportError):
                        # Never overwrite a report that appeared during a failed attempt.
                        _require(not _exists(path), "execution_report_failure")
                        if attempt < max(1, attempts):
                            print(f"{target.name}: attempt {attempt}/{attempts} failed, retrying")
                            continue
                        row = {
                            **_base_row(target),
                            "report": None,
                            "status": "operational_error",
                            "error": "execution_failed",
                            "error_type": "ScreenExecutionError",
                        }
                        entries.append(
                            _entry(
                                target,
                                {"sha256": None, "size_bytes": None, "producer_quantfit_version": None},
                                row,
                                "operational_error",
                            )
                        )
                    else:
                        phase = "invalid_executed_report"
                        remaining = saved.MAX_TOTAL_BYTES - sum(len(raw) for raw in held.values())
                        _require(remaining > 0, "report_byte_limit")
                        held[member] = _read(path, min(saved.MAX_REPORT_BYTES, remaining))
                        received = _receive(prepared, held, max_new_tokens, probe_corpus=probe_corpus)
                        if corpus_context is not None:
                            _same_numbers(
                                {k: v for k, v in received["probe_corpus"].items() if k != "population_basis"},
                                {k: v for k, v in corpus_context.items() if k != "population_basis"},
                                "executed native report versus held population",
                            )
                        row = received["rows"][index]
                        entries.append(_entry(target, received["report_bindings"][index], row, "executed"))
                    break
            rows.append(row)
            summary = _summary(
                prepared.name,
                str(prepared.manifest_path),
                prepared.targets,
                rows,
                prepared.control,
                created,
                max_new_tokens,
            )
            # A recorded control pass is not receiving proof of that control.
            for stratum in summary["by_stratum"].values():
                for axis in ("refusal_robustness", "over_refusal"):
                    stratum[axis]["conditionality"] = CONDITIONALITY_LABEL
            summary["notes"] = list(RESUME_NOTES)
            if probe_corpus is not None:
                summary["schema_version"] = 2
                summary["probe_corpus"] = corpus_context
                summary["control_evidence_verified"] = False
                summary["effective_conditionality"] = CONDITIONALITY_LABEL
            if not _fresh:
                summary["resume_receipt"] = _receipt(prepared, entries)
                summary["resume_receipt"]["exit_code"] = _exit_code(summary)
            raw_summary = (json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
            _require(
                len(raw_summary) <= saved.MAX_REPORT_BYTES
                and sum(len(raw) for name, raw in held.items() if name != SUMMARY_FILENAME) + len(raw_summary)
                <= saved.MAX_TOTAL_BYTES,
                "report_byte_limit",
            )
            phase = "output_failure"
            _publish_reproduction_outputs(
                prepared.output_plan(), [(prepared.summary, raw_summary)], recheck=lambda: current_paths()
            )
        if prepared.junit is not None:
            _publish_reproduction_outputs(
                prepared.junit_plan(),
                [(prepared.junit, screen_to_junit(summary).encode())],
                recheck=lambda: current_paths(),
            )
        return summary
    except ScreenError:
        raise
    except saved.SavedScreenError as exc:
        raise ScreenError(exc.category) from None
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, RecursionError, ImportError):
        raise ScreenError(phase) from None
