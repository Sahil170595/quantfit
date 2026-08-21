# T0 on both hardwares — L passes, CI fails — the T3 "breach" was void — 2026-08-21

`docs/cross-hardware-tolerance-v0.md` §6.1 listed "**No replicate set**" among what had
never been run. T0 — within-hardware byte-identity of the `drift` block across three
replicates — has now been collected on both machines this project has.

| hardware | replicates | T0 |
|---|---|---|
| **L** (RTX 4080 Laptop, Windows) | 3 | **PASS** — byte-identical |
| **CI-linux** (GitHub `ubuntu-latest`) | 3 | **FAIL** |

Both sets meet §3.1's three-replicate requirement (`meets_protocol_replicate_count:
true`), so neither result is a partial one.

## The CI runner disagrees with itself

Three canary runs on the **same commit**, same model, same probe revision, same decode
(`do_sample=False`), same environment — python 3.12.14, torch 2.13.0+cpu, transformers
5.15.1 — and they do not agree:

| run | `clear_unsafe` refused | `borderline` refused | dangerous at-risk | verdict |
|---|---|---|---|---|
| 32514354502 | **9** | **12** | 9 | MDE ~16pp at n=9 |
| 32514368319 | 8 | 13 | 8 | MDE ~18pp at n=8 |
| 32514904417 | 8 | 13 | 8 | MDE ~18pp at n=8 |

Two agree, one differs. At least one probe's completion is unstable across runs, and when
it moves it changes that probe's judge label — shifting a probe between the `borderline`
and `clear_unsafe` refusal counts, and with it the at-risk denominators and the printed
MDE.

**Hypothesis, not verified:** greedy decoding is deterministic given identical weights
and inputs, so the likely mechanism is floating-point reduction order varying with the
runner's thread count, flipping an argmax on a near-tie. Confirming that means capturing
completions across runs and diffing them, which this record does not do.

## The 2026-08-15 T3 "breach" is VOID, not a breach

`reproduce`, given both T0 legs, returns:

```
OUTCOME: void (exit 4)
void because: T0_failed_on_a_side
failing predicates: none — T1-T5 all hold
```

> T0 FAILED ON A SIDE: a hardware disagreed with ITSELF across its own replicates.
> Nothing in this record is about hardware differences — the outcome is `void` (§6.3) and
> the finding is a within-hardware nondeterminism leak. Fix the leak and re-run; do not
> widen the cross-hardware tolerance to absorb it.

**This overturns a published claim.** `validation/2026-08-15-crosshw-smollm2/` recorded a
T3 breach — at-risk denominators 8 vs 7 and 4 vs 3, MDEs moving 18.2→20.5pp and
33.1→41.5pp — and CHANGELOG 0.8.0 announced *"The cross-hardware tolerance is breached."*

It was not. The deltas are real, but they are **not attributable to hardware**, because
one of the hardwares does not agree with itself. That record said so at the time, in the
tool's own words: *"A hardware that disagrees with itself produces exactly these failures,
and no evidence here excludes that."* It excluded nothing because T0 had never been
collected. Now it has, and the exclusion fails.

`reproduce` withheld the reserved `breach` name on 2026-08-15 and was right to. The
correction is to the prose around it, not to the tool.

## The canary has a blind spot, and this is it

`canary.yml`'s determinism job asserts **zero flips between arms within one run**. That is
guaranteed by construction under greedy decoding with identical weights — and it stays
green through exactly this defect, because both arms see the same nondeterminism at the
same time. `baseline_refused == quant_refused` in all three runs above.

So the canary verifies within-run arm identity and says nothing about **across-run
reproducibility**. T0 is the check that catches it, and T0 had never been run on CI. A
green canary was never evidence of a reproducible measurement, and the job's own header
already warned against reading it as more than it is.

## What this does and does not mean

- **It does not invalidate any single measurement.** Every drift report remains a correct
  measurement of what that run produced. What is not established is that a rerun on the
  same CI hardware reproduces it.
- **It does invalidate cross-hardware claims involving CI-linux**, until the leak is
  fixed. §5.2: with three replicates, 0 disagreements bounds the within-hardware
  disagreement rate only below 56.1%, so *"the correct response to a T0 failure is to fix
  the nondeterminism, not to model it."*
- **Machine L is unaffected**: 3/3 byte-identical. Every local run in `validation/` sits
  on a hardware that passes T0.
- **ROADMAP 0.8's reproduction gate cannot be met on this CI runner** as it stands. That
  gate needs a reproduction within tolerance, and a `void` record licenses nothing.

## Files

| file | what it is |
|---|---|
| `t0-machine-L.json` | T0 PASS, 3 replicates, per-report `sha256` |
| `t0-ci-linux.json` | T0 FAIL, 3 replicates, per-report `sha256` |
| `reproduce-void.json` | the comparison record: outcome `void`, `T0_failed_on_a_side` |
| `replicates-L/*.json` | the three local replicate reports |
| `replicates-ci/*.json` | the three canary reports, by run id |
