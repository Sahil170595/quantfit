# Labeling-sheet reconciliation — 0.36.0

Available since quantfit 0.36.0. Existing sheet-building and calibration-ingest
commands retain their behavior.

```bash
quantfit calibrate reconcile --sheet-a rater-a.labels.csv --sheet-b rater-b.labels.csv --key labels.labelkey.json --out reconciliation.json --json
```

The API is `quantfit.safety.reconcile.reconcile_labels(sheet_a_path,
sheet_b_path, key_path, *, out_path=None)`. The CLI requires all four paths. Both
filled sheets must describe the same complete paired population from their shared
private unblinding key. Original native parsers validate opaque IDs, completion
hashes, exact coverage, supported labels, key salt/binding and capture scope.
Matching bytes establish internal consistency, not authenticated authorship.

The new receiver also requires an exact positive integer `capture.n_pairs` up to
4096 and exactly both arms for every pair, including legacy/unbound keys. Those
new command limits do not alter `calibrate ingest` behavior. Duplicate JSON keys,
nonfinite key values and inconsistent/incomplete populations refuse before joining.
Sheets retain the native UTF-8 BOM, quoted multiline, blank export record and
case-normalized label handling. Both sheets must be fully labeled; missing rows
or labels are not silently treated as agreement.

The schema-1 `quantfit.label-reconciliation` result contains:

- Whole-input SHA256 and size bindings under `inputs.sheet_a`, `sheet_b` and `key`;
  these bind the original held bytes, including CSV ordering/encoding.
- `n_pairs`, total `n_rows`, and separate `arms.baseline` and `arms.quantized` blocks.
- A 3×3 integer `matrix` per arm: rows are sheet A, columns sheet B; the explicit
  `label_order` is `refusal`, `compliance`, `unusable`.
- Counts `n_rows`, `n_both_usable`, `n_usable_agreement`,
  `n_usable_disagreement`, `n_one_unusable` and `n_both_unusable` per arm.
  `usable_agreement_rate` divides usable agreement by both-usable rows, or is null
  when that denominator is zero. Unusable labels never improve that denominator.
- `identical_sheet_bytes` for an explicit byte-identical self-control, plus limits
  and fixed unverified-rater/independence/consensus/scientific-GO declarations.

Rows are joined by native opaque ID, so ordering differences do not change the
counts. The output includes no row IDs, per-completion hashes, completion data,
sheet contents, salt or key payload. Matrices remain separate by model arm; no
pooled agreement score, automatic consensus labels, judge epsilon or replacement
calibration is produced. All-unusable input is a valid descriptive result with
null usable agreement rates. Identical files or bytes are allowed but cannot
establish two distinct or independent raters.

Exit 0 means reconciliation completed, including disagreements, all-unusable
results and self-controls. Exit 2 means invalid/unsupported/private input or unsafe
publication. Errors use fixed categories, suppressing private native-parser
diagnostics. Successful JSON uses command `calibrate reconcile`; operational
errors retain the existing parent `calibrate` envelope. Default prose gives
aggregate counts and the output location without printing private input paths.

The receiver holds regular input bytes once, rejects symbolic links/reparse points
and devices, and caps the key at 2 MiB, each sheet at 8 MiB, and all three logical
occurrences at 18 MiB. Aliases/self-controls still consume each occurrence's
budget. Population limits are 4096 pairs and 8192 IDs. Each CSV is limited to
16385 records including its header and blank records. The first excess record is
parsed by the CSV reader, then refused before appending or continuing iteration;
this is not a bound on a single record's materialization beyond the input byte cap.

Existing output guards protect all three held inputs from direct, path and hardlink
aliases. An output parent must exist; outputs cannot follow links. The optional
aggregate file replaces atomically through the existing publication primitive.
This is not a crash or hostile concurrent-filesystem guarantee. Inputs remain
private local data and unchanged by this command; no upload, inference, capture
lookup or calibration ingestion runs.

The counts do not authenticate rater identity, human truth, blinding, independence,
source/weight identity or statistical assumptions. They do not establish
sensitivity, safety, causal improvement, consensus calibration or scientific GO.
`validation/2026-10-18-label-reconciliation/` records fictional command evidence
only; its runner creates private synthetic sheets/key locally and commits only
aggregate outputs and hash receipts.
