# Bound calibration functional validation, 2026-10-05

This record checks the schema-2 capture → key → calibration → gate path on synthetic
data. It is a software fixture, not a calibration study. All labels are manufactured
from fake judge flags; no human adjudication occurred. No real model or judge loaded.

The machine is Windows 11 AMD64, Intel Core i9-13980HX. The borrowed coordinator-owned
`tools/ci/.venv` uses the hash-locked tooling/runtime groups and uv 0.12.23; exact
installed versions and source hashes are in `receipt.json`. The scope inside the fixture
reports deliberately uses synthetic arm revisions (`a`/`b` repeated 40 times) and
fixture environment versions, distinct from the actual execution environment. Judge
and corpus metadata use the existing source constants to test scope parity; this run
did not fetch those assets or verify their contents upstream.

From the repository root in PowerShell:

```powershell
tools\ci\.venv\Scripts\python.exe validation/2026-10-05-calibration-binding/reproduce.py
tools\ci\.venv\Scripts\python.exe -m pytest tests -q --cov=quantfit --cov-branch --cov-report=json:coverage.json --junitxml=validation/2026-10-05-calibration-binding/pytest.xml
tools\ci\.venv\Scripts\python.exe tools/ci_coverage.py coverage.json
tools\ci\.venv\Scripts\python.exe tools/ci_mutation.py
tools\ci\.venv\Scripts\python.exe -m ruff check quantfit tests tools
tools\ci\.venv\Scripts\python.exe -m ruff format --check quantfit tests
tools\ci\.venv\Scripts\python.exe -m quantfit.cli audit --json
```

`calibration.json` and `drift.json` are aggregates from the real producer functions
under fixture generation/judging. Each arm has 40 usable manufactured labels and zero
directional errors. Their refusal denominators differ, so their directional Wilson
maxima differ; `receipt.json` records a second derivation using `wilson_interval`.
`gate.json` records the expected smoke-tier refusal (exit 5) on the shipped 40-probe
scope, before a new run. Its status is `scope_validated_actual_run_unobserved`; it
does not claim observed weights matched. `eps.measured` stays false.
The decision also names A1/A2/A3 and keeps `eps.assumptions_verified` false; matching
scope does not prove that the labeled rates apply to the at-risk subpopulation or that
the majority-real and conditional independence assumptions hold.
Regression checks substitute capture/key/sheet files after parsing and verify that
source hashes still describe the parsed snapshots. Synthetic observed-HF metadata checks
also retain causal precision/revision/tokenizer/backend facts while excluding timing;
missing/contradictory observations and operator aliases are refused.
The public-report substitution regression presents the same counts with matching metadata
while the actual private report has different weights; it is refused. Matching private
reports are published only after verification. Calibration/output aliases are refused,
including hardlinks, without modifying input bytes.

`widened-fixture-*.json` exercise the proceeding-run path on a deliberately widened
2000-probe synthetic corpus, 1500 expected-unsafe. The existing decision primitives
produce a matched conditional gate pass. Changing the observed quantized revision is
refused; the error is in `receipt.json`. These files are marked as synthetic and do not
describe the shipped corpus or change any real protocol. Their source digest placeholders
are test data, not evidence that a human labeling study exists.

Only aggregates are committed. Raw capture, sheet, key and temporary run reports are
removed by the reproduction script. JUnit records regression checks. This record
establishes no human error rate, truthful labels, independent judge error, real backend
precision/revision correctness, GPU qualification, sensitivity result or research GO.
Hosted checks and installed-package acceptance are separate evidence.

Final local checks passed: **1474 tests**, one skipped and six deselected; exact CI Ruff
scopes; documentation audit with zero findings; all three selected CI decision mutants
killed. `checks.json` records the JUnit-derived count and coverage floors. The actual CLI
process also returned exit 5; its aggregate JSON envelope is `cli-envelope.json`.
The standalone binding test module is now included in hosted installed-wheel and rebuilt
sdist qualification outside the checkout; that hosted proof remains pending publication
of this branch.
