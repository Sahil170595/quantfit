# Artifacts and schema versions

Every file quantfit writes, what it is for, and the version it declares. This exists
because the answer to "what schema version is the screen summary?" lived only in code —
`quantfit audit` counted fourteen constants that no document stated the value of, which
means fourteen numbers a consumer could only discover by reading the source or by parsing a
file and hoping.

Every value below is checked against the shipped constant by `quantfit audit`. If one of
them drifts, the build fails rather than the table quietly going stale.

## Artifacts

| Artifact | Written by | Schema constant | Version |
|---|---|---|---|
| Drift report | `verify-safety --report`, `gate --report` | `safety.report:SCHEMA_VERSION` | `2` |
| Gate decision | `gate --out` | `gate:GATE_SCHEMA_VERSION` | `1` |
| Screen summary | `screen --out` | `screen:SUMMARY_SCHEMA_VERSION` | `1` |
| Target manifest *(input)* | you author it | `screen:MANIFEST_SCHEMA_VERSION` | `1` |
| Completion capture | `verify-safety --capture` | `safety.verify:CAPTURE_SCHEMA` | `1` |
| Calibration report | `calibrate ingest --out` | `safety.calibrate:CALIBRATION_SCHEMA` | `1` |
| Unblinding key | `calibrate sheet --key` | `safety.calibrate:KEY_SCHEMA` | `1` |
| Reproduction record | `reproduce --out` | `reproduce:REPRODUCTION_SCHEMA_VERSION` | `1` |
| Reference report | the registry | `refreports:REFREPORT_SCHEMA_VERSION` | `1` |
| Baseline cache entry | `safety.cache` | — (suffix below) | — |
| CLI JSON envelope | any command with `--json` | `cli:CLI_JSON_SCHEMA_VERSION` | `1` |

The drift report is at **schema v2** and v1 is refused on parse rather than upgraded: v1
carried no per-arm engine provenance, so a v1 file cannot answer the question the
same-binary mandate exists to ask, and silently accepting one would let an unanswerable
report look like an answered one.

## Fixed filenames

| Constant | Value | Why it is fixed |
|---|---|---|
| `screen:SUMMARY_FILENAME` | `screen-summary.json` | Written inside the `--out` directory, so the directory is the thing you pass and the summary is always found at a known name |
| `safety.cache:CACHE_ENTRY_SUFFIX` | `.baseline-cache.json` | A recognisable suffix so `.gitignore` can cover the whole class; cache entries are per-machine and must never be committed |

The capture file has no fixed name, but `*.capture.jsonl` is the documented convention and
is what `.gitignore` matches. That matters more than a naming preference: a capture holds
raw completions, which may include harmful model output.

## Protocol and spec pins

| Constant | Value | Meaning |
|---|---|---|
| `safety.cache:CAPTURE_PROTOCOL_VERSION` | `qsr-v0/capture-1` | The capture format *and* the spec it was captured under, in one string. A capture is only comparable to another under the same protocol. |
| `reproduce:SPEC_VERSION` | `v0` | The spec version the reproduction rule implements |
| `refreports:CURRENT_SPEC_VERSION` | `v0` | The spec version a reference report must declare to stay valid |
| `inspect_task:CONFORMS_TO` | `QSR v0` | What the Inspect-API runner claims conformance to |
| `reproduce:TOLERANCE_DOC` | `docs/cross-hardware-tolerance-v0.md` | Where the T1–T5 rule is defined normatively |

A reference report goes stale when its **spec** version is superseded — not when the tool
version or a dependency moves. That is the rule ROADMAP risk 5 turns on: pinning validity
to the tool version would expire every published report on every release, which would make
publishing one pointless.

## Tolerance constants in the reproduction rule

These two are the only numeric slack in the T-rule, and they are asymmetric on purpose.

| Constant | Value | Effect |
|---|---|---|
| `reproduce:AT_RISK_SLACK` | `0` | The at-risk denominators must match **exactly**. A different denominator means a different measurement, not a noisier one — the comparison is `reproduced_with_denominator_drift` at best, never a clean reproduction. |
| `reproduce:FLIP_COUNT_SLACK` | `1` | Flip counts may differ by at most one. Cross-hardware nondeterminism can move a single borderline pair; two is a different result. |

Zero slack on the denominator and one on the count is the whole asymmetry: *what was
measured* has to be identical before *what was found* is allowed to wobble at all.

## Registry cap

`refreports:MAX_REFERENCE_REPORTS = 3`. The registry ships empty and is capped at three,
because a reference report is a claim someone else has to be able to reproduce — a long
list would be a list nobody checks.
