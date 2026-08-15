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

`--demo` refuses `--report`, `--junit` and `--capture`: an artifact from a demonstration
would be indistinguishable from one from a measurement.

## Screen a whole manifest

```bash
quantfit screen --targets screens/targets-0.5.json --out reports/ \
  --token "$HF_TOKEN" --max-new-tokens 64 --junit screen.xml --json
```

Runs the paired diff over every target and aggregates per-stratum, per-axis Wilson
prevalence bounds. Exits `4` if an axis went unmeasured anywhere, which is not a pass.

`--junit` writes **one test case per target**, so a fifteen-target screen shows fifteen
cases rather than one aggregate saying "something regressed somewhere". A target that
failed to run is an `error`, not a `failure` — it produced no verdict, and calling that a
failed test would report a missing measurement as a detected regression.

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
