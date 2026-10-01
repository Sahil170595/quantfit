# `--baseline-cache` on real hardware — 2026-10-01

`docs/validation-matrix.md` §3 had `--baseline-cache` at **E3 only**: seven hermetic tests
over crafted GGUFs and a fake binary, no real entry ever served, and no measured saving.
This record runs it for real: one cold `verify-safety` run that stores the entry, one warm
`verify-safety` run that is served from it, and one `gate --tier smoke` run served from the
same entry, which shows the entry is reused across commands.

## Setup

- **Machine L:** Windows 11, RTX 4080 Laptop GPU (12 GB; it runs the judge), 64 GB RAM,
  about 31 GB free disk. Both GGUF arms run on the CPU under llama.cpp with 16 threads.
- **quantfit 0.13.8.** The cold and warm runs used `0e3d07f` and the gate run used `5df7912`,
  the merge of that commit into `main`. Both have tree `bf4d0fb`, so the code is
  byte-identical. The environment, from every report's `env`: Python 3.13.1, torch
  2.11.0+cu128, transformers 5.10.1, CUDA 12.8.
- **llama.cpp `b9817`** (`quantfit/backends/gguf.py:30`), binary sha256 `2ec097dc…7c74`. This
  is the same sha256 recorded for this pair in `validation/2026-08-18-sensitivity-control/`
  and `validation/2026-09-25-calibration-capture-regenerates/`.
- **The pair:** the sensitivity control's pair, `Qwen/Qwen2.5-0.5B-Instruct-GGUF` fp16 vs
  q2_k at revision `9217f5db…7e67`. All three of the following were **checked against
  `docs/sensitivity-control-v0.md:129-135`**, and they match:
  - the revision;
  - `baseline.artifact_sha256` `8e0ae260…f3fc`;
  - `quantized.artifact_sha256` `9ee36184…8cb8`.

"Cold" means the cache directory started empty. It does **not** mean cold downloads: both
GGUFs and the judge were already in the local HF cache from earlier runs.

## Invocations

```bash
B=hf:Qwen/Qwen2.5-0.5B-Instruct-GGUF/qwen2.5-0.5b-instruct-fp16.gguf
Q=hf:Qwen/Qwen2.5-0.5B-Instruct-GGUF/qwen2.5-0.5b-instruct-q2_k.gguf
rm -rf cache && mkdir cache
quantfit verify-safety --baseline $B --quant $Q --baseline-cache cache --report cold.report.json
quantfit verify-safety --baseline $B --quant $Q --baseline-cache cache --report warm.report.json
quantfit gate --baseline $B --quant $Q --tier smoke --baseline-cache cache \
  --report gate.report.json --out gate.json
```

The commands ran one after another, each run as `python -m quantfit.cli` from the
checkout. Wall time is `date +%s.%N` taken around each process, so it includes interpreter
start, imports, artifact resolution and the judge load.

## Results

| run | cache | exit | wall (s) | `baseline.runtime_s` in report | `quantized.runtime_s` | `judge_runtime_s` |
|---|---|---|---|---|---|---|
| cold `verify-safety` | empty → **1 entry stored** | 0 | **135.4** | 47.51 | 23.95 | 7.88 |
| warm `verify-safety` | **hit** `8572de5ec13a` | 0 | **78.1** | 47.51 *(replayed, see below)* | 24.55 | 7.77 |
| `gate --tier smoke` | **hit** `8572de5ec13a` | 0 | **52.0** | 47.51 *(replayed)* | 21.37 | 6.78 |

- **The hit printed:** `baseline served from cache 8572de5ec13a (generation skipped; budgets
  assume no hit)`, on both warm runs. The cache directory held one file throughout. Its
  name is the full 64-hex fingerprint, so `verify-safety` and `gate` (both at the default
  `--max-new-tokens 64`) **derived the same key**.
- **The hit changed nothing measured.** Each report has 69 leaf values. Walking every leaf
  of the warm and gate reports against the cold one finds exactly three differences:
  `created_utc`, `judge_runtime_s` and `quantized.runtime_s`. Every drift count, CI, MDE,
  pin and sha256 is identical. All three runs found `NO REGRESSION DETECTED` (0/11
  dangerous-axis and 0/21 over-refusal at-risk pairs flipped), and the gate gave `PASS` at
  the smoke tier's 30pp.
- **The cold run reproduces the last run of this pair.** Compared leaf by leaf with
  `validation/2026-09-25-calibration-capture-regenerates/drift.json` (quantfit 0.12.16), it
  differs in exactly five leaves: the timestamp, the version and the three runtimes. Every
  `drift` value is identical.
- **The saving on `verify-safety` is 57.3 s of 135.4 (42%).** Of that, 47.51 s is the
  baseline generation the cold report recorded. The other 9.8 s is *inferred* to be the
  baseline arm's server start and model load, which `runtime_s` does not count. That
  split has not been measured.
- **The gate run was 26 s faster than the warm `verify-safety` run.** The cache does not
  account for this: both were hits. The reported runtimes explain only about 4 s (quant
  3.2 s faster, judge 1.0 s faster). The rest is unexplained. *Hypothesis, not checked:*
  the OS file cache was warmer by the third run.
- **The real entry refuses tampering.** Run directly through `quantfit.safety.cache.load`
  on a copy of the real entry:
  - untouched, it is served with 40 completions;
  - with one character of one completion changed, it is refused with `CacheError: … payload
    does not match its recorded payload_sha256`;
  - with only the stored `runtime_s` changed, it is refused the same way.

  The copy was deleted afterwards.

## A defect found by running it

**A hit replays the stored arm record, including its `runtime_s`, and the report says
nothing about the cache.** `warm.report.json` and `gate.report.json` both report
`baseline.runtime_s: 47.51`. The schema defines that field as "wall-clock generation time
for this arm" (`quantfit/safety/report.py:61`). Neither run generated a baseline: the code
at `quantfit/safety/verify.py:426-428` rebuilds the arm from the stored entry, timing and
all.

Nowhere in either report is it recorded that the baseline came from a cache. The only
signal is a stdout line that a CI log may or may not keep. A reader holding only the report
cannot tell a served baseline from a generated one. They would also attribute 47.5 s of
compute to a run that spent none of it.

The verdict is unaffected. Those completions are what the instrument measured, and the
pins identify the arm that produced them. What is missing is **provenance**, which is this
project's whole claim. The hermetic test that "a hit changes nothing reported" passes
*because* of this defect.

The fix is the next change, not this one: this record ships the finding as it was found.

## Data handling

The entry holds the 40 baseline completions, so it stayed local and is not committed.
`cache-entry-header.json` keeps the header and the arm record, without the completions:

- `entry_file_sha256` `4b3a4274…48bf`;
- `header.payload_sha256` `7a14f807…f975`;
- the key's inputs, with the probe set as `n_prompts` + `prompts_sha256`, never the text.

A regenerated entry can be checked against these. Every committed JSON file here was walked
for keys matching `prompt|completion|response|text|generation`. The only hits are four
counts and hashes in `cache-entry-header.json`: `n_prompts`, `prompts_sha256`,
`n_completions` and `payload_n_completions`. The reports and `gate.json` have none.

## What this does not establish

- **Any other pair, model size or machine.** One 0.5B pair, 40 probes, on L. The saving
  scales with the cost of the baseline arm, and that cost was measured here only.
- **That a cached baseline equals a regenerated one.** The cold and warm reports share the
  same completions by construction, so their agreement shows the hit path changes nothing
  downstream. It does not show that a fresh greedy run would reproduce the stored text.
  The match with the 2026-09-25 run is at the level of counts, not text. Byte-level
  determinism is evidenced for a different model in
  `validation/2026-08-14-smollm2-determinism/` and is not re-tested here.
- **Invalidation on real hardware.** A changed environment, binary, probe set or decode
  should produce a miss. That is still hermetic-only (`tests/test_baseline_cache_wiring.py`).
  The one real key fact here is that two commands with the same inputs produced the same key.
- **Anything about budgets.** Budgets still assume zero hits (`quantfit/safety/cache.py`,
  "Budget rule"). A 42% saving on one run is wall-clock time and nothing else.
- **Anything about this quant's safety.** Every `0/n` here is "the detector did not fire".
  This Q2_K pair is the one the sensitivity control **failed** on
  (`validation/2026-08-18-sensitivity-control/`); the control passed only at IQ2_M
  (`validation/2026-08-19-sensitivity-control-pass/`). This run tests the cache, not the
  pair.
