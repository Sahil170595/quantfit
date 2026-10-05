# T0 synthetic offline functional validation — 2026-10-05

This record verifies the standalone T0 command and consumption of its output. Every
input under `synthetic-reports/` is a constructed aggregate fixture. No model was
loaded, no judge ran, no weights were downloaded, and no person adjudicated any output.

The schema-v2 fixture pins (`a`/`c`/`d`/`e` repeated to digest length), model and dataset
IDs, engine version and environment strings are explicitly **synthetic**. Their shape
and equality are checked against the protocol; no claim is made that these digests
identify actual external content. The fixtures use the project's `_tabulate` primitive
to compute aggregates instead of reproducing its count/interval arithmetic by hand.

The first drift-only reading would accept mixed instrument settings, mixed environments
and cached baselines. The intended reading refuses them. The dated correction is in
`docs/cross-hardware-tolerance-v0.md` (2026-10-05); the failing regressions were observed
before implementation, and the current tests are in `tests/test_t0.py` and
`tests/test_reproduce.py`.

## Machine and pins

Executed on Windows CPU, Intel Core i9-13980HX (24 cores / 32 logical processors).
The borrowed coordinator-owned environment uses Python 3.12.13, pytest 9.0.3 and Ruff
0.16.2. `pins.json` records the observed OS, installed package versions, CI lock hash,
source base HEAD and SHA256s of the changed implementation/test files. Installed torch
is a CPU build; its presence does not turn fixture evaluation into model execution.
This is source-checkout validation, not installed-wheel or hosted-runner qualification.

## Exact invocations

Run from the repository root. On this machine `$py` was
`C:\tmp\quantfit-calibration-20261005\tools\ci\.venv\Scripts\python.exe`.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& $py validation/2026-10-05-t0-replicates/run_validation.py
& $py -m pytest -q -p no:cacheprovider --basetemp=C:\tmp\quantfit-t0-pytest-20261005 --junitxml=validation/2026-10-05-t0-replicates/full-suite.junit.xml
& $py -m ruff check quantfit tests tools
$taskRuffPaths = @('quantfit', 'tests') + @(Get-ChildItem tools\ci_*.py | ForEach-Object FullName) + @('tools/ci_gate_fixture')
& $py -m ruff format --check @taskRuffPaths
```

The generator's exact per-command argv and observed exits are in
`functional-results.json`. Its CLI subprocesses use `python -m quantfit.cli`; there is
no `quantfit.__main__` entry point. They run with the Hub offline and CUDA masked.
`*-stdout.json` stores each parsed stdout envelope; the requested `--out` files retain
the bare standalone artifact. Relative source paths are relative to the repository
root, which is also the working directory for consumption.

## Observed outcomes

| Synthetic case | Observed exit / state | Evidence |
|---|---|---|
| Three agreeing uncached reports | 0; `protocol_pass: true`; execution independence unverified | `agreement.json`, `agreement-stdout.json` |
| Same identity, one differing drift block | 3; `pass: false` | `disagreement.json`, `disagreement-stdout.json` |
| Cached baseline | 2; no output artifact | `cached-refusal-stdout.json` |
| Mixed judge or recorded environment | 2; no output artifact | `mixed-judge-refusal-stdout.json`, `mixed-environment-refusal-stdout.json` |
| Byte-identical copy or repeated path | 2; no output artifact | `byte-copy-refusal-stdout.json`, `repeated-path-refusal-stdout.json` |
| CLI with two reports | 2; no output artifact | `short-set-refusal-stdout.json` |
| Library with two agreeing reports | Agreement recorded; count requirement and `protocol_pass` false | `partial-library.json` |
| Standalone artifact consumed for two member reports | 0; bound to exact report bytes and identities | `bound-comparison.json` |
| Same-identity report whose bytes are absent from the T0 set | 3; `reproduced_t0_unverified` | `nonmember-comparison.json` |
| Legacy bare positive assertions | 3; `reproduced_t0_unverified` | `legacy-assertion-comparison.json` |
| Repository audit | 0; no findings, errors or warnings | `audit-stdout.json` |

The automated tests additionally exercise missing and floating pins, equal malformed
decode declarations, source changes after artifact creation, misreported source counts,
the existing report-list CLI invocation, legacy positive artifact ingestion, and a
successful subprocess with model backend imports blocked. `full-suite.junit.xml`
contains the repository-suite result: **1,442 passed, 1 skipped, 6 deselected**, exit 0.
The passed/skipped totals were independently counted from its 1,443 test cases;
`checks.json` retains that count and the JUnit hash. Both Ruff checks passed using
CI's exact scopes. The suite emitted the existing SWIG deprecation warnings.

## What this does not establish

This is not an independently executed three-replicate measurement campaign. Distinct
paths, hashes, timestamps and runtimes cannot prove separate executions. Identical
reported `env` objects cannot verify physical-host identity; schema-v2 `cpu` identifies
no CPU model, and a GPU model string identifies no unique host. Reports contain unsigned
provenance assertions. All new T0 artifacts record
`independent_execution_verified: false`.

The agreeing synthetic reports and the synthetic comparison's exit 0 establish CLI
and binding behavior only. They establish no model safety, quantization sensitivity,
judge calibration, new reference report, hardware causality, research GO, hosted-runner
success or installed-package acceptance. Historical validation records remain unchanged.

JSON artifacts were walked for keys matching `prompt|completion|response|text|generation`;
none occurred. No captures, labeling sheets/keys or baseline cache entries were committed.
