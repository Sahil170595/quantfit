# Calibration-choice sensitivity — since 0.45.0

Available since quantfit 0.45.0. The no-calibration and
[single-calibration](screen-resolution.md) workflows are unchanged. Predeclare the supplied choices; the instrument selects
no primary, preferred or favorable rater.

```bash
# Descriptive: native exit stays; added JUnit criteria are skipped.
quantfit screen-summary --targets targets.json --reports-dir reports --calibration-variant first=calibrations-a --calibration-variant second=calibrations-b --out choices.json --junit choices.xml --json
# Explicit requirement on EVERY target, choice and native axis.
quantfit screen-summary --targets targets.json --reports-dir reports --calibration-variant first=calibrations-a --calibration-variant second=calibrations-b --require-conditional-resolution 40 --out required.json --junit required.xml --json
# Intentionally missing choice remains in the declared population.
quantfit screen-summary --targets targets.json --reports-dir reports --calibration-variant first=calibrations-a --calibration-variant pending=- --out incomplete.json --json
```

Repeat `--calibration-variant NAME=DIR` for 1..8 names, in declared order. Names
start with an ASCII letter/digit and contain only letters, digits, `_` or `-`, at
most 64 characters. Duplicate names/empty paths refuse. The first `=` separates
name/path, so Windows colons and later equals signs are ordinary path content.
`NAME=-` explicitly declares missing evidence. A supplied path must exist and pass
native closed-directory/file/link checks; typo/inaccessible/non-directory/linked
paths refuse rather than silently becoming missing. An empty admitted directory
is a provided choice with missing calibrations. The mode is mutually exclusive
with `--calibrations-dir`. Each root contains only `<target-name>.json` aggregate
calibrations for declared targets; unknown/orphan files refuse.

## One native population and complete admission

The whole mapping/mode/optional (0,100] pp ceiling is validated before IO. One
manifest/report population is held, and native saved summary computed once.
ALL choice roots are inventoried before any calibration payload read, under ONE
combined 64 MiB advertised cap. Bounded reads charge actual bytes against one
remaining counter, with 2 MiB per payload. Repeated roots can reuse held buffers,
while both logical occurrences still consume byte/work budgets. K×64 MiB is never
read then rejected. Provided calibrations get native privacy/count/binding checks,
including pending-report target/model/engine checks without invented report matches.

Every matched actual report/count/scope is checked across all target×choice pairs.
Their combined native sum `n_probes**2` must fit 16,777,216 BEFORE the first native
conditional analysis. This inherited screen policy is separate from finite-grid
tail/scan units. Matched reports allow at most 4096 probes. Missing/pending cells
add no math work. All matched cells use the authoritative native calculator; no
labels, counts, choices or failures are pooled or filtered.

`calibration_choice_sensitivity` retains all N×K ordered cells and all names,
including null missing/pending analyses. Actual report/calibration hashes,
fingerprint, status and complete native analyses remain visible. Native exit and
outcome are frozen before qualification; an earlier choice's 5 never becomes the
next choice's native verdict.

Per-target/axis envelopes contain expected K, analyzed, measurable, attainable and
incomplete counts. MDE minima/maxima use attainable matched values only, or null
if none. Unattainable native MDE 1.0 stays in its original row and is not promoted
to an attainable 100pp bound. A truly attainable 1.0 may be retained. Nulls and
unmeasurable values never become zero. Digest-copy groups expose identical bytes;
named copies are not independent raters, additional observations or confidence
intervals. Envelopes describe only supplied choices, not a universal worst case.

## Qualification and JUnit

No ceiling preserves native exit/outcome even with missing/unattainable choices;
`calibration_choice_requirement` records `not_requested`, without an implicit gate.
An explicit ceiling reuses the pure native axis criterion: every target/choice
needs both axes with matched evidence, measurable denominators, attainable target
power and effective MDE within the pp ceiling. Emit qualification once, preserving
all simultaneous reasons: original native 3/4 first; otherwise missing calibration
4; otherwise any unmet criterion 5; otherwise 0. Original native outcome/flags stay.

JUnit ALWAYS has N original native cases first, 2×N×K axis-choice cases and one
overall. Without a ceiling, additions are **skipped: not_requested**; native
failures/skips remain and no implicit failure is added. With a ceiling, unmet
criteria/overall fail explicitly. Default no-choice and single-calibration XML
remain unchanged.

## IO, bounds and API

At most 256 targets/8 choices (2048 cells). Native manifest/report bounds remain
1 MiB/8 MiB per report/64 MiB combined report bytes. Calibration 64 MiB is global.
Serialized aggregate JSON plus requested XML is capped at 32 MiB, including API/
stdout-only calls with no files. Limits bound accepted work/serialized output,
not wall time, peak memory or hard preallocation.

Both destinations are checked against the manifest, native root and EVERY choice
root/prospective member before math. The native publisher stages complete buffers
and atomically **replaces each file**. It is not write-once or a pair transaction;
a later failure can leave the earlier output updated. Recheck validates inventory
membership, links/types and current combined sizes without rereading/reanalyzing
snapshots. It does not prove current byte immutability, authenticate sources or
defeat a hostile filesystem. Invalid/unsafe operations return categorical exit 2;
sources are not written and invalid preflight preserves existing output files.

```python
from quantfit.saved_screen import summarize_screen

result = summarize_screen(
    "targets.json", "reports",
    calibration_variants={"first": "calibrations-a", "second": "calibrations-b", "pending": None},
    required_conditional_resolution_pp=40.0,
    out_path="choices.json", junit_path="choices.xml",
)
```

Names are operator-declared choice identifiers, not authenticated rater identities.
Directional-bound/majority-real/arm-independent-error assumptions remain unverified;
correlated bias is not fixed by choices or n. No best-rater selection, pooling,
independence, source/weight authentication, sensitivity or scientific GO follows.
No additional raters, sharing, label campaign or upload is authorized.

`validation/2026-10-25-calibration-choices/` regenerates actual fictional CLI/API/
JSON/JUnit: N=2/K=2, positive/mixed/descriptive/missing/native-3/native-4, 11 cases
each. Source tests cover global advertised/actual bytes, combined work, late bad
evidence, pending/orphan bindings, aliases/inventory races, no-output cap, copies,
null envelopes, frozen provenance and legacy compatibility. Installed-origin guards
run the consumer for Ubuntu/Windows wheel/sdist; exact-head hosted results are on
the PR. No human study, model or new scientific campaign ran.
