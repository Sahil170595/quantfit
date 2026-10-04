"""CI-only labels replacing inference, while the installed CLI/decision/JUnit run.

Never installed into the wheel. The action integration sets PYTHONPATH explicitly.
This establishes control propagation, not scientific detector sensitivity.
"""

import os

if "QUANTFIT_CI_CASE" in os.environ:
    import quantfit.safety.verify as sv

    def fixture_verify(baseline, quant, **kwargs):
        from quantfit import __version__
        from quantfit.safety.report import ArmRun, DriftReport

        code = int(os.environ["QUANTFIT_CI_CASE"])
        if code == 2:
            raise RuntimeError("CI fixture operational failure; no model was loaded")
        n = 12
        probes = [sv.Probe(f"CI placeholder {i}", "clear_unsafe", "unsafe") for i in range(n)]
        probes += [sv.Probe("CI safe placeholder", "clear_safe", "safe")]
        baseline_labels = [code != 4] * n + [False]
        quant_labels = ([False] * n if code in (3, 4) else [True] * n) + [False]
        drift = sv._tabulate(probes, baseline_labels, quant_labels)
        if kwargs.get("report_path"):
            arm = ArmRun("CI_LABEL_FIXTURE_NOT_A_MODEL", None, "fixture", 0.0, {"name": "fixture"}, None)
            DriftReport(
                2,
                __version__,
                "2026-10-04T00:00:00Z",
                {"kind": "CI fixture; no judge ran"},
                {"kind": "CI placeholders; no probes downloaded"},
                {},
                {"kind": "CI fixture"},
                arm,
                arm,
                0.0,
                drift.to_dict(),
            ).to_json(kwargs["report_path"])
        return drift

    sv.verify_safety = fixture_verify
