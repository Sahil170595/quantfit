"""Regenerate aggregate-only, synthetic T0 functional evidence from repository root."""

import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
os.environ.update(PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", CUDA_VISIBLE_DEVICES="-1")

from quantfit import __version__
from quantfit.reproduce import compare, within_hardware_identical
from quantfit.safety.report import ArmRun, DriftReport
from quantfit.safety.verify import Probe, _tabulate

HERE = Path("validation/2026-10-05-t0-replicates")
INPUTS = HERE / "synthetic-reports"
INPUTS.mkdir(parents=True, exist_ok=True)


def write(name, payload):
    path = HERE / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return path.as_posix()


def run(label, argv, expected):
    command = [sys.executable, "-m", "quantfit.cli", *argv, "--json"]
    process = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", check=False, cwd=ROOT, timeout=120
    )
    document = json.loads(process.stdout)
    assert document["exit_code"] == process.returncode == expected, (label, process.stdout, process.stderr)
    assert not process.stderr, (label, process.stderr)
    stdout_path = write(f"{label}-stdout.json", document)
    return {"case": label, "argv": command, "exit_code": process.returncode, "stdout": stdout_path}


probes = [Probe(str(i), "clear_unsafe", "unsafe") for i in range(12)]
probes += [Probe(str(i + 12), "clear_safe", "safe") for i in range(12)]
probes += [Probe(str(i + 24), "borderline", "safe") for i in range(16)]
baseline = [True] * 12 + [False] * 28
engine = {"name": "transformers", "version": "synthetic-offline-engine", "device": "cpu"}
environment = {
    "python": "synthetic-python",
    "torch": "synthetic-torch",
    "transformers": "synthetic-transformers",
    "cuda": None,
    "device": "synthetic-host",
}
paths = []
for i in range(3):
    path = INPUTS / f"replicate-{i + 1}.json"
    report = DriftReport(
        schema_version=2,
        quantfit_version=__version__,
        created_utc=f"2026-10-05T00:00:0{i}+00:00",
        judge={"id": "synthetic/offline-judge", "revision": "c" * 40, "input_contract": "completion-only"},
        probe_dataset={"id": "synthetic/offline-probes", "revision": "d" * 40, "split": "train", "n_probes": 40},
        decode={
            "max_new_tokens": 64,
            "do_sample": False,
            "chat_template": "model-default when present, raw prompt otherwise",
        },
        env=environment,
        baseline=ArmRun(
            model="synthetic/baseline",
            revision="a" * 40,
            resolved_dtype="torch.float16",
            runtime_s=float(i + 1),
            engine=engine,
            artifact_sha256=None,
        ),
        quantized=ArmRun(
            model="synthetic/quantized",
            revision="e" * 40,
            resolved_dtype="torch.float16",
            runtime_s=float(i + 2),
            engine=engine,
            artifact_sha256=None,
        ),
        judge_runtime_s=float(i + 3),
        drift=_tabulate(probes, baseline, baseline).to_dict(),
    )
    report.to_json(str(path))
    paths.append(path.as_posix())

seed = json.loads(Path(paths[-1]).read_text(encoding="utf-8"))
different = copy.deepcopy(seed)
quant = baseline.copy()
quant[12] = True
different["drift"] = _tabulate(probes, baseline, quant).to_dict()
different_path = write("synthetic-reports/disagreement.json", different)
cached = copy.deepcopy(seed)
cached["baseline"]["engine"]["baseline_cache"] = {"served": True, "fingerprint": "f" * 64}
cached_path = write("synthetic-reports/cached.json", cached)
mixed = copy.deepcopy(seed)
mixed["judge"]["revision"] = "f" * 40
mixed_path = write("synthetic-reports/mixed-judge.json", mixed)
other_environment = copy.deepcopy(seed)
other_environment["env"]["device"] = "synthetic-other-host"
other_environment_path = write("synthetic-reports/mixed-environment.json", other_environment)
copy_path = INPUTS / "identical-copy.json"
copy_path.write_bytes(Path(paths[0]).read_bytes())
nonmember = copy.deepcopy(seed)
nonmember["created_utc"] = "2026-10-05T01:00:00+00:00"
nonmember_path = write("synthetic-reports/nonmember-same-identity.json", nonmember)

agreement = (HERE / "agreement.json").as_posix()
cases = [run("agreement", ["t0", "--reports", *paths, "--out", agreement], 0)]
cases.append(
    run(
        "disagreement",
        ["t0", "--reports", *paths[:2], different_path, "--out", (HERE / "disagreement.json").as_posix()],
        3,
    )
)
for label, variant in (
    ("cached-refusal", cached_path),
    ("mixed-judge-refusal", mixed_path),
    ("mixed-environment-refusal", other_environment_path),
    ("byte-copy-refusal", copy_path.as_posix()),
    ("repeated-path-refusal", paths[0]),
):
    cases.append(run(label, ["t0", "--reports", *paths[:2], variant, "--out", (HERE / f"{label}.json").as_posix()], 2))
    assert not (HERE / f"{label}.json").exists()
cases.append(
    run("short-set-refusal", ["t0", "--reports", *paths[:2], "--out", (HERE / "short-set.json").as_posix()], 2)
)
assert not (HERE / "short-set.json").exists()
partial = within_hardware_identical(paths[:2], out_path=(HERE / "partial-library.json").as_posix())
assert partial["pass"] is True and partial["protocol_pass"] is False
cases.append(
    run(
        "bound-comparison",
        [
            "reproduce",
            "--reference",
            paths[0],
            "--candidate",
            paths[1],
            "--t0-reference",
            agreement,
            "--t0-candidate",
            agreement,
            "--out",
            (HERE / "bound-comparison.json").as_posix(),
        ],
        0,
    )
)
cases.append(
    run(
        "nonmember-comparison",
        [
            "reproduce",
            "--reference",
            nonmember_path,
            "--candidate",
            paths[1],
            "--t0-reference",
            agreement,
            "--t0-candidate",
            agreement,
            "--out",
            (HERE / "nonmember-comparison.json").as_posix(),
        ],
        3,
    )
)
legacy = compare(
    paths[0],
    paths[1],
    t0_reference=True,
    t0_candidate=True,
    out_path=(HERE / "legacy-assertion-comparison.json").as_posix(),
)
assert legacy["outcome"] == "reproduced_t0_unverified" and legacy["exit_code"] == 3
cases.append(run("audit", ["audit"], 0))

cpu = subprocess.run(
    [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors | ConvertTo-Json -Compress",
    ],
    capture_output=True,
    text=True,
    check=True,
)
write(
    "pins.json",
    {
        "validation_type": "synthetic offline functional validation; no model/judge execution",
        "quantfit_version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu": json.loads(cpu.stdout),
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("pytest", "ruff", "torch", "transformers", "llmcompressor", "inspect-ai", "gguf", "psutil")
        },
        "ci_lock_sha256": hashlib.sha256((ROOT / "tools/ci/uv.lock").read_bytes()).hexdigest(),
        "source_base_head_at_run": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip(),
        "source_files_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "quantfit/cli.py",
                "quantfit/reproduce.py",
                "tests/test_t0.py",
                "tests/test_reproduce.py",
                "tests/test_json_envelope.py",
            )
        },
        "fixture_scope": "Hash-shaped judge/dataset/model pins and fixture environment strings are synthetic, not verified external content or actual inference hardware.",
    },
)
write(
    "functional-results.json",
    {
        "cases": cases,
        "partial_library": {
            key: partial[key]
            for key in (
                "n_replicates",
                "pass",
                "meets_protocol_replicate_count",
                "protocol_pass",
                "independent_execution_verified",
            )
        },
        "legacy_positive_assertions": {key: legacy[key] for key in ("outcome", "exit_code")},
        "independent_execution_verified": False,
        "physical_host_verified": False,
    },
)
print(
    json.dumps(
        {
            "functional_cases": len(cases),
            "case_exits": {case["case"]: case["exit_code"] for case in cases},
            "partial_protocol_pass": partial["protocol_pass"],
        },
        indent=2,
    )
)
