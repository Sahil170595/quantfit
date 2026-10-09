# Offline replicate agreement

The candidate `repeatability` command compares exactly three saved schema-v2
aggregate reports, directly or from a schema-2 replay bundle. It runs offline
without model packages, inference, a judge, network or producer-path access.
It is unreleased and requires the candidate checkout/wheel.

```bash
quantfit repeatability --reports run-1.json run-2.json run-3.json --out agreement.json --junit agreement.xml --json
quantfit repeatability --bundle relocated/replicate-evidence --out agreement.json --junit agreement.xml --json
```

The typed API is `quantfit.repeatability.analyze_replicates(report_paths:
list[str] | None = None, *, bundle_path: str | None = None, out_path:
str | None = None) -> dict`. Input modes are mutually exclusive. Every report
is read once into a bounded buffer; validation, hashing, comparison and native T0
consume those same bytes. Bundle verification returns the held included bytes;
original producer locators remain unverified labels and are never followed.
Argument errors rejected by argparse produce exit 2, usage on stderr and empty
stdout. Errors dispatched after parsing use the selected JSON/prose mode.

Comparison covers the **full decoded original JSON**, including provenance
outside the native T0 identity. Exactly four predeclared volatile fields are
removed: `/created_utc`, `/judge_runtime_s`, `/baseline/runtime_s` and
`/quantized/runtime_s`. Runtime fields must first be finite nonnegative numbers.
All remaining types and values are exact: boolean/integer/float distinctions,
one-ULP differences, missing versus null, array order and causal metadata count.
JSON formatting and object-key order do not count. Difference locations are
RFC6901 pointers, escaping slashes and tildes to prevent ambiguous locations.

The result separately retains full-report agreement, native T0 and each run's
two original native axes/counts/verdict/exit. Native T0 uses the existing protocol
and identity logic. Canonical receiving aliases and hard links cannot become
three distinct files, even when their contents change between reads. Valid
reports with incompatible identities/environments remain `evidence_valid: true`;
their comparison and per-run facts survive while native T0 is `refused`, with
exit 2. Such refusal does not establish nondeterminism or malformed reports.

| Exit | Meaning |
|---|---|
| 0 | Full agreement, native T0 passes, and all original native runs exit 0 |
| 3 | Full/native T0 disagreement, or any original run retains native flags |
| 4 | Otherwise agreeing reports have an originally unmeasured axis |
| 2 | Malformed/unsupported input, native T0 refusal, or output failure |

An agreeing negative remains negative. The preserved historical Phi4 reports
have full/T0 agreement but each flags two unconfirmed over-refusal flips out of
20; the command exits 3. Dangerous 0/12 means **the detector did not fire**.
Counts are never pooled. Agreement does not authenticate independent execution,
physical hosts, human labels, sensitivity, reproduction qualification or GO.

JUnit has eight actual cases: two analysis cases and six original run-axis cases.
Payload/T0 disagreements fail analysis cases, native T0 refusal is an error,
original flags fail their axes, and unmeasured axes are skipped. Counts are
derived from the rendered cases. JSON/JUnit outputs must have existing parents,
cannot alias inputs/each other through paths or hard links, and cannot live
inside a closed bundle. Links/nonregular files are refused. Complete buffers
are staged first and each replacement is atomic; publication is not a
transaction across both outputs. Failed staging removes owned temporary files.

Local historical, explicitly synthetic, adverse and real source-CLI records are
in `validation/2026-10-09-repeatability/`. Installed wheel/sdist, Linux-only
filesystem tests and the Torch numerical lane await the hosted batch.
