# Screen evidence bundles — 0.33.0 candidate

This unreleased interface transports a complete saved-screen population. It requires
the candidate source or built wheel; published 0.31.0 does not provide these commands.

```bash
quantfit bundle screen-create --targets targets.json --reports-dir reports --out handoff --json
quantfit bundle screen-verify --bundle relocated/handoff --json
```

Python APIs in `quantfit.screen_bundle` are
`create_screen_bundle(manifest_path, reports_dir, out_dir)` and
`verify_screen_bundle(bundle_dir)`. Both return the same verification record shape;
`ScreenBundleError` is a categorical operational refusal, mapped to CLI exit 2.
Content success exits 0 even when `receiving_summary.exit_code` is 3 (native flags)
or 4 (missing or unmeasured evidence). Read the nested verdict before making a gate
decision. The JSON envelope's command names are `bundle screen-create` and
`bundle screen-verify`.

The exact closed layout is `manifest.json`, `targets.json`, and a required `reports/`
directory, even for an all-missing screen. Original native reports occupy
`reports/<target-name>.json`. An original `reports/screen-summary.json` is optional:
its bytes are bound, but its claims remain ignored. The outer schema-1
`quantfit.screen-bundle` manifest binds path, SHA-256 and size for the original target
manifest and every present member. Its ordered report entries retain every target;
missing entries have null digest/size. No report is synthesized to fill a gap.

Creation and receiving validation hold original bytes, then compose the strict
saved-screen receiver. Native arithmetic, privacy, references, protocol, paired
identity/duplicate checks and per-axis measured-target denominators remain in force.
The resulting `quantfit.screen-bundle-verification` record includes the outer manifest,
its digest, transport byte count, limits and the rebuilt receiving summary. Fixed
receiving source labels do not add the producer manifest/report-directory paths;
declared model/provenance paths may remain. It follows no model,
capture, calibration or binary locator from the reports and performs no inference,
asset resolution or network call. Copying bytes does not demonstrate independent runs.

The complete transport is at most 64 MiB, counting the outer manifest, target manifest
and every member occurrence, including the ignored original summary. The outer
manifest is at most 256 KiB, target manifest 1 MiB, each report/summary 8 MiB, and the
population at most 256 targets. Declared sizes are charged before large member reads;
unexpected entries, symbolic links/reparse points, nonregular members, unsafe output aliases and
malformed/mismatched content are refused. Read-only regular hard-linked inputs are
supported; a hard link does not reduce the byte budget or bypass duplicate-evidence
validation. Output publication never replaces an existing member or destination.

The destination parent must exist. Creation exclusively creates a new final directory
after source validation and writes the outer manifest last as its ready marker.
Readers refuse an incomplete directory. Cleanup removes only unchanged files still
matching the creator's recorded identity and bytes under its owned directory; foreign
or substituted content is preserved. Existing/concurrently created destinations are
never replaced. This does not promise atomic directory visibility, crash recovery or
protection against a hostile process racing filesystem operations.

Treat bundles as private handoffs: native aggregates may contain declared model paths
and provenance labels. No upload or sanitization is performed. Hashes establish byte
binding, not a trusted signer, authentic execution, human confirmations, calibrated
sensitivity, statistical validity or scientific GO. Native unconfirmed flags, missing
evidence and sensitivity caveats remain attached even when transport verification
passes. The synthetic CLI record in
`validation/2026-10-18-screen-bundle/` establishes command behavior only.
