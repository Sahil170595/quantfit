# Screen observation comparison — 0.34.0

Available since quantfit 0.34.0. Compare two portable screen bundles offline.

```bash
quantfit screen-compare --reference-bundle reference-screen --candidate-bundle candidate-screen --out comparison.json --junit comparison.xml --json
```

The Python API is `quantfit.screen_compare.compare_screen_bundles(reference_bundle,
candidate_bundle, *, out_path=None, junit_path=None)`. It returns a schema-1
`quantfit.screen-comparison` dictionary. `ScreenComparisonError` is a categorical
operational refusal, mapped to CLI exit 2. JSON and JUnit outputs are optional.

Both sides are captured as original bytes and independently checked by the strict
screen-bundle receiver. Their held target-manifest bytes must be identical; even
reformatting is a different population declaration and refuses 2. Each closed bundle
is at most 64 MiB including both manifests. Both logical transports count toward the
128 MiB combined bound, including when they share a root or regular hardlinked
members; a shared identity cache avoids reopening captured bytes. No model, capture,
weight, binary or calibration locator from a report is followed.

Rows retain the original target order and both receiving report bindings. Each axis
keeps its own original at-risk denominator, flagged flips, Wilson interval, MDE and
measured/missing state; no probe counts are pooled across targets. The complete
receiving summaries and their sensitivity-control caveats remain attached.
`identical_report_bytes` records byte-identical report content, without establishing
independent execution or how that content was produced.

Known stratum protocol declarations are compared strictly, including declared
engine/environment and pinned judge/probe/decode context. A missing context is
unavailable, rather than a fabricated mismatch. Each arm's known revision,
artifact SHA256 and precision declaration is compared independently; a known
contradiction on either arm prevents a matched transition. Empty/unknown precision
metadata remains unavailable and cannot mask a known contradiction elsewhere.
Known precision strings are compared conservatively as declared, without invented
alias equivalences.

When both reports and axes are measured and their known declarations are compatible,
the transition is `newly_flagged`, `persisting_flag`, `apparent_clearance` or `no_flag`.
Its basis is `declared_target_and_compatible_protocol`. Unknown identity fields are
explicit and can still support this descriptive bookkeeping; `same_weights_established`
is always false. Matching report statements do not authenticate actual weights.
Missing, unmeasured or known-incompatible observations retain their original native
flags but have no matched transition. An apparent clearance is an observed change
in declared aggregates, not causal improvement, authenticated human adjudication,
statistical significance or a safety result.

Exit rules are deliberately conservative:

| Exit | Meaning |
| --- | --- |
| 3 | At least one native axis on either side has a flag, including a reference flag apparently cleared in the candidate. Review is required. |
| 4 | No native flag is present, but a required observation is missing, unmeasured or incompatible. |
| 0 | Complete, compatible declared observations contain no native flag. This remains conditional. |
| 2 | Malformed/unsafe evidence, different target-manifest bytes or output failure. No comparison is invented. |

`quantfit.screen_compare_junit.screen_comparison_to_junit(record)` renders two axis
cases per target plus an overall case and rejects contradictory decision records.
A known native axis flag fails its case even when matching evidence is incomplete;
otherwise missing/unmeasured/incompatible axes skip. Overall fails for exit 3, skips
for 4, and passes only for 0. XML messages use fixed labels and native aggregate
counts, rather than arbitrary producer prose or paths. A failure means a retained
native flag, not a verified new causal regression.

Output parents must exist. JSON/XML may not alias either held member, target
manifest, outer manifest, ignored producer summary, missing declared member or each
other, nor be placed inside either closed bundle. Publication stages complete
buffers, rechecks bounded inventories without rereading held report bytes, and
replaces each output atomically. It is not a two-file transaction, crash guarantee
or hostile concurrent-filesystem protection. An operational refusal produces no
fabricated comparison; a late per-file publication failure can leave an earlier
output visible.

Keep private handoffs private: declared model/provenance paths may remain in native
receiving summaries. The command does not upload or sanitize them. No result
establishes independent execution, real host identity, human confirmations,
calibrated sensitivity or scientific GO. Dangerous zeros still mean the detector
did not fire. The synthetic record in `validation/2026-10-18-screen-comparison/`
demonstrates command behavior only.
