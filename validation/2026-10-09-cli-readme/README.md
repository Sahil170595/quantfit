# CLI README refresh — 2026-10-09

README source is frozen at `97d79d6b7c9511b308c8211bbb9356813d46892d`, based on
the reviewed feature source `9d59739645e5c0021aec8288b480ed2e9c5bea30` (#124).
Package code, tests, tools and workflows are unchanged. The README separates
published 0.16.0 from the open source stack, installs `[inspect,gguf]`, documents
cards/bundles/cold runs/managed Inspect/public candidate evidence and their limits,
and removes unsupported serving-command, quality and memory guarantees.

## Actual local results

Windows, reused Python 3.12.13 sparse CI environment; no new dependencies,
model downloads, environments, containers or worktrees. `local-gates.json` and
`unit.xml/log` record the initial frozen `ad95062` run: 1,818 passed and 32 skipped
(1,850 cases, independently counted). The remaining source changes are README
wording and required installation extras, reviewed at final `97d79d6`.

The root incorrectly included the Torch-only RTN property in this sparse
environment: original `properties.xml/log` retain **two passes and one
ModuleNotFoundError failure**. This is an environment execution failure, not a
passing gate. No test or numerical tolerance was changed. `supported-properties`
subsequently runs the two locally supported properties explicitly and passes;
the full Torch property and clean installed runtime remain hosted CI gates.

`final-local-gates.json` records the corrected exact-final-source qualification:
144 affected quickstart/audit tests pass, two supported numerical properties pass,
exact CI lint/format/types/audit pass. The syntax-only quickstart validates all
45 advertised commands and documents its unexecuted categories; no clean-runtime
execution is claimed locally. Full argparse additionally accepts all 29 fenced
quantfit examples, including required arguments. Independent review passes after
both the serving-example and missing-GGUF-extra findings were corrected.

`offline-functional.json` and five pairs of stdout/stderr files record actual
card rendering, bundle creation/verification, relocated T0 and reference listing
against the real hosted Phi4 source report. All consumer exits are zero; the
underlying model regression exit3 and unconfirmed flags remain intact. The source
report hash is bound to the already committed `2026-10-09-phi4-public-candidate`
producer bytes. Original producer T0 bytes are unchanged. No fresh calibration,
human adjudication, sensitivity, safety GO or new native run occurs here.

Exact invocations are recorded in the receipts and runner scripts. The scripts
preserve absolute original execution paths as provenance; use a new output
directory when repeating bundle creation. The initial runner intentionally remains
as the failed-attempt record; `run-corrected-gates.py` is the supported local route.
Full exact-head hosted qualification is recorded in the PR body/review and separate
hosted receipt, rather than rewriting these local run records.
