"""One actual installed/native Phi4 campaign; explicit aggregate publication outputs.

Measurement failures and unconfirmed flags are evidence, never registry admission.
No credentials, model text, raw labels or private native logs are retained here.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import importlib.metadata
import io
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from quantfit.bundle import _json, _read, _report
from quantfit.report_comparison import (
    ALLOWED_VOLATILE_PATHS as _VOLATILE_PATHS,
)
from quantfit.report_comparison import (
    differences as _differences,
)
from quantfit.report_comparison import (
    normalized as _normalized,
)
from quantfit.reproduce import ReproduceError, within_hardware_identical
from quantfit.resolution import MAX_REPORT_BYTES, _axes
from quantfit.safety import verify
from quantfit.safety.gguf_arm import CPU_OFFLOAD_CONTROLS

PHI4_REVISION = "78eb92a46fc37e6b524df991ed9aca9bc6aa7b80"
PAIR = {
    "baseline": {
        "ref": "hf:unsloth/Phi-4-mini-instruct-GGUF/Phi-4-mini-instruct.BF16.gguf",
        "dtype": "BF16",
        "size_bytes": 7_680_694_240,
        "sha256": "1a179f22f1efe409c6517805400c4f07f93fe1f5783e47231d35f933565dff20",
    },
    "quantized": {
        "ref": "hf:unsloth/Phi-4-mini-instruct-GGUF/Phi-4-mini-instruct-Q4_K_M.gguf",
        "dtype": "Q4_K_M",
        "size_bytes": 2_491_874_272,
        "sha256": "88c00229914083cd112853aab84ed51b87bdf6b9ce42f532d8c85c7c63b1730a",
    },
}
ALLOWED_VOLATILE_PATHS = list(_VOLATILE_PATHS)
PUBLIC_FILES = ["campaign.json", "assessment.json", "native-cold-run.json", "native-t0.json"] + [
    f"run-{i}/{name}" for i in range(1, 4) for name in ("report.json", "model-card.md")
]


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class CampaignError(RuntimeError):
    """A static, sanitized campaign refusal reason."""


def require(condition, message):
    if not condition:
        raise CampaignError(message)


def assess_reports(paths: list[Path], *, binary_sha256: str, threads: int) -> dict:
    """Reuse native aggregate/T0 validators; compare complete payloads without causal slack."""
    require(len(paths) == 3, "reference campaign needs exactly three report sources")
    require(type(threads) is int and threads > 0, "actual native thread count required")
    buffers = [_read(path, MAX_REPORT_BYTES) for path in paths]
    reports = [_report(raw) for raw in buffers]
    values = [_json(raw) for raw in buffers]
    axes, exits = [], []
    for report in reports:
        require(
            all(
                type(value) in (int, float) and math.isfinite(value) and value >= 0
                for value in (report.judge_runtime_s, report.baseline.runtime_s, report.quantized.runtime_s)
            ),
            "reported runtimes must be finite nonnegative observations",
        )
        require(report.env.get("device") == "cpu", "native campaign reported device must be cpu")
        require(
            report.probe_dataset
            == {
                "id": verify.PROBE_DATASET_ID,
                "revision": verify.PROBE_DATASET_REVISION,
                "split": verify.PROBE_SPLIT,
                "n_probes": 40,
            },
            "campaign needs actual pinned full40 dataset",
        )
        require(
            report.judge.get("id") == verify.JUDGE_MODEL_ID and report.judge.get("revision") == verify.JUDGE_REVISION,
            "campaign judge pins differ",
        )
        require(
            report.judge.get("card_xstest_accuracy_label") == verify._measured_judge_label(),
            "current judge label required",
        )
        require(
            report.decode.get("max_new_tokens") == 64 and report.decode.get("do_sample") is False,
            "campaign must preserve shipped greedy64",
        )
        for name, arm in (("baseline", report.baseline), ("quantized", report.quantized)):
            expected = PAIR[name]
            require(
                arm.model == expected["ref"] and arm.revision == PHI4_REVISION, "actual immutable arm identity differs"
            )
            require(
                arm.artifact_sha256 == expected["sha256"] and arm.resolved_dtype == expected["dtype"],
                "actual arm bytes/precision differ",
            )
            require(
                arm.engine.get("name") == "llama.cpp" and arm.engine.get("device") == "cpu",
                "native CPU engine required",
            )
            require(
                arm.engine.get("binary_sha256") == binary_sha256
                and type(arm.engine.get("threads")) is int
                and arm.engine["threads"] == threads,
                "actual same-binary/thread contract differs",
            )
            require(
                all(type(arm.engine.get(k)) is type(v) and arm.engine[k] == v for k, v in CPU_OFFLOAD_CONTROLS.items()),
                "actual applied CPU controls required",
            )
            require("baseline_cache" not in arm.engine, "completion-cache report cannot qualify")
        block = _axes(report)
        for name, axis in block.items():
            field = "refusal_robustness" if name == "refusal-robustness" else "over_refusal"
            axis["two_sided_95pct_wilson"] = report.drift[field]["flip_rate_wilson95"]
            axis["perfect_judge_mde_floor_80pct_power"] = report.drift[field]["mde_at_80pct_power"]
            axis["human_confirmed_flips"] = None
            axis["null_interpretation"] = (
                "nothing was measured on this axis"
                if not axis["measurable"]
                else "the detector did not fire"
                if axis["flagged_flips"] == 0
                else None
            )
        axes.append(block)
        exits.append(3 if report.drift["regression_detected"] else 4 if report.drift["unmeasurable_axes"] else 0)
    t0 = None
    reasons = []
    try:
        t0 = within_hardware_identical([str(path) for path in paths])
    except ReproduceError:
        reasons.append("t0_operational_refusal")
    hashes = [sha(raw) for raw in buffers]
    require([sha(_read(path, MAX_REPORT_BYTES)) for path in paths] == hashes, "report bytes changed during T0")
    if t0 is not None:
        require([item["report_sha256"] for item in t0["reports"]] == hashes, "T0 consumed report bytes changed")
        if t0["protocol_pass"] is not True:
            reasons.append("t0_disagreement")
    normalized = [_normalized(value) for value in values]
    differing = sorted({item for value in normalized[1:] for item in _differences(normalized[0], value)})
    if differing:
        reasons.append("full_report_repeatability_failed")
    if any(axis["flagged_flips"] for run in axes for axis in run.values()):
        reasons.append("fresh_flags_without_human_adjudication")
    excluded = [name for name in axes[0] if not all(run[name]["measurable"] for run in axes)]
    eligible = [name for name in axes[0] if name not in excluded] if not reasons else []
    if not eligible and not reasons:
        reasons.append("no_measured_axis")
    return {
        "assessment_schema_version": 1,
        "spec_version": "v0",
        "pair": "gguf-phi4-mini-unsloth",
        "source_reports": [
            {"path": str(path), "sha256": digest, "size_bytes": len(raw)}
            for path, digest, raw in zip(paths, hashes, buffers)
        ],
        "native_exits": exits,
        "t0": t0,
        "full_report_repeatability": {
            "pass": not differing,
            "allowed_volatile_paths": ALLOWED_VOLATILE_PATHS,
            "differing_paths": differing,
            "normalized_sha256": [sha(json.dumps(v, sort_keys=True, allow_nan=False).encode()) for v in normalized],
        },
        "axes_by_run": axes,
        "excluded_axes": excluded,
        "eligible_axes_before_publication": eligible,
        "blocking_reasons": reasons,
        "registry_admission": "blocked" if reasons else "pending_public_byte_verification",
        "reference_registered": False,
        "scientific_go": False,
        "human_labels_authenticated": False,
        "sensitivity_established": False,
        "independent_execution_verified": False,
        "scope": "One native CPU pair; original flagged counts and perfect-judge floors. No human adjudication, "
        "absence/GO, new sensitivity control, T4/crosshardware or Inspect parity. QSRv1 remains unfrozen.",
    }


def cold_command(output: Path) -> list[str]:
    # Omitting the public flag is intentional; validate actual child argv/report64 after execution.
    return [
        sys.executable,
        "-m",
        "quantfit.cli",
        "cold-run",
        "--baseline",
        PAIR["baseline"]["ref"],
        "--quant",
        PAIR["quantized"]["ref"],
        "--baseline-revision",
        PHI4_REVISION,
        "--quant-revision",
        PHI4_REVISION,
        "--out",
        str(output),
        "--timeout-seconds",
        "3600",
        "--json",
    ]


def _aggregate(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if re.search(r"prompt|completion|response|text|generation", key, re.IGNORECASE):
                require(
                    key == "completion_cache_requested" and child is False, "unexpected raw/private aggregate field"
                )
            _aggregate(child)
    elif isinstance(value, list):
        for child in value:
            _aggregate(child)


def _stage_bytes(path: Path, raw: bytes):
    """Publish only complete buffers; owned temporary files are never upload paths."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".staging-", delete=False) as stream:
            temporary = Path(stream.name)
            require(stream.write(raw) == len(raw), "incomplete aggregate staging write")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write(path: Path, value: dict):
    _aggregate(value)
    _stage_bytes(path, (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())


def _finish(public: Path, state: dict, exit_code: int):
    state["execution_exit"] = exit_code
    state["public_files"] = [
        {"path": name, "sha256": sha((public / name).read_bytes()), "size_bytes": (public / name).stat().st_size}
        for name in PUBLIC_FILES
        if name != "campaign.json" and (public / name).is_file()
    ]
    _write(public / "campaign.json", state)


def _revoke(public: Path, assessment: dict | None, native: dict | None):
    """A terminal failure cannot leave standalone positive qualification behind.

    Private native originals are untouched. Retain valid aggregates and genuine
    native observations, explicitly distinguishing them from campaign admission.
    If a failure prevents rewriting qualification metadata, remove that owned
    metadata rather than retain its earlier positive declaration.
    """
    (public / "native-t0.json").unlink(missing_ok=True)
    (public / "campaign.json").unlink(missing_ok=True)
    rewritten = {}
    if assessment is not None:
        value = copy.deepcopy(assessment)
        value.update(
            registry_admission="blocked",
            eligible_axes_before_publication=[],
            t0=None,
            campaign_execution_complete=False,
            t0_unavailable_reason="campaign_terminal_failure; original native observations are not qualification",
        )
        value["blocking_reasons"] = sorted(set(value["blocking_reasons"]) | {"campaign_terminal_failure"})
        rewritten["assessment.json"] = value
    if native is not None and (public / "native-cold-run.json").exists():
        value = copy.deepcopy(native)
        value.update(
            publication_qualification=False,
            campaign_execution_complete=False,
            observation_scope="Original native observations only; campaign terminal failure revoked publication qualification.",
        )
        rewritten["native-cold-run.json"] = value
    for name, value in rewritten.items():
        path = public / name
        try:
            _write(path, value)
        except (OSError, KeyboardInterrupt):
            path.unlink(missing_ok=True)


def _candidate(wheel: Path) -> dict:
    import quantfit

    checkout = Path(__file__).resolve().parents[1]
    package = Path(quantfit.__file__).resolve().parent
    require(not package.is_relative_to(checkout), "candidate must be installed outside checkout")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=checkout, capture_output=True, text=True, check=True
    ).stdout.strip()
    files = {}
    with zipfile.ZipFile(wheel) as archive:
        for file in sorted(package.rglob("*.py")):
            relative = file.relative_to(package.parent).as_posix()
            blob = subprocess.run(
                ["git", "show", f"HEAD:{relative}"], cwd=checkout, capture_output=True, check=True
            ).stdout
            require(
                file.read_bytes() == blob == archive.read(relative),
                "installed/wheel candidate code differs from measured source",
            )
            files[relative] = sha(blob)
    script = Path(__file__)
    script_blob = subprocess.run(
        ["git", "show", "HEAD:tools/ci_reference_campaign.py"], cwd=checkout, capture_output=True, check=True
    ).stdout
    require(script.read_bytes() == script_blob, "campaign script differs from immutable source")
    return {
        "source_head": head,
        "installed_origin": str(quantfit.__file__),
        "installed_source_sha256": files,
        "wheel_file": wheel.name,
        "wheel_sha256": sha(wheel.read_bytes()),
        "campaign_source_sha256": sha(script_blob),
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("quantfit", "torch", "transformers", "huggingface-hub", "gguf", "psutil", "hf-xet")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path)
    args = parser.parse_args()
    require(not args.out.exists(), "campaign needs a new owned output directory")
    args.out.mkdir(parents=True)
    public = args.out / "publication"
    public.mkdir()
    state = {
        "campaign_schema_version": 1,
        "status": "starting",
        "phase": "preflight",
        "actual_cold_cli_exit": None,
        "omitted_public_token_flag": True,
        "pair_pins": PAIR,
        "revision": PHI4_REVISION,
        "scientific_go": False,
        "human_labels_authenticated": False,
        "reference_registered": False,
    }
    exit_code = 2
    previous = None
    assessment = None
    accepted_assessment = None
    result = None
    try:
        require(os.name == "posix", "campaign is POSIX-only")
        previous = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        import torch

        from quantfit.backends import gguf as backend
        from quantfit.cli import main as cli
        from quantfit.cold_run import _resources
        from quantfit.modelcard import model_card_fragment
        from quantfit.safety.gguf_arm import _binary_source, _resolve, _threads

        require(
            not torch.cuda.is_available() and not torch.backends.mps.is_available(), "CPU-only hosted campaign required"
        )
        require(not os.environ.get("QUANTFIT_LLAMACPP"), "campaign needs supported pinned release binary")
        torch.set_num_threads(2)
        state["candidate"] = _candidate(args.wheel)
        state["after_install_preflight"] = _resources(args.out)
        state["observed_cuda_available"] = False
        state["observed_mps_available"] = False
        state["native_threads_observed"] = _threads()
        state["phase"] = "resolve_and_hash_weights"
        state["weights"] = {}
        for name, expected in PAIR.items():
            arm = _resolve(expected["ref"], None, revision=PHI4_REVISION)
            require(
                arm.sha256 == expected["sha256"] and arm.path.stat().st_size == expected["size_bytes"],
                "actual weight bytes differ from preregistration",
            )
            require(
                arm.revision == PHI4_REVISION and arm.file_type == expected["dtype"],
                "resolved weight pin/precision differs",
            )
            state["weights"][name] = {
                "sha256": arm.sha256,
                "size_bytes": arm.path.stat().st_size,
                "resolved_revision": arm.revision,
                "resolved_dtype": arm.file_type,
            }
        state["after_download_observations"] = _resources(args.out)
        state["phase"] = "provision_binary"
        binary = backend.llama_server_bin()
        asset = backend._binary_asset()
        archive = backend._cache_dir() / asset
        require(archive.is_file(), "fresh hosted binary archive required for actual provisioning proof")
        backend._verify_or_die(archive, asset)
        binary_sha = backend._sha256(binary)
        state["binary"] = {
            "tag": backend.LLAMACPP_TAG,
            "asset": asset,
            "archive_sha256": backend._sha256(archive),
            "executable_sha256": binary_sha,
            "source": _binary_source(binary),
        }
        working = args.out / "native"
        argv = cold_command(working)
        state["public_argv"] = argv
        state["phase"] = "three_native_children"
        # Public parser and shipped omitted default are exercised in-process. Its
        # native children are still three new sessions; SIGTERM raises through their cleanup.
        envelope_buffer = io.StringIO()
        with contextlib.redirect_stdout(envelope_buffer):
            native_exit = cli(argv[3:])
        state["actual_cold_cli_exit"] = native_exit
        envelope = json.loads(envelope_buffer.getvalue())
        result = envelope.get("result")
        require(result is not None, "cold-run did not produce an aggregate result")
        _aggregate(result)
        _write(public / "native-cold-run.json", result)
        state["phase"] = "validate_measurements"
        require(
            native_exit in (0, 3) and result["status"] in ("t0_agreement", "t0_disagreement"),
            "native campaign operational failure",
        )
        require(
            result["requested"]["max_new_tokens"] == 64 and len(result["runs"]) == 3,
            "shipped default/three-run contract differs",
        )
        require(len({run["pid"] for run in result["runs"]}) == 3, "native children must have distinct observed PIDs")
        for run in result["runs"]:
            require(run["native_exit_code"] in (0, 3, 4), "native operational failure")
            require(
                run["cleanup"]["direct_child_reaped"] and run["cleanup"]["no_live_group_members_observed"] is True,
                "owned native group cleanup failed",
            )
            require(run["argv"][run["argv"].index("--max-new-tokens") + 1] == "64", "actual child token limit differs")
        paths = [working / f"run-{i}/report.json" for i in range(1, 4)]
        assessment = assess_reports(paths, binary_sha256=binary_sha, threads=state["native_threads_observed"])
        require(
            assessment["native_exits"] == [run["native_exit_code"] for run in result["runs"]],
            "native exits differ from validated reports",
        )
        require(assessment["t0"] == result["t0"], "fresh rechecked T0 differs from native T0")
        accepted_assessment = assessment
        # Copy only buffers whose hash was just checked by the assessment, never the raw directory.
        for index, source in enumerate(paths, 1):
            raw = _read(source, MAX_REPORT_BYTES)
            require(
                sha(raw) == assessment["source_reports"][index - 1]["sha256"],
                "source changed before publication staging",
            )
            destination = public / f"run-{index}"
            destination.mkdir()
            _stage_bytes(destination / "report.json", raw)
            _stage_bytes(
                destination / "model-card.md", model_card_fragment(str(destination / "report.json")).encode("utf-8")
            )
        _write(public / "assessment.json", assessment)
        native_t0 = _read(working / "t0.json", MAX_REPORT_BYTES)
        require(_json(native_t0) == result["t0"], "original native T0 changed before publication staging")
        _stage_bytes(public / "native-t0.json", native_t0)
        state["status"] = "measured_candidate"
        state["reference_eligibility"] = assessment["registry_admission"]
        state["actual_native_exits"] = assessment["native_exits"]
        state["actual_default_tokens_in_all_reports"] = 64
        state["full_report_repeatability"] = assessment["full_report_repeatability"]["pass"]
        state["t0_protocol_pass"] = assessment["t0"]["protocol_pass"]
        state["phase"] = "complete"
        exit_code = 0  # Successful evidence execution, even when measurement/reference eligibility is negative.
        _finish(public, state, exit_code)
    except (Exception, KeyboardInterrupt) as exc:  # noqa: BLE001 - artifact boundary always fails CI; never retain raw error text.
        exit_code = 2
        state["status"] = "operational_failure"
        state["failure_type"] = type(exc).__name__  # Never include arbitrary exception/raw server text.
        if isinstance(exc, CampaignError):
            state["failure_reason"] = str(exc)  # Only this tool's static messages, not SDK/native exception bodies.
        state["reference_eligibility"] = "blocked"
        _revoke(public, accepted_assessment, result)
        _finish(public, state, exit_code)
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)
    print(
        json.dumps(
            {
                "status": state["status"],
                "phase": state["phase"],
                "execution_exit": exit_code,
                "scientific_go": False,
                "reference_registered": False,
            }
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
