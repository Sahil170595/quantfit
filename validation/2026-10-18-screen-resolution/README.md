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
decode, cap64, model-default template when present and raw prompt otherwise.

## Reproduction

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
