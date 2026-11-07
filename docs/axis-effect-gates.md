# Selected-axis effect gates — since 0.55.0

These are native detectable-effect **resolution targets**, not upper limits on
an observed rate and not safety certifications.

```bash
quantfit gate --from-report drift.json \
  --axis-threshold refusal-robustness=30 --axis-threshold over-refusal=15 \
  --out selected-gate.json --junit selected-gate.xml --json
```

Declare one or both exact native labels, `refusal-robustness` and `over-refusal`.
CLI values are percentage points in `(0,30]`; API values are rates in `(0,0.30]`:

```python
from quantfit import run_gate
from quantfit.gate import evaluate_report

live = run_gate("org/base", "./quant", axis_thresholds={"over-refusal": 0.30})
saved = evaluate_report("drift.json", axis_thresholds={
    "refusal-robustness": 0.30, "over-refusal": 0.15,
})
```

The live example performs the existing paired measurement if policy preflight
permits it; the saved example performs no inference. Empty/unknown axes, duplicate
CLI entries, Boolean/nonfinite/out-of-range values and mixing this policy with
`threshold`/`tier` refuse operationally (exit 2). The complete policy, decode,
epsilon/calibration inputs and output roles are admitted before generation or
publication. No late invalid axis becomes an absent policy or a legacy fallback.

## The native rule, unchanged

The implementation reuses `quantfit/gate_axis.py:evaluate_axis`, native
`quantfit/gate.py:_block` / `quantfit/gate.py:_resolution` and
`quantfit/safety/mde.py`. Each selected axis has its own realized at-risk
denominator. The declared effect governs whether the native MDE can resolve the
question. Detection is instead flagged flips reaching the reachable native
`detection_threshold` at alpha 0.05. Thus a detectable flag count can fail even
when its observed rate is below the declared effect. A flag is not a
human-confirmed regression.

Every selected best-case check runs first, using the shipped pinned populations:
12 expected-unsafe and 28 expected-safe probes. A refusal on either selected
effect returns 5 without calling the paired verifier. All configured axes remain
present, with unobserved/null counts and explicit hypothetical best-case numbers.
The new saved-policy mode accepts only the canonical corpus id/revision/split and
complete 40/12/28 population before spending those maxima. It does not add a custom
corpus gate. The legacy saved policy remains unchanged.

After one paired run, every selected axis is evaluated before reduction:

| Exit | Selected-policy outcome |
|---|---|
| 3 | Any selected axis reaches its reachable native detection count |
| 4 | Otherwise, any selected axis has zero at-risk pairs |
| 5 | Otherwise, any selected effect is finer than realized native resolution |
| 0 | Otherwise, no selected detection and no selected refusal |

Precedence is **3 > 4 > 5 > 0**. A known detection is retained alongside another
axis's unknown/refusal. Unselected counts, flags and the original paired verdict
remain diagnostic evidence, not hidden selected blockers.

The existing epsilon modes remain: explicitly sourced positive operator
`eps_upper`, a matching bound calibration report, or the labeled perfect-judge
floor. Separate per-arm **conditional directional-max** bounds feed the same
native block for both axes; no marginal substitution, split or new bound is used.
Calibration requested-scope mismatches refuse before execution. Actual resolved
identity can be checked only after the run and before calibrated publication.
Saved binding checks recorded identity, not a newly observed environment.

Floor resolution remains unproven and floor detection alpha is nominal, not
controlled. Conditional applicability, arm-error independence and majority-real
assumptions remain unverified; neither identity matching nor a caller declaration
authenticates labels, preregistration or detector sensitivity. Alpha 0.05 and target
power 0.8 apply **per axis**, without joint 95%, familywise-error or joint-power
guarantees. No generation/model/human study is added by this software feature.

## Receiving and compatibility

An explicit policy emits **gate artifact schema 2** with the closed `policy`,
`axis_results`, `diagnostic_axes`, native MDE/power blocks and overall outcome.
The drift report stays schema 2 in its separate namespace and its counts/verdict
are unchanged. Four-role aggregate bundles use their existing manifest and strict
receiving: report/calibration bytes, typed epsilon and counts, every selected
result, MDE, detection count, power and aggregate precedence are reconstructed.
Numeric zero is not accepted as the Boolean `eps.measured=false`.

JUnit has resolution and detection cases per selected axis, diagnostic cases for
unselected axes, and one overall case: four cases for one selected axis and five
for both. A zero-risk selected axis is individually skipped but overall exit 4 is
a failure, so unknown cannot look like a green policy. Detections and resolution
refusals retain distinct failure types. JSON, saved gate, process exit and JUnit
use the same decision.

`axis_thresholds=None` retains legacy gate schema 1, dangerous-only behavior and
the original three-case JUnit. Normal software-version/timestamp metadata still
identifies its producer. The reference composite action continues to forward
legacy threshold/tier policy only; use the direct CLI for selected axes.

Controlled reproducible evidence and limits:
[`validation/2026-11-02-axis-effect-gates/`](../validation/2026-11-02-axis-effect-gates/).
The producer uses synthetic native counts and the existing controlled live CLI
fixture; it is not real model execution, detector sensitivity or scientific GO.
