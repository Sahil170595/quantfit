# Selected-axis screen requirements with supplied controls

[Aggregate evidence](functional.json) records Windows Python 3.13.1 runs of the
0.67.0 editable source package. The `qualified()` fixture in
`tests/test_screen_control_calibration.py` supplies fictional reports, scopes,
calibrations, and a supplied control. These runs establish local receiving and
serialization behavior for that fixture. The evidence scope is synthetic CPU
receiving. Human-label authenticity, measurement independence, sensitivity,
scientific GO, and behavior of a real model remain unverified.

The five cases cover complete qualification, an unmet selected limit, native
flags, a missing calibration, and a missing original report. The receipt records
both exit codes, the original target count, control status, and SHA-256 hashes
of the full CLI JSON and JUnit files. The private fictional inputs and full
outputs are kept under the local evidence working directory.

Open the fixture and run its native CLI command with the following arguments.
Use `qualified(..., flagged=True)` for native flags,
`qualified(..., missing=("clean",))` for the missing calibration, and remove the
fixture's `reports/clean.json` for the missing original report. The declared
axis settings for each case are recorded in `functional.json`.

```powershell
quantfit screen-summary --targets $manifest --reports-dir $reports `
  --control-report $controlReport --control-capture $controlCapture `
  --control-adjudication $controlAdjudication --calibrations-dir $calibrations `
  --require-axis-conditional-resolution refusal-robustness=40 `
  --require-axis-conditional-resolution over-refusal=40 `
  --out $out --junit $junit --json
python -m pytest -q tests/test_screen_control_calibration.py tests/test_screen_control_evidence.py tests/test_screen_requirement.py
```
