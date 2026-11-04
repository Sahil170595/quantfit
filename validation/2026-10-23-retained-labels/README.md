# Retained-label functional command record — 2026-10-23

Fictional offline software evidence only. `acceptance.json` was produced on
Windows 11 10.0.26300, Intel64 Family 6 Model 183 Stepping 1, Python 3.12.13,
source quantfit 0.37.0, locked Torch 2.13.0+cpu and Transformers 5.17.0. The
source/unit Python floor and complete locked-runtime floor remain distinct;
this local record is not execution proof for another OS/Python/provider.

From the repository root, using the existing locked validation environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B validation/2026-10-23-retained-labels/reproduce.py --out validation/2026-10-23-retained-labels/acceptance.json
```

Use a different new `--out` path for another run; the reproducer refuses to
replace an existing record. Native blinding uses a fresh random salt, so hashes
of temporary private inputs change between runs. Private fixture material stays
inside a temporary directory and is removed by the reproducer; none is committed.

The reproducer delegates to `tools/ci_retained_labels.py` and the actual native
fresh-salt fixture in `tools/ci_label_reconciliation.py`. It creates a fictional
40-pair capture/sheet/key using the exact measurement identity of the existing
valid aggregate `validation/2026-10-18-screen-bundle/inputs/reports/clean.json`.
It then runs the actual CLI `calibrate extract`, removes only its synthetic
original sheet, runs explicit `calibrate ingest --retained-labels` with the exact
receipt/key, and passes the resulting schema-3 artifact into actual native
`resolution --report ... --calibration-report ... --out ...`. No model or asset
was downloaded or inferred. A full-sheet schema-2 calibration of the same
fictional rows provides per-arm count/Wilson/null/delta parity.

Independent values in `acceptance.json`: 40 pairs, 80 retained rows, 24 unusable,
calibration schema 3, native resolution schema 1, and original sheet unavailable
at retained ingestion. Both measured arms and original declared scope survive;
no per-row IDs/labels, key salt, capture or completion text are in this record.
The aggregate schema-3 calibration is included with its fictional native scope;
real calibration files may contain declared local model identifiers/paths.

This does **not** establish human truth, rater identity, authentication,
independent labeling/execution, a calibrated real judge, model/provider/GPU
behavior, sensitivity or scientific GO. Manufactured labels are functional
inputs, not human adjudication. Native conditional resolution still carries its
unverified assumptions and does not alter an original verdict. This is a
`validation/` command record, not the capped reference-report registry.
