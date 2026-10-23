# Conditional saved-screen resolution — 0.35.0

Available since quantfit 0.35.0. Native saved-screen summaries retain their existing
behavior when the optional calibration directory is omitted.

```bash
quantfit screen-summary --targets targets.json --reports-dir reports --calibrations-dir calibrations --out receiving.json --junit receiving.xml --json
```

`quantfit.saved_screen.summarize_screen(manifest_path, reports_dir, *, out_path=None,
junit_path=None, calibrations_dir=None)` retains its existing behavior when
`calibrations_dir` is omitted. When supplied, the directory is a closed, optional
population of aggregate bound-schema-2 calibrations named `<target>.json`.
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
