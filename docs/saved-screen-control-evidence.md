# Supplied positive-control evidence for saved screens

**Unreleased 0.61.0 source candidate. Public installation remains 0.56.0.**
This adds a separate artifact-consistency annotation to the existing offline
screen summary. It never changes native screen rows, exits, statistical bounds,
conditionality, sensitivity declarations or human/scientific verification flags.

```bash
quantfit screen-summary --targets targets.json --reports-dir saved-reports --control-report private.control.json --control-capture private.control.capture.jsonl --control-adjudication private.control.adjudication.json --out receiving.json --junit receiving.xml --json
```

```python
from quantfit.saved_screen import summarize_screen

result = summarize_screen(
    "targets.json", "saved-reports",
    control_report="private.control.json",
    control_capture="private.control.capture.jsonl",
    control_adjudication="private.control.adjudication.json",
)
```

Supply all three roles or none. The default with no roles is unchanged.
The new opted-in mode refuses `calibrations_dir`, `calibration_variants` and
`required_conditional_resolution_pp` combinations before reading inputs;
it does not silently discard them. Native source options (default, pinned Hub
triplet or local whole SHA256) remain supported without resolving a source.

The manifest's `sensitivity_control.report` must name the supplied report.
**In this opted-in mode, relative locators are interpreted relative to the
invocation's current working directory, not the manifest's directory.**
The receiver compares the normalized absolute locator only; it never opens or
follows the declared locator independently. The manifest contains no report hash.
This is declared association, not proof of the historical control used by a screen.
A missing or different locator is operational refusal, exit 2.

Each explicit role is held once, bounded by the existing native report 8 MiB,
capture 16 MiB and record 4 MiB limits (28 MiB combined). The existing saved-screen
1 MiB manifest and 64 MiB report-directory limits remain separate. These are
encoded byte policies, not heap or runtime guarantees. Native adjudication
receiving validates the complete capture, tabulation, record membership and
completion digests against the same report bytes; original queue and preparation
remain unverified declarations. No CSV, labels or private strings are reconstructed
for output. Inputs and both output roles are checked before receiving and rechecked
before native per-file atomic publication; two outputs are not a pair transaction.

The added `control_evidence` object contains only fixed status/limit declarations,
input byte sizes/hashes, aggregate dangerous counts and enum-keyed stratum results.
It excludes private paths, model/probe IDs, text, pair ordinals and label values.
Existing summary source/manifest fields remain in their original shape; keep
receiving summaries private as their existing contract requires.

A positive dangerous control needs nonzero dangerous at-risk and native flip
counts and **at least one** source-matched flagged dangerous pair whose supplied
both-arm labels agree with the native judge and whose class is `substantive` or
`degenerate`. Other unresolved or incorrect counts stay explicit. This mirrors the
at-least-one criterion in `sensitivity-control-v0.md` §4.2; labels are still
operator declarations, not authenticated human truth. A safe-axis-only exit 3,
zero risk, zero dangerous flips or entirely unresolved declarations cannot supply
positive dangerous evidence.

Applicability is checked separately for every actual saved stratum using its
native protocol: exact source identity (including custom revision/local SHA),
whole population and zones, judge, decode, causal engine and environment facts.
One GGUF control never qualifies a compressed-tensors stratum. Model-pair identity
is not claimed equal, and even protocol equality cannot establish transfer across
degradation levels or all models.

`consistent` means the declared status is `pass`, a positive dangerous annotation
is supported and every declared stratum is applicable. `conflicting` means valid
supplied evidence does not support that complete declaration (including a different
protocol, safe-only/no-positive evidence or a non-pass declaration). `missing`
means every stratum lacks saved reports. Per-stratum results distinguish missing
from conflicting and applicable. These valid annotations return the **unchanged
native screen exit** (0/3/4); they do not introduce an implicit gate or alter JUnit.
Malformed/badly bound evidence, incomplete options, oversize or unsafe roles refuse
with categorical exit 2 before publication.

Evidence: `tests/test_screen_control_evidence.py` covers the actual SDK and OS CLI
with fictional native producer data and is selected by all four existing installed
wheel/sdist consumers. Exact-head hosted qualification remains separate. No model,
Hub, human labeling, sensitivity estimate or scientific qualification is established.
