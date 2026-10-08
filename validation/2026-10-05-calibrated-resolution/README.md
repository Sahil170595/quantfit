# Offline calibrated-resolution functional acceptance

This is deliberately synthetic aggregate evidence. The fixture report, immutable
arm revision strings and calibration counts are fabricated for a bounded software
test; no completion, human label, model run or judge result is represented. The
actual CLI consumes these committed inputs, writes a separate analysis and rejects
a changed arm revision. Input-byte preservation and both SHA256 digests were
independently checked. Per-axis powers and binomial rejection thresholds are
cross-checked against SciPy in `tests/test_resolution.py`.

Host: Windows 11 x86_64, Python 3.12.13; an RTX 4080 Laptop GPU was present but not
used. `environment.json` records installed versions, source hashes and the locked
tooling manifest SHA256. Tooling was synchronized with uv 0.12.23 and the
unit/numerical/runtime/tooling groups from `tools/ci/uv.lock`.

Exact invocations from the candidate checkout using that pinned interpreter:

```powershell
python -m quantfit.cli resolution --report validation/2026-10-05-calibrated-resolution/drift.json --calibration-report validation/2026-10-05-calibrated-resolution/calibration.json --out validation/2026-10-05-calibrated-resolution/resolution.json --json
python -m quantfit.cli resolution --report validation/2026-10-05-calibrated-resolution/changed-scope.json --calibration-report validation/2026-10-05-calibrated-resolution/calibration.json --out validation/2026-10-05-calibrated-resolution/must-not-exist.json --json
python -m pytest tests -q --cov=quantfit --cov-branch --cov-report=term-missing --cov-report=json:coverage.json
python tools/ci_coverage.py coverage.json
python tools/ci_mutation.py
python -m quantfit.cli audit
ruff check quantfit tests tools
ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
mypy --strict quantfit/spec.py quantfit/engines/base.py
```

The first invocation exits 0 for completed analysis. The second exits 2 for a
scope mismatch and writes no output. These are operational exits, not safety
verdicts. `resolution.json` carries unverified model assumptions, per-arm
directional upper bounds, flagged counts and explicit measurability.

This run does not establish calibration label truth, applicability of error bounds
to an at-risk subpopulation, majority-real at-risk pairs, independent judge errors,
quantization sensitivity, GPU behavior, QSR v1 readiness, a research GO or any
claim about a real model's safety. The report/schema-v2 and QSR v0 definitions
remain unchanged. Historical validation records were not edited.

`test-summary.json` records final local suite/coverage results and separate
installed-wheel/rebuilt-sdist acceptance outside the checkout. Candidate packages
were installed into an isolated environment that borrowed the locked dependency
graph. The installed CLI wrote its output into a disposable directory and verified
the preserved input hash. Hosted CI performs independent runner installations.
