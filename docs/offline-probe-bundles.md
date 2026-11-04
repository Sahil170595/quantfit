# Private whole local probe populations — unreleased 0.55.0

`LocalProbeCorpus(sha256)` is an explicit alternative to the existing Hub
`ProbeCorpus(id, revision, split)`. It identifies every byte of one private local
bundle; it contains no path, Hub identifier or pretend commit. A pin authenticates
neither the source nor curation, complete upstream provenance, label truth,
sensitivity or scientific suitability. Even forty local rows remain noncanonical.
The public release remains 0.51.0; these are source-candidate interfaces.

## Build and use the complete population

Keep both input and bundle private. The builder accepts a UTF-8 JSON array of
objects with exactly `prompt`, `zone` and `expected`. Prompt strings retain their
order, duplicates, whitespace, CR/LF and NUL. `zone` is `clear_safe`,
`clear_unsafe` or `borderline`; independently declare `expected` as `safe` or
`unsafe`. It is never inferred from the zone. Labels are operator declarations.

```python
from quantfit import LocalProbeCorpus, prepare_probe_bundle, verify_safety

receipt = prepare_probe_bundle("private.probe-rows.json", out_path="private.probe-bundle.json")
source = LocalProbeCorpus(receipt["sha256"])
drift = verify_safety(
    "org/base", "./out", probe_corpus=source,
    probe_bundle_path="private.probe-bundle.json", report_path="drift.json",
)
```

```bash
quantfit probes bundle --rows private.probe-rows.json --out private.probe-bundle.json --json
quantfit verify-safety --baseline org/base --quant ./out --probe-bundle private.probe-bundle.json --probe-sha256 FULL64 --report drift.json --json
quantfit gate --baseline org/base --quant ./out --probe-bundle private.probe-bundle.json --probe-sha256 FULL64 --threshold 30 --report gate.report.json --out gate.json --junit gate.xml --json
quantfit screen --targets manifest.json --out reports --probe-bundle private.probe-bundle.json --probe-sha256 FULL64 --json
```

`FULL64` means the exact lowercase SHA-256 returned by the builder. CLI live
commands require **both** local flags and reject the old Hub triplet alongside
them. `inspect-run` accepts the same pair; SDK `qsr_samples`, `qsr_dataset`,
`qsr_paired_diff` and `qsr_eval` accept `probe_corpus=source` plus the separate live
path. Existing backend/configuration admission still applies. These examples
request actual model work; controlled validation below establishes no real model.

The saved manifest remains schema 1. Screen holds one native population for all
targets and retries, including its original order. Returned native reports must
match that held identity and census before rows qualify. No pooling, selection,
deduplication or additional statistical engine is introduced.

## Exact wire and limits

The bundle has exactly `{"probe_bundle_schema": 1, "probes": [...]}`. Schema 1
is an integer, not a Boolean. Rows have the same three closed keys as the input
array. Both files must be strict UTF-8 without a BOM, at most 64 MiB of raw bytes;
duplicate JSON keys, nonfinite numbers, nonnative types, extra fields and trailing
content are refused. The entire file, including EOF and the final row, is admitted
before any model or observer is created. It is a whole population of 1–4096 rows,
not a sample, split selector or head limit.

Each prompt is nonempty and at most 65,536 UTF-8 bytes. The sum of UTF-8 bytes in
all selected prompt/zone/expected strings is at most 8,388,608, using unchanged
native accounting. The raw-file limit is separate from the selected-string limit;
JSON escaping can expand the representation. These are application admission
bounds, not a heap, parser-allocation, time or hostile-filesystem transaction
guarantee. No truncation or normalization is used to fit a limit.

The builder exclusively creates a new regular output after whole admission. Live
input files and all known report/capture/JUnit/model/cache roles are admitted
before contact and rechecked at publication. Native links/identity/alias rules
apply, including actual derived GGUF cache filenames and simultaneous outputs.
Known bad paths are refused; no unseen remote cache file is inferred. Ordinary
held-file checks detect common edits and replacements, not adversarial races.

## Identity through receiving and calibration

Local reports retain schema 2 and declare exactly
`{source_kind: "local", format: "quantfit-probe-bundle-v1", sha256: FULL64, n_probes: N}`.
Flat gate schema 3 retains native decision schema 1 or 2; screen and saved-summary
opt-in schema 2 retain the same closed source plus native expected/zone census and
its declared basis. A missing-all-reports summary uses null census fields, never
fabricated zeros. Existing Hub and `None` domains/shapes remain unchanged.

Captures and their labeling keys bind local measurement identity schema 2, with
the full source hash and no private path. Both direct schema-2 calibration and
extracted-label schema-3 calibration retain this non-null identity. Existing Hub
identity schema 1 is unchanged. Source agreement alone grants no calibration or
historical default-distribution false-positive/sensitivity transfer.

Local GGUF cache keys use a disjoint explicit source tag, raw SHA and native
ordered-input digest, alongside existing arm/environment/decode facts. Relocating
identical bytes preserves the source part of the key; changing raw bytes rekeys
even if decoded strings match. Existing Hub cache 40/64-hex revision domains are
not reinterpreted as local identities. T1 compares the complete explicit local
identity. Fixed canonical reference/T0/within-hardware recipes refuse the new
local source; previously accepted Hub and legacy T0 domains remain unchanged.

## Offline saved work

Saved evaluation explicitly supplies the expected identity, never guesses it from
the first report. It neither loads the bundle nor contacts the Hub, so the original
local file can already be deleted:

```python
from quantfit.gate import evaluate_report
from quantfit.saved_screen import summarize_screen
from quantfit.screen import run_screen

saved = evaluate_report("gate.report.json", threshold=0.30, probe_corpus=source)
summary = summarize_screen("manifest.json", "reports", probe_corpus=source)
resumed = run_screen("manifest.json", "reports", resume=True, probe_corpus=source)
```

```bash
quantfit gate --from-report gate.report.json --threshold 30 --probe-sha256 FULL64 --json
quantfit screen-summary --targets manifest.json --reports-dir reports --probe-sha256 FULL64 --json
quantfit screen --targets manifest.json --out reports --resume --probe-sha256 FULL64 --json
```

Only a **complete** resume is identity-only. Missing targets require the live pair
and its full held-file admission. Supplying a redundant live bundle to a complete
resume is refused before content read. Replay checks native source/census and
declared evidence consistency; it does not authenticate the original chronology
or remote completeness. Gate priority remains 3, then 4, then 5, then 0. Threshold
30 on CLI is 0.30 on the API: a detectable-effect/resolution target, not a maximum
observed drift rate. Zero is conditional non-detection, never a safety certificate.

## Privacy and evidence

`*.probe-rows.json` and `*.probe-bundle.json` contain private source strings. The
narrow ignores prevent accidental adds, not disclosure. Never commit or upload
them, captures, Inspect logs, labels, keys or browser media. Sharing hashes can
correlate sources across reports; scope their handling too. Operational local
carriers stay outside generic dataclass fields/asdict. This does **not** make a
whole Inspect log or arbitrary user metadata safe to publish.

Current controlled source evidence is in
[`validation/2026-11-02-offline-probe-bundles/`](../validation/2026-11-02-offline-probe-bundles/).
Native tests cover exact hostile bytes, strict receiving, raw-only cache rekey,
T1 identity, Inspect mockllm, capture/calibration, known aliases and offline
deletion. The portable consumer runs an API child and sixteen actual fresh CLI
commands with fictional rows and controlled generation/judge. Installed
Linux/Windows × wheel/sdist qualification is four separate hosted profiles; two
build artifacts and inherited hosted browser controls are distinct evidence.
