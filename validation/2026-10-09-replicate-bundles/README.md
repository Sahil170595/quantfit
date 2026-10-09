# Three-report T0 handoff — 2026-10-09

This validates offline transfer of saved aggregate evidence, preserving every
producer report/T0 byte and returning a separate receiving-path T0. It executes
no model, judge, cache or network request. Original producer paths remain
unverified labels. No scientific GO or independent reproduction is established.

The functional run observed source `307e1c63bc24db29b41a7a8706c0cf75c25edcf0`.
Final full-unit qualification observed `3b766ce6a5511a0332fdb4cd664d3fecd55ee59a`:
its sole delta is the corrected CLI envelope inventory/tests. Production, API,
docs and installed-consumer blobs are unchanged. `run.json` records the actual
head/source associations and working/canonical Git hashes; `members.json` binds
retained artifacts. Earlier results are not relabelled as new runs.

## Observed machine and local gates

Windows 11, Intel64 Family 6 Model 183 Stepping 1, 32 logical CPUs, total RAM
68,319,571,968 bytes. The reused approved unit/tooling environment has Python
3.12.13, pytest 9.0.3, SciPy 1.15.3, NumPy 2.4.6, inspect-ai 0.3.269,
huggingface-hub 1.31.0, gguf 0.19.0, Ruff 0.16.2 and mypy 1.20.2. Torch is absent.
Machine observations do not authenticate a physical host.

| Check | Actual result | Artifact |
| --- | --- | --- |
| Entire supported unit lane, numerical module excluded | 1,926 passed, 40 skipped, no failures/errors | `unit-final.log`, `unit-final.xml` |
| New replay product tests | 62 passed, 6 skipped | `focused-replay.log`, `focused-replay.xml` |
| Corrected envelope and replay integration | 97 passed, 6 skipped | `envelope-corrected.log`, `envelope-corrected.xml` |
| Available SciPy properties | 2 passed; RTN deselected | `properties-final.log`, `properties-final.xml` |
| Exact CI Ruff check / format | passed / 114 files already formatted | `lint-final.log`, `format-final.log` |
| Exact CI mypy paths | passed, 2 source files | `types-final.log` |
| Instrument audit | 0 errors, 0 warnings | `audit-final.json` |
| README source CLI syntax inventory | 48 commands parsed; 0 executed | `quickstart-final.json` |
| Actual offline source CLI | 4 commands, 2 relocated bundles | `functional.json` |
| Original native T0 comparison | 2 exact dictionaries equal to the ef03 Git blob | `functional.json` |

The initial full unit gate at 307 failed the unchanged exact leaf inventory:
1 failed, 1,919 passed, 40 skipped. The inventory now lists both commands, and
new real JSON/prose refusal and success/negative subprocess cases block model
backends. No original cases/checks were waived. The initial TDD red was an import
refusal of the then-absent APIs. A development import-order lint diagnostic was
corrected before freeze. Compact counts/causes and exact recovery hashes are in
`development-summary.json`; verbose intermediates remain at
`C:\tmp\qf-next-pr-receipts-20261008\replicate-bundles-development`.

The product focused run preceded source freeze on the consumed working files.
The corrected envelope run observed 307 plus its then-uncommitted test-only
delta, subsequently frozen unchanged at 3b. The final whole unit gate covers
both sets at immutable 3b. Tooling/properties/README inventory observed 307;
their relevant production/docs blobs also equal 3b. Independent product review
passed 14 adverse probes at 307; the reviewer and root separately confirmed the
sole test delta at 3b. Root performed eight separate in-memory challenges.
`independent-review.json` is explicitly materialized from those review messages,
not another builder execution.

## Preserved actual and synthetic outcomes

`historical-phi4/relocated/` preserves the earlier hosted Phi4 BF16/Q4_K_M reports
and original native T0. Their ordered SHA256s are:

- run 1: `d585720b1c73f289ef2fd8105af1ce76ebe89884b4c2c62f241380590f1223cf`
- run 2: `5edc7f6731c265291a5560dcde5a49c5ece389cdd4d533979ce95025ba73e6bd`
- run 3: `4f8d91c0a026bb0003d49d9d307cb563a91b5dc624484a5e8ea719d8f963a8f8`
- original T0: `3b4424e1c985245ad81cb0dbbbfe14a31f5efcd1f88970785dfa6d65af22fd91`

These bytes were recomputed from the committed earlier producer artifacts,
copied to disposable source paths, packaged, then those source copies were
removed and the bundle relocated. Original producer strings were never opened
or resolved. Original T0 `protocol_pass` remains true; receiving T0 is returned
separately in `historical-phi4/receiving-check.json`. All three original reports
retain two **unconfirmed** over-refusal flags out of 20 at risk and dangerous
0/12: **the detector did not fire**. Existing native measurement results were
negative; agreement does not suppress them or provide human confirmation.

The reports retain model revision `78eb92a46fc37e6b524df991ed9aca9bc6aa7b80` and
BF16/Q4 artifact hashes `1a179f22f1efe409c6517805400c4f07f93fe1f5783e47231d35f933565dff20`
and `88c00229914083cd112853aab84ed51b87bdf6b9ce42f532d8c85c7c63b1730a`.
They record the earlier Linux CPU environment (Python 3.12.15, Torch 2.13.0+cpu,
Transformers 5.17.0), not this Windows validation machine. No model bytes or
hardware facts are freshly observed by this replay.

`synthetic-disagreement/` is explicitly synthetic: the third report's
over-refusal count is changed from 2 to 1 and existing `SafetyDrift` recomputes
its aggregate statistics. Original and receiving T0 both remain false, while
supported bundle integrity exits 0. The synthetic report is not a measured new
run. Its original T0 retains its removed disposable source labels unchanged;
`receiving-check.json` is separate. Neither example pools replicates or creates
three reference entries.

## Exact invocations

Run from the checkout root with pre-existing
`tools/ci/.venv/Scripts/python.exe` (abbreviated `PY`):

```text
PY -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-09-replicate-bundles/unit-final.xml
PY -m pytest tests/test_replay_bundle.py -q --junitxml=validation/2026-10-09-replicate-bundles/focused-replay.xml
PY -m pytest tests/test_json_envelope.py tests/test_replay_bundle.py -q --junitxml=validation/2026-10-09-replicate-bundles/envelope-corrected.xml
PY -m pytest tests/test_numerical_properties.py -q -k "not rtn" --junitxml=validation/2026-10-09-replicate-bundles/properties-final.xml
PY -m ruff check quantfit tests tools
PY -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
PY -m mypy --strict quantfit/spec.py quantfit/engines/base.py
PY -m quantfit.cli audit --json
PY tools/quickstart_check.py --quantfit-bin "C:/tmp/qf-release-0.16.0-20261008/tools/ci/.venv/Scripts/python.exe -m quantfit.cli" --min-commands 20 --no-run --json validation/2026-10-09-replicate-bundles/quickstart-final.json
PY validation/2026-10-09-replicate-bundles/run-functional.py
```

`functional.json` records the four actual CLI argv/exit codes. It also records
two exact native dictionary comparisons against executable base ef03 source.
Logs/JSON are redirected to the corresponding artifacts in the table. The
README inventory uses the source CLI with `--no-run`; generic checker wording
does not establish an installed candidate consumer.

## Bounds and resource receipt

All old schema-1/native T0 tests remain. Adverse replay tests cover removed
producers, relative/foreign labels, ordered hash substitution, duplicate bytes/
same-file/hardlink/alias inputs, cached baselines, identity/decode/binary changes,
forged T0 facts, nonfinite/duplicate/private/unknown JSON, layout corruption,
links/junctions, partial/short writes, flush/close failures and interruption.
Windows junction checks ran; three symlink and three POSIX FIFO cases were
skipped here. Actual Linux FIFO and installed wheel/sdist outside-checkout
acceptance are configured in existing hosted lanes, still pending batch push.
Full hosted numerical/RTN qualification remains pending; Torch was not installed.

Every retained JSON key is scanned using the AGENTS raw-data patterns. The sole
allowance is this record's exact `quickstart-final.json` `commands/*/text` public
README command inventory, with individual value hashes. No aggregate-role
exception is allowed. All new JSON working bytes are compared to Git blobs and
protected by the narrow new `.gitattributes` rule. For legacy text/CRLF source
files, canonical equivalence is stated separately from raw equality. Earlier
dated records are unchanged.

PRESERVE: root-owned shared checkout/environment remain consumed by the batch,
with prior cleanup rejections retained without retry. The named development
artifact directory preserves intermediate records. No task-owned processes,
new dependency/model/container copies or other disposable worktrees remain.
No branch has been pushed; no QF3 work has begun.
