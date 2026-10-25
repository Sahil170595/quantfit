# Capture-backed retained review — unreleased 0.43.0

This complete prepare/apply workflow requires 0.43.0 source or a candidate wheel.
Published quantfit 0.41.0 retains the unchanged [full-sheet review](label-review.md).
Use this explicit mode when both completion-free retained label sets, their own
extraction receipts, the shared bound key and the actual capture remain available,
but the original filled sheets need not be available. No original full sheet is read.

```bash
quantfit calibrate review prepare --input-mode retained --capture private.capture.jsonl --key private.labelkey.json --retained-labels-a a.labels.csv --retention-receipt-a a-retention.json --retained-labels-b b.labels.csv --retention-receipt-b b-retention.json --sheet private.review.labels.csv --receipt preparation.json --json
# Explicitly supply refusal, compliance or unusable for EVERY selected row locally.
quantfit calibrate review apply --input-mode retained --capture private.capture.jsonl --key private.labelkey.json --retained-labels-a a.labels.csv --retention-receipt-a a-retention.json --retained-labels-b b.labels.csv --retention-receipt-b b-retention.json --review private.review.labels.csv --preparation preparation.json --out reviewed.labels.csv --receipt application.json --json
# Separate native extraction binds the REAL newly reviewed full sheet, never a fabricated receipt.
quantfit calibrate extract --sheet reviewed.labels.csv --key private.labelkey.json --out new.labels.csv --receipt new-retention.json --json
quantfit calibrate ingest --retained-labels new.labels.csv --retention-receipt new-retention.json --key private.labelkey.json --out calibration.json --json
```

`--input-mode full-sheet` is the default: existing `--sheet-a`/`--sheet-b` calls,
receipts and native strict complete-sheet joins are preserved. Retained mode requires
all five capture/retained/receipt flags above, plus the shared key. Mixed arm modes,
missing roles and implicitly supplied retained mode are usage errors (2).

## What is actually verified

All six originals are held once before text reconstruction; apply additionally
holds the filled queue and preparation. The actual supplied capture's SHA256,
header scope, effective non-null measurement binding, complete pair/arm population,
cross-arm zone/expected consistency, judge flags and every completion digest must
agree with the same supplied v2 key. Legacy/unbound keys refuse. Each retained set
separately passes the existing native CSV/key/receipt validator against **its own**
actual extraction receipt, including exact key/label bytes, complete IDs, labels,
counts and declared capture/binding. No public loader is called twice to reread
shared files, and the native diagnostic rows still omit text.

The preparation contains no IDs, text, labels, salts or paths. It uses
`retained_review_preparation_schema=1`, `input_mode="retained_labels"`, six named
actual input hashes/sizes, blank queue hash/size, complete selected/agreed counts,
per-arm counts, binding fingerprint and explicit capture-verification limits.
`original_sheets_declared.a/b` contains the source-sheet digest from each retention
receipt and **`held_and_validated=false`**. These two sheets are never represented
as held, reconstructed originals or authenticated history. Supplied-byte agreement
does not authenticate source, labeler identity, original blinding or human truth.

Every normalized inequality is selected, including unusable versus usable labels.
The blank opaque-ID sorted queue is the same three-column native subset shape as
full-sheet review. No automatic labels, rater preference or consensus rule is added.
The operator supplies an externally fixed/disclosed judgment rule and fills every
selected label without changing IDs/text. Membership reveals disagreement; a
returning labeler may remember prior labels. Zero selections yield a header-only
queue, and all-selected inputs remain valid complete populations.

Apply revalidates all roles and regenerates the exact preparation, including its
blank queue binding; strict closed/type-sensitive JSON checks reject unknown,
duplicate and incorrectly typed fields. The producer version is an unauthenticated
compatibility declaration used internally, never echoed as caller text in apply.
Filled bytes legitimately differ from blank bytes: apply separately checks exact
selected membership, unchanged text and explicit normalized native labels.
Missing/extra/duplicate IDs, changed text, blanks and invalid labels refuse.
BOM, quoted multiline fields and queue reordering retain native support.

The NEW complete sheet preserves all agreed normalized labels, applies every
explicit selected judgment, and passes the unchanged native full-key join before
publication. The aggregate `retained_review_application_schema=1` receipt binds
all eight actual inputs, the new full sheet and per-arm reviewed/change-vs-A/
unusable counts. Change-vs-A is descriptive, not rater preference or improvement.
Source files remain intact. Nothing ingests automatically. An all-unusable sheet
is a valid transformation while native ingestion still refuses its empty measurement.
Native schema 2 may also separately ingest the new full sheet; schema 3 requires
the truthful new extraction shown above. Neither native calibration schema changes.

## Bounds and local data handling

Capture: 16 MiB and 16,385 native line records. Key: 2 MiB, 4,096 pairs/8,192 IDs,
salt at most 256 characters and existing strict numeric-token bounds. Each retained
CSV: 2 MiB; each retained/preparation receipt: 64 KiB. Queue/full output: 8 MiB;
native CSV admission allows 16,385 logical records, including header/blank records.
One combined logical-input ceiling is 30 MiB + 192 KiB, with individual role limits
and remaining-byte admission during held reads before reconstruction. Preparation
uses at most 22 MiB + 128 KiB of this ceiling. These bound accepted work, not peak
process memory or wall time. Serialized output/receipt limits are checked before
publication; no general preallocation guarantee is made.

All outputs are admitted against **all** actual inputs with the existing private
ordinary-file, link/alias and exclusive staged publisher. Existing targets are
never overwritten. Original modification or a target appearing after admission
refuses. The two outputs are not a filesystem transaction: failure can leave a
new partial/first output or owned cleanup residue; no rollback deletes published
files. Invalid/unsafe native operations return categorical
`invalid_retained_label_review`, exit 2; successful transformations return 0.
Nested JSON errors preserve the existing top-level `command: "calibrate"` envelope.

Keep captures, keys, retained labels and newly completion-bearing queues/sheets
private under [data handling](data-handling-completions.md). The existing maintainer
and single named second-annotator carveout is unchanged: share only the permitted
blinded material, never the key/capture. This mode authorizes no new sharing,
deletion, recipients, additional raters, campaign or upload. Native calibration
files may include declared local model identity; review them before public sharing.
Post-review agreement is not independent inter-rater evidence, sensitivity or GO.

## Python API and evidence

```python
from quantfit.safety.retained_review import prepare_retained_label_review, apply_retained_label_review

sources = ("private.capture.jsonl", "private.labelkey.json", "a.labels.csv", "a-retention.json", "b.labels.csv", "b-retention.json")
prepare_retained_label_review(*sources, review_path="private.review.labels.csv", receipt_path="preparation.json")
# Explicit local operator fill happens here; no default judgment is supplied.
apply_retained_label_review(*sources, "private.review.labels.csv", "preparation.json", out_path="reviewed.labels.csv", receipt_path="application.json")
```

`tools/ci_retained_review.py` regenerates the fictional CLI/API record in
`validation/2026-10-25-retained-review/`: nine pairs/18 rows per interface, original
synthetic sheets removed before review, 12 selected, 10 changes vs A, 4 unusable,
truthful extraction/schema-3 usable denominators 7/7 and partial-queue ingest refusal.
Source tests add zero/all-selected/all-unusable, both receipt roles, capture facts
after rebinding declarations, output/race/combined-budget and privacy controls.
The installed-origin guard runs the actual consumer for Ubuntu/Windows wheel/sdist.
Exact-head hosted qualification is recorded on the PR; a fictional functional
record does not establish human labels, source authenticity, measurement quality,
real study retention/deletion or scientific readiness.
