---
license: apache-2.0
pretty_name: Quantfit QSR v0 aggregate candidate evidence
tags:
- quantization
- gguf
- aggregate-evidence
---

# Quantfit QSR v0 aggregate campaign evidence

2026-10-09: one pinned Phi-4-mini BF16 / Q4_K_M pair on a GitHub-hosted
Ubuntu CPU runner, measured from source `2997c9304f4c0de02f2299fe7c42f1693539bf6d` using the
installed candidate wheel. [Original CI execution](https://github.com/Sahil170595/quantfit/actions/runs/37890682118). The campaign
uses the shipped omitted token flag (greedy 64), the full 40-probe corpus,
three fresh native processes, sequential arms and the pinned local judge.

Each run flags **2/20 over-refusal flips** (two-sided 95% Wilson interval
2.79%-30.10%, perfect-judge 80%-power MDE floor 7.73pp), and **0/12 dangerous-axis
flips** (two-sided 95% Wilson upper 24.25%, perfect-judge 80%-power MDE floor
12.55pp). The detector did not fire on the dangerous axis. These are repeated
measurements of one pair, not three independent pairs or pooled denominators.
Native exits are **3/3/3**; parent cold-run exit **0** means T0 agreement.
Full-report repeatability also passes after excluding only declared timestamp
and runtime fields.

**No new human adjudication was performed.** The fresh classifier flags are
unconfirmed, so admission to the capped reference registry is blocked; zero
qualified reference reports are registered. Historical human confirmations do
not transfer to this campaign. These files are public candidate evidence.
Publication and byte integrity do not establish model safety, producer
authenticity, calibrated detection sensitivity or scientific GO. No new
sensitivity control, T4/cross-hardware reproduction, Inspect parity or QSR v1
freeze is claimed. Report intervals carry sampling error only and MDEs are
perfect-judge floors, not bounds on real-world safety.

**GGUF stratum cap:** unquantized baseline arm <= 16.5 GB on disk (~8B-class) in CPU RAM; both arms under one pinned llama.cpp binary, CPU-only

**Judge label (verbatim):** no card XSTest figure; measured in-distribution by quantfit instead — accuracy 95.0% at n=80 (single-rater, one model, one probe set); false-positive rate 8.3% on 48 compliant completions (95% CI upper 19.6%); false-negative rate 0.0% on 32 refusals (95% CI upper 10.7%) — a measured zero at this n is not a flawless judge, and a false negative is a MISSED dangerous flip

The procedure and meaning of these statistics are in
[QSR v0](https://github.com/Sahil170595/quantfit/blob/2997c9304f4c0de02f2299fe7c42f1693539bf6d/spec/qsr-v0.md)
and the [pre-registered campaign](https://github.com/Sahil170595/quantfit/blob/2997c9304f4c0de02f2299fe7c42f1693539bf6d/docs/reference-campaign-v0.md).

## Files and integrity

[`v0/campaigns/2026-10-09-phi4-cpu/manifest.json`](v0/campaigns/2026-10-09-phi4-cpu/manifest.json) gives exact SHA256 values and
sizes of the ten original producer files. Reports and model-card fragments,
campaign/assessment aggregates and the original native/T0 observations are
preserved byte-for-byte. Raw prompts, model completions, private logs, captures,
labels and weights are excluded. Source reports, engine/weight hashes and
observed CPU/RAM/disk provenance are in those aggregates; peak RSS was not measured.

Pin downloads to the dataset's immutable commit. Original T0 paths name the
producer runner. After downloading the three report files, recompute T0 with
`quantfit t0 --reports <three actual paths> --out relocated-t0.json --json`.
Keep the original T0 and its SHA256 unchanged. Distinct hashes and T0 agreement
do not prove independent execution or physical-host identity.
