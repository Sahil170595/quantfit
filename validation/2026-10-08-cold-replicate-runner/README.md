# Cold native replicate runner — functional record

This is **synthetic functional orchestration evidence**, not a model measurement.
The production cold runner, native CLI children, POSIX sessions, file hashing and
existing T0 execute. A narrowly scoped temporary `sitecustomize.py` substitutes
fixture aggregates for `verify_safety`; no model, Hub weights or llama-server runs.
The synthetic source fixture is the unchanged Quant1 `drift.json` from commit
`61eb4e1b36a4231231291d7f7012b8916694f02a`, SHA256
`20d75c66875de2c6461de1534cbc9520f0a7dd1ba23c270fc00e4f4cd2ce5eaa`.
Fixture labels, revisions, artifact and executable hashes are declarations, never
authenticated observations or human confirmation. No source protocol is patched.

Implementation: `e8bfc0e1a5798b5bf2e17ed9e18b5ec6ec7f9491`.
`receipts.json` records actual installed Windows versions/hardware, raw consumed
source hashes, canonical Gitblob hashes and verified CRLF-to-LF source equivalence.
Windows autocrlf preserves CRLF in some legacy working sources; these runs are
explicitly **not** labelled as exact Gitblob-byte launches. New JSON evidence has
its own narrow `.gitattributes -text` rule; its actual raw bytes match Git blobs.
`byte-check.py` checks that equality and the emitted report/T0 member hashes.
Older validation records are unchanged.

The full available suite started while actual HEAD was `3f1de493` with the final
working implementation and finished after the source commit. There was no semantic
implementation change during it. **1696 passed, 29 skipped**, independently counted
from 1725 XML cases (`unit-final.xml`); `unit-final.log` reports the same counts.
Sixteen new skips are POSIX-only orchestration tests on Windows, exercised separately
on the already-installed Ubuntu WSL Python3.12.3 / pytest8.4.2 / psutil5.9.8:
**17 passed**, zero skipped (`wsl-final-qualified.xml`). Remaining13 skips are inherited
optional/platform cases. Fifteen parameterized SciPy oracle checks and two numerical
Hypothesis/SciPy properties passed. The Torch RTN property is explicitly unrun locally.
Ruff exact CI check/format paths, exact mypy paths and audit exit0 passed; audit retains
its existing2 warnings. No package installs, model downloads or new environments.

From `C:\tmp\qf-release-0.16.0-20261008`, with `PYTHONDONTWRITEBYTECODE=1`:

```powershell
tools/ci/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-08-cold-replicate-runner/unit-final.xml
tools/ci/.venv/Scripts/python.exe -m pytest tests/test_stats_scipy.py -q --junitxml=validation/2026-10-08-cold-replicate-runner/scipy.xml
tools/ci/.venv/Scripts/python.exe -m pytest tests/test_numerical_properties.py -q -k 'not rtn' --junitxml=validation/2026-10-08-cold-replicate-runner/properties.xml
tools/ci/.venv/Scripts/python.exe -m ruff check quantfit tests tools
tools/ci/.venv/Scripts/python.exe -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
tools/ci/.venv/Scripts/python.exe -m mypy --strict quantfit/spec.py quantfit/engines/base.py
tools/ci/.venv/Scripts/python.exe -m quantfit.cli audit --json
wsl.exe -d Ubuntu --cd /mnt/c/tmp/qf-release-0.16.0-20261008 -- python3 -B -m pytest tests/test_cold_run.py -q -p no:cacheprovider --junitxml=validation/2026-10-08-cold-replicate-runner/wsl-final-qualified.xml
wsl.exe -d Ubuntu --cd /mnt/c/tmp/qf-release-0.16.0-20261008 -- python3 -B validation/2026-10-08-cold-replicate-runner/run-functional.py --source-head e8bfc0e1a5798b5bf2e17ed9e18b5ec6ec7f9491
tools/ci/.venv/Scripts/python.exe validation/2026-10-08-cold-replicate-runner/record-receipts.py
tools/ci/.venv/Scripts/python.exe validation/2026-10-08-cold-replicate-runner/byte-check.py
```

`functional-proof.json` records **9 actual outer CLI calls**, each with3 fresh native
children. Native exits `[3,3,3]`, `[0,0,0]` and `[4,4,4]` remain separate from T0.
One coherent drift disagreement exits3; native operational failure, real timeout,
different binary/thread claims and quantized baseline each exit2. All nine sets show
direct children waited/reaped and no live owned group members observed. Grandchild
reaping is not established; transient shim/server directories closed. No raw child
stdout/stderr or generated output is retained. Source/substitution/cancellation
regressions run in WSL pytest; cleanup failure is a labelled control-flow injection
after actual cleanup, not a claim that a live process escaped in this validation.

Red and intermediate evidence remains distinct: revision implementation initially
failed9 new tests; missing cold CLI failed its first test; initial WSL fixtures failed
identity/count validation; pair admission failed3 regressions; terminal raw hygiene
failed2; post-T0 raw substitution failed1. Initial full unit failed only the psutil
metadata access premise; switching to installed-package metadata preserved the one
runtime API assertion. Initial exact format failed on a source line-ending issue;
Ruff correction yielded no Git content delta. The penultimate WSL suite's one failure
was the expected status becoming the more precise `aggregate_provenance_failure`;
the final assertion also verifies valid changed negative bytes are preserved. Initial
and intermediate logs/XML are historical observations, not final qualification.

No sensitivity proof, human adjudication, GPU/crosshardware measurement, physical-host
authentication, independent reproduction or scientific GO is established. QSRv1
remains unfrozen. Hosted full numerical/coverage/mutation matrices and installed
consumer execution remain pending batch push. Real installed default64/full40 cold
model execution must qualify unchanged canonical Quant3 measurement source blobs,
either in the later reference campaign or its own exact-head hosted consumer if a
later feature changes those blobs. No public HF dataset was created or uploaded.

**PRESERVE:** shared worktree and approved environment stay under sequential batch
review with local unpublished refs. Prior blocked dependency/cache cleanup is not
retried. No task-owned native child remains live; no new dependencies, worktrees,
model copies or containers were created. Final handback supplies exact HEAD/tree.
