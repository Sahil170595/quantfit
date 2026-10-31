# Whole-target adjudication screens — unreleased 0.48.0

This source candidate depends on the unreleased 0.47 capture-backed receiver.
The public install remains quantfit 0.46.0. This workflow receives saved files;
it runs no models, CSV reconstruction, key lookup or original queue/preparation.

```python
from quantfit import summarize_screen_adjudication

summary = summarize_screen_adjudication(
    "targets.json", "reports",
    adjudications_dir="adjudications", captures_dir="captures",
    require_source_complete=True,
    out_path="summary.json", junit_path="summary.xml",
)
```

All arguments after the two input paths are keyword-only. Both optional
directories default to `None`, meaning deliberately missing evidence. The flag
defaults to `False` and must be a real boolean. Paths use the existing native
saved-screen receiving and publication rules.

```bash
quantfit adjudicate screen --targets targets.json --reports-dir reports --adjudications-dir adjudications --captures-dir captures --require-source-complete --out summary.json --junit summary.xml --json
```

The actual manifest's original `Target.name` order defines every row, including
missing reports. The report root contains only `<name>.json` and the optional
native `screen-summary.json`. Its stored facts are ignored; the file still gets
the native aggregate/private/duplicate-key scan and byte charge. The optional
record root accepts only `<name>.json`; the capture root only
`<name>.capture.jsonl`. Unknown/orphan files, directories, links, junctions,
reparse points and inaccessible members refuse the whole receive. Regular-file
hardlinks retain native input behavior and are charged for each logical role.

Every supplied role is inventoried and held once. All reports are parsed and
structurally prepared, all records have closed typed/accounting admission, and
all captures have bounded schema-2, non-null canonical binding, complete arms,
zone/expected metadata and native protocol admission before fresh statistics.
Available report/capture/record byte bindings, fingerprints, exact selected pair
set, axes and both UTF8 hashes must agree. Same-stratum native protocol and
population declarations must agree across all available reports and captures,
including a capture whose report is missing.

The shared pre-math policy charges **n² for each present logical report, record
and capture**, with a limit of **4096² = 16,777,216 policy units**. Individual
admission of n <= 4096 does not guarantee the population fits: even one target
with all three 4096-probe roles exceeds this policy. This is not an exact
operation count, execution-time or heap bound. The native distinctions remain
4096 probes/pairs, up to 8192 arm IDs and 16,385 recognized capture records.

After admission, the existing native summary and whole-capture tabulation run
with unchanged statistical rules. The new `screen_adjudication` section contains
only per-target aggregate/status information and role byte hashes/sizes. It
separates:

- **Source closure:** an actual report and full capture agree, plus a matching
  record when the actual report has flagged pairs.
- **Required record coverage:** a zero-flag report needs no empty human record;
  a supplied empty record still receives complete validation.
- **Operator resolution:** declared resolved/unresolved classes remain
  unauthenticated. A complete unresolved record can be source-complete.

When a report is absent, its native probe/flag counts remain `null`. Supplied
records cannot fill them. Available record/capture contradictions still refuse;
otherwise their status is pending. Original preparation/queue bindings remain
unverified declarations. Long captured text is not subject to a new CSV field
guard because this receiver rebuilds no CSV.

Native flags, per-stratum statistics, human-verified `null`/zero, control status,
sensitivity and scientific GO stay unchanged. Default exit priority is exactly
native **3** for flags, then **4** for incomplete/unmeasurable evidence, otherwise
**0**. The opt-in requirement can change only a native 0 to 4 when source closure
is incomplete. It never clears native 3 or 4. Invalid, contradictory, unsafe or
excess evidence exits **2** with a categorical diagnostic. Source consistency is
not source/human authentication, independence or scientific qualification.

JUnit retains the native N cases first, then capture-source and record-source
cases for every original target, then one overall source case: **3N+1**. Without
the opt-in, additions are skipped `not_requested`. With it, a zero-flag record
criterion is skipped `not_required`; unknown/missing source criteria are errors.
Native flag failures remain visible regardless of source completeness.

Encoded input limits are 1 MiB manifest/N <= 256, 8 MiB per report/64 MiB combined,
4 MiB per record, 16 MiB per capture, and a separate shared 64 MiB record+capture
budget. Remaining-byte-limited reads charge aliases logically. Before any
publication, the complete bare JSON, exact CLI JSON envelope and requested JUnit
share a **32 MiB** encoded budget, including indentation/newlines. CLI JSON uses
the admitted UTF8/LF byte profile on Windows too. There is no row/path truncation.
These are encoded admission limits, not bounds on all intermediate allocations.

Both outputs are admitted against every actual/prospective role path and input
root, including lexical and same-file aliases and each other. Inventories and
guards are rechecked before publication, including when no sinks were requested.
All requested buffers are complete before native per-file atomic replacement.
A later filesystem failure can leave an earlier file; this is neither a pair
transaction nor a hostile-filesystem/race guarantee.

The new section carries no capture text, entries, keys, sheets, record/capture
paths or raw input metadata. The inherited native manifest/report path and
protocol fields remain; inspect those existing fields before sharing. Fictional
producer/receiver controls and reproducible count/hash evidence are in
[`validation/2026-10-31-screen-adjudication/`](../validation/2026-10-31-screen-adjudication/).
