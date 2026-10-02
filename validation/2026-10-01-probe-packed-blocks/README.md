# `probe` on packed blocks: the 4-bit tail was the weighting — 2026-10-01

`validation/2026-10-01-probe-at-n64/` found that the probe's 4-bit spread on
Qwen2.5-1.5B-Instruct came from short rows. Rows were tokenized one at a time and their
per-row means averaged, so a 9-token heading weighed as much as a 437-token paragraph.
There were three ways to fix it:

- token-weight the row means;
- drop heading rows, a filter chosen after seeing the data;
- measure what the quantize path calibrates on.

0.15.0 does the third. The probe now packs the calibration set into fixed-length 512-token
blocks with the quantize path's own function (`quantfit/calibset.py:packed_blocks`).

## Setup

- **Machine:** L (RTX 4080 Laptop GPU, 12 GB; 64 GB RAM; Windows 11).
- **Software:** Python 3.13.1, torch 2.11.0+cu128, transformers 5.10.1, datasets 4.8.5.
- **quantfit code:** commit `24c3e77` on top of the 0.14.3 release. The runs used that
  exact code, uncommitted at the time; nothing under `quantfit/` changed between the runs
  and the commit. The envelope reports version `0.14.3` because the version bump comes
  with the release.
- **Model:** `Qwen/Qwen2.5-1.5B-Instruct`. Every row's `model_revision` is
  `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, recorded by the probe itself.
- **Calibration set:** `Salesforce/wikitext` / `wikitext-103-raw-v1` / `train` at the
  pinned `b08601e…`, seed 42. Packing and block length are recorded in each envelope's
  `result.calibration`.

## Invocations

```bash
quantfit probe --model Qwen/Qwen2.5-1.5B-Instruct --bits 4 8 --samples 8  --json > packed-n8.json
quantfit probe --model Qwen/Qwen2.5-1.5B-Instruct --bits 4 8 --samples 64 --json > packed-n64.json
```

Both exited 0, in 21.6 s and 55.4 s. Those wall times are uncontrolled: L is a shared laptop.

## Results

| | row-based, n = 8 | row-based, n = 64 | **packed, n = 8** | **packed, n = 64** |
|---|---|---|---|---|
| 4-bit mean | 0.5716 | 0.4187 | **0.2372** | **0.2306** |
| 4-bit median | 0.2444 | 0.2827 | 0.2389 | 0.2241 |
| 4-bit SD | 0.6107 | 0.3691 | 0.0233 | 0.0309 |
| 4-bit max | 1.6139 | 1.6773 | 0.2708 | 0.3333 |
| 8-bit mean | 0.0030 | 0.0030 | 0.0009 | 0.0009 |

The row-based columns come from `validation/2026-09-25-check-and-probe/` and
`validation/2026-10-01-probe-at-n64/`.

- **The tail is gone.** Packed, mean ≈ median at both N. The 4-bit SD falls 26× at n = 8
  and 12× at n = 64, and the largest of 64 blocks is 0.333. The mean moves 0.007 between n = 8 and
  n = 64. Row-based, it moved 0.153.
- **8 bits was inflated the same way.** Its mean drops from 0.0030 to 0.0009. Short rows
  had a long tail at 8 bits too (`probe-at-n64/rows.json`).
- **The ordering holds, and widens.** 4 bits is now 271–277× 8 bits, against 142–192×
  row-based.
- **A larger N extends the default blocks.** At both widths the n = 8 per-block KLs are
  bit-for-bit the first eight of the n = 64 run.
- **The new mean (0.231) is below the old token-weighted mean (0.259).** Both count every
  token once. What differs is the tokens and their context: 32,768 packed tokens against
  the 8,796 tokens of 64 rows. A packed token has up to 511 tokens of real text before it,
  where a row-start token had none. *Inferred,
  not measured:* this is the early-position effect the n = 64 record hypothesised. The
  probe does not emit per-position KL, so it is not shown here.

## Equivalence checks run before the record

All four were run with the code at `24c3e77`, on the real dataset and the real
tokenizer, before the probe runs above.

1. **The quantize path is unchanged by the refactor.** Before and after the move to the
   shared `packed_blocks`, `backends/compressed_tensors.calib_dataset` produced the same
   blocks: 128 × 2048 tokens, sha256 of `[input_ids, attention_mask]` equal to
   `a34d09daee7bbe0b50079057d7b1a853c96cbbe3a8caf5ee0ea624fdc005915b` both times.
2. **The probe reads the head of the quantize path's stream.** The probe's 64 × 512
   blocks, laid end to end, equal the quantize path's first 16 × 2048 blocks token for token.
3. **Holding logits instead of log-probs changes nothing.** The probe now holds the
   reference logits in the model's fp16 and computes `log_softmax(logits.float())` when it
   needs it. On 4 real blocks, that equals the old float32 log-probs under
   `torch.equal`, 4 of 4. Host RAM per block halves, from 311.2 MB to 155.6 MB.
4. **Hermetic tests:** `tests/test_calibset.py` has 6 tests over a fake dataset: fixed
   block length, short-set behaviour, the head-of-stream property, both callers, and the
   probe batch.

## What this does not establish

- **Comparability with any pre-0.15.0 probe number.** Those are a row-weighted metric over
  different tokens. The JSON's `metric` string now says which quantity a number is.
- **Any other model, bit-width or block length.** One model, 4 and 8 bits, 512-token
  blocks. Block length is a choice: it sets how much context each token has, so a
  different length would give somewhat different numbers.
- **That the packed number predicts calibrated-quant quality or refusal drift.** It is
  still RTN, the worst case, and ROADMAP 0.3 and arXiv 2606.10154 say not to assume a link
  to refusal behaviour.
- **An interval.** Blocks are the unit, and 8 or 64 of them support description, not
  inference. None is reported.
