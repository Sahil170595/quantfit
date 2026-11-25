# Supplied positive-control evidence for saved screens

**Available since 0.61.0.**
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
Published 0.61.0 refuses calibration/requirement combinations before reading
inputs. [0.63.0 single-calibration composition](#single-calibration-composition-0630)
adds the single directory and optional existing scalar ceiling; named variants
remain refused. Native source options (default, pinned Hub
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
for output. Input and output roles are admitted before receiving. Before native per-file
atomic publication, the three held control roles receive explicit stamp rechecks;
saved-screen inputs retain their existing held-buffer and inventory contract.
Two outputs are not a pair transaction.

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

## Single-calibration composition (0.63.0)

Available since **0.63.0**.
It uses the existing flags and API keywords, with no new mode flag:

```bash
quantfit screen-summary --targets targets.json --reports-dir saved-reports --calibrations-dir calibrations --control-report private.control.json --control-capture private.control.capture.jsonl --control-adjudication private.control.adjudication.json --require-conditional-resolution 40 --out receiving.json --junit receiving.xml --json
```

Provide all three controls and exactly the existing single calibration directory.
The scalar ceiling is optional and keeps its finite `(0,100]` pp admission.
Partial controls, named variants with controls, or a scalar without the single
directory refuse categorically before input work. Existing default, control-only,
calibration-only and scalar workflows retain their original output semantics.

One held screen snapshot, parsed actual target-report set and native base summary
serve both annotations. All provided control/calibration roles, actual and pending
members, count checks and combined native work budgets are admitted before native
conditional MDE. Each actual target/calibration pair is analyzed once through the
existing prepared path. There is no locator follow, report/calibration reread,
analysis replay, pooling, model/judge execution or Hub work.

The original dangerous-positive criterion and native decode identity comparison
still apply to every actual target, including targets without calibration.
Nullable source pins and explicit custom/local source identities retain their
existing native eligibility. A consistent control never changes a calibration
verdict; conflicting or insufficient valid controls remain annotations.
Native 3/4 priority, missing-calibration 4, unmet scalar 5 and qualified 0 are
identical to the same single-calibration input without controls. The native
unattainable MDE saturation sentinel remains unmet even at 100 pp. JUnit is exactly
the calibration-only JUnit for those same data and scalar. No control case or
stronger sensitivity/human/scientific assurance is appended.

The original separate byte policies remain: controls 8/16/4 MiB per role and
28 MiB combined; screen members 64 MiB total; calibrations 2 MiB per member and
64 MiB total; native combined n-squared analysis work. One reproduction output
plan protects both closed roots, every actual/declared/missing member, controls
and mutual/link aliases. Held controls retain their native stamp/ancestor checks
before MDE and through each publication. Screen and calibration buffers keep
their existing inventory-only publication rechecks; no new content-stamp promise
is made for them.

Complete JSON and JUnit buffers are materialized before publication. Each file is
atomic independently; they are not a pair transaction. A late control mutation
after the first replacement can leave that first output visible while the call
fails and the second output is not published. Inputs are never rolled back or
deleted. Control output remains count/hash-only with all assurance flags held.

Fictional native SDK/OS CLI, retained-schema-3 and source consumer evidence is
recorded in `validation/2026-11-14-screen-control-calibration/`. The composition
suite is selected in the existing four installed wheel/sdist profiles. Exact-head
hosted qualification remains separate; no new job, artifact upload, dependency,
source authentication, sensitivity estimate or scientific GO is introduced.

## Selected axes with one calibration directory (0.67.0)

Quantfit 0.67.0 accepts repeatable `--require-axis-conditional-resolution AXIS=PP`
alongside all three control inputs and one `--calibrations-dir`. Supply one or two
canonical axes and use the scalar flag or selected-axis flags for a given invocation.
The requirement and JUnit are the native selected-axis projections for the same
screen and calibration. Native exits 3 and 4 take precedence. Qualification can
add exit 5 for an unmet requirement. The control receipt remains an annotation.
