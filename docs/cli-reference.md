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

Each bit-width reports the mean **and** its spread: every per-sample KL (`per_sample_kl`)
plus `kl_min`, `kl_max` and the sample SD `kl_sd` (null for a single sample — one number
has no spread, and 0.0 would read as a perfectly stable probe). Read the spread before the
mean. On Qwen2.5-1.5B at 4-bit the mean is 0.572 while the median of the eight samples is
0.244, because two rows sit near 1.5 — a mean alone would have hidden that the reading rests
on them. No interval is reported: eight skewed samples do not support one.

`--samples N` sets how many calibration rows each bit-width averages over (default 8, at
least 1). The rows are the first N usable ones from the frozen spec's calibration set,
shuffled by its seed, so a larger N extends the default eight rather than replacing them. If the set
yields fewer usable rows than N, the output says `n=X of N requested`, and the JSON carries
`requested_samples` next to each bit-width's `n_samples`. Host RAM grows with N: every
row's fp16 log-probs are held on the CPU for the whole run — one float32 per vocabulary entry
per token, about 0.6 MB per token at Qwen2.5's 151,936-entry vocabulary, so up to 311 MB
for a full 512-token row.

**What the 4-bit spread is.** At `--samples 64` on the same model
(`validation/2026-10-01-probe-at-n64/`), the tail turns out to be short rows. Every row of
22 tokens or fewer has a 4-bit KL of at least 0.569, and every longer row has at most
0.471. Most of the short rows are wikitext section headings (`= = = Ratings = = =`), and
the two near 1.5 at n = 8 are headings of 9 and 10 tokens. `mean_kl` weighs every row
equally, so the share of headings a sample draws moves it: 0.572 at n = 8, 0.419 at n = 64,
and 0.262 over the 51 longer rows alone. The 4-bit-to-8-bit ordering holds on every summary.
Read a single model's 4-bit figure as sensitive to N, and compare models only at the same N.

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
```

`--tier` picks a named threshold; `--threshold` states one directly in percentage points.
`--eps-upper` supplies a measured judge-error bound and `--eps-source` records where it came
from — without them the printed MDE is a perfect-judge floor. `--out` writes the gate
decision artifact. The gate exits `5` rather than passing a threshold the run could not
have resolved.

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

## Reproduction and reporting

```bash
quantfit reproduce --reference ref.json --candidate t4.json --out record.json \
  --t0-reference replicates-ref.json --t0-candidate replicates-cand.json --json

quantfit emit model-card --report drift.json --json
```

`--t0-*` supply the three within-hardware replicate runs that establish determinism; without
that evidence the outcome can never be the reserved gate pass. `emit` renders a report as a
paste-ready model-card section.

## Audit this repository

```bash
quantfit audit --root . --json-out findings.json --json
```

`--json-out` writes the findings to a file; `--json` puts the envelope on stdout. `--root`
says *where this checkout is*, not *which checkout to audit* — three of the five checks read
the parser and constants by import, so a root that is not the imported tree is refused as
operational rather than answered.
