# Private blinded annotation packets — since 0.55.0

This additive workflow renders **every native 2N row**, including concordant
pairs, zero flagged pairs and duplicate completion strings. It is independent of
0.50's unblinded flagged-pair adjudication page. The original native blank sheet,
private key and original chunk manifest are the sole supplied population. There
is no capture read, reblinding, salt regeneration, repartition, model call or
new calibration/statistical engine.

## Produce locally

First create the native blank/key and original chunks using the existing
[annotation-chunk workflow](annotation-chunks.md). Keep those originals unchanged.
Then create an existing empty private output directory:

```bash
mkdir private-recipient-pages
quantfit calibrate chunks packets --sheet blank.labels.csv --key private.labelkey.json --manifest annotation-parts/annotation.chunkmanifest.json --out-dir private-recipient-pages --json
```

The public SDK has the same explicit inputs:

```python
from quantfit.safety.annotation_packets import prepare_annotation_packets
receipt = prepare_annotation_packets(
    "blank.labels.csv", "private.labelkey.json",
    "annotation-parts/annotation.chunkmanifest.json",
    out_dir="private-recipient-pages",
)
```

The producer holds the three originals once and reconstructs **all** native
parts with `annotation_chunks._preparation`, the stored manifest version and
validated declared annotator. Canonical typed equality checks the entire
manifest. An older valid manifest is not rejected merely because the current
tool version differs. Each assigned ID/text and full native membership is checked.

The output contains only `part-0001.annotation.html`, etc., one per native part.
The bounded aggregate API/JSON receipt contains schema/version, input and page
hashes/sizes, counts, native round-trip bounds and explicit false-authentication
flags; it contains no row IDs, strings, salt, private key or caller paths.
CLI logical refusal exits 2 with `invalid_annotation_packets`; argparse can
reject invalid syntax before dispatch. Refusal does not authorize repairing or
replacing the original private inputs.

## Recipient page and explicit export

Open the assigned page locally in an ordinary browser. Its fresh closed payload
contains only `annotation_packet_schema: 1`, assigned `[opaque_id, exact_string]`
rows, the native assigned CSV filename and `max_csv_bytes`. No pair, arm, judge,
zone, expected outcome, key, salt, capture, unblinding manifest, other part or
global population metadata is embedded. Identical strings remain separate rows.
Exact text may itself be identifying; this is structural blinding, not perceptual
anonymity or an independent-rater guarantee.

Every choice starts blank. Select **refusal**, **compliance** or **unusable** for
each row explicitly. The page does no labeling, sending, remote request, asset
load or storage. Export is refused until every assigned row has a valid choice.
It downloads the assigned `part-NNNN.labels.csv`, with fixed columns
`id,completion,human_label` and quoted UTF-8/CRLF records. The held original IDs
and strings remain the export source even after display/JSON-element DOM edits.
Formula-like text, quotes, CR, CRLF, NUL and Unicode are preserved exactly;
**no spreadsheet formula-safety claim** is made.

## Collect, then ingest separately

Return filled files through the existing authorized private channel. Save them
separately from the original blank chunks. Supply **every** returned part, in
its original manifest order, to unchanged native collection:

```bash
quantfit calibrate chunks collect --sheet blank.labels.csv --key private.labelkey.json --manifest annotation-parts/annotation.chunkmanifest.json --part returned/part-0001.labels.csv --part returned/part-0002.labels.csv --out collected.labels.csv --receipt collection.json --json
quantfit calibrate ingest --sheet collected.labels.csv --key private.labelkey.json --out calibration2.json --json
quantfit calibrate extract --sheet collected.labels.csv --key private.labelkey.json --out retained.labels.csv --receipt retention.json --json
quantfit calibrate ingest --retained-labels retained.labels.csv --retention-receipt retention.json --key private.labelkey.json --out calibration3.json --json
```

The two-part command is an example: enumerate every actual part. Native collect
checks complete assigned IDs, byte-exact strings, typed original manifest,
explicit labels and original input identities. Missing/duplicate/foreign or
changed rows are refused. The page does not replace that authority. Native
schema-2 and schema-3 per-arm arithmetic is shared. All-unusable calibration is
refused; one empty arm stays explicitly unmeasured with null epsilon. Missing
directional denominators leave native `mde_epsilon_upper` null, even when one
observed direction has zero errors. No detector resolution follows from these
software fixtures.

## Limits and publication

Existing native limits remain: 4096 pairs/8192 rows, 128 parts, 8 MiB blank/full
sheet, 2 MiB private key and 2 MiB manifest. Existing CSV parsing/field constraints
also apply: the qualified Python 3.12 process has the standard-library default
131072-character field limit. An 8 MiB file allowance does not admit an 8 MiB
single cell; this feature does not change the process-wide CSV parser limit.

Before any page is published, every worst fully quoted filled part must fit
8 MiB, **all** filled parts must fit the native collector's remaining combined
input budget after the three held originals, and the worst reconstructed full
native sheet must fit 8 MiB. The native collection receipt (64 KiB) and combined
sheet/receipt output cap (10 MiB) are checked too. Pages are limited to 32 MiB
each and 64 MiB total including their aggregate receipt. ASCII/less-than JSON
escaping can expand input: valid native inputs can still refuse presentation.
No truncation, completion deduplication or favorable part selection occurs.

All pages and aggregate bounds are admitted before native exclusive publication
into the existing empty directory. Native held-file stamps, input/output roles,
ancestor and exclusive-output checks remain in force. Per-file publication is
not a directory transaction: an I/O failure may leave earlier new pages. Keep
those private and inspect them; this is no rollback, hostile-filesystem, heap,
or browser-memory guarantee.

## Privacy and evidence

`*.annotation.html` and downloaded `*.labels.csv` contain private completion text.
Never commit, upload, attach or capture browser screenshots/traces/video of
them. The narrow ignore is only an accidental-add backstop. The dated
[data-handling addendum](data-handling-completions.md#2026-11-02-source-addendum-blinded-annotation-packets-unreleased-054)
retains the existing one-named-second-annotator, explicit-subsample permission
and terminal retention policy. Producing all rows locally grants no authority
to share all of them, add a recipient or permit onward sharing.

`validation/2026-11-02-annotation-packets/` records fictional controlled source
API/OS CLI/native collection and ingestion. Installed acceptance uses four
profiles (Linux/Windows × wheel/sdist-rebuilt); the two Linux profiles additionally
run the hosted private browser fill/download/collect/ingest controls. These are
separate from local source qualification. No browser runs locally. No real
human labeling, model generation, source/rater authentication, measured
independence, transferred sensitivity or scientific GO is established.
