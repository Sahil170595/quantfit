---
name: quantfit
description: Use quantfit to check whether quantizing an LLM broke its refusal behaviour, whether a model fits a GPU, or to gate a quantized release in CI. Use when someone asks about quantization safety, safety drift, refusal regression after quantization, VRAM fit for quantization, or how to read a quantfit report or exit code.
---

# Using quantfit

quantfit quantizes an LLM and checks it still refuses what it should. Its distinguishing
feature is a **paired** diff: it compares a model against its own quantization, rather than
scoring a model in the absolute. That matters because strongly-aligned models are robust to
quantization and weakly-aligned ones are not, so an absolute score cannot separate "never
well aligned" from "quantization broke it".

## Start here, before suggesting a download

```bash
pip install quantfit
quantfit --version
quantfit verify-safety --demo
```

`--demo` prints a real verdict in about a second — the shipped tabulation over bundled
fixtures, no model, no network, no weights. Use it to show someone what the output looks
like. It refuses `--report` and always exits 0, because nothing was measured.

## The command that matters

```bash
quantfit verify-safety --baseline Qwen/Qwen2.5-1.5B-Instruct --quant ./out --report drift.json
```

Generates from both arms over a curated probe set, judges each completion for refusal, and
pairs the results into two axes:

- **refusal-robustness** — expected-unsafe probes, where refusing is correct. A flip from
  refusal to compliance is the dangerous regression.
- **over-refusal** — expected-safe probes, where complying is correct. A flip to refusal is
  the annoying regression.

Both are reported over **at-risk denominators**: only pairs where the baseline did the
correct thing can regress. Quoting a raw count against the full probe set instead is the
most common way to misread the output.

## Reading the exit code

| code | meaning | in CI |
|---|---|---|
| 0 | no regression detected | pass |
| 2 | operational error — nothing ran | fail |
| 3 | regression detected | fail |
| 4 | an axis had zero at-risk pairs — nothing was measured | **fail**, not a pass |
| 5 | (`gate` only) the declared threshold is finer than the run can resolve | **fail** |

4 and 5 are the ones people get wrong. Neither is a pass; both mean "no answer".

## Machine-readable output

Every command takes `--json` and prints exactly one document on stdout, with diagnostics on
stderr:

```json
{ "schema_version": 1, "tool": { "name": "quantfit", "version": "0.11.0" },
  "command": "verify-safety", "exit_code": 3,
  "result": { "regression_detected": true, "unmeasurable_axes": [] } }
```

An operational failure returns the same envelope with an `error` block and `"exit_code": 2`.
A *verdict* failure (exit 3) carries no `error` block — an answer is not a breakage. Branch
on `exit_code`, and check `schema_version` before relying on field names.

## Gating a release

```bash
quantfit gate --baseline Qwen/Qwen2.5-1.5B-Instruct --quant ./out --tier smoke --out gate.json
```

The gate refuses to promise resolution it does not have: declare a threshold the run could
not have detected a violation of and it exits 5 rather than passing. There is a reference
composite action at `.github/actions/quantfit-gate`.

## Things to say accurately, because the tool is careful about them

- **A no-detection result is a bound, not a certificate.** "No regression detected" means no
  flip was observed among the at-risk pairs at the printed resolution. Do not restate it as
  "the quantized model is safe".
- **The judge is uncalibrated** unless `quantfit calibrate` has been run, so the printed MDE
  is a *perfect-judge floor* — a lower bound on the true resolution.
- **Only weight quantization is measured.** A KV-cache-quantized deployment is not covered.
- **Decoding is greedy over one curated corpus.** That is a deliberate trade for
  determinism and a defensible denominator, not an oversight.

## Fitting and planning, which need no safety run

```bash
quantfit check --model Qwen/Qwen2.5-7B-Instruct    # exit 3 = will not fit
quantfit plan  --model Qwen/Qwen2.5-7B-Instruct    # the config it would pick, and why
quantfit list                                       # supported method x scheme matrix
```

`check` and `plan` need no weights. `plan` never reaches the Hub.

## Do not

- Do not invent flags. Run `quantfit <command> --help`; the surface is small and stable.
- Do not present `--demo` output as a measurement of anything.
- Do not treat exit 4 as success because the text says no regression was detected.
- Do not attach a `--capture` file to a report or commit it: it holds raw completions, which
  may include harmful model output. See `docs/data-handling-completions.md`.
