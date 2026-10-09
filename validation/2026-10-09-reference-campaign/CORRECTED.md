# Corrected campaign qualification

The corrected implementation is
`72c32123bc4d92dd081401d52f91ec614e06e3a9`. The initial `1f` records, original
synthetic examples and independent red remain unchanged; their passing suites
do not imply domain approval of the superseded controller.

The actual main-controller red (`terminal-red.xml`) has eight failures and five
passes over synthetic runtime facts. Interruptions/write failures immediately
after assessment, standalone T0 and final campaign metadata exposed the staging
defect. Corrected terminal tests have **42 passes**, including persistent failure
of every subsequent public write. Positive standalone T0/success metadata is
removed first; assessment eligibility becomes blocked and T0 unavailable for
qualification. Original native observations keep their genuine T0 result with an
explicit nonqualification marker. Failed marker writes withhold those public
copies. Exact validated negative reports/cards and private native originals
remain; no fake failure receipt is claimed when storage cannot write one.

Final corrected `corrected-unit.xml` has **1,816 passes, 32 skips**, from **1,848**
independently counted cases matching the pytest summary. Two SciPy properties,
exact CI Ruff/format/types and audit pass. Audit has zero errors and the same two
existing command-documentation warnings. `corrected-local-receipts.json` binds
the actual corrected source blobs, gates and these separate original/red/fix
counts. The `assess_reports` AST is unchanged from the initial fixture examples;
that equivalence does not claim native or hosted execution.

Exact commands are the initial README's gate invocations with `corrected-unit`,
`corrected-properties`, `corrected-{lint,format,mypy}` and `corrected-audit` output
filenames. Focused execution:

```powershell
tools/ci/.venv/Scripts/python.exe -m pytest tests/test_reference_campaign.py -q --junitxml=validation/2026-10-09-reference-campaign/terminal-persistent-fixed.xml
tools/ci/.venv/Scripts/python.exe validation/2026-10-09-reference-campaign/record-corrected.py
tools/ci/.venv/Scripts/python.exe validation/2026-10-09-reference-campaign/check-corrected-bytes.py
```

No new local packages, models, environments or worktrees. Windows/WSL limitations
and prior cleanup rejection remain unchanged. The actual hosted Phi4 campaign,
public aggregate upload/download proof and registry decision are still pending;
this source qualification is not the fifth PR's completed product outcome.
The delegated worktree/env stays **PRESERVE** for that execution and integration.

Subsequent independent review of exact `72c` found that direct report/card writes
could leave partial bytes in always-upload staging. The sanitized independent
receipt is `independent-partial-write-red.json`. The qualification above remains
historical local proof, not final domain approval. Atomic staging and its new
partial-write regressions will be qualified separately before dispatch.
