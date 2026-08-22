> **CORRECTED 2026-08-21 — this record is VOID, not a breach.**
>
> T0 has since been collected on both hardwares (`validation/2026-08-21-t0-replicates/`).
> **CI-linux FAILS T0**: three canary runs on one commit, same env, same decode, and they
> do not agree with each other. So the T3 deltas below are real but are **not
> attributable to hardware** — `reproduce`, given both T0 legs, returns
> `outcome: void, void because: T0_failed_on_a_side`.
>
> Nothing in the measurements below changes. What changes is what they license: this is a
> within-hardware nondeterminism finding, not a cross-hardware tolerance breach. The tool
> withheld the reserved `breach` name at the time and was right to; the overclaim was in
> the prose, and in CHANGELOG 0.8.0, not in the artifact.

# The first cross-hardware comparison — 2026-08-15

`docs/cross-hardware-tolerance-v0.md` §6.1 said, verbatim:

> **No T4 or Colab or Kaggle run of any kind.** No side-F report exists. No
> cross-hardware comparison. No pair of reports has been checked against T1–T5, on any
> hardware.

The second machine turned out not to be a GPU at all. It is the **GitHub Actions
runner** the weekly canary runs on, which produced a schema-v2 report for the same
model, the same probe revision and the same decode settings as a local run — and
therefore the first pair `reproduce` could be pointed at across two machines.

**Result: the tolerance is breached.** T3 fails on both axes.

## The deltas

| predicate | reference (L, GPU) | candidate (CI, CPU) | delta |
|---|---|---|---|
| `at_risk` — refusal-robustness | 8 | 7 | −1 |
| `at_risk` — over-refusal | 4 | 3 | −1 |
| `mde_at_80pct_power` — refusal-robustness | 0.1822 | 0.2054 | +2.3pp |
| `mde_at_80pct_power` — over-refusal | 0.3313 | 0.4152 | +8.4pp |

`slack=0` on both `at_risk` clauses: T3 admits no tolerance there at all.

**What did NOT move is the point.** Both sides return zero flips on both axes and both
verdicts are `NO REGRESSION DETECTED`. The paired drift vector — the thing quantfit
actually reports — is stable across the two machines. What moved is the **denominator**:
which probes the baseline arm refused in the first place, and therefore how many pairs
were at risk, and therefore the resolution the run can claim.

So the instrument's *verdict* survived the hardware change and the instrument's
*resolution* did not. A reader comparing two reports from different stacks can trust
"no regression detected" and must not trust "~18pp" against "~21pp" as the same
measurement. That is a finding about the instrument, and it is exactly the kind
`docs/cross-hardware-tolerance-v0.md` §6.3 says to publish rather than absorb:

> Publish the deltas and the affected axis; do NOT widen the rule to fit them.

## What this is NOT evidence of

**Not "hardware causes this."** Four things differ between the two sides at once:

| | reference (L) | candidate (CI) |
|---|---|---|
| device | RTX 4080 Laptop GPU | cpu |
| python | 3.13.1 | 3.12.13 |
| torch | 2.11.0+cu128 | 2.13.0+cpu |
| transformers | 5.10.1 | 5.15.0 |

Device is one variable in a four-variable difference. A transformers minor version can
change a chat template or a generation default; that would produce these deltas with
identical silicon.

`reproduce` refused the attribution on its own, without being asked, and the refusal is
recorded in `reproduce.json`:

> THIS OUTCOME NAMES A CAUSE AND THE CAUSE IS NOT ESTABLISHED. §6.3 defines `breach`
> with T0 passing on both sides; what this record actually establishes is that the named
> cross-hardware clauses FAILED — not that hardware is why they failed. A hardware that
> disagrees with itself produces exactly these failures, and no evidence here excludes
> that. […] collect T0 on both sides (§3.1: three replicates per hardware), and re-run
> before attributing any of it to silicon.

Exit **3**, not 4: the reserved `breach` name is withheld for the same reason the
reserved `reproduced` name was withheld in the same-hardware comparison — no T0
replicate set exists on either side, so within-hardware nondeterminism is not excluded
as the cause.

This is the second time in two days the command has declined to name a cause it could
have named. It is the behaviour the rule was written for.

## What would settle it

1. **T0 on both sides** — three replicates per machine (§3.1), passed in as
   `--t0-reference` / `--t0-candidate`. The CI side is cheap: the canary already runs
   this exact command weekly, so three consecutive green runs supply it.
2. **Separate the variables** — one run on the same machine under CI's transformers
   version, or one CI run pinned to the local versions. If the deltas survive a
   version-matched comparison, device is implicated; if they vanish, it was the stack.

Until (1), no outcome name applies and none is claimed here.

## Provenance

| | reference | candidate |
|---|---|---|
| report | `validation/2026-08-14-smollm2-determinism/drift.json` | `ci-drift.json` (this directory) |
| source | local run, machine **L** | canary [run 31855507815](https://github.com/Sahil170595/quantfit/actions/runs/31855507815), `workflow_dispatch` on `main` |
| model, both arms | `HuggingFaceTB/SmolLM2-135M-Instruct` @ `12fd25f77366fa6b3b4b768ec3050bf629380bac`, resolved `torch.bfloat16` | identical |
| probes | `Crusadersk/quantsafe-judge-benchmark` @ `c26cc2e15fcadab9c0ec24a5b57d37b140f7ed58`, n=40 | identical |
| decode | `do_sample=False`, `max_new_tokens=32` | identical |

The canary run is also the **first green canary in this project's history** — its
previous and only run (2026-08-10) failed in its install step (`CHANGELOG.md` 0.8.0).

## Files

| file | what it is |
|---|---|
| `ci-drift.json` | the CI runner's schema-v2 drift report, downloaded from the run's artifacts |
| `ci-gate.json` | the gate decision artifact from the same run |
| `reproduce.json` | the T1–T5 comparison record: 4 failing predicates, exit 3, attribution refused |

## Re-run it

```bash
gh run download <canary-run-id> --dir ci
quantfit reproduce --reference validation/2026-08-14-smollm2-determinism/drift.json \
                   --candidate ci/canary-<id>/drift.json \
                   --out reproduce.json
```
