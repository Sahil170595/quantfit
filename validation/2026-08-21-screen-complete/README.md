# The 0.5 screen, complete — 14 of 15 measured — 2026-08-21

Every target in `screens/targets-0.5.json` has now been measured except one that cannot
run on this host at all. `all_targets_attempted: true`, and **no bound carries a
conditionality label** — the sensitivity control passed on 2026-08-19.

## The bounds

| stratum | axis | flagged | **confirmed** | confirmed bound (Wilson 95%) |
|---|---|---|---|---|
| gguf | **refusal-robustness (dangerous)** | **0/12** | **0/12** | **0.0–24.2%** |
| gguf | over-refusal | 6/9 | **3/9** | 12.1–64.6% |
| compressed-tensors | refusal-robustness | 0/2 | 0/2 | 0.0–65.8% |
| compressed-tensors | over-refusal | 2/2 | **1/2** | 9.5–90.5% |

**The dangerous axis is zero across all twelve GGUF targets and both compressed-tensors
targets.** Fourteen third-party quantized artifacts, five quantizer organisations, two
strata, and not one probe where the baseline refused and the quantized model complied.

## What changed since the 11-target run

Three targets were previously blocked by disk — the machine had 21 GB and their pairs
need 19.1, 21.0 and 21.4 GB. Removing 92 GB of unrelated local Ollama models freed the
space, and `--resume` (shipped in 0.10.0, written *because* of this run) skipped the
eleven already measured rather than re-running them.

| newly measured | dangerous | over-refusal |
|---|---|---|
| `gguf-ministral-8b-bartowski` | 0/10 | 0/24 |
| `gguf-olmo2-7b-bartowski` | 0/12 | 0/21 |
| `gguf-qwen3-8b-unsloth` | 0/12 | 0/**0** unmeasurable |

**All three flagged nothing**, which *lowers* the flagged prevalence rather than raising
it: the GGUF over-refusal denominator went 7 → 9 while the numerator stayed 6, so
flagged-basis prevalence falls from 85.7% to 66.7%. They need no adjudication — there is
nothing to adjudicate — and the confirmed count is unchanged at 3 targets.

The dangerous-axis bound tightened with the larger denominator: **29.9% → 24.2%** upper.

## The one that cannot run here

`ct-qwen25-15b-official-awq` — `ModuleNotFoundError: No module named 'triton'`, raised by
gptqmodel's AWQ kernel validation. Triton does not ship on Windows, so this target is
unrunnable on this host **at any disk size**. It is recorded as an error row rather than
dropped, because a silently omitted target overstates coverage.

As of 0.10.0 that failure exits 2 with a clean message rather than 1 with a traceback, and
per-target isolation means it costs exactly itself.

## What the dangerous-axis zero now means — and what it still does not

It is **no longer conditional**. The sensitivity control passed
(`validation/2026-08-19-sensitivity-control-pass/`), so these are nulls from an instrument
**demonstrated to detect a real, human-confirmed dangerous-axis flip** rather than from a
detector of unknown sensitivity. That is the difference the whole 0.5 milestone turned on.

It is still **not** evidence that quantization preserves refusal behaviour:

- The control passed at **IQ2_M**; these targets are mostly **Q4_K_M**.
  `docs/sensitivity-control-v0.md` §6 — *"detecting the loud case says little about the
  quiet one"* — is the binding limit, and the gap is unquantified.
- **n is 12 and 2.** An upper bound of 24.2% is not a small number. It admits roughly one
  in four artifacts carrying a detectable dangerous regression.
- Two GGUF targets are `0/0` on the over-refusal axis and are excluded from that
  denominator rather than counted as clean.

## The finding, stated plainly

**It took a 2-bit i-quant to break a single refusal.** Fourteen third-party artifacts at
ordinary quantization levels produced zero dangerous flips; a Q2_K control produced none
either; only IQ2_M did. Refusal behaviour is more robust to ordinary quantization than
this project was built expecting — and that is now a measured result from an instrument
with a passing positive control, not a null from a detector nobody had checked.

## Provenance

| | |
|---|---|
| quantfit | 0.10.0 + `main` |
| judge | `garak-llm/garak-refusal-detector` @ `5cb5ec8f` — measured 95.0% acc / 8.3% FPR |
| control | `status: "pass"`, 2026-08-19, confirmed flip on the refusal-robustness axis |
| decode | `do_sample=False`, `max_new_tokens=64` |
| hardware | machine **L**, which passes T0 3/3 (`validation/2026-08-21-t0-replicates/`) |

That last line matters: every measurement here was taken on the one hardware this project
has that agrees with itself.

## Files

| file | what it is |
|---|---|
| `screen-summary.json` | the screen's own summary, 15 rows, `all_targets_attempted: true` |
| `screen-summary-verified.json` | re-aggregated with `human_verified` stamped from the 2026-08-19 adjudication |
| `reports/*.json` | the 14 schema-v2 drift reports |

Captures were written for every target and are **not** committed
(`docs/data-handling-completions.md`).
