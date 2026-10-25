# Conditional finite-grid resolution budget — unreleased 0.44.0

This opt-in block requires 0.44.0 source or a candidate wheel. Published 0.41.0's
default `resolution` workflow remains unchanged. Planning evaluates one declared
**hypothetical at-risk** range under the supplied calibration bounds; it never
rewrites a report, its scope/corpus/actual denominators or observed verdict.

```bash
quantfit resolution --report drift.json --calibration-report calibration.json --plan-n-min 0 --plan-n-max 128 --plan-mde-pp 50 --plan-effect 30 --plan-effect 50 --out budget.json --json
```

All three `--plan-n-min`, `--plan-n-max` and `--plan-mde-pp` flags are required
together. `--plan-effect` can repeat for up to eight distinct effect sizes. Bounds
are inclusive integers, with **every integer** evaluated. Effect/MDE units are
percentage points: 30 means 30pp, not 0.30pp. The MDE ceiling is in (0,100], extra
effects in [0,100]. Native power 0.8 and alpha 0.05 stay fixed. Four registered
native effects are always reported; requested effects are additional descriptive
values even when equal to a registered effect. No favorable result selects them.

## Actual analysis and hypothetical curve

The complete options are validated before IO, range allocation or native math.
The original report (8 MiB maximum) and calibration (2 MiB) are each held once.
Native schema/scope receiving recomputes calibration counts/bounds, matches the
original measurement identity and validates every actual axis/zone count. Complete
actual-plus-planned work is admitted before any power, threshold or MDE evaluation.
No hypothetical report or relaxed calibration binding is constructed.

Existing `resolution_schema=1` keeps its original hashes, fingerprint, distinct
actual axes/counts, flags, statistics and caveats. Only the opt-in adds `planning`.
Default calls preserve shape/statistics/output behavior. An actual zero-at-risk
axis remains unmeasurable even if hypothetical points pass. Hypothetical at-risk n
is neither a future observation nor a guarantee of that many probes/usable samples.

The axes use the same global directional-bound union q at hypothetical n, so one
curve is emitted. These are not two independent axis measurements. Each point
uses native `detection_threshold`, `_power`, `_effective_mde_at` and a local exact
`(n,q,alpha)` threshold cache. No rounded keys, new statistics, global cache or
duplicate binomial implementation is used. Planned points omit an extra perfect-
judge contrast; the unchanged actual analysis retains its native contrast.

Each point records hypothetical n, threshold, effective MDE, detectability at
target power, MDE-ceiling criterion, registered and requested powers. Native MDE
1.0 can mean unattainable: even a 100pp ceiling requires actual power at a 100%
effect to meet the target. Zero n, saturated error and unreachable thresholds
cannot pass through that sentinel.

Native threshold jumps make power/MDE nonmonotone in n. At q=0.055, MDE is near
44.7pp at n=6 and 54.7pp at n=7: six can meet 50pp while seven fail. Therefore:

- `first_passing_n` is the first feasible point, or null.
- `feasible_runs` contains every maximal contiguous passing integer interval.
- `stable_suffix` is the last passing interval **only if it ends at n_max**,
  otherwise null. It proves nothing above that finite endpoint.
- `no_feasible_point` is true when no point in the declared range passes.

This is exhaustive finite enumeration, never monotone bisection on n, a universal
minimum sample size or a recommendation to add observations until a result passes.
No adaptive stopping, protocol amendment, sampling permission or new evidence follows.

## Bounds and output

0 <= n_min <= n_max <= 4096, at most 256 points, at most eight requested effects.
One separate ceiling admits 40,000,000 conservative tail/scan units across actual
and planned analysis. It is not wall time, peak memory or exact operation counting.
For n define T=n(n+1)/2, S=n+1 and C=T+S. Current actual native analysis is charged
**3C+127S per axis**, including zero axes: calibrated MDE, perfect-judge contrast
and detectability each obtain a threshold. The 127 requests include both native
60-iteration MDE searches, initial max-effect checks, registered powers and
detectability. Actual analysis is not assumed cached.

Each planned point is charged **C+(66+E)S** for E requested effects: one threshold,
the native 60-iteration MDE plus initial check, four registered powers, detectability
and E extra powers. Coefficients derive from native constants. The **complete sum**
is admitted before math; no cheap prefix runs before a costly last-point refusal.
For scale, actual axes 4096+0 plus one planned n=4096 with eight effects charge
34,402,639 units. Wider high-n grids may refuse. Saved-screen work units are separate.

Output is capped at 4 MiB after serialization, before publication. Opt-in mode uses
native held/exclusive IO: all actual input/output aliases, existing targets, links
and special files refuse; held files are checked again at finish. It writes one
NEW output, never overwriting another artifact. Default resolution's prior output
replacement behavior stays unchanged. Failure can leave a new partial file or
cleanup residue; no hostile-filesystem transaction or rollback deletion is promised.
Invalid/configuration/scope/unsafe-output/work-budget refusal is categorical
`invalid_resolution_budget`, exit 2. Completed planning, including no feasible point
or actual unmeasurable axes, remains analysis success **0**, not a gate decision.

## API and evidence

```python
from quantfit.resolution import analyze_resolution, analyze_resolution_inputs, analyze_resolution_bytes
from quantfit.resolution_budget import ResolutionBudget

plan = ResolutionBudget(n_min=0, n_max=128, max_mde_pp=50.0, effects_pp=(30.0, 50.0))
result = analyze_resolution("drift.json", "calibration.json", "budget.json", planning=plan)
# The same optional planning= applies to held-input and pure-byte adapters.
```

Directional-bound applicability, arm-independent errors and majority-real at-risk
assumptions remain unverified. Arm-correlated error is bias no sample size repairs.
Matching metadata/counts authenticates neither human labels/source nor future
distribution, independence or sensitivity. No safety or scientific GO is issued.

`validation/2026-10-25-resolution-budget/` records actual CLI/API execution using
existing fictional reports and manufactured calibration: 129-point enumeration,
native summaries/counts/hashes, unchanged actual axes and no-feasible completion.
Tests independently compare small grids to native primitives, pin nonmonotone 6/7
and sentinel behavior, and cover all-before-math budget/scope/option refusals,
held adapters, IO/races and default compatibility. Installed-origin consumers run
on Ubuntu/Windows wheel/sdist. Exact-head hosted qualification is linked on the PR;
these command checks are not new observations or a calibration study.
