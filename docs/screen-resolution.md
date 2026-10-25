# Conditional saved-screen resolution — 0.35.0

Unreleased 0.45.0 adds [named calibration-choice sensitivity](calibration-choices.md)
as a mutually exclusive input mode. The published single-calibration workflow
below and its JSON/JUnit behavior stay unchanged.

Available since quantfit 0.35.0. Native saved-screen summaries retain their existing
behavior when the optional calibration directory is omitted.

```bash
quantfit screen-summary --targets targets.json --reports-dir reports --calibrations-dir calibrations --out receiving.json --junit receiving.xml --json
```

`quantfit.saved_screen.summarize_screen(manifest_path, reports_dir, *, out_path=None,
junit_path=None, calibrations_dir=None)` retains its existing behavior when
`calibrations_dir` is omitted. When supplied, the directory is a closed, optional
population of aggregate bound-schema-2 or closed retained-schema-3 calibrations
named `<target>.json`.
Unrelated entries, symbolic links/reparse points, nonregular files, malformed or
unsupported calibration data and known incompatible scope refuse exit 2. Inputs
remain unchanged; no inference, download, model resolution or capture lookup runs.

The native target manifest and reports are captured once and feed the unchanged
strict native aggregator. Calibration bytes undergo privacy/duplicate-key checks
and the existing authoritative binding/statistics validator. Every present
report/calibration pair must match its full actual recorded scope before analysis.
Then the existing `resolution.analyze_resolution_bytes` calculator produces the
conditional per-axis MDE and its assumptions; no new statistical rule is introduced.

The result appends `conditional_resolution`, a schema-1
`quantfit.screen-resolution` block. Its ordered rows contain target name, original
native report SHA256, calibration member/hash/size, stored binding fingerprint and
either a direct analysis or null. Statuses are mutually exclusive:

| Status | Meaning |
| --- | --- |
| `analyzed` | Both supported native report and calibration are present and their declared scope matches; conditional analysis is attached. |
| `calibration_missing` | The native report is present but its calibration is absent. |
| `pending_report_missing` | A calibration validates against its stored declaration and target, but the native report is missing. No actual report match or analysis is claimed. |
| `report_and_calibration_missing` | Both inputs are absent. No result is invented. |

Coverage counts these four row statuses and sums to the original target population;
`complete` means every row was analyzed. Missing calibration digests and sizes are
null. A pending row retains only its supplied calibration hash/fingerprint, not a
fabricated qualification for missing native evidence. Even pending supplied data
must validate; a wrong known target or backend refuses instead of being ignored.

The top-level native exit, measured-target prevalence, original flags, control
declarations, human status and sensitivity/resolution caveats remain unchanged.
JUnit remains the same native target-level result. Missing optional calibration
does not create a new gate failure: a native exit 0 can coexist with incomplete
conditional analysis. Inspect the added coverage explicitly. Native flags remain
unconfirmed, and a dangerous zero still means the detector did not fire.

Native limits stay at 256 targets, a 1 MiB manifest, 8 MiB per native member and
64 MiB native members total. Calibrations add at most 2 MiB per file and 64 MiB
over all named occurrences. Analysis supports at most 4096 probes per actual
native/calibration pair. Before any calculator call, the sum of squared native
probe counts across all analyses must be at most `4096**2`. This limits batch work
relative to the existing single-analysis bound; it is not a wall-clock guarantee.
Native-only and pending rows perform no conditional analysis work. Limits and
charged analysis work are recorded in the added block.

Both closed roots, original manifest, every declared native/calibration member
(including absent ones), and JSON/XML outputs share the existing path/alias
protection. Output parents must exist; outputs cannot live inside either closed
root, alias an input or each other, or follow links. Publication rechecks finite
inventories without rereading held report/calibration bytes and replaces each file
atomically. JSON/XML are not a transaction, crash guarantee or hostile concurrent
filesystem protection; late failure can leave an earlier output visible.

Calibration labels, completion hashes and stored bindings are supplied evidence,
not authenticated humans or verified assumptions. The existing directional-error,
arm-independence and majority-real assumptions stay attached to each analysis.
No annotation establishes fresh sensitivity, independent execution, actual weight
identity, causal improvement, safety or scientific GO. Declared model/provenance
paths may remain in native summaries; no sanitization or upload occurs. The record
under `validation/2026-10-18-screen-resolution/` is synthetic command evidence only.

## Explicit requirement (0.41.0)

Install `quantfit==0.41.0`. This version adds an opt-in requirement to this **existing** command, rather than a separate screen gate:

```bash
quantfit screen-summary --targets targets.json --reports-dir reports --calibrations-dir calibrations --require-conditional-resolution 40 --out receiving.json --junit receiving.xml --json
```

The API adds `required_conditional_resolution_pp=None` to
`quantfit.saved_screen.summarize_screen` and
`quantfit.screen_resolution.summarize_screen_with_resolution`. A supplied requirement
must be a finite number in `(0,100]` percentage points, excluding booleans, and requires
`calibrations_dir`. Invalid options refuse 2 before any input hold, calculator or
output. Omit it to retain exactly the existing default field presence, native exit,
human output and JUnit cases. Quantfit 0.37 and later admit closed retained-label
calibration schema 3 through the same native binding loader.

The complete declared manifest is qualified without filtering or pooling. Every
target needs a present native report and calibration matched to its actual declared
scope. **Both** `refusal-robustness` and `over-refusal` need a nonzero measurable
at-risk denominator, native `detectable_at_target_power is True`, and finite native
`effective_mde * 100 <= required_conditional_resolution_pp` (inclusive). These are
criteria on the same already-computed native analysis, not a new statistical model,
an extra read or another calculator pass. In particular, native effective MDE `1.0`
can be an unattainable-power saturation sentinel: a numeric 100 pp ceiling alone
does not make it pass.

Opt-in output appends `conditional_resolution_requirement` (schema 1), binding the
declared ceiling and held manifest SHA256, ordered target/report/calibration hashes,
both axes' criteria and all fixed-vocabulary reasons. It explicitly records
`native_exit_code`, `native_outcome`, `qualification_exit_code` and `requirement_met`.
The original native `outcome`, rows, flags, counts, coverage and caveats remain;
top-level `exit_code` and the CLI envelope emit the qualification exit. All simultaneous
target/axis reasons survive even when a higher-priority native result determines it:

| Priority | Qualification exit |
| --- | --- |
| Native flags | 3, regardless of resolution or other missing evidence |
| Native missing/unmeasured evidence | 4, retaining any additional coarse/missing reasons |
| Otherwise missing required calibration | 4 |
| Otherwise any unattainable, unmeasurable, unavailable or coarser axis | 5 |
| Native 0 and every target/axis meets the requirement | 0 |
| Invalid evidence, options, unsafe output or publication failure | 2 |

Missing reports/calibrations, zero denominators and coarse axes remain visible.
An absent calibration does not silently remove a target. A native conditional
no-detection outcome may therefore coexist with qualification exit 4 or 5; human
output prints the requested pp ceiling, MET/UNMET and both exits before that native
headline. Native 0 still means conditional no-detection, never safety certification.

JUnit keeps every original native case in its original order, then appends two
requirement cases per declared target and an overall requirement case. Missing or
unmet required evidence produces failures, so XML cannot look all-green when required
calibration is absent; native missing/unmeasured cases remain their original skips.
The overall case also fails on a native flag even when all resolution criteria pass.

The same native input/analysis-work bounds, alias protections and per-file replacement
publisher described above apply. Both JSON and XML use the qualification before their
buffers are published. There is no new write-once, fsync, transaction or hostile-filesystem
guarantee. Whole native artifacts can retain declared model identities and paths;
the new fixed reason vocabulary neither strips them nor authenticates them.

`validation/2026-10-23-screen-requirement/` contains offline fictional command evidence
for positive/coarse/saturated/missing/native-priority cases and an actual retained-
schema-3 producer/consumer. The installed-origin guard runs the same complete CLI
workflow on Ubuntu/Windows wheel/sdist; exact-head hosted proof is separate from local
source execution. No new inference, calibration study, label authentication, verified
directional-error assumptions, independent execution, sensitivity or scientific GO
is established. Protected-main source/security and versioned release qualification
remain separate requirements.
