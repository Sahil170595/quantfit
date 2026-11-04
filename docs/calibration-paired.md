# Paired calibration diagnostics (quantfit 0.39.0)

`calibrate paired` compares supplied labels with captured judge observations while
preserving the original baseline/quantized pairing. It requires the accepted
0.38 held capture/key admission and either a complete original sheet or the
0.37 explicit retained-label workflow. Install `quantfit==0.39.0`; Python source/unit
support remains 3.10+, while the complete locked runtime requires Python 3.11+.

```bash
quantfit calibrate paired --capture private.capture.jsonl --key private.labelkey.json --sheet filled.labels.csv --out paired.json --json
quantfit calibrate extract --sheet filled.labels.csv --key private.labelkey.json --out private.retained.labels.csv --receipt retention.json --json
quantfit calibrate paired --capture private.capture.jsonl --key private.labelkey.json --retained-labels private.retained.labels.csv --retention-receipt retention.json --out retained-paired.json --json
```

The product never deletes source material. Retained mode can run after the original
sheet is unavailable, but still needs the original capture, key, retained labels
and receipt. It verifies their held bytes before analysis. No capture regeneration,
private-label upload, model contact or automatic adjudication is performed.

## Populations and table orientation

`pair_state_order` is `RR, RC, CR, CC`, baseline first. `R` means refusal and `C`
compliance, separately for the judge and supplied labels. `coverage` retains all
admitted pairs: total, both labels usable, only baseline unusable, only quantized
unusable, and both unusable. `analysis_complete` is false when any pair lacks two
usable labels. Successful descriptive completion still exits 0; this is not an
assertion that label coverage is complete. `common_population_unmeasured` marks
zero common-usable pairs. A missing structural pair is invalid, not an unusable
label, and refuses 2.

`whole_judge_pair_state_counts` counts every pair, including unusable labels.
`common_usable` retains only pairs with two usable labels and contains:

| Field | Rows | Columns | Population |
|---|---|---|---|
| `judge_by_human_pair_state` | judge RR/RC/CR/CC | supplied-label RR/RC/CR/CC | two usable labels |
| `baseline_error_by_quantized_error` | baseline judge/label mismatch | quantized judge/label mismatch | same two-usable-label pairs |

`boolean_state_order` is `[false, true]`. A mismatch is defined against a supplied
label, not authenticated human truth. Judge and label pair-state marginals are
reported alongside the tables. The joint tables retain information that separate
per-arm error summaries cannot recover: tests include identical per-arm errors and
error marginals with opposite pair association.

## Expected groups and at-risk denominators

`axes.dangerous` uses expected-unsafe pairs and refusal→compliance (`RC`) flips.
`axes.overrefusal` uses expected-safe pairs and compliance→refusal (`CR`) flips.
Expected is read from validated capture metadata, never inferred from zone;
`borderline` with expected unsafe is valid.

Each axis reports `whole_judge.n_pairs_expected` and its judge-only at-risk/flips
separately from `common_usable.n_pairs_expected`. The latter population contains
**all** two-usable-label pairs in that expected group. Its
`judge_flip_by_human_flip` rows are judge flip false/true; columns are supplied-label
flip false/true. False means no flip, including a baseline that was not at risk.
It does not mean correct, safe, or a true negative. The joint table therefore is
not an at-risk-conditional cross-tabulation.

Within the same common-usable expected group, `judge` and `human` each retain their
own `n_at_risk`, `n_flips`, conditional `rate` and native `wilson95`. Expected-unsafe
risk requires baseline refusal; expected-safe risk requires baseline compliance,
using the corresponding source's baseline observation. Whole-judge rate summaries
have their own population too. A judge flip on an unusable-label pair appears only
in whole-judge counts and cannot bias the common comparison.

Zero-at-risk rates are null, `at_risk_unmeasured` is true and native Wilson is
`[0,1]`. No missing label is silently converted to a negative observation. These
source-specific intervals are descriptive conditional summaries with the native
assumptions; their differing denominators do not supply a bias estimate, paired
inference, a test of independence or evidence that complete cases represent the
excluded labels. No McNemar/Newcombe test, pooled `2n` inference or correction is
computed.

## Admission, privacy and publication

The unchanged [strata admission](calibration-strata.md) holds each input once,
requires a complete v2 key, matches actual capture SHA/header/effective binding and
every pair/arm judge flag and completion digest, and validates cross-arm zone and
expected metadata. Native capture-v1/key-v2 is explicitly unbound. Existing strict
JSON, numeric token, key-salt, physical-record and input-work caps apply unchanged:
capture 16 MiB, key 2 MiB, sheet 8 MiB, retained labels 2 MiB, receipt 64 KiB,
at most 4,096 pairs and 16,385 physical capture records. Accepted held-input totals
are at most 26 MiB in full mode and 20 MiB + 64 KiB in retained mode; these are
input/work bounds, not a whole-process memory or runtime guarantee.

Output is capped at 256 KiB encoded before publication. Both JSON output and the
CLI envelope contain only fixed vocabulary, counts/statistics, whole-input
hashes/sizes, a fingerprint and declared proof limits. No row IDs, per-row labels,
text, salts, caller paths or key-derived model identity are reflected. Byte/header
agreement is not source authentication. In retained mode, the original-sheet hash
is a receipt declaration and `held_and_validated=false`, not a fresh read. In full
mode, true means the present held sheet passed native joins, not authenticated
historical labels.

The unchanged publisher uses staged, exclusive, write-once publication, refuses
existing/aliased/unsafe output and rechecks held identities. It is not a hostile-
filesystem transaction; a failed publication can leave a partial new target and a
failed stage cleanup can leave residue. Categorical `invalid_calibration_paired`
exit 2 suppresses private parser/IO causes. No output is a calibration schema: both
the native bound loader and actual gate reject using it as replacement calibration.

`validation/2026-10-23-calibration-paired/` records the actual fictional 24-pair full
CLI→extract→owned-sheet removal→retained CLI workflow. The existing installed-origin
guard runs the same consumer for Ubuntu/Windows wheel/sdist; hosted proof is separate
from local source checks. Protected-main source/security qualification and versioned
release qualification remain separate requirements.

This does not authenticate labels or raters, establish independent execution,
calibration validity, sensitivity or scientific GO. It does not replace calibration,
alter native verdicts, wire a gate or perform label review/adjudication.
