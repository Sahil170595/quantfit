# Retained labels and native calibration

Status: **unreleased 0.37.0 source candidate**. Published installation remains
`quantfit==0.36.0`; these new commands require the candidate source. Use Python
3.12 for the complete runtime actually qualified by hosted CI; its locked runtime
requires 3.11+, while source/unit support includes Python 3.10.

A filled sheet holds irreproducible labeling work beside regenerable completion
text. This workflow validates the original text hashes once and retains only the
private row identifiers and labels. It does not label anything or establish human
truth, rater authentication, independent labeling, sensitivity or scientific GO.

```bash
quantfit calibrate extract --sheet filled.labels.csv --key private.labelkey.json \
  --out private.labels.csv --receipt retention.json --json
quantfit calibrate ingest --retained-labels private.labels.csv \
  --retention-receipt retention.json --key private.labelkey.json \
  --out calibration.json --json
quantfit resolution --report report.json --calibration-report calibration.json \
  --out conditional-resolution.json --json
```

The original filled sheet need not be available to the second command. These
commands never delete sources. The existing retention protocol still requires
finishing all planned capture-dependent analyses before disposing of text; the
key has no probe zone, so retained rows alone cannot reconstruct per-zone or
at-risk membership. No deletion advice is implied by successful extraction.

`extract` admits the complete native three-column `id,completion,human_label`
sheet and exact native key population, verifies completion digests and every
label, then sorts by row ID and writes UTF-8/LF `id,human_label` CSV. Unusable
labels stay in the retained population. BOM, CRLF, quoted multiline completion
text and original row order do not change the resulting CSV for the same labels.
Hashes in the receipt bind the actual original input bytes, including formatting.

The retained CSV and key remain **private**, never commit them. The extraction
receipt (retention schema 1) carries only schema/version, original sheet/key and
retained-CSV SHA256/size, pair/row/unusable counts, a binding fingerprint or null,
and `capture_sha256_declared` or null. No capture is read: that digest is the v2
key's declaration, not independently verified capture provenance. A legacy-v1
key stays unbound even if extra fields look like v2 provenance.

## Explicit ingestion and consumer compatibility

`ingest --retained-labels` requires the exact receipt and key; it is mutually
exclusive with `--sheet`. The native old `--sheet` path still requires exactly
three columns and produces calibration schema 2. It does not silently accept a
stripped two-column CSV. The retained path admits exact two-column rows and
complete key coverage, verifies every available hash/size/count/fingerprint,
and produces the distinct closed **calibration schema 3**.

Its source has exactly `sheet_sha256` (original full sheet), `key_sha256`,
`retained_labels_sha256`, `retention_receipt_sha256`, and
`capture_sha256_declared`. The original sheet's digest is recorded provenance
from the receipt; ingestion cannot recheck the unavailable original. Rewriting
both the CSV and its receipt can create a different declaration. Hash agreement
is neither human authentication nor evidence of unchanged human judgment.

The API/report file preserves the native exact measurement `binding.identity`
for actual scope matching. **That identity may contain declared local model
identifiers or paths. Treat the calibration file accordingly; it is not a
universally path-free public artifact.** New CLI stdout uses a whitelist of
schema/counts/unmeasured arms/source hashes and binding fingerprint instead of
printing this identity. Extraction stdout is the aggregate receipt. No caller
input/output filenames, per-row IDs/labels, completion text or key salt are
printed by the new modes. Errors are categorical `invalid_retained_labels`.

Native per-arm counts, unusable denominators, directional Wilson intervals and
arm delta use the same arithmetic as full-sheet ingestion. Extraction of an
all-unusable sheet succeeds; either ingestion refuses an entirely unusable
sample. A one-empty-arm report preserves nulls and a qualified partial label.
The native bound loader accepts schemas 2 and 3 only with a valid declared
binding, both measured arms and measured error directions, full
`n_labeled == 2*n_probes` population and recomputed Wilson/delta values.
Actual-report consumers additionally check matching scope when the report is
available. Standalone loading validates the declaration, not an actual-run
match. Unbound/partial evidence is never promoted to a paired bound.

API: `quantfit.safety.retained_labels.extract_labels(sheet_path, key_path,
out_path=..., receipt_path=...)` and
`ingest_retained_labels(labels_path, receipt_path, key_path, out_path=...)`.
`load_retained_labels` holds validated private key/rows/receipt and exact input
buffers for reuse without path rereads. Its private in-memory object is not a
public serialization format or an authentication credential.

## Bounds, refusal and publication

Per-input limits are key 2 MiB, original sheet 8 MiB, retained CSV 2 MiB and
receipt 64 KiB. Extraction therefore holds at most 10 MiB of accepted input
bytes; retained ingestion at most 4 MiB + 64 KiB. Population is 1–4096 complete
pairs (at most 8192 IDs); CSV admission is at most 16385 parsed records including
header and blank records. Native CSV parsing rules/field limits still apply.
Before native JSON/key loops, integer tokens are at most 20 digits, floating
numeric tokens 64 characters and nonempty key salt 256 characters. Duplicate
JSON keys, nonfinite numbers and malformed population are refused. These are
retained-path application admission/work bounds, **not whole-process memory or
runtime ceilings**. Serialized calibration output must fit the native 2 MiB
consumer limit.

Inputs must be regular single-link files with no symlink/reparse ancestors;
held bytes and path/file identities are checked before publication. Outputs
require existing safe parent directories and new independent filenames. Existing
targets, input aliases, hardlinks, symlinks/reparse points and unsafe Windows
alternate-stream/device/trailing-dot or space names are refused. Checks include
parent file identity and normalized basename for Windows extended-prefix aliases.

All output bytes are serialized and staged before exclusive creation of each
new target. There is no replacement or rollback deletion of published outputs.
Exit **0** means the operation completed, not a scientific verdict; invalid,
incomplete, mismatched, unsafe or failed publication exits **2**. If the second
output cannot be published, a newly created first output can remain and the
command still fails. No pair transaction, crash atomicity or hostile concurrent
filesystem guarantee is claimed. An unattested empty stage after an initial
filesystem-identity failure can remain; a failed removal is never called success.

The fictional [offline command record](../validation/2026-10-23-retained-labels/)
and installed wheel/sdist acceptance exercise extract → original-sheet removal →
retained ingest → actual native resolution, without model or network inference.
