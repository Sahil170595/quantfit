# Pinned-corpus gates and screens — 0.53.0 source candidate

This unreleased candidate extends the native `ProbeCorpus` workflow introduced in
0.51.0. The public release remains 0.51.0; build this candidate from its reviewed
source. The accepted 0.52.0 selected-axis feature is an unreleased dependency.
No new population loader, statistics engine or sensitivity validator is added.

## Declare one source

```python
from quantfit import ProbeCorpus
from quantfit.gate import run_gate, evaluate_report
from quantfit.screen import run_screen
from quantfit.saved_screen import summarize_screen

source = ProbeCorpus("org/probes", "1111111111111111111111111111111111111111", "validation")
decision = run_gate("org/base", "org/quant", threshold=0.30,
                    probe_corpus=source, report_path="drift.json", out_path="gate.json")
replayed = evaluate_report("drift.json", threshold=0.30, probe_corpus=source)
screen = run_screen("targets.json", "reports", probe_corpus=source)
saved = summarize_screen("targets.json", "reports", probe_corpus=source)
resumed = run_screen("targets.json", "reports", resume=True, probe_corpus=source)
```

These are operator requests, not a corpus/model run established by this document.
Replace the example source and models with deliberately selected actual pins.
The API accepts the existing native descriptor, never a per-target source or a
new manifest field. `probe_corpus=None` retains the previous shapes, source,
ordering and native decisions. An **explicit canonical descriptor** also opts in
to the new profile, even though its source is the native canonical triple.

The existing all-or-none triplet now also applies to `gate` (live and saved),
`screen` (including `--resume`) and `screen-summary`:

```bash
quantfit gate --baseline org/base --quant org/quant --threshold 30 --probe-dataset org/probes --probe-revision 1111111111111111111111111111111111111111 --probe-split validation --report drift.json --out gate.json --junit gate.xml --json
quantfit gate --from-report drift.json --axis-threshold refusal-robustness=30 --axis-threshold over-refusal=30 --probe-dataset org/probes --probe-revision 1111111111111111111111111111111111111111 --probe-split validation --out replay.json --json
quantfit screen --targets targets.json --out reports --probe-dataset org/probes --probe-revision 1111111111111111111111111111111111111111 --probe-split validation --json
quantfit screen --targets targets.json --out reports --resume --probe-dataset org/probes --probe-revision 1111111111111111111111111111111111111111 --probe-split validation --json
quantfit screen-summary --targets targets.json --reports-dir reports --probe-dataset org/probes --probe-revision 1111111111111111111111111111111111111111 --probe-split validation --out summary.json --json
```

CLI thresholds are percentage points; API thresholds are rates. The threshold is
a detectable-effect **resolution target**, not a maximum tolerated observed rate.
Scalar/tier policy and the exact selected-axis labels/rules are unchanged. All
selected axes are evaluated before native `3 > 4 > 5 > 0` reduction.

## Whole population and admission order

All known local policies, source/target/stratum options, output roles/aliases and
provided calibration syntax/requested scope are checked before Hub or model
contact. The existing `_prepare_probes` then resolves the whole split once.
Its exact admitted rows are held privately and reused for every target/retry;
no prompt appears in public gate/summary objects. No filtering, deduplication,
prefix selection, re-sorting or per-target reload is used.

Native source limits remain 1..4096 rows, 64 KiB per prompt and 8 MiB across
selected prompt/zone/expected strings. Expected safe/unsafe labels are explicit,
independent of `zone`, including borderline rows. The actual expected-label
census supplies best-case denominators, instead of assuming canonical 12/28.
An absent expected selected axis gives native pre-run 5 without model work;
positive expected population but observed at-risk zero gives post-run 4. A
detected selected regression remains 3 even if another axis is unknown.

Malformed remote rows can require Hub contact to discover, but cause no model,
judge, backend or generation calls and no public output. These retained-input
limits do not bound SDK downloads, parsing, memory, latency or remote effects.
A matching builder hash is not external-data authentication. A coherent clean
SDK EOF cannot independently prove that the remote split was complete.

## Counts-only source context and strict receiving

Opted gate JSON is **flat schema 3**: all native decision fields, including
top-level `exit_code`, remain. Strict integer `decision_schema_version` selects
the native scalar/tier decision (1) or selected-axis decision (2). The new closed
`probe_corpus` context contains exactly:

`id`, `revision`, `split`, `n_probes`, `expected_unsafe_n`, `expected_safe_n`,
`zone_counts` and `population_basis`. The three zone keys are `clear_safe`,
`clear_unsafe` and `borderline`. Known counts are strict integers and agree with
the native population/report; booleans and float spellings do not substitute.

Live context uses `resolved_native_population`; offline replay uses
`saved_report_native_counts`. Saved evaluation holds original report bytes once,
matches the **explicit expected triple**, validates native counts/statistics and
binds their raw SHA. It never reloads Hub. This records saved native counts, not
fresh proof of remote completeness, curation or execution chronology.
The existing bundle receiver reconstructs the same native decision and rejects
missing/extra fields, source/census/SHA/MDE/overall contradictions. JUnit retains
the native decision kind and includes the counts-only source context.

Live opted screen summaries use schema 2; offline opted summaries use
`saved_screen_summary_schema_version: 2`. Manifest schema 1 stays unchanged.
All original targets, missing/error rows and both strata are retained. Every
present report must match one source and census across strata, while native
engine/environment constraints remain per stratum. There is no pooling.
An entirely missing saved screen has `unavailable_no_reports` and **all census
fields plus `zone_counts` null**, never zero or inferred from a convenient file.

Complete resume holds/admit all reports and stays offline. Partial resume first
holds every existing report and path; it resolves one source only for missing
targets, checks the held census before model work, and executes only those
targets. Each new report is checked against that resolved census before a row or
summary qualifies. Existing evidence is not replaced; malformed late evidence
refuses before regeneration. Fresh opted runs refuse existing report members
unless `--resume` is explicit. Publication is per file, not a transaction over
reports, private captures, summary and JUnit; failure can leave native evidence.

All requested opted gate outputs, including CLI JUnit, undergo the native path
and alias checks before dispatch and again before publication. Known local GGUF
inputs from live arguments or every manifest target are protected by resolved
file identity, including hardlink aliases. Original local symlink labels remain
unchanged for native model reading; output checks protect their resolved target.
Opaque saved-report arm labels and unobserved remote `hf:` cache paths are not
treated as live model inputs. These are current filesystem role checks, not a
model-byte snapshot, lock or guarantee against concurrent filesystem mutation.

## Calibration and interpretation

Provided calibration is held once. Known requested judge/source/arm/decode
mismatches refuse before Hub; resolved population-count mismatch refuses before
models; actual resolved arm/engine/environment fingerprint mismatch refuses
before a calibrated result is published. Existing conditional directional-max
per-arm bounds, epsilon sources, floor labels and power calculations remain.
Native cache/capture identity includes the actual triple and population; changing
revision/split is substantive even under the same dataset ID.

Declared sensitivity-control fields remain visible, including a declared pass.
For a supplied noncanonical source they remain **unverified and conditional on
undemonstrated sensitivity**. A path, status or human-name string authenticates
neither applicability nor labels. No historical default-distribution accuracy,
epsilon, false-positive rate or `n <= 34` claim transfers to this distribution.
Nothing here establishes model safety, independence, pooled prevalence, joint
error control, authenticated preregistration, human truth or scientific GO.

## Evidence

[The dated aggregate](../validation/2026-11-02-pinned-corpus-gates/README.md)
records actual public APIs, OS CLI, native writers/strict receivers/JUnit and
controlled source/generation seams. Existing installed acceptance is wired for
**four** profiles: Linux/Windows × wheel/sdist; building two distribution artifacts
is separate from executing those consumers. Current source execution, hosted
installed results and a public release remain distinct evidence boundaries.
