# Explicit local label review (quantfit 0.40.0)

Unreleased 0.43.0 additionally supports explicit [capture-backed retained review](retained-review.md)
when original full sheets are unavailable. The default full-sheet calls and receipt
contract documented below remain unchanged and available in published 0.41.0.

This workflow prepares a private disagreement subset, accepts explicit operator
judgments, and writes a new **complete** native labeling sheet. Both preparation
and application are available in quantfit 0.40.0; install `quantfit==0.40.0`. No data is sent to anyone and no reviewer, labeling
rule or protocol is invented by software. Use the externally fixed/disclosed rule
appropriate to your existing [calibration protocol](judge-calibration-v0.md).

```bash
quantfit calibrate review prepare --sheet-a a.labels.csv --sheet-b b.labels.csv --key private.labelkey.json --sheet private.review.labels.csv --receipt review.json --json
# Locally supply refusal, compliance, or unusable for EVERY selected row.
quantfit calibrate review apply --sheet-a a.labels.csv --sheet-b b.labels.csv --key private.labelkey.json --review private.review.labels.csv --preparation review.json --out reviewed.labels.csv --receipt application.json --json
# Separate, unchanged native ingestion; neither review command runs it automatically.
quantfit calibrate ingest --sheet reviewed.labels.csv --key private.labelkey.json --out calibration.json --json
```

## Prepare

The command holds both complete original sheets and their shared key once before
parsing. The accepted bounded/strict key reader and **both unchanged native full
sheet joins** check complete IDs, completion digests and valid labels. Native
label normalization strips whitespace and lowercases `refusal`, `compliance` and
`unusable`. Every unequal normalized A/B label is selected, including inequalities
involving unusable. Equal unusable labels are agreements too.

The private queue has exactly `id,completion,human_label`, opaque-ID sorted, with
unchanged completion strings and blank labels. It withholds arm, pair, judge flags
and the initial labels. Membership reveals disagreement, and a returning labeler
may remember earlier labels/IDs; this is **not authenticated blinding**. A zero-
disagreement prepare emits a valid header-only review subset.

The closed preparation receipt contains `review_preparation_schema=1`, producer
version, exact role-specific input hashes/sizes (`sheet_a`, `sheet_b`, `key`), the
generated **blank queue** hash/size, total/selected/agreed counts and per-arm counts,
a fingerprint or null, key-declared capture hash or null, fixed selection/limits
and scope. It contains no IDs, per-row labels, text, paths or native model identity.
No capture is read here: scope/digest remain key declarations, not actual capture
verification or authentication. Legacy key-v1 remains explicitly unbound even if
extra scope-like fields exist.

## Explicitly fill and apply

Fill every selected row with one supported label; leave its ID and completion
unchanged. Do not add/remove rows. There is no default choice, preferred rater or
blank-as-agreement rule. Application holds all five inputs before validation,
rechecks the complete originals and regenerates the selected population and blank
queue. The original preparation must match exact role-specific bytes and counts.
Strict JSON rejects duplicates/nonfinite/oversized numeric tokens; a canonical,
type-sensitive closed comparison distinguishes `true` from `1` and `1.0` from `1`.
Its producer version is a declared compatibility field checked internally, never
echoed as caller-controlled text in application output.

Operator edits naturally change the filled queue hash. Apply therefore checks the
exact selected subset, unchanged completion strings and explicit normalized labels;
it does **not** require filled bytes to equal the blank queue hash. BOM, quoted
multiline fields and row reordering are supported. Header-only input is valid only
for zero selections. Missing/duplicate/extra/unknown IDs, modified agreement rows,
changed text or blank/unknown labels refuse before output. The native full-sheet
parser is not weakened to accept subsets.

The new complete private sheet includes every original ID and completion. Agreed
normalized labels remain unchanged; only selected rows receive supplied judgments.
A zero-selection apply still writes a complete no-op sheet. `n_reviewed` counts
explicit supplied values, not authenticated reviewer activity. `n_changed_vs_a`
is a descriptive role-A comparison, not improvement, consensus or rater preference.

The closed application receipt contains `review_application_schema=1`, current
software version, actual hashes/sizes of A/B/key/preparation/**filled** review,
complete-output hash/size, total/reviewed/change-vs-A/unusable counts and per-arm
counts, fingerprint/key-declared capture digest and fixed proof limits. Neither
receipt contains its own hash. Receipts themselves can be hashed externally.

Fresh preparation after A/B swap, row order/BOM changes or normalized label
reserialization can produce the same logical selection/blank queue. An **existing**
receipt still refuses changed original role bytes unless those bytes actually
coincide. Freshly reviewed output may agree logically after swap, while its role-A
change count has a different reference.

## Native ingestion and interpretation

Blank queues refuse native ingestion because labels are missing; filled **partial**
queues refuse because IDs are missing. If every row was selected and filled, that
CSV may already be a complete native sheet: native ingestion is intentionally
unchanged and no provenance marker or extra ingest gate is added. Apply supplies
the general complete merge and bound application receipt.

The separately requested native ingestion keeps schema 2, per-arm usable/unusable
and directional denominators, null rates and native Wilson intervals. If the whole
applied output is unusable, review application succeeds as a transformation and
native ingestion refuses its empty measurement. Selecting unusable for every
disagreement does not imply all output is unusable when agreed usable rows remain.
Native calibration FILE/API retains declared measurement identity and may include
local model identifiers/paths; inspect it before public sharing. New review
receipts/stdout summaries exclude that identity.

Post-review agreement never replaces original independent inter-rater statistics.
No labels/raters, rule preregistration, source authenticity, independent adjudication,
human truth, sensitivity or scientific GO are authenticated. No statistical
recalibration or automatic consensus is performed.

## Bounds, publication and evidence

Accepted key: 2 MiB, at most 4,096 pairs/8,192 IDs, salt at most 256 characters,
strict integer/float token bounds. Each original/review CSV: 8 MiB and at most
16,385 **logical CSV records**, including blank records; multiline fields do not
mean one physical line per record. Preparation receipt: 64 KiB. Accepted held
input totals are at most 18 MiB for prepare and 26 MiB + 64 KiB for apply. These
bound accepted bytes/work, not whole-process memory or universal runtime.

Both private CSV output (8 MiB) and aggregate receipt (64 KiB) are serialized and
capped before the unchanged [write-once publisher](retained-labels.md) runs. Existing
files, links/junctions, special files, hard links, unsafe Windows names and target
aliases are refused. Success requires completed flush/fsync/close and owned-stage
cleanup. Failed publication can leave a new partial/first output; cleanup failures
can leave residue. This is not a hostile-filesystem transaction, and no rollback
deletes a published file. Originals remain intact. Invalid/unsafe operation returns
categorical `invalid_label_review` exit 2 with private causes suppressed; completed
prepare/apply return 0 without a readiness or truth judgment. Nested leaves accept
`--json`; failures preserve the existing top-level `command: "calibrate"` envelope.

`validation/2026-10-23-label-review/` records a fictional nine-pair/18-row actual
prepare/fill/apply/native-ingest workflow and partial-queue refusal. The unchanged
installed-origin guard exercises this workflow for Ubuntu/Windows wheel/sdist.
Local source, protected-main security, hosted installed/CPU and versioned release
qualification remain separate requirements. Keep queues, keys and full sheets private under
[the data-handling policy](data-handling-completions.md); this workflow authorizes
no new recipients or automatic source deletion.
