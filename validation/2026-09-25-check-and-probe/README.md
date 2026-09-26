# `check` and `probe`, run and recorded for the first time — 2026-09-25

`docs/validation-matrix.md` §2 listed both at **"Validated: Nothing"** — each had a fixed
defect in the changelog implying someone once ran it, and no artifact. `check` is the first
command in the README's quickstart, and `probe` had never had a single number recorded.

Both were run with `--json` from quantfit 0.12.16 (tree at `main` `6cdfa4c`, after #86),
Windows 11, RTX 4080 Laptop GPU (12 GB, 11.6 GB free at run time), 12.5 GB RAM available,
**13.5 GB free disk** on a 927 GB volume that is 99% full (`df`, cross-checked against the
`bytes.disk_free` field below).

## `check` — three model sizes, two of its tiers

| model | exit | mode | limit | fp16 weights | disk needed | disk free |
|---|---|---|---|---|---|---|
| `Qwen/Qwen2.5-1.5B-Instruct` | **0** | `gpu` | — | 3.09 GB | 4.94 GB | 13.52 GB |
| `Qwen/Qwen2.5-7B-Instruct` | **3** | `refuse` | **disk** | 15.23 GB | 24.37 GB | 13.52 GB |
| `Qwen/Qwen2.5-72B-Instruct` | **3** | `refuse` | **disk** | 145.41 GB | 232.66 GB | 13.52 GB |

(bytes from the JSON, divided by 10⁹.) All three verdicts are correct for this machine. The
7B is the README's own headline example, and here it is refused on **disk** before VRAM is
even considered — its fp16 weights (15.2 GB) would exceed the free VRAM (11.6 GB) too, which
would have made it an `offload` candidate on a box with room to download it.

## `probe` — the first RTN-KL numbers this repository has ever recorded

`quantfit probe --model Qwen/Qwen2.5-1.5B-Instruct --bits 4 8 --json`, 124 s wall:

| bits | mean per-token RTN-KL (fp16 ‖ quant) | samples |
|---|---|---|
| 4 | **0.5716** | 8 |
| 8 | **0.0030** | 8 |

Run twice; both runs agree **to the last float digit** (`probe-rerun.json`). Roughly two
orders of magnitude between 8-bit and 4-bit round-to-nearest — the shape the command's own
interpretation string predicts ("LOW KL = safe bit-width").

## A defect found by running it

**`check`'s human-readable `reason` says "GB" and prints GiB.** The 1.5B's reason reads
*"~2.9 GB"* while its `bytes.fp16` is 3,087,467,144 (3.09 GB, 2.88 GiB); *"only 12.6 GB is
free"* while `bytes.disk_free` is 13,522,411,520 (13.52 GB, 12.59 GiB) and `df` says 13G.
The JSON is right; the prose unit is wrong by 7.4%. It does not change a verdict here — the
comparisons are done in bytes — but a reader deciding whether to free disk by the printed
figure is told the wrong amount. Recorded in `docs/validation-matrix.md` §5, not fixed in
this evidence change.

## What this does NOT establish

- **`check`'s `offload` tier and its VRAM- and RAM-limited refusals are still unexercised.**
  This disk is too full to reach them: every model big enough to need offload is refused on
  disk first. Moving that needs ~25 GB free.
- **Nothing about `check` on a machine with no GPU**, where `route()` takes a different branch.
- **`probe` at n = 8 is a sensitivity reading, not a measurement with an interval.** The
  command reports a mean over 8 samples and no spread; two identical runs show it is
  deterministic, not that 8 samples are enough.
- **RTN-KL is not a refusal predictor.** ROADMAP 0.3 and arXiv 2606.10154 say so, and nothing
  here tests the relationship.
- **One machine, one model family.**

## Files

| file | what it is |
|---|---|
| `check-Qwen_Qwen2.5-{1.5B,7B,72B}-Instruct.json` | the `--json` envelopes, verbatim |
| `probe-Qwen_Qwen2.5-1.5B-Instruct.json` | the probe run |
| `probe-rerun.json` | the second run, identical |
