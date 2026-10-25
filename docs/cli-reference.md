# CLI reference — every command, every flag

This reference documents published quantfit 0.41.0. The explicitly marked
annotation-chunks section requires unreleased 0.42.0 source or a candidate wheel.
Software versions do not establish roadmap or scientific GO.

`quantfit verify`, available since 0.26.0, validates a bounded GGUF structural profile and offers
explicit Linux native CPU usability with `--runtime`. Its profile, typed API,
deadline/cleanup and 0/3/2 semantics are in [GGUF verification](gguf-verification.md).

`quantfit evidence fetch`, available since 0.25.0, retrieves one fixed immutable public aggregate
snapshot, with independent installed byte pins and separate negative native
analysis. Its bounded anonymous API, publication and exit contract is in
[Public aggregate retrieval](public-evidence-fetch.md).

`quantfit repeatability`, available since 0.24.0, compares three saved full aggregates directly
or through a portable replay bundle, with separate native T0/original outcomes.
The typed API, JSON/JUnit, strict comparison and exit contract are in
[Offline replicate agreement](repeatability.md).

`quantfit cold-run` starts three fresh uncached native GGUF children and checks existing
T0 on POSIX hosts. Native measurement exits remain separate from T0. Its revision,
cleanup and aggregate-output contract is in [Three fresh native GGUF runs](cold-replicate-runner.md).

### Recipe-bound native reruns

Quantfit 0.30.0 adds a fresh native rerun bound to an original handoff and
explicit target, using the supported Linux native path:

```bash
quantfit evidence rerun --bundle reference-handoff --target target.json --out rerun-evidence --timeout-seconds 3600 --json
```

The API is `quantfit.reference_replay.rerun_candidate(bundle_path, target, out_path, timeout_seconds=3600)`;
the timeout is keyword-only. Bundle/target arguments are paths, and `out_path` is a
new directory. The 64 KiB target and original bundle are held once; producer T0/report
locators remain labels. Use the [closed target schema](#reference-candidate-assessment).
Unsupported or incomplete execution recipes refuse before generation, preserving
the original assessment where safely available. Arbitrary commands, moving Hub
revisions, capture, completion-cache serving and fallback are unsupported.

The recipe requires enforceable weight SHA/size, executable SHA, precision, CPU
threads/offload controls, shipped judge/probe/input policy and greedy64 settings.
Each resolved arm and actual executable are checked before its native server starts,
then assets and fresh report identities are rechecked after execution. Three fresh
children use the existing owned deadline/cleanup lifecycle. A finite positive
`--timeout-seconds` up to 3600 applies to each child; preparation/resolution is outside
that budget. Windows refuses native execution; other platforms do not inherit
Linux `/proc` cleanup qualification.

Hub GGUF references require a lowercase immutable 40-hex revision before resolution.
Local GGUF files can be bound by exact SHA/size with `revision=null`; a Transformer
conversion pin does not become a Hub GGUF snapshot revision. Local Hub lineage remains
unknown in the reference/fresh assessment, and a missing publication fact remains
unestablished even when execution succeeds. Ref spelling and original evidence are
not rewritten to hide native identity differences.

The new `reference_replay_schema_version: 1` result keeps original/fresh native
exits, `reference_assessment`, `fresh_assessment`, `comparison`, `cold_run` and execution
observations separate. Operational, provenance or cleanup failure exits **2**. Fresh
T0 or full-payload disagreement exits **3**. Otherwise the existing reproduction
comparison's **0/3/4** is retained. Agreement can coexist with original/fresh flagged
regressions or unestablished publication criteria; it never converts a native safety
failure into a model pass. Valid negative or failed execution observations remain
visible, without raw completions or provider diagnostics.

Complete aggregate files are staged in a new closed directory and its manifest is
published last. Preflight and publication protect the original target/bundle/members,
resolved weights/executable and aliases; interrupted or cleanup-uncertain work cannot
qualify success. Registration, authenticated human labels/weights/physical hosts,
independent execution, sensitivity and scientific GO remain separate and unverified.

Quantfit 0.35.0 adds optional `--calibrations-dir DIR` to `screen-summary`:
`screen-summary --targets targets.json --reports-dir reports --calibrations-dir
calibrations --out receiving.json --junit receiving.xml --json`. The Python
`summarize_screen` API gains the same optional `calibrations_dir` keyword.
Per-target conditional resolution is appended; original native exits, prevalence,
flags, sensitivity/control status and XML remain unchanged. Valid stored calibrations
without a native report stay pending, and absent calibrations remain explicit.
Malformed/incompatible supplied evidence or bounded-work refusal exits 2.
See [Conditional saved-screen resolution](screen-resolution.md) for exact limits,
coverage states, byte bindings and label/assumption boundaries.

Quantfit 0.41.0 adds the opt-in `--require-conditional-resolution PP` to this same
`screen-summary` command:

```bash
quantfit screen-summary --targets targets.json --reports-dir reports --calibrations-dir calibrations --require-conditional-resolution 40 --out receiving.json --junit receiving.xml --json
```

The finite `(0,100]` percentage-point ceiling requires `--calibrations-dir`. Every
declared target and both axes need matched report/calibration evidence, measurable
at-risk denominators, native attainable target power and effective MDE within that
ceiling. Native flags/missing evidence retain exits 3/4; otherwise missing calibration
exits 4 and an unmet requirement exits 5. Native exit/outcome, all target rows and
all reasons remain visible. JUnit preserves its native cases, then appends two axis
cases per target and an overall requirement case. Omitting the option preserves
default output, native exits and JUnit. The receiving APIs add the keyword
`required_conditional_resolution_pp=None`; the requirement reuses each pair's same
native analysis. No label authentication, independence, sensitivity or scientific
GO is established, including at exit 0. Invoke `screen-summary` directly in a
workflow step when requiring this ceiling. See [the complete requirement contract](screen-resolution.md#explicit-requirement-0410).

Quantfit 0.34.0 adds `screen-compare --reference-bundle DIR
--candidate-bundle DIR --out comparison.json --junit comparison.xml --json`.
The optional JSON/XML outputs share source/alias protection; they do not form a
transaction. Both bundles must contain the exact same target-manifest bytes.
Native flags on either side retain exit 3 before incomplete/incompatible 4;
conditional complete no-flag is 0, invalid/unsafe input or output failure is 2.
Two axis cases per target plus overall retain failures and skips separately.
See [Screen observation comparison](screen-comparison.md) for the API, declared
identity availability, original denominators and descriptive-transition boundaries.

Quantfit 0.33.0 adds `bundle screen-create --targets PATH --reports-dir DIR
--out NEWDIR --json` and `bundle screen-verify --bundle DIR --json`. These package
original bytes for the complete screen population and rebuild its strict receiving
summary offline after relocation. Content verification exits 0 independently of
nested screen flags/incompleteness (3/4); invalid, unsafe or mismatched evidence
exits 2. See [Screen evidence bundles](screen-bundles.md) for the API, exact closed
inventory, full transport limits, publication and claim boundaries.

`quantfit bundle create` and `quantfit bundle verify` package and check portable
aggregate evidence offline. Their role/flag/exit-code contract and worked commands are
in [Portable aggregate evidence bundles](portable-evidence-bundles.md). Integrity never
authenticates scientific claims or human labels.

The README shows the path most people want. This is the complete surface, because a flag
that exists and appears in no example is a flag nobody finds: the parity auditor counts
those, and it counted 21 before this file existed.

Read alongside:

- [`spec/qsr-v0.md`](../spec/qsr-v0.md) — what a verdict means, normatively.
- [`docs/ci-integration.md`](ci-integration.md) — wiring the gate into a release pipeline.
- `quantfit <command> --help` — always authoritative; this file is checked against it by
  `quantfit audit`, so if the two disagree the build fails rather than the doc rots.

## Conventions across every command

**`--json`** puts exactly one document on stdout and sends every notice to stderr, so a
caller never strips lines before parsing. The envelope is `schema_version` / `tool` /
`command` / `exit_code` / `result`. An operational failure returns the same shape with an
`error` block; a *verdict* failure carries no `error` block, because an answer is not a
breakage.

**Exit codes** follow each command's contract: `0` command-specific success, `2`
operational failure, `3` a known blocker or failed verdict, `4` unestablished
measurement/comparison prerequisites, and `5` an unresolved declared threshold.
Retained execution observations stay separate from an operational failure.
**4 and 5 are not passes.**

**`--token`** takes a Hugging Face token for gated or private repos, falling back to
`$HF_TOKEN`. It is on the commands that reach the Hub and deliberately nowhere else —
`plan` does not have it, because nothing in its path makes a network call.

---

## Fit and configuration — no weights, no GPU

```bash
quantfit check --model Qwen/Qwen2.5-7B-Instruct --token "$HF_TOKEN" --json
quantfit plan --model Qwen/Qwen2.5-7B-Instruct --prefer speed --json
quantfit list --json
```

`check` estimates the footprint from Hub metadata and exits `3` when the model will not
fit. `--prefer` takes `quality` (default), `speed` or `size`. `list` prints the supported
method × scheme matrix.

## Offline reference artifacts

```bash
quantfit references list --json
quantfit references list --registry references.json --json
quantfit references verify --registry references.json --slug my-report --report report.json --json
```

`references list` shows declared entries, pinned URLs and spec validity. The bundled
registry is empty. `--registry` selects an explicitly external registry, never adds to
the official registry, and does not verify publication. Its object contains
`refreport_schema_version: 1` and `reports`, an array of complete `ReferenceReport`
entries; the existing cap, uniqueness and spec rules apply. `hf_revision` is null or an
immutable 40-hex commit. No network request is made.

`references verify` checks local bytes against the selected `--slug`: exit 0 match,
3 mismatch, 2 unreadable/invalid input or unknown slug. A match verifies bytes, not
measurement validity, human adjudication or reproduction. No model or judge loads.

`citable` remains false because publication and citation provenance were not
authenticated. `declared_reference_citable` preserves the library's narrower
pin-present flag; list entries expose `declared_spec_validity` rather than a
measurement validity verdict. Each entry carries its own publication disclaimer.

### Reference candidate assessment

Quantfit 0.29.0 adds offline candidate-specific publication preconditions:

```bash
quantfit references assess --bundle candidate-handoff --target target.json --out receiving-assessment.json --json
```

The API is `quantfit.reference_assessment.assess_candidate(bundle_path, target, out_path=None)`;
`target` is a JSON file path, and `out_path` is keyword-only. The target is read
once up to 64 KiB and SHA-bound. The schema-2 three-report replay bundle is verified
once, then assessment consumes its ordered held bytes. Producer paths remain labels;
the core performs no path, network or model I/O. Native reports and original T0 are
preserved, with separate receiving T0 and a new `receiving_assessment_schema_version: 1`
result. CI campaign assessment keeps its existing schema and wire.

The target is a closed JSON object: every listed key is required, and extra keys
are refused. Evidence leaves can be explicitly `null` to state an unavailable fact;
they are never filled from reports. Pins are lowercase 40-hex revisions and 64-hex
digests; positive integer facts reject booleans.

| Target field | Required declaration |
|---|---|
| `target_schema_version` | Exact integer `1` |
| `pair_slug` | Bounded nonempty pair label |
| `spec_version` / `profile` | Supported qualification is `v0` / `native-gguf-cpu-full40-greedy64-v0` |
| `arms.baseline` / `arms.quantized` | Each has `model`, `revision`, `resolved_dtype`, `artifact_sha256`, `size_bytes` |
| `engine` | `name`, `device`, `binary_sha256`, `threads`, `offload_device`, `n_gpu_layers`, `op_offload`; supported controls are `llama.cpp`, `cpu`, positive threads, `none`, `0`, `false` |
| `judge` | `id`, `revision`, `input_contract`, matching the shipped pinned instrument |
| `probe_dataset` | `id`, `revision`, `split`, `n_probes`; the pinned full40 population is required |
| `decode` | `max_new_tokens`, `do_sample`, `chat_template`; shipped greedy64 is required |

The reported baseline must be unquantized `F16`, `BF16` or `F32` under [QSR v0 §3.2](../spec/qsr-v0.md); the quantized arm may also be unquantized for a control.

The fixed QSR v0 baseline cap is **16,500,000,000 decimal bytes**. Both weight sizes
are supplied declarations; native reports contain no weight-size field, and bundle
member sizes describe JSON files. Missing sizes cannot establish readiness. A
declared cap comparison does not authenticate actual weights, memory use or RAM fit.

Assessment retains native 0/3/4 exits, per-run axes, Wilson intervals, perfect-judge
MDE floors, full-report differences and eligible/excluded axes. Only the four
declared volatile fields are stripped for full-payload agreement. Native exit 4
excludes an unmeasured axis; another measured axis can remain eligible. Fresh
unadjudicated flags block readiness, and human-confirmed counts remain unknown.
Dangerous-axis `0/n` means **the detector did not fire**, until sensitivity is established.

Exit **0** means ready for publication review with complete declarations and at
least one qualifying measured axis. **3** means a known target/cap, T0, payload or
fresh-flag blocker. **4** means no known blocker but missing required facts,
unsupported profile/spec or no measured axis. Known blockers outrank missing facts.
**2** means malformed/private input, failed byte integrity, forged bindings or
unsafe I/O. Error categories omit raw paths, payloads and provider diagnostics.

The separate receiving output is checked and atomically replaced, protecting the
target, closed bundle, every member and aliases. It never changes producer evidence,
uploads data or adds a registry entry. Registration, human-label authentication,
weight/size/physical-host authentication, independent execution, sensitivity and
scientific GO remain unverified even at exit 0. The public Phi4 candidate stays
blocked with its original **2/20 unconfirmed over-refusal flags** and dangerous-axis
**0/12 detector did not fire** result.

## Quantize

```bash
quantfit quantize --model Qwen/Qwen2.5-1.5B-Instruct --method awq --scheme W4A16_ASYM \
  --out ./out --token "$HF_TOKEN" --no-check --json
quantfit quantize --model Qwen/Qwen2.5-1.5B-Instruct --method gguf --out ./out \
  --push my-org/my-quant --private --json
```

`--no-check` skips the GPU pre-flight — use it when you know the machine differs from the
one that will serve. `--push` uploads the result to a Hub repo; `--private` makes that repo
private. `--scheme` overrides the method's default.

## Sensitivity, before committing to a bit-width

```bash
quantfit probe --model Qwen/Qwen2.5-1.5B-Instruct --bits 4 8 --token "$HF_TOKEN" --json
```

Forward-only RTN-KL per bit-width. It is a **conservative upper bound**: a low value means
the bit-width is safe, a high one can over-escalate, because calibrated AWQ/GPTQ may still
be fine where RTN is not. Read it as sensitivity, not as a verdict.

`--model` is loaded at the Hub's `main`. Each bit-width loads it afresh and records the
commit it resolved to as `model_revision`, and the human output prints it. If `main` moves
between two loads in one run, the output says the revision differs between bit-widths, and
those rows must not be compared.

**What it averages over.** The KL is measured on packed 512-token blocks of the calibration
set: rows are concatenated and chunked by the quantize path's own function
(`quantfit/calibset.py:packed_blocks`). The probe's blocks are therefore exactly the first
tokens of the stream the quantizer calibrates on. The set is loaded at its pinned commit
(`quantfit/spec.py:calib_revision`), and the JSON records all of this under `calibration`.
Every block is the same length, so the mean over blocks is also the mean over tokens.

Each bit-width reports the mean **and** its spread: every per-block KL (`per_sample_kl`)
plus `kl_min`, `kl_max` and the sample SD `kl_sd` (null for a single block — one number
has no spread, and 0.0 would read as a perfectly stable probe). No interval is reported.
Tokens within a block are correlated, so the block is the unit, and eight are not many.

**Before 0.15.0 the probe measured a different quantity.** It tokenized rows one at a
time and averaged a per-row mean, so a 9-token wikitext heading weighed as much as a
437-token paragraph. On Qwen2.5-1.5B at 4 bits that gave 0.572 at n = 8 and 0.419 at
n = 64: the heading rows formed a tail that moved the mean with N
(`validation/2026-10-01-probe-at-n64/`). Packed, the same model reads **0.237 at n = 8
and 0.231 at n = 64**, with mean ≈ median and SD 0.02–0.03
(`validation/2026-10-01-probe-packed-blocks/`). Numbers from before 0.15.0 are not
comparable with these. The metric string in the JSON says which one a number is.

`--samples N` sets how many blocks each bit-width averages over (default 8, at least 1).
A larger N extends the default eight rather than replacing them: the first eight blocks
at N = 64 are the same blocks, with bit-identical KLs. If the set runs out of tokens
before N blocks, the output says `n=X of N requested`, and the JSON carries
`requested_samples` next to each bit-width's `n_samples`.

Host RAM grows with N: each block's reference logits are held on the CPU for the whole
run, in the model's dtype. At fp16 on a GPU that is 512 tokens × vocabulary × 2 bytes.
At Qwen2.5's 151,936 entries that is 156 MB per block: 1.2 GB at the default 8 and
10 GB at 64. On a CPU-only machine the model runs in float32, so double it.

## Verify the artifact loads

```bash
quantfit verify --model ./out --json
```

Smoke-loads and generates for Transformers artifacts. The GGUF branch, available since 0.26.0,
uses bounded structure validation, with separate optional native CPU usability
through `--runtime` and its `--timeout-seconds` deadline. See
[the supported profile](gguf-verification.md); neither result is a safety verdict.

## The safety check

```bash
# See the output shape in about a second — fixtures, no model, no network.
quantfit verify-safety --demo

# The real thing, with every artifact it can produce.
quantfit verify-safety \
  --baseline Qwen/Qwen2.5-1.5B-Instruct \
  --quant ./out \
  --token "$HF_TOKEN" \
  --max-new-tokens 64 \
  --report drift.json \
  --junit drift.xml \
  --capture run.capture.jsonl \
  --json
```

`--max-new-tokens` sets the completion length generated per probe and judged for refusal.

**The legacy alias.** `--baseline` was called `--fp16` in 0.1–0.3, and invocations from
then still work unchanged:

```bash
quantfit verify-safety --fp16 Qwen/Qwen2.5-1.5B-Instruct --quant ./out --json
```

Both spellings set the same argument. The name changed because the baseline loads at its
*native* dtype, which is frequently bf16 — calling it `--fp16` stated a precision the run
does not necessarily use, and the report records the resolved dtype for exactly that reason.
New scripts should use `--baseline`.

`--report` writes the schema-v2 auditable artifact. `--junit` writes a JUnit XML so the
verdict renders as a test result in any CI system. `--capture` writes every completion to a
local JSONL for judge calibration — **it may contain harmful model output**; never commit
it, redistribute it, or attach it to a report. See
[`docs/data-handling-completions.md`](data-handling-completions.md).

`--demo` refuses `--report`, `--junit`, `--capture` and `--baseline-cache`: an artifact
from a demonstration would be indistinguishable from one from a measurement, and a flag
the demo would silently ignore is refused for the same reason.

**Reusing the baseline arm across runs.** Gating several quants of one base model
regenerates the identical baseline every time — greedy decode, one pinned probe set, one
binary — and it is the expensive half of the pair. `--baseline-cache DIR` (also on
`quantfit gate`) serves it from `DIR` when that exact arm was generated before, and stores
it when not:

```bash
quantfit verify-safety --baseline hf:org/repo/model-f16.gguf --quant model.Q4_K_M.gguf \
  --baseline-cache ~/.cache/quantfit-baselines/
quantfit gate --baseline hf:org/repo/model-f16.gguf --quant model.Q4_K_M.gguf \
  --tier smoke --baseline-cache ~/.cache/quantfit-baselines/
```

The key is a sha256 over the arm's identity — the GGUF file's sha256, the llama.cpp
binary's sha256, the file type, the probe set's revision and exact prompt text, the decode
settings and the execution environment — derived **before** any server starts, so a hit
skips baseline generation entirely. Every entry re-derives its own key on load and is
refused if it disagrees, so an edited or misfiled entry is never served
(`quantfit/safety/cache.py`).

A served baseline says so in the report. `baseline.engine.baseline_cache` records the
entry's key, when it was generated and by which quantfit. The arm's `runtime_s` is that
generation's wall clock, not this run's. The model card from `emit model-card` repeats it.
Until 0.14.1 a hit replayed the stored arm silently, so a report could not tell a served
baseline from a generated one (`validation/2026-10-01-baseline-cache-real-hardware/`).

It is **GGUF pairs only**. A transformers arm's identity includes the dtype it resolved to
and the commit it resolved at, both known only after the model loads, so no key exists
before the expensive part runs; the flag is refused for a transformers pair rather than
accepted and ignored. Budgets assume zero hits — a hit is wall-clock time and nothing else.
Entries hold **completion text**: local-only, never committed (`*.baseline-cache.json` is
gitignored), and see [`docs/data-handling-completions.md`](data-handling-completions.md).

## Inspect HF runner

```sh
quantfit inspect-run --baseline hf/org/base --quant hf/org/quant \
  --baseline-revision <40-character-commit-sha> --quant-revision <40-character-commit-sha> \
  --max-new-tokens 64 --report inspect-drift.json --json
```

For a gated repository and retained local captures:

```sh
quantfit inspect-run --baseline hf/org/base --quant hf/org/quant \
  --baseline-revision <40-character-commit-sha> --quant-revision <40-character-commit-sha> \
  --token <hf-token> --log-dir ./logs --json
```

Both revisions are required immutable HF commits. The runner downloads each
snapshot, loads its weights and tokenizer from the same path, checks actual loaded
precision/source, serializes arm generation, and uses the full pinned corpus and
one real pinned judge batch. Only the reviewed Inspect 0.3.269 HF provider is
supported. Exits are 0 (no regression detected), 2 (operational refusal), 3
(regression flagged), and 4 (an axis unmeasurable), with 3 taking precedence.

`--token` uses existing Hub access. `--log-dir DIR` retains local Inspect captures
with a warning; without it, temporary logs are deleted on exit. Never commit logs.
`--report PATH` writes aggregate-only schema-v2 provenance; it is optional.
`--max-new-tokens` defaults to 64, applied identically to both arms. `--json`
prints one envelope. See [the observation contract](inspect-run.md) for exact
timing boundaries and the distinction from verify-safety generation.

## Screen a whole manifest

```bash
quantfit screen --targets screens/targets-0.5.json --out reports/ \
  --token "$HF_TOKEN" --max-new-tokens 64 --junit screen.xml \
  --capture captures/ --resume --attempts 3 --json
```

Runs the paired diff over every target and aggregates per-stratum, per-axis Wilson
prevalence bounds. Exits `4` if an axis went unmeasured anywhere, which is not a pass.

`--junit` writes **one test case per target**, so a fifteen-target screen shows fifteen
cases rather than one aggregate saying "something regressed somewhere". A target that
failed to run is an `error`, not a `failure` — it produced no verdict, and calling that a
failed test would report a missing measurement as a detected regression.

`--capture DIR` writes **one `DIR/<target>.capture.jsonl` per target**, and it exists
because the screen's own protocol demands it. QSR v0 and ROADMAP 0.5 both require every
flagged flip to be **human-verified** before it counts as a positive existence claim,
and until this flag existed the command that flags them produced nothing to verify
against. The first full screen run flagged twelve over-refusal flips and could
adjudicate none of them (`validation/2026-08-19-screen-full/`).

A capture is the bytes the judge actually scored, written by the same call that scored
them, so adjudication needs no re-run and no provenance argument
(`docs/sensitivity-control-v0.md` 5.2). It is **off by default**: a screen must not
start writing model output unasked. When on, captures may contain harmful model output,
are local only, and are never committed or redistributed; the `*.capture.jsonl` pattern
in `.gitignore` backstops that. See
[`docs/data-handling-completions.md`](data-handling-completions.md).

Quantfit 0.32.0 makes `--resume` validate the complete present native
report population before any model contact or output mutation. Original target
references, pinned protocol, native arithmetic, privacy, duplicate evidence and
requested `--max-new-tokens` must match. Valid flagged or unmeasured reports remain
saved evidence and are skipped with their original denominators and caveats.
Only missing target reports are executed. A present malformed or incompatible
file refuses with exit 2, preserving its bytes rather than regenerating it.
The resume receipt records skipped/executed target identities and original hashes.
The current generation-side chat-template policy must match; receiver-supported
historical policies remain valid for offline `screen-summary`, but cannot be mixed
into a current resume run. Producer package versions are preserved.
Optional JUnit output must be outside report/capture directories with an existing
parent. Its aliases and the summary/native/capture output paths are checked before
contact, with guarded per-file atomic publication. Fresh results are checked against
held evidence after execution; a later incompatibility preserves existing evidence
without promising whole-run rollback. Progress goes to stderr under `--json`.
Valid flags exit 3 before partial execution errors or unmeasured evidence exit 4;
neither an operational-error row nor incomplete measurement becomes a clean result.
Strict resume is available since quantfit 0.32.0.

`--attempts N` retries a target up to N times before recording it as an operational
error (default `1`, meaning no retry). The absorbed failure class is mostly transient.
On the first full 15-target screen **six targets were lost** to
`Cannot send a request, as the client has been closed` after sustained downloading, and
every one succeeded on a later attempt - a network hiccup had become a permanent hole in
the prevalence bound. Retry is opt-in because the default must not silently triple a
screen's wall clock.

## Summarize a saved screen

Quantfit 0.31.0 adds a strictly offline receiving analysis:

```bash
quantfit screen-summary --targets screens/targets-0.5.json --reports-dir screen-reports --out receiving-screen.json --junit receiving-screen.xml --json
```

`quantfit.saved_screen.summarize_screen(manifest_path, reports_dir, out_path=None, junit_path=None)`
returns the receiving result; output arguments are keyword-only and optional.
`--targets` and `--reports-dir` are required paths. `--out` writes receiving JSON,
`--junit` writes XML, and `--json` prints the usual CLI envelope. No token,
generation, resolver, network, retry or resume path is used.

The existing schema-1 target manifest is held once, bounded to 1 MiB and 256
case-insensitively unique target names. The closed report directory permits its
named `<target>.json` reports and the optional fixed producer `screen-summary.json`.
That producer summary is held, privacy-checked and byte-bound under `ignored_members`;
its counts, status, confirmations and control claims never enter the receiving
analysis. Other entries, subdirectories, captures and caches are refused. Each
member is bounded to 8 MiB and all members together to 64 MiB. Duplicate JSON keys,
non-finite literals, private fields, symbolic links/junctions and non-regular
members are refused. Report statistics and derived flags are checked with native
validators before exact baseline/quant references and backend-to-stratum bindings
are counted. Judge/probe pins, input/decode and causal engine/environment context
must be compatible within each stratum. Different supported strata remain separate.
Duplicate report bytes or a shared complete pair of known weight hashes/snapshot
pins cannot become separate population entries. Missing identities remain unknown;
they do not prove unique weights or independent targets.

The `saved_screen_summary_schema_version: 1` result carries manifest/report byte
bindings, all declared target rows, coverage and per-axis/per-stratum aggregates.
Missing reports remain `missing_evidence`, with an explicit JUnit skip. An axis
with zero at-risk pairs contributes no numerator or denominator on that axis; the
other axis still counts. Prevalence denominators count measured targets, not pooled
probes. Original per-report at-risk counts, flips, Wilson intervals and perfect-judge
MDE floors remain visible. Every human confirmation remains unestablished; no
adjudication is ingested.

The manifest's sensitivity-control status is a declaration only. Even `pass`
does not clear effective detection-sensitivity conditionality or the unconditional
resolution caveat. A dangerous-axis `0/n` means the detector did not fire. Recorded
pins and integrity do not authenticate actual weights, physical hosts, independent
execution, human labels or scientific GO.

Malformed/incompatible/duplicate evidence or operational/IO failure exits **2**.
Otherwise any preserved valid regression flag exits **3**, before missing evidence
or any required unmeasured axis (**4**). Complete supported no-detection evidence
alone exits **0**, retaining those caveats. JUnit preserves flagged failures and
missing/unmeasured skips rather than turning incomplete coverage green.

Both receiving output buffers are staged before per-file atomic replacement. The
manifest, report directory, members and same-file aliases are protected, and outputs
must be distinct and outside the input report directory. JSON/XML publication is
not a transaction across two paths. Producer reports and summaries are not edited;
contradictory historical verdicts are refused rather than silently repaired.

## Gate a release

```bash
quantfit gate --baseline Qwen/Qwen2.5-1.5B-Instruct --quant ./out \
  --tier smoke --max-new-tokens 64 --token "$HF_TOKEN" \
  --report drift.json --out gate.json --junit gate.xml --json

# Or declare the resolution you need explicitly, in percentage points.
quantfit gate --fp16 Qwen/Qwen2.5-1.5B-Instruct --quant ./out --threshold 30 --json

# Or explicitly consume a calibration bound to this exact measurement scope.
quantfit gate --baseline Qwen/Qwen2.5-1.5B-Instruct --quant ./out \
  --tier smoke --calibration-report calibration.json --report drift.json --out gate.json --json
```

`--tier` picks a named threshold; `--threshold` states one directly in percentage points.
`--eps-upper` supplies an operator judge-error bound and `--eps-source` records where it came
from. Without those inputs or a bound calibration report, the printed MDE is a perfect-judge
floor. `--out` writes the gate
decision artifact. The gate exits `5` rather than passing a threshold the run could not
have resolved.

`--calibration-report PATH` instead reads a schema-2 calibration produced through the
capture → key → label-ingest pipeline. It is exclusive with `--eps-upper`/`--eps-source`.
Each arm retains its own recomputed directional Wilson upper bound. Judge, corpus, decode,
immutable arm weights, actual precision, engine and environment must match. A pre-run refusal
validates requested scope but has not observed actual weights; a run that proceeds must match
its actual report before a calibrated decision is emitted. Old unbound calibration reports
remain available for explicit operator use. Binding does not authenticate human label truth,
independent judge errors, sensitivity or a research GO; `eps.measured` remains `false`.
The aggregate read is limited to 2 MiB; duplicate keys and non-finite/overflow literals
are refused. `eps.assumptions_verified` stays `false`: applicability to realized at-risk
populations (A1), conditional arm independence (A2) and majority-real at-risk probes (A3)
remain assumptions of the existing MDE bound, even when measurement identities match.
Bound runs validate a private aggregate before publishing `--report`; shared output files
are never the provenance oracle. The calibration input must differ from report/decision
outputs, including same-file aliases.

`--junit` renders the gate as three cases rather than one. **Exit 5 fails as a refusal, not
as a breached threshold** — "I cannot resolve what you asked" and "you failed what you
asked" are different facts that would otherwise share a colour and a message. The ungated
over-refusal axis gets its own case: a regression there never fails the build, because the
gate does not gate on it, but it is recorded rather than swallowed by a green tick. And a
run whose resolution is a perfect-judge floor says so, because a green gate under a floor
is a weaker claim than one under a measured judge error.

## Judge calibration

```bash
quantfit calibrate sheet --capture run.capture.jsonl \
  --sheet labels.labels.csv --key labels.labelkey.json --json

quantfit calibrate ingest --sheet labels.labels.csv \
  --key labels.labelkey.json --out calibration.json --json
```

`sheet` builds a blinded labeling sheet; the key file is what unblinds it and the labeler
never receives it. `ingest` folds the filled labels into a per-arm judge-error report.

Quantfit 0.36.0 adds aggregate reconciliation of two private filled sheets:

```bash
quantfit calibrate reconcile --sheet-a rater-a.labels.csv --sheet-b rater-b.labels.csv \
  --key labels.labelkey.json --out reconciliation.json --json
```

All four paths are required. Both sheets must cover the key's same complete paired
population, with original IDs, completion hashes and supported labels. Per-arm
matrices use rows from sheet A and columns from B, ordered
`refusal, compliance, unusable`. Only counts and whole-input byte bindings are
published. Exit 0 includes disagreement/all-unusable results and establishes no
rater authentication, independence or consensus calibration; invalid/unsafe input
or publication exits 2. Operational JSON errors retain the existing `calibrate`
parent-command envelope. See [Label reconciliation](label-reconciliation.md).

Quantfit 0.37.0 adds completion-free retained labeling:

```bash
quantfit calibrate extract --sheet labels.labels.csv --key labels.labelkey.json --out retained.labels.csv --receipt retention.json --json
quantfit calibrate ingest --retained-labels retained.labels.csv --retention-receipt retention.json --key labels.labelkey.json --out calibration.json --json
```

The retained CSV/key remain private. Extraction validates the full sheet and writes
new retained-label and receipt paths; ingestion can then run without the original
sheet. Neither command deletes source material or authenticates label truth. See
[the retained-label contract](retained-labels.md).

Quantfit 0.38.0 adds descriptive strata diagnostics, and 0.39.0 adds paired diagnostics:

```bash
quantfit calibrate strata --capture run.capture.jsonl --key labels.labelkey.json --sheet labels.labels.csv --out strata.json --json
quantfit calibrate paired --capture run.capture.jsonl --key labels.labelkey.json --sheet labels.labels.csv --out paired.json --json
```

Both require the original capture and a complete key. Each accepts either the full
sheet or the explicit retained-label/receipt mode, with a new output path. Strata
retain per-group, per-arm usable denominators. Paired tables preserve whole-judge
and common-usable populations, unusable coverage and source-specific at-risk
denominators. Exit 0 means the descriptive analysis completed, including empty or
unusable groups; invalid input or publication exits 2. Neither diagnostic is a
replacement calibration or gate, and neither establishes independence, sensitivity
or scientific GO. See [strata](calibration-strata.md) and [paired](calibration-paired.md)
for the API, bounds and proof limits.

Quantfit 0.40.0 adds explicit local review of disagreements between two complete sheets:

```bash
quantfit calibrate review prepare --sheet-a a.labels.csv --sheet-b b.labels.csv --key private.labelkey.json --sheet private.review.labels.csv --receipt review.json --json
# Locally fill EVERY selected row with refusal, compliance, or unusable.
quantfit calibrate review apply --sheet-a a.labels.csv --sheet-b b.labels.csv --key private.labelkey.json --review private.review.labels.csv --preparation review.json --out reviewed.labels.csv --receipt application.json --json
# Ingestion is a separate explicit operation.
quantfit calibrate ingest --sheet reviewed.labels.csv --key private.labelkey.json --out calibration.json --json
```

Prepare validates both complete sheets against their shared key and queues every
unequal normalized label. Apply requires the exact selected subset, unchanged
completion text and explicit labels; agreed rows are preserved in the new complete
sheet. Both commands keep originals intact and require new output/receipt paths.
Queues, sheets and keys stay private. Receipts expose fixed aggregates and byte
bindings. These commands do not read the capture: its digest/scope remain key
declarations. Exit 0 means the transformation completed; invalid input or publication
exits 2. Native ingestion still refuses an entirely unusable measurement. Review
counts establish no label truth, independent adjudication, authentic blinding,
improved accuracy or scientific GO. See [the review contract](label-review.md) for
API, bounds and publication limits.

### Annotation chunks — unreleased 0.42.0 source

The source/candidate workflow accepts only a complete **blank** native template
and its original key. Create an empty private directory first, then prepare every
bounded partition and its private manifest:

```bash
quantfit calibrate chunks prepare --sheet blank.labels.csv --key private.labelkey.json --out-dir annotation-parts --rows-per-part 100 --json
```

Explicitly fill every returned part, then collect them in manifest order:

```bash
quantfit calibrate chunks collect --sheet blank.labels.csv --key private.labelkey.json --manifest annotation-parts/annotation.chunkmanifest.json --part annotation-parts/part-0001.labels.csv --part annotation-parts/part-0002.labels.csv --out collected.labels.csv --receipt collection.json --json
quantfit calibrate ingest --sheet collected.labels.csv --key private.labelkey.json --out calibration.json --json
```

The example assumes two actual parts; repeat `--part` for the complete assigned
set. Collection binds exact unchanged source/key/manifest bytes, assigned IDs and
text, records the **changed filled hashes** separately from original blank hashes,
and native-validates a NEW complete sheet. Partially filled originals belong in
the existing review workflow. All-unusable collection succeeds; unchanged native
ingestion refuses the empty measurement. Missing/extra/overlapping parts, blank
labels, text drift, aliases, existing outputs or publication failures exit 2.

Only blinded parts fall within the existing one-named-second-annotator carve-out;
keep the key and `*.chunkmanifest.json` private. `--annotator-role named_second`
requires `--annotator-name`; attribution is declared, not authenticated. No
automatic sending, labeling, ingestion, independence or scientific GO. See
[the complete contract](annotation-chunks.md) for API, limits and manifest-last
partial-publication behavior. This section requires an unreleased candidate,
not the published 0.41.0 installation.

## Analyze an existing run's resolution

```bash
quantfit resolution --report drift.json --calibration-report calibration.json \
  --out resolution.json --json
```

This offline command consumes an existing schema-v2 report and a bound schema-2
calibration aggregate with exactly matching observed measurement scope. It checks
the paired count arithmetic and recomputes the calibration bounds, retaining each
arm's directional upper bound separately. The separate `resolution_schema: 1`
artifact includes both input SHA256 hashes, the binding fingerprint, flagged flip
counts, realized at-risk denominators, exact-binomial thresholds, effective MDEs
and power at pre-registered effect sizes. Input bytes and QSR v0 verdicts are preserved.

`--out` is required and cannot overwrite either input, including through a hard
link. Input reports are limited to 8 MiB and 4096 probes to bound the existing
exact-binomial calculator's work. Malformed counts, unbound legacy calibration or
scope mismatches exit 2 before output; exit 0 means the analysis ran, including
an unmeasurable axis. It is not a safety gate. Counts remain judge-flagged, not
human-confirmed. Matching metadata cannot authenticate human labels or establish
that directional bounds apply to the at-risk subpopulation, that the at-risk set
is majority-real, or that judge errors are arm-independent; the artifact carries
these assumptions explicitly. No sample size fixes correlated judge error.

## Reproduction and reporting

Quantfit 0.27.0 adds a bundle input mode to the existing command:

```bash
quantfit reproduce --reference-bundle reference-handoff --candidate-bundle candidate-handoff --out comparison.json --json
```

Use exactly both `--reference-bundle DIR` and `--candidate-bundle DIR`. They accept
schema-2 three-report T0 handoffs made by `bundle replay-create`, not generic
aggregate bundles. Either bundle flag mixed with `--reference`, `--candidate`,
`--t0-reference` or `--t0-candidate` is an operational error before any input I/O.
`--out PATH` and `--json` retain their existing command envelope and native exits.

Both sides must verify their ordered held members and original T0. Selection is
fixed to `replicate-1` / `report-1.json`; it is recorded, not chosen for a favorable
result. Positive T0 identity, membership and protocol prerequisites come from held
buffers, without reopening producer paths. Original native bytes are never rewritten.
Valid negative T0 remains void/4; malformed/forged bindings or I/O failures exit 2.

Each side's `bundle_evidence` records its receiving bundle path, selected role/member
and report SHA, ordered role/path/report-SHA bindings, parsed manifest, original T0
and separate receiving T0. The manifest is a parsed declaration, not an invented
original-byte digest. Producer paths are labels. Producer-location, execution
independence and scientific-claim verification remain false.

The library API is
`quantfit.reproduce.compare_bundles(reference_bundle_path, candidate_bundle_path, out_path=None)`.
The shared comparison performs no path I/O; loose-report inputs below retain their
existing loader/T0 behavior. This is the current native tolerance/projection-based
reproduction policy, not a new full-payload repeatability protocol. P1 retains its
selected-byte SHA rule: exact selected report copies remain void/4 after relocation.
Reproduced outcomes exit 0, known breach/denominator-drift/unverified outcomes 3,
and void outcomes 4. None establishes authenticated human labels, sensitivity,
physical hosts, independent generation, safety or scientific GO.

Output preflight and checked atomic publication protect both closed directories and
all member paths, including manifests and hardlink aliases. An output cannot replace
consumed evidence or appear inside either bundle. Both original native T0/report
bytes and historical producer versions remain intact.

### Reproduction JUnit

Quantfit 0.28.0 adds `--junit PATH` in both loose-report and bundle input
modes. The library renderer is
`quantfit.reproduce_junit.reproduction_to_junit(decision)`, accepting a mapping
and returning XML. It reports the native decision without recalculating tolerance.

```bash
quantfit reproduce --reference-bundle reference-handoff --candidate-bundle candidate-handoff --out comparison.json --junit reproduction.xml --json
```

The suite `quantfit.reproduce` has ten stable cases: `reference-t0`, `candidate-t0`,
`P0`, `P1`, `T1`, `T2`, `T3`, `T4`, `T5` and `overall`. Unknown T0 skips with a
bounded reason; known negative T0 fails. P0/P1 and T1–T5 use their native boolean
results. The overall case passes only for `outcome=reproduced`, exit 0 and
`passed=true`. Every other native outcome fails overall, including void and
unverified results. XML therefore cannot turn a withheld comparison into a pass.
Messages are bounded and omit raw paths, provider diagnostics and private data.

The CLI preserves native JSON and exit codes. An operational failure can publish
one fixed-message error case when the output destination is safe; it does not
fabricate a native comparison. Invalid or protected destinations refuse publication.
JSON and XML are staged before replacing either destination. Each replacement is
atomic, and successful XML is published last; this is not a transaction across
both files. A later replacement fault exits 2 and can leave the already-published
JSON result. Both outputs must be distinct from each other and every consumed
input, including aliases. Loose positive T0 source reports receive the same
protection; negative or legacy producer locators remain labels.

### Loose report inputs

```bash
quantfit t0 --reports ref-a.json ref-b.json ref-c.json --out replicates-ref.json --json

quantfit reproduce --reference ref.json --candidate t4.json --out record.json \
  --t0-reference replicates-ref.json --t0-candidate replicates-cand.json --json

quantfit emit model-card --report drift.json --json
```

`t0 --reports REPORT [REPORT ...] --out PATH` checks at least three existing uncached
schema-v2 reports on CPU, without loading models or using the network. Their pinned
judge/corpus/arms, decode settings, engine builds and recorded environments must match
before the `drift` blocks are compared. `--out` writes the standalone T0 artifact;
`--json` emits the existing stdout envelope. Exit **0** means agreement under these
reported prerequisites, **3** means disagreement, and **2** means invalid evidence,
including fewer than three reports. Distinct paths and hashes do not establish actual
execution independence or physical-host identity. See the dated 2026-10-05 clarification
in `docs/cross-hardware-tolerance-v0.md` and the synthetic functional record at
`validation/2026-10-05-t0-replicates/`.

`--t0-reference` and `--t0-candidate` each accept one standalone artifact, or the existing
list of replicate report paths. New T0 artifacts record canonical absolute source
paths and can be consumed from another working directory. Older relative-path
artifacts remain readable from the producer's directory; regenerate them before
consuming them elsewhere. Positive
evidence is reread and checked against its hashes; each compared report must belong to
its side's source set by exact bytes and identity. Bare `true` and legacy identity-less
positive results are accepted as unverified assertions, so they cannot produce the
reserved gate pass. A reported failure remains conservative failure. The library can
record a two-report partial set but its `protocol_pass` is false. `emit` renders a report
as a paste-ready model-card section.

## Audit this repository

```bash
quantfit audit --root . --json-out findings.json --json
```

`--json-out` writes the findings to a file; `--json` puts the envelope on stdout. `--root`
says *where this checkout is*, not *which checkout to audit* — three of the five checks read
the parser and constants by import, so a root that is not the imported tree is refused as
operational rather than answered.
