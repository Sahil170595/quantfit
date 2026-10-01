# `probe` at n = 64: the 4-bit tail is short rows — 2026-10-01

The first recorded probe run (`validation/2026-09-25-check-and-probe/`) averaged over 8
calibration rows. On Qwen2.5-1.5B-Instruct at 4 bits it found mean 0.572 against median
0.244, because two of the eight rows sat near 1.5. `--samples` (0.14.0) made it possible
to ask whether that shape survives a larger n, and what the two rows are.

**Answer: the tail survives, and it is short rows.** Every row of 22 tokens or fewer has
a 4-bit KL of at least 0.569. Every longer row has a 4-bit KL of at most 0.471. Most of
the short rows are wikitext section headings (`= = = Ratings = = =`). The two n = 8
outliers were headings of 9 and 10 tokens.

## Setup

- **Machine L:** RTX 4080 Laptop GPU (12 GB), 64 GB RAM, Windows 11.
- **Software:** Python 3.13.1, torch 2.11.0+cu128, transformers 5.10.1, datasets 4.8.5.
- **quantfit:** commit `d4c118a`, the `--samples` commit exactly as merged in #101. It sits
  before the 0.14.0 version bump, so the envelope says `0.13.8`. The probe code is
  identical to 0.14.0's.
- **Model:** `Qwen/Qwen2.5-1.5B-Instruct`. `probe` loads it by id with no revision pin. The
  only snapshot in the local cache is `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, so that is
  the one used (*inferred*: the run does not record it).
- **Calibration rows:** `Salesforce/wikitext` / `wikitext-103-raw-v1` / `train`, shuffled
  with seed 42 (`quantfit/spec.py`).
  - **Also unpinned** (`quantfit/policy/probe.py:133`). The revision used was
    `b08601e04326c79dfdd32d625aee71d232d685c3`, recorded in `rows.json` as `revision_used`.
  - That revision is both the local cache's `refs/main` and the Hub's current `main`, read
    from `https://huggingface.co/api/datasets/Salesforce/wikitext`, last modified 2024-01-04.
  - The quantize path loads the same dataset the same way
    (`quantfit/backends/compressed_tensors.py:50`).

## Invocation

```bash
quantfit probe --model Qwen/Qwen2.5-1.5B-Instruct --bits 4 8 --samples 64 --json > probe-n64.json
```

Exit 0. Wall time was 37.2 s, from `date` around the process. The model, the dataset and the
tokenizer were already cached. The estimated host RAM for the held fp16 log-probs is
5.35 GB: 8,796 tokens × 151,936 vocabulary entries × 4 bytes. This was computed, not
measured.

`rows.json` was built afterwards, without the model. It re-runs the probe's own row
selection (`_probe_batch`: drop empty rows, shuffle by the seed, take the first 64 rows of
at least `_MIN_PROBE_TOKENS` = 8 tokens) with the model's tokenizer. For each row it
records the token count, whether the row is a section heading, a sha256 of the row's text,
and the two KLs from `probe-n64.json`. The heading rule is
`re.fullmatch(r"\s*(= )+.*?( =)+\s*", text)`. The rebuilt token counts of the first eight
rows (221, 123, 116, 9, 246, 379, 318, 10) are the batch the probe ran on. The KLs are
taken from the probe's output by position.

## Results

| bits | n | mean | median | SD | min | max | mean, rows > 22 tokens (n = 51) | token-weighted mean |
|---|---|---|---|---|---|---|---|---|
| 4 | 64 | **0.4187** | 0.2827 | 0.3691 | 0.1786 | 1.6773 | **0.2620** | 0.2591 |
| 8 | 64 | 0.0030 | 0.0014 | 0.0035 | 0.0007 | 0.0216 | 0.0017 | 0.0014 |

- **A larger N extends the default rows, it does not replace them.** The mean of the first
  eight samples is `0.571582242846489` at 4 bits and `0.00297176162712276` at 8 bits. Both
  are bit-for-bit equal to the 2026-09-25 run's `mean_kl`. This is the prefix property
  `docs/cli-reference.md` states, now observed. It is also a second exact reproduction of
  that run, six days and one release later.
- **The tail is short rows, and only short rows.**
  - Sorting the 64 rows by token count splits them cleanly: 13 rows have 8–22 tokens, and
    the other 51 have 36 or more. No row falls between 23 and 35.
  - Every short row has a 4-bit KL ≥ 0.569. Every long row has a 4-bit KL ≤ 0.471.
  - Spearman correlation between 4-bit KL and token count is −0.762.
  - Ten of the 13 short rows are section headings. The other three are 12–17-token
    fragments (a credits line, a list entry, a title).
  - All six rows above 1.0 are headings.
- **The n = 8 tail was overrepresented.** Two of the first eight rows are headings, 25%.
  Over 64 rows the headings are 10, or 15.6%. So the n = 8 mean (0.572) sat well above the
  n = 64 mean (0.419). Neither is wrong as arithmetic, but both are dominated by how many
  headings the sample happened to draw.
- **8 bits shows the same pattern at 1/100th the scale.** Spearman correlation with token
  count is −0.829. The 8-bit and 4-bit KLs rank rows alike (Spearman 0.827), so short rows
  are the most "sensitive" at both widths.
- **What the mean measures.** `mean_kl` is the unweighted mean of per-row per-token means
  (`quantfit/policy/probe.py:115-124`). A 9-token heading therefore weighs as much as a
  437-token paragraph. Weighting by tokens, or dropping rows of 22 tokens or fewer, gives
  about 0.26 at 4 bits. That is 62% of the reported 0.419.

*Hypothesis, not checked:* a short row is mostly early positions, which have the least
context. The per-token KL there is plausibly highest, and the shift from fp16 at 4 bits
largest. Testing that needs per-position KL, which the probe does not emit.

## What this changes, and what it does not

The 4-bit-vs-8-bit ordering, the only thing the probe's interpretation string asks a
reader to use, is untouched. 4 bits is about 100× 8 bits on every summary above.

What changes is how to read the 4-bit number and its spread. The spread the 0.13.x change
added is real. It is a property of the calibration set's row-length mix, not of the model:
headings sit in the tail at both bit-widths. A per-model comparison of `mean_kl` therefore
depends on how many headings each sample drew, and that depends only on N and the seed.

No change to the probe ships with this record. Whether `mean_kl` should be token-weighted,
or headings excluded, changes a published number and is a decision of its own.

## What this does not establish

- **Any other model.** One model, two bit-widths, one seed. That the split falls at 22 vs
  36 tokens is a fact about these 64 rows, not a threshold.
- **That headings cause the high KL.** Short rows and headings coincide here. Three
  non-heading short rows sit in the tail too, so length is the better-supported variable.
  Neither is shown to be causal.
- **Anything about calibrated quantizers.** This is RTN, the worst case, as the command
  says. AWQ and GPTQ calibrate on this same dataset, and nothing here says how they treat
  headings.
- **Any relationship to refusal drift.** ROADMAP 0.3 and arXiv 2606.10154 say not to
  assume one, and nothing here tests it.
- **A pinned measurement.** The model and the calibration dataset are both loaded at `main`.
  The revisions above are what this run resolved, not what quantfit pins. A Hub change to
  either would change these numbers silently.
