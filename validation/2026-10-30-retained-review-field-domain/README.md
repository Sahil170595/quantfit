# Retained-review native CSV field-domain controls

Fictional, local command evidence for the `counts.json` record beside this file.
CPython 3.12.13, pytest 9.0.3 and the unchanged 176-package private CI lock were
used. No model, inference, remote provider, human labeling or scientific campaign
was run.

In `counts.json`, `prepare_exit_code` maps an API receipt to harness 0 and
`RetainedReviewError` to harness 2; CLI cases record the native CLI exit code
returned by its in-process entrypoint.

The existing native capture writer and key/sheet producer create all inputs.
Both retained-label receipts are produced by actual `extract_labels` calls under
an explicit setup-only CSV field limit of 131073 characters. The test restores
the original 131072-character reader limit **before** public API/CLI preparation.
This models genuinely issued artifacts from a wider reader configuration; it
does not claim that default-limit extraction accepted oversized fields. Original
test-owned full sheets are then unavailable, as in the existing retained fixture.

Before the fix, the exact-limit API/CLI controls passed through review, native
full-sheet join, separate extraction and schema-3 ingestion. All four expected
oversized-input refusals failed: preparation returned 0 and created both outputs
for selected and all-agreed rows. The record preserves those six observations,
the unchanged original runtime/test hashes, and the original log/JUnit hashes.
After the two-line admission correction, the same six tests passed. Oversized
inputs refuse before either output; exact-limit complete native behavior remains.

The six cases are in `tests/test_ci_retained_review.py`, already selected by the
existing original-wheel/rebuilt-sdist installed test profiles. No new job or
separate measurement implementation is introduced. Actual installed and hosted
qualification is distinct from this local source run.

## Regenerate the current controls

Run from the repository root in the qualified environment. PowerShell example:

```powershell
$fieldCaseDir = Join-Path ([IO.Path]::GetTempPath()) ("qf-retained-field-" + [guid]::NewGuid().ToString("N"))
python -B -X utf8 -m pytest tests/test_ci_retained_review.py::test_retained_review_respects_native_csv_field_domain -q -p no:cacheprovider "--basetemp=$fieldCaseDir" "--junitxml=$fieldCaseDir.xml"
python -B -X utf8 -c 'import json,pathlib,sys; rows=[json.loads(p.read_bytes()) for p in pathlib.Path(sys.argv[1]).rglob("field-domain-evidence.json")]; print(json.dumps(sorted(rows,key=lambda x:(x["interface"],x["field_characters"],x["mode"])),indent=2))' $fieldCaseDir | Set-Content -Encoding utf8 "$fieldCaseDir-summary.json"
```

Compare the six resulting control outcomes with `after_fix.observations` in
`counts.json`. Fresh native salts and capture timestamps change input hashes;
counts, limits, output/refusal behavior and native join/ingestion facts must agree.
This command regenerates GREEN controls, not the historical RED result by
rewriting production source. Keep private capture, key, sheet and label files
local; publish only the count/hash projection after inspection.

Hashes establish supplied-byte identity, not authenticated producers, real human
judgments, independent evidence, sensitivity, accuracy or scientific GO. The
record bounds serialization compatibility, not a measurement-quality claim.
