# The published bounds are perfect-judge floors, and the measured judge error destroys them

**2026-08-22.** Every MDE quantfit prints assumes a judge that never errs. The judge has
since been measured. Putting the measured value into quantfit's own MDE machinery gives:

| n at-risk | perfect-judge MDE (**printed**) | MDE at measured ε |
|---|---|---|
| 8 | 18.2pp | **100pp** |
| 10 | 14.9pp | **100pp** |
| 11 | 13.6pp | **100pp** |
| 12 | 12.6pp | **100pp** |
| 19 | 8.1pp | **100pp** |
| 20 | 7.7pp | **100pp** |
| 40 | 3.9pp | 98.9pp |

**At every n this project has ever run, no effect size is detectable.** An MDE of 1.0 means
the instrument cannot distinguish *any* true flip rate from zero at 80% power.

## How that number is reached, entirely from committed artifacts

`quantfit/safety/mde.py:EPS_DEFINITION` — verbatim: *"per-arm **upper** bound on BOTH
directional judge-error rates (max of false-compliance and false-refusal upper CIs)"*.

From `validation/2026-08-18-judge-calibration/calibration.json`, the selected judge scored
**4 false positives in 48 compliant completions** and 0 false negatives in 32 refusals.

- Wilson upper on 4/48 → **0.1955**
- Wilson upper on 0/32 → 0.1072
- ε = per-arm max = **0.1955**
- `false_flip_rate_bound(ε, ε) = ε + ε` = **0.3911**
- `effective_mde(12, 0.3911)` = **1.0**

Computed with `quantfit.safety.mde` and `quantfit.safety.verify` — the project's own
primitives, no hand arithmetic (`CLAUDE.md` §3).

## The most generous defensible reading is still ~60pp

Using the FPR **point estimate** of 8.3% instead of its upper bound — which
`EPS_DEFINITION` does not permit, and which `mde.py`'s own docstring shows is not a bound
(it walks through a marginal 0.05 admitting a true conditional of 0.1318) — the MDE at
n=12 is **59.6pp**. Roughly three in five at-risk pairs would have to flip before this
instrument could see it.

So the choice is not between "12.6pp" and "100pp". It is between **100pp** (correct) and
**~60pp** (optimistic and not permitted). 12.6pp is not on the menu; it is the number that
would be true if the judge were perfect, and the judge has been measured and is not.

## What this does and does not overturn

**Does not:** any observed result. Fourteen third-party artifacts produced zero dangerous
flips, and that remains a true statement about what was observed. The sensitivity control
passed, and the instrument really did detect a real flip at IQ2_M.

**Does:** every *bound* attached to those nulls. `validation/2026-08-21-screen-complete/`
reports the gguf dangerous axis as "0/12, Wilson 95% upper 24.2%". The Wilson interval is
a statement about sampling error alone; it does not carry judge error. With ε folded in,
the honest statement is that the screen could not have detected a dangerous regression at
**any** prevalence, so 0/12 bounds nothing about reality.

The screen's own conditionality machinery does not catch this, because that machinery keys
on the sensitivity control's pass/fail (`screen.py:420`) and the control **passed**. A
passed control says the detector is not blind at IQ2_M-level degradation. It says nothing
about resolution at the shipped corpus size, which is what ε governs. **Two different
qualifiers, and only one of them is wired up.**

## Why this was not visible before today

`mde.py` has always printed the perfect-judge floor with the label "perfect-judge floor",
and ROADMAP 0.6 gated ε calibration behind a 0.5 GO — so for the entire life of the
project there was no ε to substitute in. The calibration was run early
(2026-08-18) because the sensitivity control failed and the judge had to be measured to
find out why. Nobody then took the measured ε and fed it back through `effective_mde`.

That is the whole finding: the two halves existed for four days and had not been put
together.

## What follows

1. **The corpus is the binding constraint, not the judge.** `mde.py` already says raising n
   is corpus v2 work (ROADMAP 0.6). At ε=0.1955 even n=40 gives 98.9pp, so this is not a
   "run more probes" problem at any plausible corpus size — ε has to come down.
2. **ε has to come down, which means a better judge or a second annotator.** 4/48 with a
   Wilson upper of 0.1955 is driven by the small denominator as much as the error rate;
   n=80 hand-labelled completions is a thin calibration set.
3. **Nothing should be published as a bound on reality until (1) or (2) lands.** The screen
   results stay valid as observations, with their bounds restated as perfect-judge floors.

## Files

| file | what it is |
|---|---|
| `mde-under-measured-eps.json` | the table, the confusion counts, ε, the bound, and which primitives produced each number |
