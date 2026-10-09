"""Three uncached native GGUF processes and the existing within-host T0 check.

Child measurement exits are evidence, not this runner's orchestration status. Resource
observations are companion facts; they never change the native report.env/T0 identity.
POSIX sessions contain native llama-server descendants. No arbitrary command, raw log,
completion cache or capture interface is offered.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

from quantfit import __version__
from quantfit.bundle import _json, _no_links, _private_fields, _read, _report
from quantfit.reproduce import within_hardware_identical
from quantfit.resolution import MAX_REPORT_BYTES
from quantfit.safety.gguf_arm import UNQUANTIZED_FILE_TYPES, _threads, is_gguf_ref, validate_revision


def _resources(path: Path) -> dict:
    cpu = {}
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            key, _, value = line.partition(":")
            if key.strip() in ("model name", "flags") and key.strip() not in cpu:
                cpu[key.strip()] = value.strip()
    except OSError:
        pass
    memory = psutil.virtual_memory()
    return {
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "logical_cpu_count": os.cpu_count(),
        "ram_available_bytes": memory.available,
        "ram_total_bytes": memory.total,
        "disk_free_bytes": shutil.disk_usage(path).free,
        "platform": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "psutil": importlib.metadata.version("psutil"),
        "cpu_observations": cpu,
        "kernel": platform.release(),
        "native_threads_observed": _threads(),
        "gpu_driver_observed": None,
        "gpu_toolkit_observed": None,
        "gpu_capability_observed": None,
    }


def _group_members(group: int) -> list[dict] | None:
    """Linux /proc observations only; never infer non-child wait/reap from absence."""
    proc = Path("/proc")
    if platform.system() != "Linux" or not proc.is_dir():
        return None
    members = []
    for path in proc.iterdir():
        if not path.name.isdigit():
            continue
        try:
            # comm can contain spaces and parentheses; fields after its final ')' are stable.
            fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) == group and int(fields[3]) == group:
                members.append({"pid": int(path.name), "state": fields[0], "start_ticks": int(fields[19])})
        except (OSError, ValueError, IndexError):
            continue  # A process disappearing while observed is normal.
    return sorted(members, key=lambda item: item["pid"])


def _signal_group(group: int, sig: int) -> bool:
    try:
        os.killpg(group, sig)
        return True
    except ProcessLookupError:
        return False


def _close_group(proc: subprocess.Popen) -> dict:
    before = _group_members(proc.pid)
    term = _signal_group(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    # Even when the direct child has exited, a reparented server still belongs to
    # this session/group. Signal that group rather than relying on ancestry polls.
    killed = _signal_group(proc.pid, signal.SIGKILL)
    proc.wait(timeout=5)
    deadline = time.monotonic() + 2
    after = _group_members(proc.pid)
    while after and any(member["state"] != "Z" for member in after) and time.monotonic() < deadline:
        time.sleep(0.05)
        after = _group_members(proc.pid)
    return {
        "direct_child_reaped": proc.returncode is not None,
        "group_sigterm_sent": term,
        "group_sigkill_sent": killed,
        "observed_group_before_cleanup": before,
        "observed_group_after_cleanup": after,
        "no_live_group_members_observed": None if after is None else not any(m["state"] != "Z" for m in after),
        "grandchild_reaping_verified": False,
    }


def _observed_report(path: Path, baseline: str, quant: str, revisions: dict, code: int, max_tokens: int) -> dict:
    raw = _read(path, MAX_REPORT_BYTES)
    _private_fields(_json(raw))
    report = _report(raw)
    if report.baseline.model != baseline or report.quantized.model != quant:
        raise RuntimeError("native report arm refs do not match the requested run")
    if report.baseline.resolved_dtype not in UNQUANTIZED_FILE_TYPES:
        raise RuntimeError("native GGUF baseline must be unquantized")
    base_engine, quant_engine = report.baseline.engine, report.quantized.engine
    if base_engine.get("binary_sha256") != quant_engine.get("binary_sha256"):
        raise RuntimeError("native GGUF arms must use the identical executable hash")
    threads = base_engine.get("threads")
    if (
        type(threads) is not int
        or threads < 1
        or type(quant_engine.get("threads")) is not int
        or threads != quant_engine["threads"]
    ):
        raise RuntimeError("native GGUF arms must use the identical positive thread count")
    for key, arm in (("baseline", report.baseline), ("quant", report.quantized)):
        if arm.engine.get("name") != "llama.cpp" or arm.engine.get("device") != "cpu":
            raise RuntimeError("cold-run needs observed native CPU GGUF arms")
        if "baseline_cache" in arm.engine:
            raise RuntimeError("a completion-cache marker cannot be a cold-run replicate")
        if revisions.get(key) is not None and arm.revision != revisions[key]:
            raise RuntimeError("native report does not carry the requested resolved GGUF revision")
        if not arm.model.startswith("hf:") and arm.revision is not None:
            raise RuntimeError("local GGUF files cannot claim a resolved Hub revision")
    if report.decode.get("max_new_tokens") != max_tokens or report.decode.get("do_sample") is not False:
        raise RuntimeError("native report decode does not match the requested greedy run")
    expected = 3 if report.drift["regression_detected"] else 4 if report.drift["unmeasurable_axes"] else 0
    if code in (0, 3, 4) and code != expected:
        raise RuntimeError("native exit and observed aggregate verdict disagree")
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "regression_detected": report.drift["regression_detected"],
        "unmeasurable_axes": report.drift["unmeasurable_axes"],
        "reported_env_device": report.env.get("device"),
        "arm_threads_observed": {
            "baseline": report.baseline.engine.get("threads"),
            "quantized": report.quantized.engine.get("threads"),
        },
    }


def cold_run(
    baseline: str,
    quant: str,
    out_path: str,
    *,
    timeout_seconds: float = 3600,
    max_new_tokens: int = 64,
    baseline_revision: str | None = None,
    quant_revision: str | None = None,
) -> dict:
    """Attempt exactly three sequential new native children; 0=T0 pass, 3=disagreement, 2=operational.

    These exits never replace child 0/3/4 measurement outcomes. Hub *weight* caches may
    be reused; every arm's inference runs anew. No completion-cache/capture is passed.
    Existing environment credentials may be consumed by the native child, but neither
    argv nor receipts contain a token. Windows refuses before creating output.
    """
    if not is_gguf_ref(baseline) or not is_gguf_ref(quant):
        raise RuntimeError("cold-run supports native GGUF pairs only")
    validate_revision(baseline, baseline_revision)
    validate_revision(quant, quant_revision)
    if os.name != "posix":
        raise RuntimeError("cold-run requires POSIX process-session containment; Windows is unsupported")
    if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise RuntimeError("timeout-seconds must be finite and positive")
    if type(max_new_tokens) is not int or max_new_tokens < 1:
        raise RuntimeError("max-new-tokens must be a positive integer")
    root = Path(out_path).absolute()
    _no_links(root.parent)
    if root.exists() or root.is_symlink() or not root.parent.is_dir():
        raise RuntimeError("cold-run needs a new output directory whose parent exists")
    root.mkdir()
    result = {
        "cold_run_schema_version": 1,
        "tool_version": __version__,
        "runner": "three_fresh_native_GGUF_children",
        "requested_runs": 3,
        "requested": {
            "baseline": baseline,
            "quant": quant,
            "baseline_revision": baseline_revision,
            "quant_revision": quant_revision,
            "max_new_tokens": max_new_tokens,
            "timeout_seconds": timeout_seconds,
        },
        "completion_cache_requested": False,
        "capture_requested": False,
        "weight_cache_may_be_reused": True,
        "preflight_observations": _resources(root),
        "runs": [],
        "t0": None,
        "exit_code": 2,
        "status": "incomplete",
        "independent_execution_verified": False,
        "scientific_go": False,
        "human_labels_authenticated": False,
        "statement": "Observed fresh native processes and aggregate T0 only. Resource observations are companion "
        "facts, not report.env identity. Native measurement exits remain separate. No host "
        "authentication, human adjudication, sensitivity proof or scientific GO is established.",
    }
    try:
        for index in range(1, 4):
            run_dir = root / f"run-{index}"
            run_dir.mkdir()
            report = run_dir / "report.json"
            argv = [
                sys.executable,
                "-m",
                "quantfit.cli",
                "verify-safety",
                "--baseline",
                baseline,
                "--quant",
                quant,
                "--report",
                str(report),
                "--max-new-tokens",
                str(max_new_tokens),
            ]
            for flag, revision in (("baseline", baseline_revision), ("quant", quant_revision)):
                if revision is not None:
                    argv.extend([f"--{flag}-revision", revision])
            receipt = {
                "index": index,
                "pid": None,
                "argv": argv,
                "status": "starting",
                "report": None,
                "native_exit_code": None,
                "resources_before": _resources(root),
            }
            result["runs"].append(receipt)
            started = time.monotonic()
            # Abruptly killed llama-server logs remain in an owned transient directory,
            # never in the aggregate output. It closes after the owned group is stopped.
            with tempfile.TemporaryDirectory(prefix="quantfit-cold-private-") as private:
                env = os.environ.copy()
                env.update(TMPDIR=private, TMP=private, TEMP=private, PYTHONDONTWRITEBYTECODE="1")
                proc = subprocess.Popen(
                    argv,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                receipt["pid"] = proc.pid
                receipt["process_session_id"] = proc.pid
                try:
                    receipt["native_exit_code"] = proc.wait(timeout=timeout_seconds)
                    receipt["status"] = "completed" if proc.returncode in (0, 3, 4) else "operational_failure"
                except subprocess.TimeoutExpired:
                    receipt["status"] = "timeout"
                except BaseException:
                    receipt["status"] = "cancelled"
                    raise
                finally:
                    try:
                        receipt["cleanup"] = _close_group(proc)
                    finally:
                        receipt["elapsed_seconds"] = time.monotonic() - started
                        # Every terminal path validates/removes the owned report, including
                        # cancellation and failed cleanup. Those states never become T0.
                        if report.exists() or report.is_symlink():
                            try:
                                receipt["report"] = _observed_report(
                                    report,
                                    baseline,
                                    quant,
                                    {"baseline": baseline_revision, "quant": quant_revision},
                                    receipt["native_exit_code"],
                                    max_new_tokens,
                                )
                                receipt["aggregate_validation"] = "validated"
                            except (OSError, RuntimeError, ValueError, TypeError):
                                if receipt["status"] == "completed":
                                    receipt["status"] = "invalid_aggregate_report"
                                receipt["aggregate_validation"] = "invalid_removed"
                                report.unlink()
                        elif receipt["status"] == "completed":
                            receipt["status"] = "missing_report"
                        receipt["resources_after"] = _resources(root)
            if receipt["cleanup"]["no_live_group_members_observed"] is False:
                receipt["status"] = "cleanup_failure"
                break
        ready = len(result["runs"]) == 3 and all(r["status"] == "completed" and r["report"] for r in result["runs"])
        if ready:
            try:
                t0 = within_hardware_identical([r["report"]["path"] for r in result["runs"]])
                # The T0 helper consumes/rechecks the actual sources itself. Ensure they
                # are still the buffers this receipt observed; no substitution can buy pass.
                if [s["report_sha256"] for s in t0["reports"]] != [r["report"]["sha256"] for r in result["runs"]]:
                    raise RuntimeError("T0 source bytes changed after child observation")
                result["t0"] = t0
                result["exit_code"] = 0 if t0["protocol_pass"] else 3
                result["status"] = "t0_agreement" if t0["protocol_pass"] else "t0_disagreement"
            except (OSError, RuntimeError):
                result["status"] = "t0_operational_refusal"
                (root / "t0.json").unlink(missing_ok=True)
        else:
            result["status"] = "native_operational_failure"
    except BaseException:
        result["status"] = "cancelled_or_operational_failure"
        raise
    finally:
        # Terminal cleanup includes a final check of current owned bytes, not merely
        # the earlier receipt. A source substituted during T0 can never leave raw data
        # or a positive standalone T0 artifact at handback. Valid negative aggregates
        # are retained with changed-byte provenance explicitly recorded.
        provenance_failed = False
        for receipt in result["runs"]:
            report = root / f"run-{receipt['index']}" / "report.json"
            previous = receipt["report"]
            if report.exists() or report.is_symlink():
                try:
                    final = _observed_report(
                        report,
                        baseline,
                        quant,
                        {"baseline": baseline_revision, "quant": quant_revision},
                        receipt["native_exit_code"],
                        max_new_tokens,
                    )
                    receipt["final_report"] = final
                    if previous is None or final["sha256"] != previous["sha256"]:
                        provenance_failed = True
                        receipt["source_bytes_changed"] = True
                except (OSError, RuntimeError, ValueError, TypeError):
                    report.unlink()
                    receipt["final_report"] = None
                    receipt["final_aggregate_validation"] = "invalid_removed"
                    provenance_failed = True
            elif previous is not None:
                receipt["final_report"] = None
                receipt["source_bytes_changed"] = True
                provenance_failed = True
        if provenance_failed:
            result["exit_code"] = 2
            result["status"] = "aggregate_provenance_failure"
            result["t0"] = None
        if result["t0"] is not None:
            (root / "t0.json").write_text(json.dumps(result["t0"], indent=2) + "\n", encoding="utf-8")
        else:
            (root / "t0.json").unlink(missing_ok=True)
        (root / "cold-run.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
