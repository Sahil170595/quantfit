# Descriptive two-judge diagnostics — unreleased 0.49.0

`quantfit.safety.calibration_judges.analyze_calibration_judges` receives two
independent native capture/key/label suites and writes a new aggregate diagnostic:

```python
analyze_calibration_judges(
    capture_a, key_a, capture_b, key_b,
    sheet_a=full_sheet_a,
    retained_labels_b=retained_b, retention_receipt_b=receipt_b,
    out_path="new-judges.json",
)
```

Each side independently requires exactly one full `sheet_a`/`sheet_b`, or its
`retained_labels_a`/`retained_labels_b` and own matching retention receipt.
Both mode suites are checked before IO. All roles are held once before output
preflight and parsing; repeated canonical files are physically held once while
every logical role is charged independently. Native role caps remain 16 MiB
capture, 2 MiB key, 8 MiB sheet, 2 MiB retained labels and 64 KiB receipt, under
one 52 MiB logical total. Native maximum is 4,096 pairs per judge, not 8,192
pairs. Byte and encoded-output limits are not heap, CPU-time or authenticity bounds.

Every own v2 key must bind a complete schema-2 capture, actual capture SHA,
completion digests, judge flags and cross-arm metadata. Both judges must declare
the exact native completion-only contract, truncated to **512 judge tokens**.
Only judge ID and revision may differ in common protocol identity. Environment,
decode settings, engines, weights and probe scope remain type-sensitive under
the native canonical fingerprint. Different IDs do not establish independence.

The join uses the complete canonical `(pair, arm)` population from each own key,
never opaque salted IDs, file order, an intersection or text-based rematching.
Actual completion strings, zone, explicit expected value and normalized ternary
truth labels must agree at every cell, including unusable labels. Repeated
identical text at different indices is legitimate and stays distinct. Equal
strings do not imply equal tokenization, truncation, prompts or real execution.

Each judge's native per-arm/directional error blocks retain their Wilson
intervals and own truth denominators. Whole-N flag matrices include unusable
truth. Error-concordance matrices use only that arm's usable truth and reproduce
the native judge-error margins; they do not drop a usable arm merely because the
other arm is unusable. Four pair-level usability patterns are counted explicitly.
All-unusable diagnostics complete with null epsilon and native [0,1] intervals.
Existing calibration ingestion still refuses an entirely unusable calibration.
No pooled epsilon, winner, significance test or calibration replacement is added.

Full sheets and retained CSVs keep all native header/cell/extra-row admission.
The retained path does not rebuild a completion-bearing CSV, so long captured
strings are bounded by capture bytes rather than an unrelated CSV-field limit.
The complete aggregate file and complete actual CLI JSON envelope are each
limited to 256 KiB, admitted before native publication. These are independent
per-buffer caps, not a combined 256 KiB claim. The CLI reuses admitted bytes.
Output is required and exclusively creates a new target: existing files and
input aliases are refused, with native input/ancestor rechecks and owned-stage
cleanup. No overwrite, paired transaction or hostile-filesystem guarantee is made.

Completion means descriptive protocol completion (exit 0); invalid, mismatched,
unsafe or excessive evidence exits 2. Output contains aggregate counts, hashes,
own/common fingerprints and fixed limits only, without private text, keys,
salted IDs, full identity dictionaries or paths. Retained original-sheet hashes
remain unheld declarations, explicitly distinct from a full held sheet.
This does not authenticate human labels, source/weights, actual judge execution,
rater independence, sensitivity, null clearance or scientific GO. No real models,
providers, GPU, paid calls or uploads are needed by the fictional controls in
`validation/2026-10-31-calibration-judges/`. Public installation remains 0.46.0.
