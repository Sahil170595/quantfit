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

Four fixed roles are supported: schema-v2 `report.json`, native bound
`calibration.json`, native `gate.json`, and conditional `resolution.json`.
The outer bundle remains schema 1; its native receiver also supports the existing
bound retained calibration and selected-axis/corpus gate variants.
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
The separate schema-2 [three-report T0 handoff](replicate-bundles.md)
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
`validation/2026-10-08-portable-evidence-bundles/`. The introduced source passed [hosted acceptance](https://github.com/Sahil170595/quantfit/actions/runs/37880847032); release publication separately qualifies the exact versioned distributions.

<a id="single-file-transport-0590-candidate"></a>

## Single-file transport (0.59.0)

Quantfit 0.59.0 can carry this existing **outer schema-1**
directory in one deterministic archive. Identical exact directory bytes produce
identical archive bytes; a newly generated manifest can have a different clock.
Replay/schema-2 and screen bundles have different receiving contracts and are
not admitted as schema-1 archives.

```bash
quantfit bundle pack --bundle evidence --out evidence.zip --json
quantfit bundle archive-verify --archive evidence.zip --sha256 FULL64 --json
quantfit bundle unpack --archive evidence.zip --sha256 FULL64 --out received-evidence --json
quantfit bundle verify --bundle received-evidence --json
```

Use the actual `archive.sha256` returned by pack as `FULL64` (lowercase 64 hex).
Receiving always checks that complete raw hash before ZIP parsing. It is an
expected integrity pin, not a signature or an authenticated publisher identity.
A malformed pin, mismatched hash, unsupported archive, invalid native relationship
or unsafe destination exits 2. Successful transport exits 0 only for container
integrity; nested report/gate adverse and unknown outcomes remain unchanged,
including a pre-run refusal with no report. Existing directory byte-mismatch
exit 3 remains unchanged. No inferred PASS, synthetic generation or redaction is
introduced.

API functions in `quantfit.bundle_transport` are:

```python
packed = pack_bundle("evidence", "evidence.zip")
checked = verify_bundle_archive("evidence.zip", packed["archive"]["sha256"])
received = unpack_bundle("evidence.zip", packed["archive"]["sha256"], "received-evidence")
```

The closed format is ZIP_STORED, no compression, encryption or ZIP64; fixed member
order is manifest, report, calibration, gate, resolution (omitting absent roles).
Timestamps are 1980-01-01, creator is Unix, members are regular mode 0600, and
comments/extra fields are empty. Every member name must be exact and flat; no
normalization, duplicate, extra, nested, absolute, traversal, backslash, NUL or
special/symlink entry is admitted. Declared entry count and central-directory
bytes are bounded **before** SDK construction, including refusal of ZIP64
locator overrides. The native ZIP reader checks headers, sizes, overlap and CRC;
whole canonical reserialization equality then refuses alternate headers, ordering,
metadata and trailers. An arbitrary ZIP from another tool is not this format.

At most five members: manifest <=64 KiB, report/gate/resolution <=8 MiB each,
calibration <=2 MiB, whole payload <=26 MiB +64 KiB and raw archive <=32 MiB.
All roles and native relationships are validated from the same held buffers
before destination creation. These are byte/work admission bounds, not a hard
heap-allocation limit. No capture, raw labels, cache or model role is allowed;
no producer URL or original artifact path is followed.

Pack holds every directory member once and checks the exact inventory. Output
anywhere inside that source directory is refused. It stages bytes in the final
parent, then atomically creates an exclusive hard link; unsupported hard linking
refuses without a replacing-rename fallback. Existing archives are never
replaced, and failure before publication leaves no partial final archive.

Unpack requires a **fresh, absent** directory with an existing parent. It reserves
that directory exclusively and writes the exact original manifest last as a
readiness marker. It is not an atomic directory transaction. On failure, cleanup
only removes inode-attested regular files whose bytes are an expected prefix,
then the empty owned directory. Replaced paths or unknown entries are preserved,
never recursively deleted. `partial_destination_preserved` reports uncertain
restoration ownership; `archive_stage_preserved` reports an unattested stage.
Keep and inspect those resources rather than retrying destructive cleanup.
Mode bits are requested where supported; Windows still uses inherited ACLs.
Ordinary identity checks do not guarantee protection from every hostile rename
or crash. The tool grants no new sharing permission and never deletes inputs.

[Controlled source checks](../validation/2026-11-07-bundle-transport/README.md)
include out-of-band expected-pin refusal, native adverse roundtrip, hostile ZIPs,
parser admission and failure/cleanup/retry controls. Four hosted installed
profiles are extended; their execution and public release are separate evidence.


## Explicit archive kinds (0.64.0)

Available since **0.64.0**.
Only the three existing archive commands accept `--kind aggregate|replay|screen`:

```bash
quantfit bundle pack --kind replay --bundle original-replay --out replay.zip --json
quantfit bundle archive-verify --kind replay --archive replay.zip --sha256 FULL64 --json
quantfit bundle unpack --kind replay --archive replay.zip --sha256 FULL64 --out new-replay --json
quantfit bundle replay-verify --bundle new-replay --json
quantfit bundle pack --kind screen --bundle original-screen --out screen.zip --json
quantfit bundle archive-verify --kind screen --archive screen.zip --sha256 FULL64 --json
quantfit bundle unpack --kind screen --archive screen.zip --sha256 FULL64 --out new-screen --json
quantfit bundle screen-verify --bundle new-screen --json
```

The SDK adds the same keyword-only `kind="aggregate"` to `pack_bundle`,
`verify_bundle_archive` and `unpack_bundle`. Admit an exact canonical string before
path work. Omitted and explicit aggregate retain the original schema-1 ZIP bytes,
result, default human output and limits. The dated ownership-diagnostic repair below
applies to all kinds. Other kinds require explicit selection:
wrong kinds refuse; there is no inference or fallback. Selected replay/screen results
are a closed transport schema 2 with `kind`, raw `archive` hash/size, original
`manifest`, `integrity_verified`, `scientific_claims_verified: false`,
`native_verification` and `scope`.

| Profile | ZIP members | Raw archive cap | Native payload cap | Maximum safe member name / central directory |
| --- | --- | --- | --- | --- |
| Aggregate (unchanged) | 2–5 | 32 MiB | 27,328,512 bytes | 16 / 310 bytes |
| Replay | exactly 5 | 33 MiB | 33,619,968 bytes | 13 / 295 bytes |
| Screen | 2–259 | 65 MiB | 64 MiB **including** outer manifest, targets, all reports and optional summary | 77 / 31,857 bytes |

Replay contains original `manifest.json`, `report-1.json` through `report-3.json`
and `t0.json`, in that canonical ZIP order. Each report/T0 is bounded to 8 MiB;
the manifest is 64 KiB. Maximum canonical replay is exactly 33,620,488 bytes,
including 520 bytes of stored-ZIP overhead. Native closed manifest/member hash
validation and original `_validate`/T0 logic are reused. Producer locations remain
unverified labels and are never read. Archive receiving T0 uses canonical relative
report labels; native verification of the restored directory honestly relocates its
receiving labels. Original T0 bytes, facts and adverse protocol outcomes are unchanged.

Screen contains original `manifest.json`, `targets.json`, PRESENT reports in the
original requested target order, then the optional original
`reports/screen-summary.json`. There are no directory entries in the ZIP. Only native
safe ASCII `reports/NAME.json` members are admitted; no arbitrary nested tree is
transported. Outer manifest is bounded to 256 KiB, targets to 1 MiB, each report/summary
to 8 MiB and all roles together to native 64 MiB. Maximum 256 targets and the optional
summary produce at most 259 entries and 59,592 bytes of conservative ZIP overhead.
Native held screen verification rebuilds all original target rows, including missing
members and native exits 3/4. A producer summary remains untrusted bytes. All-missing
screens still restore an empty `reports/` directory.

Both profiles pin the full raw SHA256 before any ZIP parse. Final classic EOCD,
single-disk/no-comment/count/central bounds precede `ZipFile` construction. ZIP64,
compression, encryption, extras, descriptors, special files, duplicate/casefold names,
traversal, backslashes, NUL/non-ASCII names, alternate headers/order/metadata, CRC/size
mismatch, prefix polyglots and trailers refuse. Full canonical re-encoding equality
closes alternate ZIP representations. Every declared size is admitted before large
payload reads. Source roles are held once with native stability/ancestor guards and
closed inventories; verification never follows original paths or rereads a directory
through a creator.

Archives retain exclusive atomic publication. Restore only into a fresh directory:
replay uses native flat ownership; screen reuses the native nested publication with
child identities and manifest last. Archive/ancestor checks continue through selected
screen writes. Only attested owned files are eligible for cleanup; unknown members,
substituted roots/reports or a successfully created but initially unattested root are
preserved and reported as `partial_destination_preserved`. Preexisting destinations
and failed mkdir remain ordinary categorical refusals. No recursive extraction,
deletion, destination recreation, directory transaction, crash-durability or hostile
concurrent-rename guarantee is offered.

Outer transport exit 0 means integrity only. Native T0/screen adverse or unknown
outcomes and all scientific/authentication caveats remain separate; no safety PASS,
model/judge/provider work or new data assets are implied. Exact fictional SDK/OS CLI,
maximum-boundary, adverse and ownership evidence lives under
`validation/2026-11-14-bundle-archive-kinds/`. All four existing installed profiles
select these controls and the native screen/CPU consumer; hosted qualification remains
separate. No jobs, artifact uploads or dependencies are added.


### Dated ownership-diagnostic repair (2026-11-14)

A controlled real archive publication can create the final hard link and then fail
stage cleanup because the stage was replaced, became unattestable or could not be
unlinked. The existing implementation correctly retained the uncertain stage, but
reported only `invalid_bundle_transport`. Quantfit 0.64.0 reports
`archive_stage_preserved` uniformly for aggregate, replay and screen. No unknown
stage is deleted and an already linked archive remains visible. Default aggregate
success bytes, schema, results and caps and unrelated refusals are unchanged.
The old nine-failure/new passing fault controls, including actual stage substitution
and retained linked output, are recorded separately from ordinary functional passes.
