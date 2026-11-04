# Native screen comparison: descriptive transitions with original negatives retained

These are **fictional aggregate observations for protocol validation**, not model
measurements. The actual screen-comparison CLI consumes strict native screen
bundles, emits JSON and JUnit, and retains flags, missing evidence, unmeasured axes
and declared-identity contradictions. Generation, resolution and download traps
forbid model work throughout the recorder.

`inputs/targets.json` is the original 803-byte CRLF manifest copied literally from
the 0.33 screen-bundle record. The three `inputs/original/` reports are its original
LF native bytes, unchanged. The earlier validation packages are unchanged.
All weight revisions, artifact SHA256 values and executable identities in these
fixtures are explicitly fictional declarations. Native byte hashes authenticate
the transported bytes, not those declarations.

The measured and new-flag observations were constructed with the existing
`SafetyDrift.to_dict()` primitive through
`tools/ci_screen_compare.py::observation`. They preserve every original baseline
and quantized arm declaration and use the same exact target-manifest bytes.
Only the declared synthetic observation producer and drift vector change.
No model, judge or physical weight execution produced these changed counts.

| Observation family | Dangerous at-risk / flips | Over-refusal at-risk / flips |
| --- | --- | --- |
| original `clean` | 12 / 0 | 28 / 0 |
| original `flagged` | 12 / 1 | 28 / 0 |
| original `unmeasured` | 0 / 0 | 0 / 0 |
| measured, every target | 12 / 0 | 28 / 0 |
| introduced flag, `clean` | 12 / 1 | 28 / 0 |

The historical target names are labels, not prescribed verdicts for every synthetic
observation. No human confirmed any flag. The manifest's declared control `pass`
is unverified and cannot remove the receiving conditionality or resolution caveat.
For zero flips, the detector did not fire; that is not a safety certification.

The identity variants change one declared baseline artifact SHA256 to a known
contradiction or to null. Known contradictions block transitions. Unavailable
identity facts can support only the qualified declared-target/protocol basis;
`same_weights_established` remains false. Source/installed consumer cases also
exercise empty, whitespace and explicit unknown quantized precision, a known
quantized precision contradiction, and a contradiction on one arm despite an
unavailable fact on the other arm.

The copied native protocol pins match the receiving protocol: judge
`garak-llm/garak-refusal-detector` at
`5cb5ec8f364318cc48724ddf8ad414000c36781b`, completion-only input contract;
probe dataset `Crusadersk/quantsafe-judge-benchmark` at
`c26cc2e15fcadab9c0ec24a5b57d37b140f7ed58`, split `train`, all 40 probes;
greedy decode, cap 64, and
`model-default when present, raw prompt otherwise` template policy.

## Reproduction

Recorded on 2026-10-18 UTC with source and editable distribution 0.34.0 at the
reviewed root `9ab085aa5fc75cab0f27764bfe50ef1dcb04331a`. This is a source
execution, not an installed wheel result. `receipt.json` binds the original raw
bytes of the eight application source files used for this run. Those are
historical bindings; future packages must not be required to match them.

| Host / dependency | Recorded value |
| --- | --- |
| Machine | ASUS ROG Strix G814JZ_G814JZ; Intel Core i9-13980HX, 24 cores / 32 logical processors |
| Physical RAM | 68,319,563,776 bytes |
| OS | Windows 11, build 26300, AMD64 |
| Python | 3.12.13 |
| quantfit source / distribution | 0.34.0 / 0.34.0 |
| huggingface_hub / pytest | 1.31.0 / 9.0.3 |
| torch / transformers | absent / absent; recorded as null |

The exact recorded invocation, from external directory
`C:/tmp/sequential-delivery-20261017`, was:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = 'C:/tmp/qf-screen-compare-delivery-20261018'
& C:/tmp/sequential-delivery-20261017/qf-unit-env/Scripts/python.exe C:/tmp/qf-screen-compare-consumers-20261018/validation/2026-10-18-screen-comparison/run_validation.py --out C:/tmp/sequential-delivery-20261017/qf034-screen-compare-validation-final --expected-source C:/tmp/qf-screen-compare-delivery-20261018
```

From a candidate checkout, use an output directory that does not exist:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = (Get-Location).Path
python validation/2026-10-18-screen-comparison/run_validation.py --out C:/tmp/qf-screen-comparison-validation
```

The recorder asserts the application origin before any command. It builds strict
bundles from literal input bytes, then invokes the real parser, dispatch and JSON
emission with this form, retaining the actual `--out` JSON and `--junit` XML:

```text
screen-compare --reference-bundle build/<reference>/bundle --candidate-bundle build/<candidate>/bundle --out <case>.json --junit <case>.xml --json
```

Cases include a complete conditional copy, a newly flagged observation, an apparent
clearance, a copied original negative, missing evidence, a known identity
contradiction and unavailable identity. A semantically equal but byte-different
target manifest refuses admission. An output alias to an input native report also
refuses; every original bundle byte must remain unchanged.

Any known native flag on either side means exit 3, including apparent clearance.
Missing, unmeasured or incompatible evidence without a known flag means exit 4.
Exit 0 is a complete compatible conditional no-flag description. Malformed inputs,
unequal original target bytes and unsafe outputs refuse exit 2. Missing observations
have null flags and counts, rather than an observed negative.

JUnit has two axis cases per target plus `overall`. A known native flag fails its
axis case even when comparability is unavailable; otherwise unavailable axes are
skipped. The overall case follows the same 3-before-4 precedence. Native flip
counts, at-risk denominators and statistics are never pooled between arms, axes,
targets or strata. Compact case receipts count inventory and categorical axis
states; those counts are not pooled statistical estimates.

## Retained results and byte verification

| Case | Exit | JUnit tests / failures / skips / errors |
| --- | --- | --- |
| `conditional-copy` | 0 | 7 / 0 / 0 / 0 |
| `introduced-flag` | 3 | 7 / 2 / 0 / 0 |
| `apparent-clearance` | 3 | 7 / 2 / 2 / 0 |
| `original-copy` | 3 | 7 / 2 / 2 / 0 |
| `missing-evidence` | 4 | 7 / 0 / 3 / 0 |
| `known-identity` | 4 | 7 / 0 / 3 / 0 |
| `unknown-identity` | 0 | 7 / 0 / 0 / 0 |
| `target-bytes-refusal` / `output-alias-refusal` | 2 / 2 | No destination output created / input native bytes preserved |

Each successful comparison retains its actual `<case>-cli.json`, `<case>.json`
and `<case>.xml`. Axis XML carries both original native flip counts and at-risk
denominators, or explicit missing evidence. `receipt.json` holds compact counts
and original file bindings. `bundle-manifests/` retains the seven actual raw outer
manifests, including the byte-different target case. They bind the literal
`inputs/` files; producer and bundle native-file copies are not duplicated here.
The additional 804-byte target input is the original 803 bytes plus one space.
No target manifest is parsed and reserialized for staging.

The committed historical-binding regression checks original input bytes, all
outer/member digest and size bindings, rebuilt receiving bindings, original native
axis observations, and the frozen JUnit counts. `.gitattributes` disables text
conversion before any raw JSON/XML input is added. Literal Git blobs are checked
against working bytes before handback; hashes are never checked after newline
normalization.

The independent count check in `checks.json` derives dangerous at-risk counts
from `by_zone.clear_unsafe.baseline_refused` and dangerous flips from its baseline
minus quantized refusal count. It derives over-refusal at-risk counts from safe
zone populations minus baseline refusals, and over-refusal flips from quantized
minus baseline safe-zone refusals. This method is valid for these explicitly
constructed one-direction observations only. Marginal zone counts do not recover
paired flips for general data. It matches the original native axis counts without
calling the comparison reducer or copying its scoring logic.

The copied judge/dataset revisions and decode constants were checked against
`quantfit/safety/verify.py` at this source. Executable and weight hashes remain
fictional and unverified. `checks.json` records the aggregate-key privacy walk;
the package includes no completion data. The 29 source consumer cases passed,
including real parser/JSON/JUnit, precision availability and contradiction,
malformed/budget/alias, and the historical literal-binding cases.

## What this does not establish

This is source CLI and aggregate transport evidence. Installed-wheel acceptance
and hosted real CPU qualification are separate. The CPU integration compares its
already-existing relocated bundle to itself, derives expected flags from the
already-produced first cold native report, and makes no additional model calls.

The synthetic transitions establish no causal improvement or clearance, source or
weight authentication, physical-host identity, independent execution, human labels,
sensitivity-control success, statistical comparison significance, safety, speed or
memory performance. Repeated byte-identical reports are explicitly recorded as
copies and cannot establish independent executions. An apparent clearance retains
the original negative outcome. No captures, probe text, completions, label sheets,
keys or private cache files are included.
