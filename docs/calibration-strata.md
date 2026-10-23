# Descriptive calibration strata

Status: **unreleased 0.38.0 stacked source candidate**, depending on the retained-label
0.37.0 candidate. Published installation remains `quantfit==0.36.0`. Python source/unit
support includes 3.10; the complete locked runtime requires 3.11+, actually qualified
on hosted Python 3.12. These software diagnostics start no human calibration study.

```bash
quantfit calibrate strata --capture private.capture.jsonl --key private.labelkey.json \
  --sheet filled.labels.csv --out strata.json --json
quantfit calibrate strata --capture private.capture.jsonl --key private.labelkey.json \
  --retained-labels private.labels.csv --retention-receipt retention.json \
  --out retained-strata.json --json
```

The full-sheet and retained-label modes are mutually exclusive. Retained mode requires
the exact extraction receipt, produced by [the retained-label workflow](retained-labels.md).
**Both modes require the original capture** for zone, expected behavior and original judge
observations. Neither the key nor the aggregate calibration contains all that metadata.
These commands never delete sources or authorize early text disposal; finish the existing
retention protocol's planned analyses first.

API: `quantfit.safety.calibration_strata.analyze_calibration_strata(capture_path,
key_path, sheet_path=..., out_path=...)`, or the keywords `retained_labels_path=...`
and `retention_receipt_path=...` instead of `sheet_path`. The shared
`load_calibration_inputs` admission returns held private buffers and validated paired
rows for native diagnostics without rereading paths; it is not an authentication token.

## Counts and denominators

`all_rows` describes every complete captured pair. `observed_at_risk.dangerous` selects
pairs with **expected unsafe AND baseline judge refusal**.
`observed_at_risk.overrefusal` selects pairs with **expected safe AND baseline judge
compliance**. These are the existing instrument's observed predicates, not selections
based on human truth or label usability. Both arms of every selected pair remain present,
including an unusable label on either arm.

Every cohort includes `n_pairs_selected`, `n_rows_selected` and separate native
`baseline`/`quantized` arm blocks. An arm's `n` counts usable labels; `n_unusable` counts
its unusable labels. Directional false-compliance rates use human-refusal denominators;
false-refusal rates use human-compliance denominators. Native per-arm and directional
Wilson intervals are recomputed from those counts; no pooled `2n` rate or paired
independence claim is introduced. An empty or all-unusable group has null epsilon,
Wilson `[0,1]`, and explicit `unmeasured_arms`. Completing those diagnostics still exits 0.

Each cohort also includes **all three** fixed `zones`: `clear_safe`, `clear_unsafe`,
`borderline`, including empty groups. Per QSR v0 §2.2, zone is a transparency grouping,
**not an independent statistical stratum**. Expected safe/unsafe behavior is validated
independently of zone; borderline/unsafe is valid. Both arms must agree on both metadata
values. These conditional diagnostics do not establish transfer to the at-risk
population assumed by MDE A1, authenticated labels or a replacement calibration.

## Exact input agreement and provenance

A **v2 key is required**: its capture SHA256 must match the exact held capture bytes.
The key's capture header projection (`created_utc`, `baseline`, `quant`, `n_pairs`),
effective declared binding and every pair/arm's judge flag and completion digest must
match. Opaque IDs bind pair/arm through the salt; they do **not** bind judge flags, so
checking only IDs would miss an edited key. Native nonempty header strings are required,
but their timestamp/model declarations are not authenticated.

Native capture schema 1 with a v2 key remains usable and explicitly unbound; any extra
legacy-header binding is ignored as in native sheet creation. Capture schema 2 requires
its explicit binding or null. A regenerated or reformatted capture does not match an old
key's exact byte hash even if its rows look the same. Self-consistent rewriting of all
inputs can create a new declaration; agreement is not source authenticity.

Full mode reuses native three-column sheet/text-hash/label admission. Retained mode
reuses the strict receipt/CSV/key loader. `inputs` records only hashes/sizes of buffers
actually read. `original_sheet.held_and_validated` is true only for a present original
sheet whose held bytes passed the native join; in retained mode its original hash/size
are receipt declarations and the marker is false. It does not authenticate historical
human judgment. Full/retained counts and Wilson values agree for the same supplied labels.

The diagnostic file and CLI output have fixed aggregate vocabulary, counts/statistics,
whole-input hashes and a binding fingerprint or null. They include no private row IDs,
labels, text, salt, caller paths or key-derived model/engine scope. This differs from
native calibration files/API, which retain exact measurement identity. The strata JSON
has its own schema; the native bound-calibration loader refuses it. No gate is wired to
it and `replaces_calibration`, `gate_eligible` and all truth/independence/sensitivity/GO
claims are false.

## Limits, failure and evidence

Accepted per-input caps: capture **16 MiB**, key **2 MiB**, full sheet **8 MiB**,
retained CSV **2 MiB**, receipt **64 KiB**. Full mode holds at most **26 MiB** of accepted
input bytes; retained mode at most **20 MiB + 64 KiB**. Native population is bounded at
4096 complete pairs / 8192 row IDs before native population construction. Capture
admission counts at most **16385 physical records**, including blank records and native
Unicode line separators, before allocating a split-line list; nonblank records must
be exactly header plus `2*n_pairs` rows. Every JSON line is checked for duplicates,
nonfinite numbers and the retained loader's 20-digit integer / 64-character floating
numeric token bounds. Key salt is at most 256 characters; native CSV record/field rules
remain in force. Encoded output is at most **256 KiB**. These bound accepted input and
work, not whole-process memory or a universal runtime ceiling.

Regular single-link held files, no symlink/reparse ancestors, path/file identity
checks, output aliases and Windows naming checks reuse the accepted retained-label I/O.
The output must be new and independent of every input. Publication is staged and
exclusive, never replacement; filesystem/interruption failures are errors even if a
new partial output remains. No hostile concurrent-filesystem or crash-atomic guarantee
is claimed. Invalid, mismatched, unsupported or unsafe input/output exits categorical
**2** (`invalid_calibration_strata`); completed descriptive computation exits **0**,
including empty/all-unusable results.

The fictional [command record](../validation/2026-10-23-calibration-strata/) and existing
Ubuntu/Windows wheel/sdist acceptance exercise both label modes, source-sheet absence,
native Wilson groups and refusal as replacement calibration, without inference or assets.
Fresh hosted qualification is distinct from local functional evidence. Default CodeQL
runs at the protected-main boundary; the unprotected stacked base does not create a fresh
run, and inherited predecessor scanning is not a new scan of this change.
