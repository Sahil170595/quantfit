# Saved-report policy replay

This unreleased interface evaluates a saved schema-v2 aggregate without models,
judge execution, downloads or completion caches. A public 0.16 install does not
advertise `--from-report`; install a reviewed candidate for this opt-in path.

```bash
quantfit gate --from-report drift.json --threshold 30 --out gate.json --report copied-drift.json --junit gate.xml
quantfit gate --from-report drift.json --tier smoke --calibration-report calibration.json --out conditional-gate.json
```

Thresholds remain percentage points at the CLI. API rates remain fractions:

```python
from quantfit.gate import evaluate_report

decision = evaluate_report("drift.json", threshold=0.30, out_path="gate.json")
```

The API also accepts `tier`, `eps_upper`/`eps_source`, `calibration_report` and
`report_path_out`. Declare one threshold/tier and one epsilon mode. Without
calibration/operator bounds, results carry the existing perfect-judge floor.

Report and calibration inputs are read, hashed and validated once. Saved verdict,
Wilson interval, MDE and aggregate flags must agree with counts. Wrong schemas,
private/raw fields, duplicate keys, nonfinite numbers, inconsistent counts and
calibration scope mismatch refuse operationally (exit 2). Greedy decode/token limit
and arm names come from the report. Live arms, `--token`, `--max-new-tokens`, and
`--baseline-cache` are refused; an explicitly supplied matching limit is still refused.
`--report` copies held original bytes, including best-case refusal. Input/output and
output/output aliases, including hardlinks and symlinks, refuse before writing.

Native policy order remains unchanged. Its pinned-corpus best-case check can
return 5 before count evaluation: `resolution.stage=pre_run`, null decision drift,
and `source_evidence.evaluation_phase=policy_preflight`. This is a policy phase
applied after consuming an already-produced report, not predeployment chronology.
Otherwise actual dangerous at-risk counts determine 0/3/4/5 using the same native
post-observation rules. Over-refusal never changes the gate code and is explicitly
reconciled with the report's own verdict. Flags remain unconfirmed. Dangerous 0/n
means the detector did not fire; no absence, sensitivity, scientific GO or safety claim.

Replay alone adds the closed schema-1 `source_evidence` block: `kind=saved_report`,
exact `report_sha256`, policy phase, and `inference_performed=false`. Legacy gate
keys/statuses/messages are unchanged. Four-role schema-1 bundles support replay
gate/report/optional calibration and resolution without a new manifest format.
Every replay gate requires its consumed report role even when its decision drift
is null. Relocation verifies SHA256 rather than treating `arms.report` as identity.

Bound calibration matches the recorded report scope (`actual_run_matched=true`),
including policy refusal. The canonical statement says weights/environment were
not freshly observed. `measured=false`, `assumptions_verified=false` and A1/A2/A3
remain explicit; binding never authenticates labels or the producing host.
JUnit uses recorded arm names and preserves refusal/unmeasurable/ungated cases.

The composite action accepts `from-report` instead of baseline/quant. Do not set
`max-new-tokens` or `hf-token`. Use its existing `quantfit-path` to install the exact
candidate wheel; preflight requires the new capability only when requested.
Outputs include `replay-source-sha256`, `evaluation-phase`, and
`inference-performed`; the latter is false for replay and not_applicable for live
gates. All nonzero codes still fail the action; evidence uploads on refusals.

Functional validation and limitations: `validation/2026-10-09-saved-report-gate/`.
Saved Phi4 aggregates are real earlier measurements; replay does not rerun them.
Synthetic adverse tests prove contract behavior, not scientific qualification.
