# Calibration strata functional command record — 2026-10-23

Fictional offline software evidence only. `acceptance.json` was produced on
Windows 11 10.0.26300, Intel64 Family 6 Model 183 Stepping 1, Python 3.12.13,
source quantfit 0.38.0, locked Torch 2.13.0+cpu and Transformers 5.17.0. This
local record is not execution proof for another OS, Python version or provider.

From the repository root, using the existing locked validation environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B validation/2026-10-23-calibration-strata/reproduce.py --out validation/2026-10-23-calibration-strata/acceptance.json
```

Use a different new `--out` path for another run; the reproducer refuses to
replace an existing record. Fresh native blinding salts and capture timestamps
make private-input hashes vary. The reproducer removes its own temporary
fictional inputs; the product commands never delete source files.

The reproducer delegates to `tools/ci_calibration_strata.py`. Its native
capture/sheet/key fixture contains eight fictional pairs across all three zones,
including both expected values in `borderline` and asymmetric unusable labels.
It runs actual CLI full-sheet strata, extracts retained labels and a receipt,
removes only the owned synthetic original sheet, then runs retained-label strata
with the original capture still present. Counts, native Wilson intervals,
cohorts and fingerprint agree. The actual native bound-calibration loader
refuses this diagnostic as a replacement calibration. No model or asset was
downloaded or inferred; the synthetic capture scope derives from the existing
aggregate `validation/2026-10-18-screen-bundle/inputs/reports/clean.json`.

Independent fixture counts, also asserted cell by cell in
`tests/test_calibration_strata.py`: eight pairs and 16 rows; zone populations
`clear_safe=2`, `clear_unsafe=2`, `borderline=4`; dangerous and over-refusal
observed-at-risk cohorts each select two pairs. All-row usable/unusable counts
are baseline `6/2` and quantized `6/2`. Baseline has two false refusals and two
false compliances; quantized has two false refusals and one false compliance.
These directional rates use their own human-compliance/refusal denominators,
not selected-pair counts or pooled `2n` observations. Empty directional rates
remain null with native Wilson `[0,1]` intervals.

Only aggregate counts, fixed vocabulary, hashes and a binding fingerprint are
committed. No per-row IDs, labels, key salt, capture text, completion text or
private caller paths are in the record. The unavailable original-sheet hash in
retained mode is a receipt declaration, not a fresh read or authentication.

This does **not** establish human truth, rater identity, independent labeling or
execution, source authenticity, a calibrated real judge, model/provider/GPU
behavior, sensitivity or scientific GO. Zones are transparency groupings, not
independent statistical strata. Manufactured labels are functional inputs, not
human adjudication. No calibration replacement, A1 transfer or gate wiring is
performed. This is a `validation/` command record, not the capped reference-report
registry.
