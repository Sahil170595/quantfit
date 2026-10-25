# Conditional screen-requirement functional record — 2026-10-23

Fictional offline software evidence only. `acceptance.json` was produced on
Windows 11 10.0.26300, Intel64 Family 6 Model 183 Stepping 1, Python 3.12.13,
source/editable quantfit 0.41.0, locked Torch 2.13.0+cpu and Transformers 5.17.0.
This is not execution proof for another OS, Python version or provider.

From the repository root, using the existing locked validation environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B validation/2026-10-23-screen-requirement/reproduce.py --out validation/2026-10-23-screen-requirement/acceptance.json
```

Use a different new `--out` path for another run: the reproducer refuses to replace
a record. Owned private fixture material stays in a temporary directory and is
removed on completion; product receiving commands never delete caller sources.
Fresh native salts/capture timestamps change retained-source hashes.

`tools/ci_screen_requirement.py` uses the actual CLI, native `SafetyDrift` recount,
native calibration arm arithmetic and the existing scope-matched resolution
calculator. Report declarations originate in
`validation/2026-10-18-screen-bundle/inputs/`; they are fictional functional input,
not a new measurement of those models. The ordinary synthetic cases recount 120
probes with 60 at-risk pairs on **each** report axis. Their declared zero-error
calibration has baseline human R/C counts 60/60 and quantized 30/90: these calibration
denominators differ from report at-risk denominators. No human labeled these inputs.

Every case separately runs default annotation and required receiving, verifies
unchanged native rows/coverage/flags/manifest/report bindings, and compares CLI JSON
with the published receiving buffer and JUnit. Each product call holds its own inputs
once and uses its one authoritative analysis per present report/calibration pair;
the default/opt-in comparison is two explicit CLI calls, not one combined run.

| Case | Native exit | Qualified exit | JUnit cases / failures / skips |
| --- | --- | --- | --- |
| `qualified`, 120 probes, 40 pp | 0 | 0 | 4 / 0 / 0 |
| `coarse`, same counts, 30 pp | 0 | 5 | 4 / 3 / 0 |
| `saturated`, 40 probes, 100 pp | 0 | 5 | 4 / 3 / 0 |
| `missing`, calibration absent | 0 | 4 | 4 / 3 / 0 |
| `native_flagged`, 40 pp otherwise met | 3 | 3 | 4 / 2 / 0 |
| `mixed_flags`, three targets, missing plus coarse, 1 pp | 3 | 3 | 10 / 8 / 0 |
| `mixed_incomplete`, three targets, unmeasured/missing/coarse, 1 pp | 4 | 4 | 10 / 7 / 1 |
| `retained_schema3`, actual extract/ingest, 100 pp | 0 | 5 | 4 / 3 / 0 |

Both 120-probe axes return native effective MDE `0.3737690191664753` and
`detectable_at_target_power=true`, hence 37.37690191664753 pp passes 40 and fails
30. The `saturated` case has **20/20 at-risk report counts**, native MDE `1.0` and
detectability false on both axes. Even its 100 pp ceiling therefore fails. These
are native calculator outputs, not an independent power calculation or study.

The retained-schema-3 case separately uses the original 40-probe clean report with
12/28 at-risk pairs. It produces native private labels/key, actually extracts
retained labels, removes only the owned fictional full sheet, ingests schema 3 and
receives that calibration against the real saved-report scope. Both native axes
remain unattainable with MDE `1.0`; schema 3 is accepted without relaxing the requirement.

The flagged case has one dangerous-axis flagged flip and all resolution criteria
met; native 3 still wins. Mixed cases retain all three declared targets, both axes,
missing calibration and coarser/unmeasurable reasons despite native exit priority.
Native cases remain first; missing/unmeasured native skips remain skips, and the
new requirement cases add failures. All original input bytes remain unchanged.

The committed projection includes only fixed criteria, counts, hashes, admitted
fixture target names and explicit proof limits. It excludes ephemeral paths, full
native identity, private labels/IDs, text and salts. Whole native receiving artifacts
are intentionally unchanged and may retain declared model identities/paths; this
projection is not a product-wide sanitization claim.

No model inference, asset download, new statistical formula, human calibration study,
authenticated labels or directional-error assumptions, independent execution,
weight/source authenticity, sensitivity or scientific GO is established. A qualified
native 0 remains conditional no-detection. This is a `validation/` command record,
not the capped reference-report registry.
