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
