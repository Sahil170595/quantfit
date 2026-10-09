# Portable three-report T0 handoff

The candidate `bundle replay-create` and `bundle replay-verify` commands transfer
exactly three saved aggregate reports and their original native T0 artifact. They
run offline; no model, judge, cache, network fetch or producer location is used.
These commands are unreleased and need the candidate checkout/wheel; public
0.16.0 does not provide them.

```bash
quantfit bundle replay-create --reports run-1.json run-2.json run-3.json --t0 native-t0.json --out replicate-evidence --json
quantfit bundle replay-verify --bundle relocated/replicate-evidence --json
```

The typed APIs are `quantfit.bundle.create_replay_bundle(report_paths: list[str],
t0_path: str, out_path: str)` and `verify_replay_bundle(bundle_path: str)`. Creation
requires a new output directory with an existing parent. Exactly three distinct
source files and byte-distinct reports are required, in the order bound by the
original T0. Copies/repeated paths and served-baseline cache markers are refused.

Schema 2 has exactly four fixed roles: `replicate-1`, `replicate-2`, `replicate-3`
and `t0`, stored as `report-1.json`, `report-2.json`, `report-3.json` and `t0.json`.
`manifest.json` binds those relative paths, original byte lengths and SHA256 hashes.
Unknown/missing/extra roles/files, traversal, noncanonical paths, links, junctions,
nonregular files and unsupported/raw JSON are refused. Inputs are held once;
validation, hashing and copying consume those same buffers. The manifest is
written last and failed partial/short writes, flush/close errors and cancellation
remove the owned incomplete bundle rather than advertise valid evidence.

The original `t0.json` is never rewritten. Its ordered source SHA bindings, native
instrument/environment identity, identity SHA, replicate count, agreement flags,
disagreement records, distinctness/independence fields and canonical statement
must match T0 recomputed from the validated held reports. Original producer paths
are **labels only**: a foreign absolute path or a relative name is never opened or
resolved, even if a namesake exists locally. SHA binding establishes which included
bytes were cited, not where they originated. `producer_locations_verified` is
always false. Identityless, unbound or forged positive legacy declarations are
refused; they cannot acquire qualification by being packaged.

Each result returns `original_t0` and a **separate** `receiving_t0` calculated with
the receiving member paths. This check is returned, not added as an extra bundle
member or substituted for the producer artifact. Producer files can be removed and
the bundle moved before verification; every original report/T0 byte remains intact.
Native T0 identity/drift logic is shared with `within_hardware_identical` through
held report views; no alternative protocol or widened disagreement tolerance is
introduced. Recorded identity facts retain exact types/values; report-derived
statistics retain the existing finite arithmetic checks.

Exit 0 means supported format, relationships and manifest-byte integrity match.
A genuine `protocol_pass: false` is a valid negative bundle and still exits 0.
Exit 3 means bytes/lengths differ from the manifest; T0 checks are then withheld.
Exit 2 means unsupported/malformed evidence, layout or an operational failure.
An existing schema-1 report/calibration/gate/resolution bundle still uses
`bundle create` / `bundle verify` with its original API, layout and result shape.

Integrity and native T0 do not establish full-payload repeatability, independent
execution, physical-host identity, authenticated human labels, sensitivity, a
scientific GO or cross-hardware reproduction. Replicates are not pooled and are
not independent reference reports. The preserved historical Phi4 example has
two unconfirmed over-refusal flags per run; dangerous 0/12 means **the detector
did not fire**. Local actual handoff and synthetic adverse records are in
`validation/2026-10-09-replicate-bundles/`; installed wheel/sdist and POSIX FIFO
qualification remain pending until the hosted batch runs.
