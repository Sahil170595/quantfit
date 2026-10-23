# Paired calibration functional command record — 2026-10-23

Fictional offline software evidence only. `acceptance.json` was produced on
Windows 11 10.0.26300, Intel64 Family 6 Model 183 Stepping 1, Python 3.12.13,
source quantfit 0.39.0, locked Torch 2.13.0+cpu and Transformers 5.17.0. This
local record is not execution proof for another OS, Python version or provider.

From the repository root, using the existing locked validation environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B validation/2026-10-23-calibration-paired/reproduce.py --out validation/2026-10-23-calibration-paired/acceptance.json
```

Use a different new `--out` path for another run; the reproducer refuses to
replace a record. Native fresh salts and capture timestamps change private-input
hashes. Its private fictional fixture stays in an owned temporary directory and
is removed on completion; product commands never delete source files.

`tools/ci_calibration_paired.py` creates a native 24-pair capture/sheet/key, runs
actual full-sheet `calibrate paired`, extracts retained labels, removes only its
owned synthetic sheet, then runs retained-label `calibrate paired` with the
original capture still present. The actual native bound-calibration loader and
actual `gate --from-report --calibration-report` both refuse this diagnostic as
replacement calibration; the latter exits 2 without a gate artifact. No model,
asset download or inference is performed. Capture scope comes from the existing
aggregate `validation/2026-10-18-screen-bundle/inputs/reports/clean.json` and is
fictional functional input, not a new measurement of that model.

Independent literal oracles (rows judge, columns supplied label, order
`RR,RC,CR,CC`; baseline first):

```text
common-usable judge/label table = [[1,2,1,1], [1,1,3,1], [2,1,1,1], [1,1,1,2]]
baseline-error/quantized-error table (false,true) = [[5,5], [5,6]]
common judge marginals = [5,6,5,5]; label marginals = [5,5,6,5]
whole judge marginals = [5,8,6,5]
coverage: total24, both-usable21, baseline-only-unusable1,
          quantized-only-unusable1, both-unusable1
```

The dangerous expected group has whole judge `(pairs,at-risk,flips)=(12,6,4)`;
common expected pairs 10, judge `(at-risk,flips)=(4,2)`, supplied label `(5,2)`,
and judge-flip/label-flip joint `[[7,1],[1,1]]`. Over-refusal has whole judge
`(12,5,3)`; common expected pairs 11, judge `(4,2)`, supplied label `(6,4)`,
and joint `[[5,4],[2,0]]`. These are distinct denominators. Joint false includes
not-at-risk baseline states; no-flip is not a true negative or safety claim.

Tests independently check every cell, asymmetric orientations, null rates/native
Wilson `[0,1]`, all-unusable retained inputs, and equal per-arm errors/error
marginals with opposite paired association. Full/retained statistics agree.
The original-sheet hash in retained mode is a receipt declaration, not a fresh
read or authentication. Only fixed aggregates/hashes/fingerprint are committed;
no per-row labels/IDs, text, salts or private paths occur in the record.

This does **not** authenticate labels/raters, establish independent labeling or
execution, source authenticity, a calibrated real judge, model/provider/GPU
behavior, sensitivity or scientific GO. Complete cases need not represent
excluded labels; native source-specific Wilson summaries do not justify
McNemar/Newcombe inference, bias correction or pooled `2n` observations. No
calibration replacement or gate wiring is performed. This is a `validation/`
command record, not the capped reference-report registry.
