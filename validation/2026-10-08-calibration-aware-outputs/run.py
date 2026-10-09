"""Record synthetic source/real-Bash acceptance; never download models or publish data."""

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
from test_action_calibration import action_reader, action_shell  # noqa: E402

from quantfit.cli import main  # noqa: E402
from quantfit.modelcard import model_card_fragment  # noqa: E402


def record():
    commands = []
    (OUT / "model-card.md").write_text(
        model_card_fragment(str(OUT / "drift.json"), calibration_report=str(OUT / "calibration.json")), encoding="utf-8"
    )
    (OUT / "original-model-card.md").write_text(model_card_fragment(str(OUT / "drift.json")), encoding="utf-8")
    argv = [
        "resolution",
        "--report",
        str(OUT / "drift.json"),
        "--calibration-report",
        str(OUT / "calibration.json"),
        "--out",
        str(OUT / "resolution.json"),
        "--json",
    ]
    assert main(argv) == 0
    commands.append({"argv": [sys.executable, "-m", "quantfit.cli", *argv], "exit_code": 0})
    bash = shutil.which("bash") if os.name != "nt" else r"C:\Program Files\Git\bin\bash.exe"
    for name, expected, calibration, template in (
        ("pre-run", 5, "calibration.json", ""),
        ("observed", 0, "action-calibration.json", str(OUT / "action-drift.json")),
    ):
        case = OUT / name
        case.mkdir(exist_ok=True)
        for path in (case / "run-outputs.txt", case / "outputs.txt", case / "summary.md"):
            path.write_text("", encoding="utf-8")
        env = dict(os.environ)
        env.update(
            PATH=os.pathsep.join((str(Path(sys.executable).parent), env["PATH"])),
            PYTHONPATH=os.pathsep.join((str(ROOT), str(ROOT / "tools/ci_gate_fixture"))),
            QUANTFIT_CI_CASE=str(expected),
            QUANTFIT_CI_BOUND_REPORT=template,
            BASELINE="base",
            QUANT="quant",
            TIER="",
            THRESHOLD_PP="30",
            EPS_UPPER="",
            EPS_SOURCE="",
            CALIBRATION_REPORT=str(OUT / calibration),
            MAX_NEW_TOKENS="",
            HF_TOKEN="",
            REPORT=str(case / "drift.json"),
            GATE_OUT=str(case / "gate.json"),
            JUNIT=str(case / "junit.xml"),
            GITHUB_OUTPUT=str(case / "run-outputs.txt"),
        )
        for step in (
            "Validate inputs",
            "Preflight — the installed quantfit must expose the gate contract",
            "Run quantfit gate",
        ):
            completed = subprocess.run(
                [bash, "-s"],
                input=action_shell(step),
                env=env,
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            (case / (step.split(" —")[0].replace(" ", "-") + ".log")).write_text(
                completed.stdout + completed.stderr, encoding="utf-8"
            )
            assert completed.returncode == 0, (step, completed.stdout, completed.stderr)
            commands.append(
                {
                    "step": step,
                    "source": ".github/actions/quantfit-gate/action.yml",
                    "case": name,
                    "env": {
                        k: env[k]
                        for k in (
                            "QUANTFIT_CI_CASE",
                            "QUANTFIT_CI_BOUND_REPORT",
                            "BASELINE",
                            "QUANT",
                            "CALIBRATION_REPORT",
                        )
                    },
                    "exit_code": completed.returncode,
                }
            )
        decision = json.loads((case / "gate.json").read_text(encoding="utf-8"))
        assert decision["exit_code"] == expected
        outputs, _ = action_reader(case, decision)
        assert outputs["actual-run-matched"] == ("true" if expected == 0 else "false")
        assert outputs["assumptions-verified"] == outputs["human-labels-verified"] == "false"
        assert outputs["calibration-sha256"] == hashlib.sha256((OUT / calibration).read_bytes()).hexdigest()
        (case / "outputs.json").write_text(json.dumps(outputs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    metadata = {
        "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu": platform.processor(),
            "logical_cpus": psutil.cpu_count(),
            "physical_cpus": psutil.cpu_count(logical=False),
            "ram_bytes": psutil.virtual_memory().total,
        },
        "versions": {
            p: importlib.metadata.version(p)
            for p in ("quantfit", "pytest", "ruff", "mypy", "inspect-ai", "huggingface-hub")
        },
        "commands": commands,
        "scope": "Synthetic source/real-Bash functional validation only. No models, human calibration, sensitivity, hosted candidate install, research GO or reference publication.",
    }
    (OUT / "run.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    record()
