# Local annotation chunks (since 0.42.0)

Available since quantfit 0.42.0, this complete prepare/collect workflow
partitions a **complete blank**
native three-column template and reconstructs a new full sheet from explicit
returned judgments. Existing native ingestion and review workflows are unchanged.

## Prepare and collect

Start with the original `calibrate sheet` outputs. Keep the source and key
unchanged. Create a new empty local directory, then run:

```bash
mkdir annotation-parts
quantfit calibrate chunks prepare --sheet blank.labels.csv --key private.labelkey.json --out-dir annotation-parts --rows-per-part 100 --json
```

The directory receives `part-0001.labels.csv`, subsequent numbered parts, and
`annotation.chunkmanifest.json` **last**. Parts preserve source row order, not
unblinded arm/pair/judge order. Only their `human_label` cells should be filled
with `refusal`, `compliance`, or `unusable`. Every source row must return exactly
once. Case and surrounding label whitespace follow native normalization; text
must remain exact. UTF-8 BOMs, quoted multiline text and within-part row
reordering are accepted. Existing labels, including partially filled templates,
are refused at prepare: use the [review workflow](label-review.md) for those.

After explicitly filling every part, supply them in manifest order:

```bash
quantfit calibrate chunks collect --sheet blank.labels.csv --key private.labelkey.json --manifest annotation-parts/annotation.chunkmanifest.json --part annotation-parts/part-0001.labels.csv --part annotation-parts/part-0002.labels.csv --out collected.labels.csv --receipt collection.json --json
quantfit calibrate ingest --sheet collected.labels.csv --key private.labelkey.json --out calibration.json --json
```

The two-part example requires a preparation that actually produced two parts;
repeat `--part` once for every assigned part. No labeling is automated and no
missing part, label, unusable row or completion is dropped. Collection returns a
NEW complete native sheet and an aggregate counts/hash receipt. Ingestion is a
separate command using the unchanged schema-2 consumer. A collected all-unusable
sheet is valid, but native ingestion refuses it because nothing was measured.

### Indexed collection (0.69.0)

Use a repeated `--indexed-part INDEX=PATH` to assemble work returned in
any order. Supply exactly one filled part for every original manifest index.
Indices are explicit even if a file was renamed. A missing, repeated, invalid
or mismatched index refuses collection before either output is written.

```bash
quantfit calibrate chunks collect --sheet blank.labels.csv --key private.labelkey.json --manifest annotation-parts/annotation.chunkmanifest.json --indexed-part 2=second-return.csv --indexed-part 1=first-return.csv --out collected.labels.csv --receipt collection.json --json
```

Use either all ordered `--part PATH` options or all `--indexed-part INDEX=PATH`
options. The SDK alternative to positional paths is `indexed_parts=((2, second_path), (1, first_path))`.
Collection still validates the returned rows against the original assignments
and assembles the original manifest order. Part filenames are only path locators.

For completion-free retention, explicitly extract the **collected** sheet and
then use its truthful receipt with the existing schema-3 consumer:

```bash
quantfit calibrate extract --sheet collected.labels.csv --key private.labelkey.json --out retained.labels.csv --receipt retention.json --json
quantfit calibrate ingest --retained-labels retained.labels.csv --retention-receipt retention.json --key private.labelkey.json --out retained-calibration.json --json
```

Library functions are `quantfit.safety.annotation_chunks.prepare_annotation_chunks`
and `collect_annotation_chunks`. Prepare takes source/key paths and keyword
`out_dir`, `rows_per_part=100`, `annotator_role="maintainer"`,
`annotator_name=None`. Collect takes source/key/manifest paths and an ordered
tuple of returned part paths, with keyword `out_path` and `receipt_path`.
Both return only aggregate counts, hashes, explicit attribution and limits.
Failures raise categorical `AnnotationChunksError("invalid_annotation_chunks")`;
CLI operational refusals emit the native envelope and exit 2, success exits 0.

## Inspect indexed returns (0.58.0)

Quantfit 0.58.0 can inspect complete returned parts before all other parts
arrive. Assign each returned
CSV its **original manifest index** explicitly; arrival order is irrelevant:

```bash
quantfit calibrate chunks validate --sheet blank.labels.csv --key private.labelkey.json --manifest annotation-parts/annotation.chunkmanifest.json --part 4=returned-part-4.labels.csv --part 2=returned-part-2.labels.csv --out inspection.json --json
```

This example assumes an actual four-part preparation. A valid subset exits 0
as an inspection, with `complete: false`, received `[2, 4]` and missing `[1, 3]`.
Each supplied part must itself be complete, with native valid explicit labels
and unchanged text. No incomplete part, unknown index or substituted partition
is admitted. Repeat the command with a **new output path** as other parts arrive.
Even `complete: true` only describes part coverage: run the original `collect`
in manifest order and then `ingest` separately. No labels are inferred, dropped
or combined into an epsilon by inspection; `unusable` is a valid explicit label.

The API is `quantfit.safety.annotation_chunks.validate_annotation_returns`:

```python
result = validate_annotation_returns(
    "blank.labels.csv", "private.labelkey.json", "annotation.chunkmanifest.json",
    ((4, "returned-part-4.labels.csv"), (2, "returned-part-2.labels.csv")),
    out_path="inspection.json",  # optional for the API; required by CLI
)
```

Use a nonempty tuple of `(int, str)` pairs (maximum 128); indices are strict
positive integers, not bools, floats or inferred filenames. CLI index spelling
is canonical ASCII decimal (`2=PATH`, not `02=PATH`). Duplicate indices and file
roles are rejected. The original source, key and exact stored-version manifest
are required on every inspection. Preparation is fully regenerated before any
supplied partition is joined through the native receiver. All native input,
record and aggregate byte limits below still apply; inspection receipts are
bounded by the existing 64 KiB receipt cap and use exclusive checked publication.

The closed receipt contains counts, expected/received/missing indices and raw
byte SHA-256/size bindings. It excludes private paths, row IDs, text, label values
and annotator names. Categorical failure is
`AnnotationChunksError("invalid_annotation_returns")` or CLI exit 2; no partial
receipt is published after a late-invalid row. Byte agreement does not verify
human identity or truth, rater independence, sensitivity, safety or scientific GO.
Current fictional [regressions](../validation/2026-11-07-annotation-returns/README.md)
cover API and actual CLI receiving; hosted installed proof is separate.

## Integrity and private handling

Preparation validates all blank IDs, unique full-key coverage and completion
digests against the actual held key. The private manifest binds exact original
sheet/key bytes and every regenerated blank partition. Filled file hashes are
expected to change: collection checks membership and text against the regenerated
blank partitions, records actual filled hashes separately, then validates the
entire newly serialized sheet through the unchanged native `_join` before writing.
Key capture scope/digest remain declarations: this workflow does not read a capture.

The source, key, manifest and each returned part are held once. Duplicate/aliased
input paths, unknown/missing/overlapping rows, source/key byte drift, contradictory
manifest bindings or changed text,
blank/invalid returned labels, existing outputs and output aliases are refused.
Native checked staging and exclusive creation protect existing files and detect
ordinary source/ancestor changes. This is not protection against every hostile
filesystem race or an atomic directory transaction: an interruption or later
publication failure can leave earlier **new** parts or a new collected sheet.
The manifest is published last; an incomplete directory is not a successful preparation.

The native limits remain 4,096 pairs / 8,192 rows, 8 MiB per sheet and 2 MiB per key.
There are at most 128 parts, 2 MiB of private manifest and 10 MiB total generated
outputs. Combined held inputs are bounded by
`2*8 MiB + 2 MiB + 2 MiB + 128*512 bytes` (20 MiB + 64 KiB).
Returned CSV record limits are twice their assigned rows plus one header, including
blank records; source and final full-sheet scans use the native 16,385-record cap.
The resulting combined CSV work is bounded by `3*16,385 + 128` records. Input,
row and part bounds are admitted before partitioning, and native record limits
bound CSV work. Serialized part, manifest and complete-output byte limits are
checked before publication; this is not a hard preallocation-memory guarantee.
No HTTP, models, external queue or annotation service is involved.

All text-bearing sheets remain ignored `*.labels.csv`; the private manifest is
ignored `*.chunkmanifest.json`. Neither manifest nor key goes to an annotator or
into git. Aggregate CLI/receipt output excludes completion strings, opaque IDs,
salt and input paths; the manifest itself carries private IDs and must stay local.
Only the [existing data-handling decision](data-handling-completions.md) permits
the maintainer plus **one named second annotator**, sharing only blinded parts
under identical local retention/deletion rules. This capability grants no new
recipient, redistribution or scientific collection permission.

For that existing carve-out, prepare can record `--annotator-role named_second
--annotator-name "Name declared in the published record"`. The name is required
for this role and bounded to 120 characters; it is an operator declaration, not
authenticated identity. Keep attribution alongside the published number as the
protocol requires. The tool sends nothing and deletes no source material.
Chunks are partitions of one population, not independent samples or raters.

When that existing authorization applies, create a fresh empty private directory
and supply the declared attribution explicitly:

```bash
quantfit calibrate chunks prepare --sheet blank.labels.csv --key private.labelkey.json --out-dir named-annotation-parts --rows-per-part 100 --annotator-role named_second --annotator-name "Declared Annotator" --json
```

Regenerable fictional CLI/API/native-consumer evidence, including adverse
controls and privacy checks: [functional record](../validation/2026-10-25-annotation-chunks/README.md).
Fixture judgments establish neither human truth, rater independence, sensitivity,
safety, QSR v1 readiness nor scientific GO.


## Complete-return requirement and JUnit (0.65.0)

Available since **0.65.0**.
Only `calibrate chunks validate` adds these options:

```bash
quantfit calibrate chunks validate --sheet blank.labels.csv --key private.labelkey.json --manifest annotation-parts/annotation.chunkmanifest.json --part 2=returned-part-2.labels.csv --require-complete --junit inspection.xml --out inspection.json --json
```

The existing typed SDK function adds keyword-only `require_complete=False` and
`junit_path=None`. Policy must be an exact boolean before private IO. Omitted and
explicit False retain exact schema-1 JSON and human output, even when XML is requested.
A valid partial default remains exit 0. Opt-in True emits a schema-2 receipt, preserving
all original top-level expected/received/missing indices and row counts, with only
this closed `completeness_requirement` block:

```json
{"requirement_schema":1,"require_complete":true,"native_validation_exit_code":0,"exit_code":4}
```

Native full manifest reconstruction uses its **stored producer version** and exact
encoded equality. Every supplied part is then fully joined against its original
assigned IDs, text and completion digest before completeness is considered. A late
bad row exits 2 even when other original parts are missing, and publishes no fabricated
success XML. Valid missing required coverage exits 4; complete coverage exits 0,
including all-unusable returns. Inspection does not collect, ingest, discover files,
compute an epsilon or authenticate labels/rater identity. Existing 1–128 explicit
indexed roles, exact integer indices, native byte/CSV/work limits and assurance flags
remain unchanged. Complete coverage describes a file census, not usable calibration.

Requested JUnit has one fixed overall case and every original part index in numeric
order (maximum 129 cases). Supplied native-valid parts pass. Missing parts skip when
coverage is optional, with overall exit 0; required missing parts error, including the
overall case, with exit 4. Complete all-unusable returns pass this coverage check.
The renderer accepts only a validated frozen private projection of original per-part
row counts, received indices, complete row census, exact policy and a safe manifest
hash. Names/messages are fixed or numeric and properties contain only counts/hash;
no annotator names, IDs, paths, CSV rows, salts, text, labels, arbitrary exceptions
or raw manifest enter XML. Standard ElementTree serialization is bounded to 64 KiB
without truncation. JSON-only inspection does not generate XML or apply the XML cap.

All explicit roles are held once. **After those private bytes are held**, both requested
sinks are admitted together against held sources, before CSV parsing or rendering.
This is not a pre-read output-admission claim. Native validation, requirement and all
requested buffers finish before one existing `retention_io.publish` call. With no
outputs, the original held-file checks still run. Valid exit-4 JSON/XML are published
before the CLI emits exit 4; any output failure takes operational exit 2 instead.

Publication uses staged buffers and exclusive `O_EXCL` target creation. It is **not
per-file atomic and not a pair transaction**: an interrupted file or a first output
may remain if a later write fails. Native source stamps are checked after all staging,
**before the first target creation**, with no source recheck between outputs. A source
mutation before that checkpoint refuses before targets; a source-only mutation after
it may still return the unchanged held snapshot. Target/ancestor substitution between
outputs still refuses and preserves the first output and foreign work. No rollback,
source deletion, target overwrite or stronger race guarantee is added.

Fictional native SDK and actual OS CLI, original/stored-version parity, maximum
population, privacy, cap and publication evidence is in
[the local functional record](../validation/2026-11-14-annotation-return-completeness/README.md).
The existing four installed consumers retain collection, native schema-2/schema-3
ingest and the all-unusable ingest refusal. Hosted OS/matrix/canonical typing/CodeQL
and clean installed proof remain separate gates; no jobs, uploads, dependencies,
model/judge/provider work, label truth, sensitivity or scientific GO are introduced.
