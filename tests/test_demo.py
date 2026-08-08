"""`verify-safety --demo` — a real verdict in seconds, that cannot pass for a measurement.

Two things are being protected, and they pull in opposite directions:

1. **It must be real.** The demo calls `safety.verify._tabulate`, the same function a live
   run uses. If it drifted into a second implementation of the statistics it would become
   the divergence channel the spec exists to prevent, and a demo that printed made-up
   numbers would be worse than no demo.
2. **It must be unmistakable.** Nothing it produces may be confusable with a measurement:
   not the text, not the payload, not an artifact on disk, and not the exit code.

The second is the one that needs teeth, because it is the one that erodes quietly.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from quantfit.safety.demo import DEMO_VERDICT_PREFIX, demo_drift, demo_probes, demo_summary
from quantfit.safety.verify import EXPECTED_SAFE, EXPECTED_UNSAFE, _tabulate

_ROOT = Path(__file__).resolve().parent.parent
_ENV = dict(os.environ, PYTHONIOENCODING="utf-8", CUDA_VISIBLE_DEVICES="-1")


def _run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "quantfit.cli", *argv],
        capture_output=True,
        cwd=str(_ROOT),
        env=_ENV,
        check=False,
        timeout=300,
    )


# --------------------------------------------------------------------------------
# It is real
# --------------------------------------------------------------------------------


def test_the_demo_runs_the_same_tabulation_a_real_run_does():
    """Not a lookalike: the drift object is built by `_tabulate` from probes and flags."""
    drift = demo_drift()
    probes = demo_probes()
    baseline = [True, True, True, True, True, True, False, True, False, False, False, True]
    quant = [True, True, False, True, False, True, False, True, False, True, False, True]
    assert drift == _tabulate(probes, baseline, quant), (
        "the demo's numbers must come from the shipped tabulation, not from a second copy of it"
    )


def test_the_demo_statistics_are_genuinely_computed():
    """At-risk denominators, not raw counts — the distinction the whole spec turns on."""
    drift = demo_drift()
    # 8 expected-unsafe probes, 7 with the baseline refusing => 7 at-risk, 2 flips.
    assert drift.unsafe_n == 8
    assert drift.dangerous_at_risk == 7
    assert drift.harmful_compliance_regressions == 2
    # 4 expected-safe, 3 with the baseline complying => 3 at-risk, 1 flip.
    assert drift.safe_n == 4
    assert drift.overrefusal_at_risk == 3
    assert drift.overrefusal_regressions == 1


def test_the_fixture_shows_a_finding_not_a_clean_run():
    """A no-detection demo teaches the output shape but not the shape of a finding."""
    assert demo_drift().regression_detected is True


# --------------------------------------------------------------------------------
# It cannot pass for a measurement
# --------------------------------------------------------------------------------


def test_no_probe_prompt_is_real_text():
    """Shipping the curated expected-unsafe corpus in the wheel to prettify a demo would
    put harmful text in every install, for a convenience feature."""
    for probe in demo_probes():
        assert probe.prompt.startswith("<demo placeholder probe"), probe.prompt
        assert probe.expected in (EXPECTED_UNSAFE, EXPECTED_SAFE)


def test_every_rendering_says_it_is_a_demonstration():
    drift = demo_drift()
    summary = demo_summary(drift)
    assert summary.startswith(DEMO_VERDICT_PREFIX)
    assert "not a measurement" in summary
    assert "No model was loaded" in summary


def test_the_cli_demo_exits_zero_despite_showing_a_regression():
    """The fixture contains a regression; exit 3 would be a verdict about a model, and no
    model ran. The banner carries the finding, the exit code carries the truth."""
    result = _run("verify-safety", "--demo")
    assert result.returncode == 0
    out = result.stdout.decode("utf-8", "replace")
    assert DEMO_VERDICT_PREFIX in out
    assert "REGRESSION DETECTED" in out, "the demo should show what a finding looks like"


def test_the_demo_refuses_to_write_an_artifact():
    """An artifact indistinguishable from a real report is the one thing this must not make."""
    for flag in ("--report", "--capture"):
        result = _run("verify-safety", "--demo", flag, "demo-artifact.json")
        assert result.returncode == 2, flag
        message = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
        assert "cannot be combined" in message, flag
        assert not (_ROOT / "demo-artifact.json").exists(), "the refusal must precede any write"


def test_the_demo_payload_is_flagged_under_json():
    result = _run("verify-safety", "--demo", "--json")
    document = json.loads(result.stdout.decode("utf-8", "replace"))
    assert document["exit_code"] == 0
    assert document["result"]["demo"] is True
    assert document["result"]["measured"] is False, (
        "a consumer branching on this field is the reason it exists; 'demo' alone could be "
        "read as a mode rather than as 'nothing was measured'"
    )
    assert "No model was loaded" in document["result"]["note"]


def test_a_real_run_still_requires_both_arms():
    """Making the arms non-required for --demo must not make them optional in general."""
    result = _run("verify-safety")
    assert result.returncode == 2
    message = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
    assert "--baseline and --quant" in message
    assert "--demo" in message, "the error should name the way to see output without a model"


def test_the_demo_needs_no_network_no_gpu_and_no_weights():
    """The whole point. Runs with CUDA masked and no Hub credentials, in seconds."""
    env = dict(_ENV, HF_HUB_OFFLINE="1", HF_TOKEN="", NO_NETWORK="1")
    result = subprocess.run(
        [sys.executable, "-m", "quantfit.cli", "verify-safety", "--demo"],
        capture_output=True,
        cwd=str(_ROOT),
        env=env,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0
    assert DEMO_VERDICT_PREFIX in result.stdout.decode("utf-8", "replace")
