# quantfit roadmap

## Current state (v0.2.0, verified 2026-07-05)

quantfit is a GPU-aware LLM quantization CLI: `check`, `plan`, `quantize` (awq/gptq/smoothquant/fp8/rtn via llm-compressor; gguf via llama.cpp), `probe`, `verify`, and `verify-safety` — the differentiator: a paired fp16-vs-quantized refusal diff over a curated 40-probe set with a local judge, reported as a vector (refusal-robustness loss vs over-refusal), per zone. Facts re-verified at roadmap time, because two of them were stale in our own notes: **PyPI already serves quantfit 0.1.0** (uploaded 2026-06-27) with a version skew against the repo (`__init__.py` 0.1.0 vs pyproject 0.2.0); the dev box has **71.0 GB free disk**, not 14 GB, so disk-gated deferrals are unblocked. Known weaknesses, verified in code: the verdict is a single-flip binary (verify.py:85-96) over only 12 dangerous-direction probes — a "CLEAN" run bounds harmful flips only below ~24pp — and the term "safety tax" collides with established alignment-tax usage.

**Standing rules (every milestone):** re-measure disk/RAM/VRAM at milestone start and print it; one validated, pushed chunk per milestone; every gate can fail, and every GO/NO-GO states its NO-GO consequence; if a validation gate cannot run on hardware this project actually has, the feature does not ship; upper-bound dependency pins + a weekly runtime canary (CPU oneshot on a toy model, plus a clean-venv quickstart install from the lockfile).

## Vision

No maintained tool ships the paired fp16-vs-quant refusal diff with pinned provenance, calibrated statistics, and stated decision rules — that gap is either unowned ground or thin demand, and this roadmap is built to find out which before spending like it knows. The durable asset is the QSR (Quantization Safety Regression) spec plus the reference reports; the CLI is its reference implementation. We do not compete on quantization convenience (auto-round already ships a checkpoint-to-vLLM one-liner; llm-compressor engineered away "can it be quantized") — we compete on measurement nobody else does honestly.

## 0.3 — Reconcile and make the verdict honest

**Goal:** the tool's first real public impression is not its statistically weakest claim.

- PyPI reconciliation, not "first publish": audit the 0.1.0 upload attestation, fix the `__init__`/pyproject skew, publish 0.3.0 superseding the stale 0.1.0 (whose description still leads with "safety tax"). CHANGELOG; drop the dead `gptqmodel` dep; catch `ValueError` in `cli.main`.
- Fix verdict statistics **before any announcement or demand probe**: replace single-flip CLEAN/REGRESSION with bounded language — "NO REGRESSION DETECTED (dangerous-axis MDE ~13pp at n=12)" — plus Wilson CIs on both axes and explicit n=40/12 disclosure.
- Rename `safety tax` → **safety drift vector** across code (`SafetyTax` class), README, and package description; the dangerous axis reports as refusal-robustness drift. Breaking now, while real users are ~zero.
- Document the greedy fp16-vs-fp16 rerun as a **determinism canary only** — zero-flip by construction under `do_sample=False`; never call it a noise floor.
- Delete the deprecated accelerate `device_map="auto"` offload path (llm-compressor ≥0.10 has native disk offload). Dead code is removed, not validated.
- Reword probe.py: RTN-KL is a quality signal, not a refusal predictor — our own paper's point (arXiv 2606.10154).

**Gate:** clean-venv `pip install quantfit==0.3.0` works on Windows and Linux CI; two consecutive verify-safety runs identical minus timestamps; no "safety tax" string on any shipped surface; bounded verdict + CIs in output.

## 0.4a — Provenance schema + stats hardening (CI-gated)

**Goal:** reports become auditable artifacts. Split from the old bundled 0.4 to honor the one-validated-chunk rule: everything here is CI-verifiable with no hardware dependency, and it ships on its own gate regardless of 0.4b's fate.

- Report schema v1: judge + probe-dataset `revision=` pins, seed, decode params, explicit dtype (never "auto"), env fingerprint (torch/transformers/CUDA, GPU), per-arm runtime. Verify and pin the currently ASSUMED judge input contract (completion text alone, truncated).
- Stats cross-checked against scipy; hermetic CPU tests for GGUF hashing and dispatch.

**Gate:** schema round-trips; scipy cross-check and hermetic tests pass in CI. This gate is independent of 0.4b — a 0.4b slip does not hold schema v1 or the stats hardening back from shipping.

## 0.4b — GGUF judging + over-VRAM validation (hardware-gated)

**Goal:** the paired diff runs on the format the ecosystem actually publishes. Split from 0.4a because both deliverables here are gated on real local hardware runs, not CI.

- **GGUF judging** via a pinned llama.cpp binary: baseline mandated as Qn-GGUF vs F16-GGUF under the identical binary (isolates quantization); transformers-fp16 vs llama.cpp-Qn reported separately as a deployment delta, never pooled. The F16 arm runs on CPU/RAM (63.6 GB), so 7–8B pairs are feasible on this hardware — this removes the fp16-arm VRAM cap for the stratum where third-party quants actually live.
- Over-VRAM quantize-side validation: one ~8B run through llm-compressor's default sequential onloading (71 GB free, measured), with telemetry confirming real spill; README offload wording follows the evidence.

**Gate:** end-to-end paired diff on a real third-party Q4_K_M vs its F16 under the identical pinned binary; the 8B onload run completes with observed CPU spill.

**Slip rule (stated up front):** a 0.4b slip narrows 0.5, it does not stall it. If GGUF judging is late, the 0.5 screen runs on compressed-tensors artifacts only (≤3B in-GPU, cap stated), the prevalence bound is reported for that narrower stratum, and the spec v0, replication package, model-card emit, and outreach proceed on schedule. If the 8B onload run slips, only the README offload wording waits.

## 0.5 — Demand probe with real artifacts; QSR spec v0 (GO/NO-GO)

**Goal:** a demand signal from artifacts people can actually run and check, before the expensive milestones — not after.

**Independence rule:** the five deliverables below are not a bundle. Each ships independently the moment its own check passes; none blocks another, and the GO/NO-GO clock is keyed to outreach alone (below), not to the last deliverable landing.

- **Minimal sensitivity control, pulled forward from 0.6:** one Egashira-style injected quantization-conditional regression (arXiv 2405.18137) on a ~1B model, demonstrated end-to-end — the shipped judge must flag the injected flip. This is the precondition for reading the screen's null result: human verification of flagged flips catches judge false positives, but only a passed positive control shows the instrument can detect a genuine flip at all, so without it "no regression found" cannot be distinguished from "instrument insensitive to genuine flips." If the control fails or cannot be produced by screen time, the screen still runs and the prevalence bound is still published, but labeled "conditional on undemonstrated detection sensitivity," and the decision rule's regression leg is downgraded (below). Full ε calibration and the full-scale control stay in 0.6.
- **Existence-proof hunt:** run the paired diff over ~10 popular third-party quants (≤8B GGUF via the same-binary CPU F16 arm; compressed-tensors capped at ≤3B in-GPU, cap stated in every report). Every flagged flip is **human-verified** — positive existence claims need no validated judge. This doubles as an honest small-scale prevalence screen: 0/10 clean means "95% upper bound ~26% prevalence of detectable regressions at this MDE," reported as exactly that, never as falsification — and interpretable as a bound on reality (rather than on the instrument) only alongside a passed sensitivity control.
- **QSR spec v0** published as a versioned doc: paired protocol, provenance rules, two-class outcome (a "degraded" class is deferred until a validated detector exists — the shipped judge is binary), stated hardware/scale caps.
- **Replication package for arXiv 2606.10154** including RTSI — the one asset no better-resourced competitor can contest, and a runnable artifact for the probe.
- `--emit model-card` fragment: drift vector, CIs, provenance, and the exact `vllm serve` line for compressed-tensors artifacts.
- Outreach: GGUF publishers (their format is now runnable), vendor deployment teams (the R1-1776 8-bit incident shows vendors miss this in-house), and safety researchers; announce on r/LocalLLaMA and HF forums — after 0.3's stats fix, never before. Raw pypistats counts are treated as mirror/bot noise unless decomposed.
- **Decision rule (NO-GO stated):** the 8-week clock starts when outreach lands, and only outreach starts it — slips in the other deliverables do not move the clock. NO-GO fires if, within those 8 weeks, there is no design partner, no hand-verified regression found, and fewer than 3 independent external signals (substantive issue, citation, dataset reuse, replication). The "no hand-verified regression found" leg carries evidentiary weight **only if the sensitivity control passed**; if it did not, that leg is recorded as "uninformative — instrument sensitivity undemonstrated," the decision rests on the other two legs alone, and the recorded decision says so explicitly. On NO-GO, 0.6+ shrinks to maintenance mode: spec + paper + replication package stay published — with the screen result carrying its conditionality label permanently if the control never passed — and corpus/judge/gate work does not start.

**Gate:** per-deliverable, not all-or-nothing — the screen gate is ≥10 quants with human-checked flips plus a recorded pass/fail on the sensitivity control; spec v0, replication package, model-card emit, and outreach each gate on their own shipping. The milestone closes when the GO/NO-GO decision is recorded with its evidence, either way.

## 0.6 — Judge calibration and corpus v2 (runs only on GO)

**Goal:** measure the instrument before making claims with it.

- **In-distribution judge error first:** hand-label 300–500 of quantfit's own completions (both arms, concordant pairs included — flips-only is verification bias); per-arm error ε with CIs. Until this lands, the judge card's 2.3% XSTest/GPT-4 figure is labeled "uncalibrated, out-of-distribution" everywhere it appears. Second annotator on a subsample if one exists; otherwise single-rater, disclosed. Arm-correlated judge error is bias no sample size fixes — stated as a limit in the spec.
- Corpus: clear_unsafe 12→60+, **curated and redistributable only** — the shipped "never raw harmbench/advbench" invariant (verify.py:20-22) is part of the differentiator and is never silently reversed. XSTest enters only as an over-refusal tier with a contamination disclosure (the judge was validated on XSTest responses; ε is never measured there), with corrected counts (250 safe / 200 unsafe).
- MDE machinery: per-run MDE from ε's upper CI at pre-registered effect sizes; honest headline is 10–15pp, not 5pp.
- End-to-end sensitivity control at full scale: extends the 0.5 mini-control (one injected flip on a ~1B model) to the Egashira-style injected quantization-conditional regression (arXiv 2405.18137) measured against the calibrated MDE — not 3-bit RTN, which this stack cannot produce (SCHEMES bottom out at W4). GGUF Q2_K serves as a degradation stressor; incoherent outputs are human-spot-checked and stats stay two-class.
- KL-vs-drift correlation reported descriptively only; a handful of checkpoints on one model cannot validate or kill the proxy.

**Gate:** ε with CIs published; the injected regression is detected above the printed MDE; corpus revision pinned; every report prints its MDE.

## 0.7 — `quantfit gate` and CI integration

**Goal:** the pre-release check a quantizer runs on their own GPU, which refuses to promise resolution it does not have.

- Printed MDE = statistical MDE + upper CI of measured judge error; thresholds finer than that are hard-refused with a distinct exit code. Smoke tier gates ≥30pp only and says so.
- Fingerprint-keyed baseline caching (budgets assume zero hits); reference GitHub Action with a scheduled CPU smoke job.
- Cross-hardware tolerance: local RTX vs free T4/Colab, dtype pinned fp16 on all arms, 3 replicates; the write-up states which factors the tolerance covers. This tolerance is what 0.8's reproduction gate uses.

**Gate:** an injected catastrophic regression is caught on the scheduled CPU job; a too-fine threshold is refused with the documented exit code; the model-card fragment renders on a real HF page.

## 0.8 — QSR v1, reference reports, Inspect runner (citable release)

**Goal:** the citable, reproducible standard.

- QSR v1 frozen: decision rules, CI method, ε-calibrated MDE, per-format runtime and baseline policy, calibrated tolerance, terminology note. CITATION.cff.
- **Three** reference reports on HF — capped at three; reports are versioned to the spec and regenerated only at spec-version bumps, so dependency pin bumps do not invalidate published artifacts (regeneration is the budgeted cost, not an accident).
- A QSR-conformant paired-diff runner built on the Inspect API, in quantfit's own repo; an inspect_evals submission is contingent upside only (their policy requires demonstrated adoption — a merge is an outcome, not a deliverable).
- Launch post led by the actual 0.5/0.6 findings, null or positive.

**Gate:** one reference report reproduced from scratch on a free T4 within the 0.7 tolerance.

## 1.0 — Frozen standard

Spec and schema frozen; dependencies bounded; every advertised command hardware-validated; docs=code parity audit; honest offload wording; CONTRIBUTING and bus-factor docs.

**Gate:** ≥1 third-party reproduction, citation, or gate adoption; two cross-release runs identical on a pinned stack; scripted README-only quickstart passes in a clean venv.

## Non-goals (through 1.0)

No new quantization methods (including sub-4-bit compressed-tensors, AQLM/QuIP#, FP4, QAT, kernels). No AMQ-style learned routing (5–44 GPU-hours per model per AMQ Table 4 — infeasible here). No raw harmful corpora or archived harmful long-form completions without an explicit recorded data-handling decision — never a silent reversal. No harm taxonomy, MoE, ROCm/Apple/Intel breadth, GGUF-production investment, hosted service, or compliance/EU-AI-Act claims. No three-class "degraded" outcome until a validated detector exists. No externally staked numbers from an uncalibrated judge. No per-block safety attribution. No convenience-wedge race against auto-round/Unsloth/Ollama.

## Risks and mitigations

1. **Demand is null, or runs the other way** — the reachable community rewards refusal *removal*, and the sympathetic direction is over-refusal. Mitigation: the instrument measures both directions symmetrically and the R1-1776-style re-censorship case is first-class, not secondary; the 0.5 probe with a pre-committed NO-GO bounds sunk cost before corpus/labeling spend.
2. **Judge error too high or arm-correlated** — all resolution claims are conditional on measured ε by construction; calibration precedes any externally staked number; contingency is a stronger pluggable judge; pinned reports stay interpretable regardless.
3. **A better-resourced actor ships the glue** (promptfoo has an `is-refusal` assertion; Red Hat has the eval capacity). Mitigation: neutrality, the public spec, and the maintainer's paper are assets an in-house self-audit cannot replicate; speed on the 0.5 artifacts.
4. **Hardware cap on fp16 arms** (12 GB VRAM). Mitigation: the same-binary GGUF F16-on-CPU route covers 7–8B; compressed-tensors pairs are capped at ≤3B with the cap stated in every report; features whose gates cannot run do not ship.
5. **Report regeneration burden** — pinning discipline guarantees recurring regeneration. Mitigation: reports capped at three, valid as-of their spec version, regenerated only at spec bumps.
6. **Solo burnout and labeling exposure** — small milestone chunks; labeling scoped and time-boxed with an explicit personal-exposure decision; measurement-layer-only surface; CONTRIBUTING at 1.0.
7. **Upstream churn** (llm-compressor, llama.cpp near-daily releases) — upper-bound pins, weekly runtime canary including the quickstart install path.

## Success metrics

- **Honesty:** every printed number carries a CI and its MDE; nothing derived from an uncalibrated judge ships unlabeled; two consecutive runs identical minus timestamps at every release.
- **0.5 decision quality:** the GO/NO-GO is recorded with named evidence (partners, human-verified flips, independent external signals — mirror-noise downloads excluded), including the pass/fail status of the sensitivity control and, on a failed control, the explicit downgrade of the no-regression leg.
- **Reproducibility:** the 0.8 T4 reproduction lands within the pre-registered tolerance.
- **Adoption by 1.0:** ≥1 third-party reproduction, citation, or gate adoption, and ≥3 independent external signals; every advertised command validated on real hardware.

## Open questions (maintainer decisions)

- Can the Egashira-style injected quantization-conditional regression actually be produced on a ~1B model with the current stack (SCHEMES bottom out at W4) before 0.6's tooling exists, or does the 0.5 mini-control need a simpler surrogate (e.g., a human-confirmed Q2_K-induced flip) as its fallback?
- If 0.4b slips and the 0.5 screen runs on compressed-tensors <=3B only, is a ~10-quant screen in that narrower stratum still a meaningful prevalence bound for the GO/NO-GO, or should the quant count target be restated per-stratum?
- Should the 0.4a/0.4b split get its own line in the Risks section (cross-milestone dependency of the GGUF screen path), or is the stated slip rule in 0.4b sufficient acknowledgment?
