# Local label-review functional record — 2026-10-23

Fictional offline software evidence only. `acceptance.json` was produced on
Windows 11 10.0.26300, Intel64 Family 6 Model 183 Stepping 1, Python 3.12.13,
source quantfit 0.40.0, locked Torch 2.13.0+cpu and Transformers 5.17.0. This
record does not establish execution on another OS, Python version or provider.

From the repository root, using the existing locked validation environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B validation/2026-10-23-label-review/reproduce.py --out validation/2026-10-23-label-review/acceptance.json
```

Use a different new `--out` path for another run; the reproducer refuses to
replace a record. Fresh native salts and capture timestamps change private-input
hashes. Its private fictional fixture stays in an owned temporary directory and
is removed on completion; product commands never delete source files.

`tools/ci_label_review.py` uses the native labeling fixture for nine pairs and
18 rows, then supplies explicitly manufactured labels. Actual CLI preparation
writes a blank disagreement subset; the fixture explicitly fills it, application
writes a complete native sheet, and unchanged native ingestion produces schema 2.
No human adjudicated this fixture. No model, asset download or inference ran.
Declared measurement identity comes from the existing aggregate
`validation/2026-10-18-screen-bundle/inputs/reports/clean.json`; it is functional
input, not a new measurement of that model. Review commands do not read a capture;
their capture hash and measurement scope remain key declarations.

Independent literal oracle, repeated for each arm (`R=refusal`, `C=compliance`,
`U=unusable`; pair positions run left to right):

```text
sheet A = R R R C C C U U U
sheet B = R C U R C U R C U
final   = R C R U C R C R U
selected positions = 1,2,3,5,6,7; agreements = 0,4,8
baseline judge flags  = true,false,true,false,true,false,true,false,true
quantized judge flags = false,true,false,true,false,true,false,true,false
```

All nine A/B label combinations occur once per arm. Preparation selects six
rows per arm (12 total), preserving three agreements per arm. Application records
five changes versus A per arm (10 total) and two unusable final rows per arm
(four total); every original ID and exact completion remains in the complete
private output. The filled **partial** 12-row queue refuses native ingestion with
exit 2 and no calibration artifact; the complete 18-row sheet ingests with exit 0.
A fully filled queue containing every key ID can already be native-complete;
this record makes no universal queue-refusal claim.

The native `(usable,unusable,human-refusal,human-compliance,JR-HC,JC-HR)` tuples
are baseline `(7,2,4,3,2,2)` and quantized `(7,2,4,3,1,2)`. Overall errors are
4/7 and 3/7. Directional denominators remain the native three human compliances
and four human refusals; native Wilson intervals are recorded without pooling.
Preparation binds blank-queue bytes, while application binds actual filled bytes
and the complete output. Both retain exact role-specific original hashes/sizes;
all original bytes remain unchanged.

Only fixed aggregates, hashes and a fingerprint are committed. The native
calibration FILE/API retains declared measurement identity, which can include
local model identifiers/paths; this record deliberately whitelists native
counts/intervals/source hashes instead. No per-row IDs, labels, text, salts or
private paths are published. Queues and complete sheets remain private.

This does **not** authenticate labels, raters, source authenticity, blinding,
independent adjudication, preregistration, a real calibrated judge, sensitivity,
model/provider/GPU behavior or scientific GO. Explicit fixture judgments are not
a software consensus policy or evidence of improved human truth. Post-review
agreement cannot replace original independent inter-rater statistics. Native
partial/all-unusable/null behavior is unchanged; review application never
automatically ingests. This is a `validation/` command record, not the capped
reference-report registry.
