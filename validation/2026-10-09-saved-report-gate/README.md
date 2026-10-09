# Saved-report policy replay — 2026-10-09

This record validates offline policy evaluation of already-produced aggregates. It
does not run either model, a judge, a cache or a Hub request. `run.json` records
observed versions, source hashes, independently parsed JUnit counts and limits;
`members.json` records the retained artifact bytes.

The functional run observed implementation head
`150eaa4b8c3b81de5c68c4ba8438d2b113d85f4c`. Final local gates observed
`edc69700fe58646563adcb917b728b0e598b0493`; its sole difference from that head is
the missing `--from-report` validation-matrix row. The earlier results are retained
as earlier runs, with the unchanged implementation blobs checked separately.

## Machine and results

Observed Windows 11, Intel64 Family 6 Model 183 Stepping 1, 32 logical CPUs and
68,319,571,968 bytes total RAM. The reused unit/tooling environment has Python
3.12.13, pytest 9.0.3, SciPy 1.15.3, NumPy 2.4.6, inspect-ai 0.3.269,
huggingface-hub 1.31.0, gguf 0.19.0, Ruff 0.16.2 and mypy 1.20.2. Torch is absent.
These observations describe the validation machine, not an authenticated host.

| Local check | Actual result | Artifact |
| --- | --- | --- |
| Entire unit lane excluding the numerical-properties module | 1,858 passed, 34 skipped, no errors/failures | `unit-final.log`, `unit-final.xml` |
| Replay, existing gate/bundle and metadata integration | 185 passed, 7 skipped | `focused-corrected.log`, `focused-corrected.xml` |
| Available SciPy properties | 2 passed; RTN deselected | `properties-final.log`, `properties-final.xml` |
| Ruff check / format | passed / 112 files already formatted | `lint-final.log`, `format-final.log` |
| Exact CI mypy paths | passed, 2 source files | `types-final.log` |
| Instrument audit | 0 errors, 0 warnings | `audit-final.json` |
| README syntax inventory through source CLI | 46 commands parsed, 0 executed | `quickstart-final.json` |
| Functional source CLI | 6 commands; 2 relocated bundles verified | `functional.json` |
| Native legacy decision comparison | 5 synthetic cases equal in every field except `created_utc` | `functional.json` |

The first full-unit run at 150 failed only because the validation matrix lacked
the new flag: 1 failed, 1,857 passed, 34 skipped. The checker remained unchanged;
the docs-only correction was followed by the successful final run. Initial TDD
collection refused the absent public API. Intermediate module extraction briefly
removed the native `_write` helper; it was restored and the legacy comparisons
then passed. An initial README checker invocation could not find `quantfit` on
PATH; its supported `--quantfit-bin` option supplied the existing source CLI.
`development-failures.json` preserves actual counts, causes and byte hashes of
the verbose intermediate artifacts retained at
`C:\tmp\qf-next-pr-receipts-20261008\saved-report-gate-development`.

## Actual aggregate examples

`run-functional.py` invokes the source CLI and records exact argv/envelopes. It
consumes the preserved earlier Phi4 report whose SHA256 is
`d585720b1c73f289ef2fd8105af1ce76ebe89884b4c2c62f241380590f1223cf`.
The saved report has two unconfirmed over-refusal flags out of 20 at-risk probes
and zero dangerous flags out of 12: **the detector did not fire**. The offline
dangerous-axis floor policy returns 0, while retaining the original
`REGRESSION DETECTED (over-refusal axis)` verdict and the ungated flags. This is
policy replay of an earlier measurement, not a new model run or a scientific GO.

The bound example consumes explicitly **synthetic** Quant1 report/calibration
fixtures. Native best-case policy preflight returns 5 before evaluating observed
counts. The original saved report is still copied exactly; calibration records
matching of its recorded scope, not a fresh weights/environment observation or
authenticated human labels. Gate-only replay bundles are refused because replay
requires the consumed report. Both example bundles were moved and verified from
their relocated paths, with exact-byte manifest binding.

## Exact invocations

Run from the checkout root using the pre-existing
`tools/ci/.venv/Scripts/python.exe` (abbreviated `PY` below):

```text
PY -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-09-saved-report-gate/unit-final.xml
PY -m pytest tests/test_saved_report_gate.py tests/test_meta.py tests/test_gate.py tests/test_bundle.py -q --junitxml=validation/2026-10-09-saved-report-gate/focused-corrected.xml
PY -m pytest tests/test_numerical_properties.py -q -k "not rtn" --junitxml=validation/2026-10-09-saved-report-gate/properties-final.xml
PY -m ruff check quantfit tests tools
PY -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
PY -m mypy --strict quantfit/spec.py quantfit/engines/base.py
PY -m quantfit.cli audit --json
PY tools/quickstart_check.py --quantfit-bin "C:/tmp/qf-release-0.16.0-20261008/tools/ci/.venv/Scripts/python.exe -m quantfit.cli" --min-commands 20 --no-run --json validation/2026-10-09-saved-report-gate/quickstart-final.json
PY validation/2026-10-09-saved-report-gate/run-functional.py
```

Logs/JSON shown in the table capture the corresponding redirected output. The
README checker is static source CLI validation; its wording does not establish
an installed-wheel consumer. The actual Bash action route is exercised by the
unit tests, while the existing hosted action matrix and installed wheel/sdist
consumers have been extended and await batch publication.

## Evidence boundary and lifecycle

Independent exact-edc domain review passed, including recorded-scope calibration,
policy preflight/observed-count relationships, rejected forgeries and unchanged
live decision dictionaries. This is local functional qualification. Hosted
numerical/RTN tests, actual installed candidate consumers, actionlint and hosted
composite-action qualification remain pending. No sensitivity result, human
adjudication, independent reproduction, GPU execution or new reference admission
is inferred.

Every retained JSON key is scanned for the AGENTS raw-data patterns. The only
matching keys are this run's README inventory `commands/*/text`: the strings are
public command syntax extracted from the repository README, not model data. No
report/calibration/gate/bundle exception is granted. Exact new JSON bytes are
protected by the narrowly scoped `.gitattributes` rule and compared to staged Git
blobs before commit. Existing historical records are untouched.

PRESERVE: this root-owned shared checkout and its approved sparse environment are
still used by the five-feature batch. Prior cleanup rejections remain in force.
The named development-artifact directory preserves uncommitted intermediate
evidence. There are no remaining task-owned processes or new dependency/model/
container copies. No branch has been pushed for this feature.
