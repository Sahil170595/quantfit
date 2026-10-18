# Screen bundle: offline aggregate handoff

This package exercises actual `bundle screen-create` and `bundle screen-verify`
CLI parser, dispatch, JSON emission and receiving logic. The native aggregates are
explicitly **synthetic protocol fixtures**, copied byte for byte from the committed
0.32 strict-resume validation. No model, judge, weight resolver or download runs.
The previous validation record is unchanged.

`inputs/targets.json` is the original 803-byte CRLF manifest. The three original
native reports have LF endings: `clean` 3321 bytes, `flagged` 3303 bytes and
`unmeasured` 3343 bytes. Every synthetic weight revision, artifact SHA256 and
executable SHA256 is fictional, not an authenticated model or binary identity.
The report producer version remains `synthetic-bounded-aggregate-fixture`.
The new 75-byte producer summary declares favourable claims deliberately; it is
transported as an ignored original member, not receiving evidence for those claims.

The runner stages original manifest and report bytes with `write_bytes`; it never
parses and reserializes the manifest for staging. The local `.gitattributes` was
created before the first input commit and preserves JSON/XML bytes on every OS.
The receiver binds exact bytes, including whitespace and line endings.

| Target | Dangerous at-risk / flips | Over-refusal at-risk / flips | Native row |
| --- | --- | --- | --- |
| clean | 12 / 0 | 28 / 0 | no_regression |
| flagged | 12 / 1 | 28 / 0 | regression |
| unmeasured | 0 / 0 | 0 / 0 | unmeasurable |

The complete fixture has two measured dangerous targets, one judge-flagged target,
two measured over-refusal targets and zero over-refusal flags. No human confirmed
any flag. Removing `flagged` leaves two present reports and one explicitly missing
target; the unmeasured report remains unmeasured. Both strata and axes retain their
native denominators. The manifest's declared control `pass` is unverified, so it
cannot remove receiving conditionality or the perfect-judge resolution caveat.

The copied native protocol pins match the strict receiver:

- Judge `garak-llm/garak-refusal-detector`, revision
  `5cb5ec8f364318cc48724ddf8ad414000c36781b`, completion-only input contract.
- Probe dataset `Crusadersk/quantsafe-judge-benchmark`, revision
  `c26cc2e15fcadab9c0ec24a5b57d37b140f7ed58`, split `train`, all 40 probes.
- Greedy decode, `max_new_tokens=64`, current
  `model-default when present, raw prompt otherwise` policy.

## Reproduction

Recorded host: Windows 11 build 26300, Intel Core i9-13980HX (24 physical cores,
32 logical processors), AMD64, Python 3.12.13. Candidate source and editable
distribution versions were both 0.33.0. The offline unit environment contained
`huggingface_hub` 1.31.0 and pytest 9.0.3; Torch and Transformers distributions
were absent, recorded as `null`. No installation or environment change was needed
for these lazy aggregate-receiving paths. The six exact application source files
used by the run are bound by SHA256 and size in `receipt.json.runtime.source_files`.

From the candidate repository checkout, use an output directory that does not exist:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = (Get-Location).Path
python validation/2026-10-18-screen-bundle/run_validation.py --out C:/tmp/qf-screen-bundle-validation
```

The recorded invocation ran from the external `C:/tmp/sequential-delivery-20261017`
directory and asserted the candidate application source before any CLI call:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = 'C:/tmp/qf-screen-bundle-delivery-20261018'
C:/tmp/sequential-delivery-20261017/qf-unit-env/Scripts/python.exe C:/tmp/qf-screen-bundle-consumers-20261018/validation/2026-10-18-screen-bundle/run_validation.py --expected-source C:/tmp/qf-screen-bundle-delivery-20261018 --out C:/tmp/sequential-delivery-20261017/qf033-screen-bundle-validation-final
```

The script asserts the imported application origin before any CLI call. It creates
a bundle, relocates it, makes the original producer paths unavailable and verifies
using only bundle members. It separately creates and verifies an incomplete bundle,
then refuses a one-byte native-member tamper and a corrupt source report. The
generation, resolution and download traps must remain uncalled.
Read-only regular input hardlinks are supported; every occurrence is charged and
native duplicate-evidence checks still apply. Symbolic links and reparse points
are refused. A foreign output member hardlinked to an input must never be
overwritten; the injected publication test checks refusal and both original bytes.

The actual CLI argument forms are:

```text
bundle screen-create --targets producer/targets.json --reports-dir producer/reports --out bundle --json
bundle screen-verify --bundle relocated-bundle --json
bundle screen-create --targets missing-producer/targets.json --reports-dir missing-producer/reports --out missing-bundle --json
bundle screen-verify --bundle missing-bundle --json
bundle screen-verify --bundle tampered-bundle --json
bundle screen-create --targets corrupt-producer/targets.json --reports-dir corrupt-producer/reports --out refused-bundle --json
```

Valid content has command exit 0 even when the separate nested receiving summary
reports flags (3) or incomplete evidence (4). The complete fixture retains its
flagged and unmeasured rows. The missing bundle retains the declared missing member
with null hash and size. Corruption refuses exit 2. Exact byte hashes and sizes
belong to the transport; they do not authenticate the source or its declarations.

| Recorded command | Content exit | Nested receiving exit | Evidence |
| --- | --- | --- | --- |
| create complete | 0 | 3 | `bundle/`, three native reports and ignored producer summary |
| verify relocated | 0 | 3 | Original producer paths unavailable |
| create missing | 0 | 4 | `missing-bundle/`, `flagged` explicitly absent |
| verify missing | 0 | 4 | Missing target and unmeasured row retained |
| verify tampered | 2 | No result | One whitespace byte breaks an original native binding |
| create corrupt | 2 | No result | Original corrupt bytes retained; destination not published |

The complete bundle contains six files and 11923 transport bytes; the incomplete
bundle contains four files and 8422 bytes. Both totals include the outer manifest,
original target manifest and every present member. `receipt.json` records compact
counts, component bindings and source/runtime limits; the full CLI records retain
the receiving summaries. Bundle commands have no JUnit output option.

A second method sums `by_zone` populations and compares the explicitly constructed
one-direction refusal counts: complete dangerous 2 measured / 1 flagged,
over-refusal 2 measured / 0 flagged; incomplete dangerous 1 / 0 and over-refusal
1 / 0. This method is specific to these fixtures; marginal refusal differences
do not generally recover paired flips. JSON keys were walked for
`prompt|completion|response|text|generation`; zero matched. No payload text is
present; protocol input-contract strings describe configuration only.

## What this does not establish

This is source CLI and transport evidence. It is not an installed wheel or hosted
real CPU inference record. Those lanes use the guarded installed consumer tests
and reuse the CPU job's already-produced first cold native report without additional
inference, respectively. Simulated publication-race tests inject an existing
destination; they are not real concurrent-process or filesystem durability proof.

This package establishes no model safety, judge quality, sensitivity-control pass,
human-confirmed regressions, independent execution, authentic weights or hardware,
repeatability, speed or memory performance. A zero-flip result means the detector
did not fire, not that an artifact is safe. No captures, probe text, completions,
labels, adjudication keys or private caches are included.
