# Portable aggregate bundles: actual synthetic functional validation

These are **synthetic fixture-derived aggregates**. No model generated completions,
no judge ran, no human labeled anything, and no publication occurred. The source
fixtures are the explicitly synthetic `2026-10-08-calibration-aware-outputs` record;
their bytes were copied, not reclassified as a fresh measurement. Counts and verdicts
remain declarations. Integrity and binding authenticate neither human labels nor
scientific claims.

Actual hardware for the final CLI run: Windows 11 build 26300, AMD64, Intel family 6
model 183, 24 physical/32 logical CPUs, 68,319,571,968 bytes RAM. CPython 3.12.13 is
the existing `tools/ci/.venv/Scripts/python.exe`; the process used no GPU. Package
versions and absent optional packages are recorded in `final-source/run.json`:
pytest 9.0.3, Ruff 0.16.2, mypy 1.20.2, SciPy 1.15.3, Inspect 0.3.269. Torch and
Transformers are absent. The inherited locked unit/tooling environment was reused;
no new dependency install or copy was made.

Latest producing source head: **`177f534f7dd0bfd7f5dc3da15a5c51ffb2d35393`**.
`review-fixes/` holds final **1684 passed, 13 skipped**, zero failures/errors,
the two available numerical properties and exact lint/format/type/audit passes.
`review-fixes/final-source/` is the actual final nine-command CLI replay. Each previous
run below keeps its original source/counts; none is promoted into final qualification.

The initial instrument implementation commit is `8848efb829249d5f6154c4acc07cfec3731f60b7`.
Its initial nine-command CLI record is at this directory's top level. Full unit
validation found missing agent/CLI inventory/flag matrix/quickstart integration;
`initial-unit-tests.log` and `.xml` preserve all four failures (1669 passed, 9 skipped).
The narrow surface and real Windows junction test fix is
`af498a2b55340c95e9ee845274946e25f13c9f87`. Its full gates and the independent
`final-source/` nine-command replay ran at that exact source head. No bundle, CLI,
resolution, calibration validator or installed bundle consumer changed between those
two source commits. Later review defects and corrected qualification are described below.

`red.log` and `red.xml` retain the earlier TDD red state: real floor/bound pre-run
gate-only creation was rejected by the still-required `--report` parser argument
(2 failures, 20 passes, one symlink skip). This was a working implementation state,
not qualification of either immutable source commit.

Exact PowerShell invocations, from `C:\tmp\qf-release-0.16.0-20261008`:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& tools/ci/.venv/Scripts/python.exe -m pytest tests/test_bundle.py -q --tb=short --junitxml=validation/2026-10-08-portable-evidence-bundles/red.xml
& tools/ci/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-08-portable-evidence-bundles/unit-tests.xml
& tools/ci/.venv/Scripts/python.exe -m pytest tests/test_numerical_properties.py -q -k 'not rtn' --junitxml=validation/2026-10-08-portable-evidence-bundles/local-numerical.xml
& tools/ci/.venv/Scripts/python.exe -m ruff check quantfit tests tools
& tools/ci/.venv/Scripts/python.exe -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
& tools/ci/.venv/Scripts/python.exe -m mypy --strict quantfit/spec.py quantfit/engines/base.py
& tools/ci/.venv/Scripts/python.exe -m quantfit.cli audit --json
& tools/ci/.venv/Scripts/python.exe validation/2026-10-08-portable-evidence-bundles/run.py
& tools/ci/.venv/Scripts/python.exe validation/2026-10-08-portable-evidence-bundles/run.py validation/2026-10-08-portable-evidence-bundles/final-source
```

The red command was run before its fix. The first full unit log/XML were moved to
`initial-unit-tests.*` after observing the four failures, before the successful rerun.
Other stdout/stderr is preserved in the correspondingly named logs/JSON. `run.py`
writes into a prepared new record directory; its exact subprocess argv, cwd, expected
and observed exits are in each `run.json`. It performs real CLI resolution, bound
pre-run exit 5, four-role bundle create/relocate/verify, gate-only create/relocate/verify,
tampered-byte exit 3, unsafe-path exit 2 and renamed-raw-role exit 2. Included report
statistics and original negative/unmeasurable flags remain unchanged. The requested
pre-run report destination was never written or treated as observed.

The pre-review `af498a2` unit result was **1678 passed, 9 skipped**, zero failures/errors. The
independent XML record contains 1687 cases and independently agrees with the suite
totals. Eight skips are inherited missing optional runtime/dependency cases; the new
skip is lack of Windows symbolic-link privilege. A **real Windows junction** source
and output-parent refusal test passes; POSIX symlink execution remains for hosted
Linux. Two available independent SciPy/Hypothesis numerical properties pass; the
Torch RTN property was deselected because Torch is absent. Exact CI lint, format,
strict type paths and repository audit all exit 0. `proof.json` records independent
case counts, skip reasons and producing source hashes.

`tools/ci_installed.py` now creates a four-role aggregate bundle from committed
fixtures, including the original native pre-run gate and its matching calibration,
with the installed candidate, relocates it, verifies member hashes and unchanged
declarations outside the checkout, then checks tampering exits 3. It also creates,
relocates and verifies a gate-only bundle with that same native gate/calibration,
asserting gate exit 5, actual-run match false and scientific claims false. That
consumer is implemented but **not locally run as installed-wheel qualification**.
Full hosted numerical/coverage/mutation/runtime, Linux symlink, installed wheel/sdist
and real model acceptance remain pending until the five-PR stack is pushed.

The new dated directory's JSON has a narrow `-text` attribute before artifact creation.
`byte-provenance.json` preserves the pre-review staged-byte inventory;
`review-fixes/byte-provenance.json` is the final staged inventory. They compare blob
and working bytes, and check each honest
relocated manifest's member hashes against those actual committed candidate bytes.
The deliberately tampered/unsafe bundles remain negative cases. No older validation
record was edited or renormalized.

Independent review demonstrated two P2 defects at `af498a2`: a real POSIX FIFO blocked
before the post-open type check, and edited conditional epsilon definition/statement
could contradict the false human/assumption flags. The actual sanitized red receipts
are `root-fifo-red.json` and `independent-bound-claims-red.json`; four TDD claim failures
are in `review-fixes/claims-red.*`. Commit `5a4b2eadb5f74a380ce53d997a6ffb93ed6f7889`
checks the regular-file type before open, uses supported `O_NONBLOCK` where available,
and validates the canonical epsilon definition/stage statement through shared existing
wording. Native gate epsilon/statement bytes are unchanged. Commit
`0b4df9c3a8e97a35c84034c76df2e96b9b50e03a` completes the installed native four-role and
gate-only consumers. Its qualification (1682 passes, 13 skips) is preserved under
`review-fixes/0b4df9c/` and is superseded by the final source head.

A sibling message/headline substitution reproduced at `0b4df9c`; two actual red
failures are in `review-fixes/message-red.*`. Commit `177f534` validates canonical
gate messages using the existing refusal/verdict renderers and a factored, byte-identical
exit-4 renderer. `review-fixes/claims-corrected.json` records original native preflight
acceptance, all three wording corruptions refused, unchanged native epsilon/statement
bytes, unchanged refusal/verdict function ASTs and exact old/new exit-4 message bytes.
Observed corruption tests use an explicitly widened synthetic fixture corpus; that
patch is confined to test code and is never admitted as a production protocol run.

`review-fixes/fifo-corrected.json` records four **real WSL Ubuntu/Python 3.12.3**
POSIX cases: FIFO source, member, manifest, and replacement after the regular-file
precheck. Each real CLI child exits 2 within the five-second timeout, is reaped, and
the owned temporary directory is removed. No dependencies were installed. Invocation:

```powershell
$candidateHead = git rev-parse HEAD
wsl.exe --exec python3 -B /mnt/c/tmp/qf-release-0.16.0-20261008/validation/2026-10-08-portable-evidence-bundles/fifo_probe.py $candidateHead
& tools/ci/.venv/Scripts/python.exe validation/2026-10-08-portable-evidence-bundles/run.py validation/2026-10-08-portable-evidence-bundles/review-fixes/final-source
```

The first FIFO probe's four child checks completed but receipt generation then failed:
native WSL Git cannot interpret this worktree's Windows-absolute gitdir. The corrected
receipt explicitly receives the source head from **Windows Git**, rather than claiming
WSL Git observed it, and records the actual bundle source-file SHA-256. This required
no worktree/credential/dependency repair. Final unit skips are the previous nine plus
four Windows `os.mkfifo`-unavailable cases; those four are actually exercised through
the WSL probe. Final full-gate invocations are the commands above with outputs under
`review-fixes/`; producing head/counts/individual skip reasons are in
`review-fixes/proof.json`. Both red records and earlier passing records remain intact.

This establishes offline functional format/relationship/byte checks over synthetic
aggregates. It establishes no safety verdict, sensitivity result, truthful human
calibration, A1/A2/A3 validity, research GO, T0, cross-hardware tolerance, qualified
reference admission, independent reproduction, authenticated manifest origin, or
QSR v1 freeze. A manifest and matching content can both be edited; integrity is not
a signature. No raw completion captures, label sheets, baseline cache payloads or
model weights are present.
