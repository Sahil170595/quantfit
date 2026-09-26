# The calibration capture regenerates byte-for-byte — 2026-09-25

The judge-error measurement this project's whole resolution argument rests on
(`validation/2026-08-18-judge-calibration/`, ε = 0.1955) was hand-labelled from a capture
that is **not committed** — completion text stays local under
`docs/data-handling-completions.md`. What *is* committed is a sha256 per completion, and
that record's README says the labels "remain checkable against a regenerated capture".

Nobody had checked. This run does.

## Result

| | recorded 2026-08-18 | regenerated 2026-09-25 |
|---|---|---|
| completions | 80 | 80 |
| **identical by sha256** | — | **80 / 80** |
| shipped judge vs the human labels | tp 32 · fp 4 · tn 44 · fn 0 | **tp 32 · fp 4 · tn 44 · fn 0** |

Every completion the human labels describe came back **byte-identical**, 38 days and twenty
quantfit releases later (0.8.0 → 0.12.16, by `git tag`). And because the regenerated capture
carries the *shipped* judge's labels, the confusion matrix ε is computed from reproduces
exactly: 4 false positives in 48 compliant completions, 0 misses in 32 refusals.

The hash is `quantfit.safety.calibrate._completion_sha256` — sha256 over UTF-8 — and the
match count was re-derived a second way with raw `hashlib`: also 80/80.

## What had to be the same for that to mean anything

Checked field by field against `validation/2026-08-18-sensitivity-control/sensitivity-control.json`:

| | both runs |
|---|---|
| baseline | `hf:Qwen/Qwen2.5-0.5B-Instruct-GGUF/qwen2.5-0.5b-instruct-fp16.gguf`, F16, `artifact_sha256` 8e0ae260… |
| quant | `…/qwen2.5-0.5b-instruct-q2_k.gguf`, Q2_K, `artifact_sha256` 9ee36184… |
| HF revision | 9217f5db… on both arms |
| engine | llama.cpp release `b9817`, `binary_sha256` 2ec097dc…, CPU |
| probe set | `Crusadersk/quantsafe-judge-benchmark` at the pinned revision |
| decode | greedy, `max_new_tokens` 64, model chat template |

**What differed:** the judge (`Crusadersk/quantsafe-refusal-modernbert` on 2026-08-18,
retired; `garak-llm/garak-refusal-detector@5cb5ec8f` now) and the quantfit version. The judge
scores completions and does not produce them, so it cannot move a completion hash.

## Invocation

```bash
quantfit verify-safety \
  --baseline hf:Qwen/Qwen2.5-0.5B-Instruct-GGUF/qwen2.5-0.5b-instruct-fp16.gguf \
  --quant    hf:Qwen/Qwen2.5-0.5B-Instruct-GGUF/qwen2.5-0.5b-instruct-q2_k.gguf \
  --report drift.json --capture regen.capture.jsonl
```

quantfit 0.12.16 (tree at `main` after #85, `6b70657`), Windows 11. The report's `env` block
is identical to 2026-08-18's (RTX 4080 Laptop GPU, torch 2.11.0+cu128, Python 3.13.1), which
is the evidence this is the same machine. Exit 0.
Baseline arm 43.6 s, quant arm 21.1 s, judge 25.6 s.

## What this does NOT establish

- **It is not a cross-hardware reproduction.** Same machine, same binary, same env block. The
  GGUF arms run on CPU, so the GPU did not generate anything, but the CPU is also the same
  one. Whether these completions reproduce on other hardware is the cross-hardware
  tolerance's question (`docs/cross-hardware-tolerance-v0.md`), and T3 already breached once
  between this box and a CI runner (`validation/2026-08-15-crosshw-smollm2/`).
- **It does not re-verify the human labels.** It shows the labels still attach to the same
  text. Whether that text was labelled *correctly* is still one rater's judgement.
- **It does not change ε.** Same completions, same judge, same counts: ε is still 0.1955 and
  the effective MDE is still 1.0 for every n ≤ 34. What moved is how much weight that number
  can bear — it is now reproduced, not just recorded.
- **The drift result in `drift.json` is not comparable to 2026-08-18's.** It was judged by a
  different judge, so its at-risk denominators differ (n = 11 dangerous here; the retired
  judge called all 12 baseline completions refusals). It is committed as the run's own record,
  not as a second measurement of the pair.

## Files

| file | what it is |
|---|---|
| `drift.json` | the run's schema-v2 report — aggregates only, walked for text-bearing keys before commit (none) |
| `comparison.json` | per completion: pair, arm, zone, human label, recorded sha256, regenerated sha256, `identical`, the shipped judge's label; plus the confusion matrix both ways. **No completion text.** |

The regenerated capture itself is local-only and not committed, like the original. Its file
sha256 is in `comparison.json` so a later run can compare against it. (The file hash is
*expected* to differ from the 2026-08-18 capture's — the header carries a timestamp and the
judge labels differ — which is why the comparison is per completion.)
