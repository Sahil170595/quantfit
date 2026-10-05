# CLI reference — every command, every flag

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

**Exit codes** are the CI contract: `0` clean, `2` operational (nothing ran), `3` the
verdict failed, `4` nothing was measured, `5` the gate cannot resolve the declared
threshold. **4 and 5 are not passes.**

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

Smoke-loads and generates. For GGUF this is a structural magic-number check only.

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

`--resume` skips targets whose report already exists in `--out`, rebuilding their rows
from disk so a resumed summary is identical to the one an uninterrupted run would have
written. A screen over a large manifest runs for hours, and a machine that cannot hold
every pair at once has to run it in pieces; without resume an interruption costs every
target already measured. A report that will not parse is re-run rather than trusted:
resuming onto a truncated artifact would publish it.

`--attempts N` retries a target up to N times before recording it as an operational
error (default `1`, meaning no retry). The absorbed failure class is mostly transient.
On the first full 15-target screen **six targets were lost** to
`Cannot send a request, as the client has been closed` after sustained downloading, and
every one succeeded on a later attempt - a network hiccup had become a permanent hole in
the prevalence bound. Retry is opt-in because the default must not silently triple a
screen's wall clock.

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
