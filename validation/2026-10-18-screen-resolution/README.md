# Optional conditional resolution of saved native screens

The inputs are **fictional aggregate protocol fixtures**, not model measurements or
a human calibration study. The original 803-byte CRLF target manifest and three
LF native reports are literal copies from the 0.33 screen-bundle validation.
`inputs/measured/` copies the explicitly synthetic measured observations from the
0.34 screen-comparison package. Those earlier records are unchanged.

`inputs/calibrations/` contains manufactured bound schema-2 aggregate labels.
They were constructed by `tools/ci_screen_resolution.py::calibration_bytes` using
the existing native `_arm_block`, `measurement_identity`, `identity_fingerprint`
and strict bound-calibration loader. Both arms declare 40 labels and zero judge
errors; baseline declares 20 refusal / 20 compliance labels, and quantized 10 / 30.
The source capture/key/sheet hashes and weight/executable identities are explicitly
fictional. No private capture, key, labeling sheet or completion data is included.
No person supplied labels and no judge-error study produced these aggregates.

The native originals retain dangerous-axis at-risk / flip counts `12/0`, `12/1`,
`0/0`, and over-refusal counts `28/0`, `28/0`, `0/0`, for clean, flagged and
unmeasured respectively. The measured variants all have dangerous `12/0` and
over-refusal `28/0`. Native Wilson intervals, floor MDE, flags, unmeasured axes,
target prevalence, control declarations and receiving conditionality are retained.
Calibration availability does not alter any native gate outcome or JUnit case.

The bound fingerprints match declared measurement scope. They do not authenticate
human labels, weights, hardware or source files. The conditional analysis output
comes directly from the existing `analyze_resolution_bytes` primitive on the exact
held native and calibration buffers. Its assumptions remain unverified, including
directional error applicability, arm-conditional independence and the majority-real
at-risk set. An error-aware resolution calculation is not a safety verdict,
sensitivity-control result or scientific GO. For dangerous zeros, the detector did
not fire; without a passing sensitivity control that does not establish absence.

The protocol pins are judge `garak-llm/garak-refusal-detector` at
`5cb5ec8f364318cc48724ddf8ad414000c36781b`, completion-only input; dataset
`Crusadersk/quantsafe-judge-benchmark` at
`c26cc2e15fcadab9c0ec24a5b57d37b140f7ed58`, split train, 40 probes; greedy
decode, cap 64, model-default template when present and raw prompt otherwise.

## Reproduction

Recorded on 2026-10-18 UTC against the independently reviewed source
`57dade3327caedfbc55ad1860e94ca00ceaf8359`, with source and editable distribution
version 0.35.0. The eight raw application-file bindings in `receipt.json` describe
the actual Windows source buffers used by this historical run. They are not a
requirement that future versions or normalized Linux source files match them.

| Host / dependency | Recorded value |
| --- | --- |
| Machine | ASUS ROG Strix G814JZ_G814JZ; Intel Core i9-13980HX, 24 cores / 32 logical processors |
| Physical RAM | 68,319,563,776 bytes |
| OS | Windows 11, build 26300, AMD64 |
| Python | 3.12.13 |
| quantfit source / editable distribution | 0.35.0 / 0.35.0 |
| huggingface_hub / pytest | 1.31.0 / 9.0.3 |
| torch / transformers | absent / absent; recorded as null |

The exact recorded invocation, from external directory
`C:/tmp/sequential-delivery-20261017`, was:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = 'C:/tmp/qf-screen-resolution-delivery-20261018'
& C:/tmp/sequential-delivery-20261017/qf-unit-env/Scripts/python.exe C:/tmp/qf-screen-resolution-consumers-20261018/validation/2026-10-18-screen-resolution/run_validation.py --out C:/tmp/sequential-delivery-20261017/qf035-screen-resolution-validation-final --expected-source C:/tmp/qf-screen-resolution-delivery-20261018
```

From the candidate checkout, with an output directory that does not exist:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = (Get-Location).Path
python validation/2026-10-18-screen-resolution/run_validation.py --out C:/tmp/qf-screen-resolution-validation
```

The recorder asserts application source origin before CLI execution. It stages
every target/native/calibration file with `write_bytes`, retains native and
annotated JSON/XML, and invokes the actual parser and dispatch:

```text
screen-summary --targets build/<case>/targets.json --reports-dir build/<case>/reports --calibrations-dir build/<case>/calibrations --out <case>.json --junit <case>.xml --json
```

Cases cover full, partial and empty calibration inventories; valid pending orphans;
missing native+calibration evidence; a complete conditional no-detection screen;
and native incomplete evidence. A late invalid calibration refuses before any
earlier target analysis. An output alias to a held calibration refuses before
analysis. Generation, model-arm resolution and download traps forbid new model
work; the required conditional-resolution math remains enabled on positive paths.

The native reader's existing 4096-probe cap is unchanged. Optional analysis
preflights all actual scope matches, individual probe bounds and the combined
`sum(n_probes**2) <= 4096**2` work budget before the first math call. Orphan stored
bindings remain pending, with no actual-report match or resolution claim and zero
analysis work. Missing calibration is an annotation state, not a new gate failure.

## Recorded outcomes and literal bindings

Every native exit equals its annotated exit. Every native XML file is byte-equal
to its corresponding annotated XML. Coverage columns below are mutually exclusive
target counts, not pooled observations or statistical estimates.

| Case | Native / annotated exit | Analyzed / calibration missing / pending report / both missing | Work units | JUnit tests / failures / skips / errors |
| --- | --- | --- | --- | --- |
| `full` | 3 / 3 | 3 / 0 / 0 / 0 | 4800 | 3 / 1 / 1 / 0 |
| `partial` | 3 / 3 | 1 / 2 / 0 / 0 | 1600 | 3 / 1 / 1 / 0 |
| `empty` | 3 / 3 | 0 / 3 / 0 / 0 | 0 | 3 / 1 / 1 / 0 |
| `pending` | 3 / 3 | 2 / 0 / 1 / 0 | 3200 | 3 / 1 / 2 / 0 |
| `both-missing` | 3 / 3 | 2 / 0 / 0 / 1 | 3200 | 3 / 1 / 1 / 0 |
| `conditional` | 0 / 0 | 3 / 0 / 0 / 0 | 4800 | 3 / 0 / 0 / 0 |
| `conditional-missing-calibrations` | 0 / 0 | 0 / 3 / 0 / 0 | 0 | 3 / 0 / 0 / 0 |
| `native-incomplete` | 4 / 4 | 2 / 0 / 1 / 0 | 3200 | 3 / 0 / 2 / 0 |

`invalid-late-refusal.json` and `output-alias-refusal.json` both record operational
exit 2 with zero analysis calls. The invalid calibration deliberately changes the
aggregate label total to 79 while the two arms still declare 40 each. No earlier
valid target is analyzed first, and no refused output destination is created.
The alias case leaves the original calibration bytes unchanged.

Each positive case retains the actual annotated CLI envelope, annotated JSON/XML,
and native JSON/XML. All raw inputs are retained once under `inputs/`; temporary
case-directory copies are omitted. The 31 source consumers include the historical
literal-binding regression. It verifies the original 803 bytes, all raw input
digests/sizes, native receiving bindings, calibration member/digest/fingerprint
bindings, original analysis inputs and native counts, exclusive coverage/work
counts, and unchanged native/JUnit outcomes. It does not recompute historical MDE
values with a future package or compare historical source hashes to that package.

Before handback every committed JSON/XML Git blob is compared directly with the
working bytes, without newline normalization. `.gitattributes` disabled text
conversion before the first input was added. No earlier validation package is
edited. `receipt.json` binds the 11 literal input files and the eight actual source
buffers; `checks.json` records the independent count/privacy checks.

For these constructed one-direction observations, the second native-count method
uses unsafe baseline refusals as the dangerous at-risk denominator and unsafe
baseline minus quantized refusals as flips. It derives safe at-risk counts from
zone population minus baseline refusals and over-refusal flips from quantized
minus baseline safe-zone refusals. This is valid for this construction only;
marginal zone counts do not identify paired flips in general. Calibration checks
separately sum the two directional error counts and label totals, and use the
existing Wilson primitive on each directional denominator to verify the stored
upper bounds. Those checks validate arithmetic, not label truth or applicability.
The aggregate-key walk covers 39 JSON files and finds zero forbidden keys.

## What this does not establish

This records source CLI/JSON/XML behavior and aggregate binding only. Installed
wheel acceptance and hosted real CPU qualification are separate. The CPU consumer
uses the existing first cold native report plus an empty calibration directory;
it adds zero inference calls and invents no human calibration for that report.

These synthetic inputs establish no human-confirmed flag or judge error rate,
authenticated weight or source identity, physical host equivalence, independent
execution, causal improvement, sensitivity success, scientific GO, safety, speed
or memory performance. Synthetic zero errors are not a claim of a flawless judge.
The control declaration `pass` remains unverified and the native perfect-judge
floor remains labeled. Native flips and at-risk denominators are not pooled across
targets, arms or axes.
