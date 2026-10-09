# Inspect GGUF qualification — 2026-10-09

The final implementation is `6bf34b4ed80b076bb647ad23bc4b859f063d0ebf`.
`receipts.json` records its actual consumed working/source Gitblob hashes,
independently counted XML results, installed versions and hardware. Windows
PowerShell/Python3.12.13 on an i9-13980HX was used with the existing locked
`tools/ci/.venv`; no dependencies, weights or runtime copies were installed.
CRLF working source bytes and canonical LF blobs have separate SHA256 values;
only their exact EOL equivalence is asserted. New JSON evidence is protected by
the directory-specific `-text` rule and checked against actual Gitblob bytes.
No historical validation file was changed.

`qualified-synthetic/` is an actual public Inspect0.3.269/quantfit CLI execution
over declared synthetic files, server facts and judge flags. It runs all40
fixture probes, observes40public SDK calls per arm, closes both fake servers
before one80-label fixture batch, retains a dangerous-axis flagged regression
(exit3), emits matched bound conditional resolution and verifies a three-role
bundle. Binding/integrity success retains human/assumption verification false.
Native requests/models loaded are **zero**. GGUF architecture/dtype, served
metadata, RAM, CPU execution, process cleanup and protocol dataset membership
in these examples are declared fixtures, never actual backend observations.
`--max-new-tokens` is omitted in that synthetic invocation and resolves to64.

The real installed wheel entrypoint/full40/explicit64/real80-label judge consumer
is `tools/ci_inspect_gguf_acceptance.py` in the hosted `cpu-inspect` GGUF matrix.
It uses the pinned small SmolLM2 source and converter, actual packed GGUFs,
actual file/executable hashes and CPU argv; it asserts both owned native
processes are terminated/reaped **at real judge entry**, and qualifies outside
the checkout. It is configured, **not locally run**. The new synthetic stdlib
HTTP cancellation test actually owns a POSIX session/socket on hosted Linux;
Windows skips it. It proves process/socket control rather than model behavior.
Global WSL remains unrun after the previously recorded sharing violations;
no launch, repair, shutdown or disk dismount was attempted here.

Failed evidence stays visible. `red.xml` records13 missing-extension errors;
early focused harness corrections have their own logs/XML. The stop-reason red
shows missing metadata incorrectly labelled clean stop, followed by public
limit/unknown mapping tests. `managed-default-red.*` shows public `qsr_eval`
omitting GGUF slots bypassed closure before judging; explicit and omitted local
calls now use the managed route. Report-alias reds use tripwires rather than
overwriting even synthetic weights. Direct/relative/hardlink/symlink inputs,
actual observed weights/binary, late alias substitution and existing unrelated
report overwrite are tested. `second-pin-red.*` shows first-arm construction
before second-pin refusal; both sources now validate before either factory.
The standalone Hub omission has a separate public API red/fix. These are
synthetic functional proofs, not native model observations.

The earlier `f72` suite (`unit.xml`) is1758pass30skip. Packaging correction7782
(`metadata-checks.xml`) is100pass2skip. Superseded9f full suite was interrupted
after the alias defect was demonstrated; only its verified task-owned Python
wrapper/child77500/52524 were stopped, with no final results claimed. The1c8
suite (`1c8-final-unit.xml`) is1766pass32skip/1failure: an obsolete less-than-only
test rejected the tighter exact SDK pin. Its corrected PEP440 check retains
upper bounds and demonstrates269accepted/252and270refused without an exemption.
Final-source counts and statuses are in `receipts.json`, separately from these
historical runs. `synthetic-*` is the olderf72 fixture, `final-synthetic/` the
older1c8 fixture; their source-head fields remain unchanged. An evidence-driver
wrong option (`--resolution-report` instead of `--resolution`) is preserved in
`synthetic-initial-failure.json` and `initial-synthetic/` before correction.

The final available suite passed **1,774 tests**, with **32 skips**, from 1,806
independently counted XML cases. Two available SciPy numerical properties also
passed. Exact CI Ruff, formatting and mypy checks passed; the audit returned
zero errors and two existing command-documentation warnings. `byte-check.json`
records 49 input/evidence JSON files before its own addition and nine exact
bundle member hashes/sizes. The subsequent check includes that receipt itself.
All 28 broad raw-field key matches are integer `native_context_size` metadata.

From `C:\tmp\qf-release-0.16.0-20261008`, with `PYTHONDONTWRITEBYTECODE=1`
(and current-worktree `PYTHONPATH` for the standalone record scripts):

```powershell
tools/ci/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-09-inspect-gguf/final-unit.xml
tools/ci/.venv/Scripts/python.exe -m pytest tests/test_numerical_properties.py -q -k 'not rtn' --junitxml=validation/2026-10-09-inspect-gguf/final-properties.xml
tools/ci/.venv/Scripts/python.exe -m ruff check quantfit tests tools
tools/ci/.venv/Scripts/python.exe -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
tools/ci/.venv/Scripts/python.exe -m mypy --strict quantfit/spec.py quantfit/engines/base.py
tools/ci/.venv/Scripts/python.exe -m quantfit.cli audit --json
tools/ci/.venv/Scripts/python.exe validation/2026-10-09-inspect-gguf/run-synthetic.py --out validation/2026-10-09-inspect-gguf/qualified-synthetic
tools/ci/.venv/Scripts/python.exe validation/2026-10-09-inspect-gguf/record-receipts.py
tools/ci/.venv/Scripts/python.exe validation/2026-10-09-inspect-gguf/byte-check.py
tools/ci/.venv/Scripts/python.exe validation/2026-10-09-inspect-gguf/byte-check.py --check-only
```

Torch RTN/coverage/mutations and real installed/POSIX model qualification remain
hosted-only pending. This record establishes no native-generation parity,
sensitivity, human adjudication, safety GO, T0, GPU/crosshardware or independent
reproduction. QSRv1 remains unfrozen; two-resident RAM admission is an estimate,
not peak RSS and not the one-arm native Phi4 campaign's memory rule. No public
dataset was created/uploaded.

**PRESERVE:** shared worktree/env under exact-source review and later sequential
batch use. Previously blocked dependency/cache cleanup is not retried. No
task-owned native process/container, new dependency/model/worktree copy remains.
Exact final HEAD/tree/status are supplied in the delegated handback. No push or
Quant5 implementation before root approval/publication.
