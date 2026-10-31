# Source-bound flip adjudication — since 0.46.0

Available since quantfit 0.46.0, this CLI/API workflow records explicit operator declarations
about the original judge-flagged population and renders them alongside unchanged
native statistics. It never authenticates human judgment or changes a gate.

```bash
quantfit adjudicate prepare --report drift.json --capture private.capture.jsonl --review private.adjudication.csv --receipt private.adjudication-preparation.json --json
# Privately fill BOTH labels and flip_class for EVERY selected row.
quantfit adjudicate apply --report drift.json --capture private.capture.jsonl --review private.adjudication.csv --preparation private.adjudication-preparation.json --out adjudication.json --json
quantfit emit model-card --report drift.json --adjudication adjudication.json
quantfit emit model-card --report drift.json --adjudication adjudication.json --calibration-report calibration.json --json
```

`emit model-card` returns the existing string/stdout fragment; it has no `--out`.
Preparation/application success exits 0; invalid, unsafe or excess evidence exits
2 with a categorical error. Model-card emission retains its native success/error
behavior. Neither success is a new safety decision.

## Actual source binding and complete selection

Preparation holds the actual report and capture once. Capture schema 2 must have
a non-null native binding whose identity AND canonical fingerprint match the
actual report. Every pair/arm must exist, with fixed explicit zone/expected values
and matching cross-arm metadata. The whole native tabulation is recomputed from
the captured judge flags and compared against every original drift field, using
the native typed comparator and its computed-float tolerance. Counts, bools,
zones, at-risk populations, verdict, Wilson intervals and MDE cannot be replaced
by merely matching model identity.

The private queue selects exactly unsafe judge-refusal→compliance and safe
judge-compliance→refusal flags, retaining both original completions and all zero,
all-selected and repeated-text cases. Reverse discordances are not selected.
Do not change the protected pair/axis/zone/expected/text columns or remove rows.
Every selected row requires explicit `baseline_label`, `quantized_label` and
`flip_class`; no blank decision is confirmation.

Labels are `refusal`, `compliance` or `unusable`. Both usable labels recompute each
arm's judge correctness. A resolved axis flip requires the operator to choose
`substantive` OR `degenerate`; the tool chooses neither. A resolved non-flip must
be `not-a-flip`. Any unusable arm makes the pair `unresolved`, with that arm's
correctness null. A binary refusal→gibberish flip can be declared degenerate.
These four disjoint counts sum to each axis's original flagged count.

Application holds report/capture/filled queue/preparation once, regenerates the
blank queue and receipt, checks exact selected population and protected text,
and records the legitimately changed filled queue hash separately. The native
closed receiver validates the newly constructed public record before publication.
No source is edited, deleted, automatically labeled or automatically ingested.

## Private inputs, public declarations and bounds

The capture and `*.adjudication.csv` queue contain private text. The preparation
`*.adjudication-preparation.json` is private source evidence too; these suffixes
are ignored. Apply the existing [data-handling rules](data-handling-completions.md),
including dangerous-axis exposure limits and existing named-second-annotator
permission. This feature grants no additional sharing permission.

The public closed record contains fixed vocabulary, complete aggregate counts,
bounded unique pair indices and per-arm SHA256 hashes. Repeated completion hashes
are legitimate. It contains no prompts, completions, arbitrary notes, model IDs,
private paths, key IDs or salts. Producer source checks are declarations to a
receiver lacking the capture. That receiver verifies actual report bytes,
canonical scope, typed count/label/class arithmetic, index bounds and hash shapes;
it cannot freshly verify selected pair membership, text hashes, reading,
authorship or source authenticity. `human_confirmation_verified` remains false.

Native admission caps are report 8 MiB, capture 16 MiB, preparation 64 KiB,
queue 16 MiB and public record 4 MiB, with at most 4096 pairs and 8193 CSV logical
records. Prepared fields must also fit the native `csv.field_size_limit()`
(131072 characters in the qualified interpreter); the process-wide setting is
never changed. Oversized completions refuse before publishing an unusable queue.
Input/row bounds precede reconstruction; serialized queue/record/card
limits are checked before publication/return. Optional calibrated card math
admits a conservative 40,000,000 native work-unit bound before analysis; this is
not a wall-time guarantee. Card string output is capped at 16 MiB.

All producer outputs must be NEW, distinct from every held input and each other,
including aliases. Native staged exclusive publication rechecks inputs and
protects existing files. Outputs publish sequentially, receipt last: a later
failure can leave earlier new files. There is no multi-file transaction or
hostile-filesystem guarantee. Capture-free model-card receiving emits only a string and changes no file.

## API and proof limits

```python
from quantfit.safety.adjudication import prepare_adjudication, apply_adjudication
from quantfit.modelcard import model_card_fragment

prepare_adjudication("drift.json", "private.capture.jsonl",
    review_path="private.adjudication.csv",
    receipt_path="private.adjudication-preparation.json")
# Explicit private operator decisions occur here.
apply_adjudication("drift.json", "private.capture.jsonl",
    "private.adjudication.csv", "private.adjudication-preparation.json",
    out_path="adjudication.json")
card = model_card_fragment("drift.json", adjudication_record="adjudication.json")
calibrated = model_card_fragment("drift.json", adjudication_record="adjudication.json",
    calibration_report="calibration.json")
```

The new card mode shares one held/parsed report with the strict record receiver
and optional native calibration analysis. Plain and calibration-only defaults
retain their output bytes. A demonstrated native scope defect is also corrected:
Python equality conflates boolean/integer/float declarations, so native
`BoundCalibration.match_report` now checks the actual canonical fingerprint too.
Valid scopes/statistics are unchanged; type-coerced mismatches refuse.

The deterministic operator-declared section precedes the existing footer. Native
counts, axes, verdict, Wilson/MDE, calibration, control/sensitivity and QSR status
remain unchanged. Confirmation cannot validate false negatives or null screens.
Fictional CLI/API cases, including absent-capture receiving with/without native
calibration, are regenerable at `validation/2026-10-25-adjudication/`. They establish
instrument behavior, not human truth, rater independence, sensitivity or GO.

## Capture-backed receiving — unreleased 0.47.0

This source-only extension freshly verifies an already produced record against
its actual supplied report and private capture. Public installation remains
0.46.0. It does not require the original queue/preparation, label key or CSV.

```python
from quantfit.safety.adjudication import verify_adjudication
from quantfit.modelcard import model_card_fragment

proof = verify_adjudication("drift.json", "private.capture.jsonl", "adjudication.json",
    out_path="verification.json")  # Optional NEW output; never overwrite.
card = model_card_fragment("drift.json", adjudication_record="adjudication.json",
    adjudication_capture="private.capture.jsonl", calibration_report="calibration.json")
```

```bash
quantfit adjudicate verify --report drift.json --capture private.capture.jsonl --record adjudication.json --out verification.json --json
quantfit emit model-card --report drift.json --adjudication adjudication.json --adjudication-capture private.capture.jsonl --json
```

The API returns a small `adjudication_verification_schema: 1` aggregate proof.
It binds actual SHA256/encoded sizes of all three held inputs, native scope,
original flagged counts, disjoint operator-declared counts and checked population.
`source_verified=true` means **supplied-source consistency only**. Native whole
capture tabulation, exact unique selected index SET, axis and BOTH UTF8 completion
hashes are checked. Entry order is immaterial; repeated text/hashes are legitimate.
Unselected rows still participate in full tabulation. Zero selected and unresolved
declarations are valid consistency outcomes (CLI 0); invalid, unsafe or excessive
evidence is a categorical `invalid_adjudication` refusal (CLI 2). Selection uses
each probe's explicit expected role, never its zone as a surrogate.

The existing schema-1 record, proof-limit declarations, native math/flags/verdict,
Wilson/MDE/calibration and scope rules are unchanged. The new proof freshly
checks source facts, but original queue/preparation hashes remain unverified
operator declarations. It contains no copied entries, labels, completion text,
model IDs or private paths. Hashes cannot authenticate coordinated fabrication,
human reading/truth, rater independence or genuine model execution. Confirmation
cannot validate false negatives or null screens, and grants no sensitivity,
control, QSR or scientific GO. Keep the capture private under existing data rules.

Each report/capture/record role is held once under 8/16/4 MiB bounds (28 MiB total
encoded input profile); native work admission remains 1..4096 pairs. Output
admission checks all held roles before parsing. The report is parsed once and
shared with the existing strict record receiver and native capture helper. No
queue reconstruction or CSV-field check occurs, so long captured text can verify
within the native byte/count bounds even if it cannot be rebuilt as a CSV queue.
A NEW proof output is at most 64 KiB and uses existing exclusive staged publication;
inputs are rechecked before publication or return. Existing files, symlinks,
hardlinks, input aliases and ordinary replacement races refuse. This is not a
hostile-filesystem transaction or a heap/runtime bound.

`adjudication_capture` without a record refuses before I/O. In capture-aware card
mode the same held report/raw bytes feed record verification, capture checking,
optional native 2 MiB calibration (30 MiB total encoded profile), and rendering.
Conditional analysis runs once under its existing work admission. The new section
states the actual capture was read; capture-free/default cards keep their old
bytes and limited wording. No operational timestamp enters the card. Card output
is still a string/stdout, with its existing 16 MiB cap and no `--out`; the existing
CLI `emit --json` envelope retains `report_path`. Only the new proof and section
are path/text-free, not every legacy output.

Regenerable fictional API/CLI producer → explicit synthetic fill → apply → receive
controls are in `validation/2026-10-31-adjudication-verification/`. They remove
only their own original synthetic queue/preparation before receiving, exercise
cards with/without native calibration and retain native outcomes. No inference,
real human labels, GPU, paid calls or network execution is established. Hosted
installed qualification and public release remain separate acceptance steps.
