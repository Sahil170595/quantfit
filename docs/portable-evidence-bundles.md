# Portable aggregate evidence bundles

`quantfit bundle create` packages supported aggregate JSON files for offline transfer.
`quantfit bundle verify` checks their bytes and relationships after relocation. Neither
command loads a model, fetches a URL, follows an artifact's original source paths, or
publishes anything. The implementation is `quantfit/bundle.py`.

```bash
quantfit bundle create --report drift.json --calibration-report calibration.json \
  --resolution resolution.json --gate gate.json --out evidence --json
quantfit bundle verify --bundle relocated/evidence --json
```

The API equivalents are `create_bundle(report_path, out_path, calibration_path=None,
gate_path=None, resolution_path=None)` and `verify_bundle(bundle_path)`. Optional paths
are keyword arguments. Each input is consumed once; validation, hashing and copying use
that same byte buffer. The source files are never modified. The destination must be a
new directory with an existing parent; existing destinations and input aliases fail.

Four fixed roles are supported: schema-v2 `report.json`, bound schema-2
`calibration.json`, schema-1 `gate.json`, and conditional `resolution.json`.
The manifest declares relative role filenames, byte lengths and SHA-256 hashes.
Unknown roles, extra files, absolute/traversing/noncanonical member paths, links and
junctions fail closed. Renaming a capture, raw label sheet, baseline cache, or arbitrary
JSON does not make it an aggregate role. Report metadata supports the current
Transformers, llama.cpp and Inspect aggregate shapes, including the aggregate cache
provenance marker; the cache's completion payload is never included.

A supplied calibration must match the included report's scope. A supplied resolution
must match analysis recomputed from the exact bundled report and calibration bytes,
apart from its generation clock/version metadata. Observed gates require an included
report with matching arms, decode and drift counts. Gate arithmetic and decision
precedence are checked with the existing gate primitives; the bundle does not replace
the gate's decision rule or suppress an ungated-axis regression.

Computed floating-point statistics use the calibration validator's existing
`1e-12` relative/absolute tolerance so a final binary-digit difference between
Windows and Linux does not refuse unchanged evidence. Counts retain integer types;
booleans, hashes, status and claim wording remain exact. Bound gate decisions are
recomputed from the validated calibration bounds. The original JSON bytes are copied
and hashed without rounding or regeneration.

A real pre-run refusal has no observed report. Package it without inventing one:

```bash
quantfit bundle create --gate refused-gate.json --out negative-evidence --json
```

For a bound pre-run refusal, also supply `--calibration-report calibration.json`.
The omitted report is accepted only for a validated pre-run exit-5 decision whose
drift is absent. Its `arms.report` may name a requested destination; that historical
locator is never treated as an observed report or opened during verification.
Its actual-run binding remains false. Calibration-only bundles and resolution without
its report/calibration are refused. Three-report T0 evidence is outside this version's
schema-1 four-role interface; a disconnected T0 declaration is not accepted.
The separate candidate schema-2 [three-report T0 handoff](replicate-bundles.md)
uses `bundle replay-create` / `bundle replay-verify` and preserves the original
producer bytes. It does not change the schema-1 interface described here.

Exit 0 means format/relationship and declared-byte integrity checks succeeded. Exit 3
means a member's length or SHA-256 differs from the manifest. Exit 2 means unsupported
input/layout, inconsistent aggregates, or an operational failure. Thus an intact bundle
can contain a gate exit 3, 4 or 5, regression flags, unmeasurable axes, and conditional
assumptions: verification never promotes these into a passing measurement.

Every result sets `scientific_claims_verified` to false. A manifest is an assertion,
not a signature or authenticated origin: editing both a member and its manifest can
create another internally consistent bundle. Binding and byte integrity authenticate
neither human label truth, sensitivity, independent error assumptions, a safety verdict,
research GO nor independent reproduction. The existing analyzer's 4096-probe work bound
and aggregate byte bounds remain implementation limits, not scientific eligibility
rules. QSR v1 remains unfrozen.

Synthetic local functional records and their limitations are in
`validation/2026-10-08-portable-evidence-bundles/`. Hosted numerical/runtime and installed
wheel/sdist qualification remain pending until the five-PR batch is pushed.
