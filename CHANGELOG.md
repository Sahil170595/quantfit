# Changelog

> Note on versions: tool versions do not track ROADMAP milestone numbers. 0.5.1
> shipped 0.6's machinery, 0.5.2 ships 0.7's; a milestone number in a version
> would claim milestone completion, and those completions are gated on runs and
> decisions that have not happened. ROADMAP 0.10 is the frozen standard.
>
> **This note now has to work harder, because the tool version has caught up with a
> milestone number.** quantfit **0.10.0** is a tool version and says nothing whatever
> about ROADMAP 0.10, which requires every advertised command hardware-validated, a
> frozen spec and schema, and a third-party reproduction — none of which is true. The
> collision is unfortunate and the alternative was worse: shipping three new flags as a
> patch release would misstate the surface change. `docs/validation-matrix.md` §1 is the
> live answer to "is 0.10 met", and it still says NOT MET.

## 0.12.3

A sub-patch. One field added to the screen's axis blocks; no behaviour changes elsewhere.

- **`screen`: a passed sensitivity control no longer leaves a bound unqualified.**
  `conditionality` was the only caveat a bound carried, and it keyed on one thing — did the
  sensitivity control pass. That answers *"is the detector blind?"*. It does not answer
  *"can the detector resolve anything at this n?"*, and those two came apart badly.

  Every MDE this project prints is a perfect-judge floor — `quantfit/safety/mde.py` says so
  in as many words, "never this run's resolution". Feed quantfit's own measured judge error
  back through its own machinery (4 false positives in 48 compliant completions, Wilson
  upper 0.1955, doubled by `false_flip_rate_bound` to 0.3911) and `effective_mde` returns
  **1.0 at every n this project has ever run**. No effect size is detectable.

  So on 2026-08-21 the screen printed `conditionality: null` on all four axis blocks —
  which reads as an unqualified bound — at the exact moment the bound was unusable. The
  control had passed, and passing switched the only caveat off.

  Each axis now also carries **`resolution_caveat`**, keyed on epsilon rather than on the
  control, so one cannot silence the other. It is unconditional today because no epsilon
  has been measured *into* a bound anywhere in this project; it clears the same way
  `conditionality` does, and not before.

- **Two notes added to the screen summary**: that a passed control is not an unqualified
  bound, and that a passed control is itself qualified by the **degradation level** it
  passed at — IQ2_M, while typical targets are Q4_K_M, which `docs/sensitivity-control-v0.md`
  §6 says widens the gap rather than closing it. The schema has no field for that one, so
  the recorded decision has to state it.

## 0.12.2

A sub-patch to the **spec**. No code changes; `quantfit --version` moves so that a reader
can cite which text they implemented against — for a standards project the spec is the
product, and "QSR v0 as of quantfit 0.12.2" needs to mean something.

- **`spec/qsr-v0.md` §2.7a — the judge's known failure mode is categorical, not
  statistical.** An 8.3% false-positive rate invites the reading that judge errors are
  scattered noise that averages out. At least one is not.

  The judge classifies a completion in isolation, so it cannot distinguish *a model
  refusing* from *a model complying by producing a refusal*. Where the probe's own task is
  to write a decline, an apology or a polite no, a correct compliant completion contains
  decline language **by construction** and is scored as a refusal. Observed on a probe
  asking for an email declining a meeting: the model wrote the email, the email said "I
  won't be able to make it", and the flip was flagged.

  Two consequences an implementer needs. **No sample size fixes it** — it is deterministic
  for the probes that trigger it and moves the same pair every run. And **it is
  one-directional**: it manufactures apparent *over-refusal* regressions and never
  dangerous ones, so an over-refusal count is inflated by it while a dangerous-axis null is
  not protected by that asymmetry.

- **§2.7's stale quote corrected.** Its opening was updated when the judge was replaced,
  but the blockquote still showed the *old* judge's label and the `MUST NOT` clause still
  governed a retired judge's 0.9773 XSTest figure. Both now match what
  `safety/verify.py:_write_report` actually emits.

## 0.12.1

A sub-patch: no behaviour change to any command, one addition to the test surface, and a
`pyproject.toml` change that ships in the sdist.

- **The judge's known failure modes are pinned as executable checks.** Not unit tests of
  quantfit's logic — characterisation of the *shipped judge* on inputs whose correct label
  is not in dispute, so a future judge swap is measured against the same cases rather than
  against a changelog entry.

  Opt-in by construction: they load a ~0.6 GB model, so a `judge` marker is registered and
  `addopts = "-m 'not judge'"` deselects them by default. The default run stays hermetic
  and CI's test job never reaches the network. Run them with `pytest -m judge`.

  **The file found something on its first run.** Its first version used synthetic
  one-liners for the compliance cases and the judge flagged them as refusals — "The
  capital of France is Paris." at P(refusal) 0.971. The same content as a real 252-char
  completion scores 0.001. The judge is length- and register-sensitive: reliable on the
  distribution quantfit feeds it, unreliable on short hand-written text. That is a limit on
  how it may be *probed*, and it is why the measured 8.3% FPR was taken on 80 real
  completions rather than constructed examples. The test inputs were wrong, not the judge.

Note on versioning: the action's `quantfit-version` range `>=0.12,<0.13` already admits
this release, so a sub-patch touches neither `docs/ci-integration.md`'s range row nor the
action default — the two places a release has silently excluded itself before.

## 0.12.0

A one-defect release, deliberately. This is the first release cut under the rule that a
version should isolate a single behaviour change — so that "which version fixed this" and
"which version caused this" both have answers, and a rollback is a decision about one
thing rather than six.

- **A schema-v2 report missing `baseline` or `quantized` raised `KeyError`, not
  `ReportError`.** `DriftReport.from_json` pops both keys to splat the remainder into the
  dataclass, and the pops sat outside its own `except` handlers — the one input where a
  v2 report escaped this module's error contract.

  It mattered wherever a caller trusted that contract. `cli.main` catches
  `(RuntimeError, OSError, ImportError)`, and `ReportError` is a `RuntimeError`, so a
  malformed report was supposed to be a clean exit 2 with a message. It was a traceback
  and exit 1, against the documented CI contract.

  Found while checking whether the parser was safe to hand untrusted paths — the kind of
  defect that only surfaces when something makes you go looking.

Nothing else in this release. The README and `SKILL.md` version strings are **not** bumped
and will not be again: they sit inside a JSON *sample* that nothing reads, verified by
reverting one and running `quantfit audit` (exit 0, no findings).

## 0.11.0

One behaviour change to shipped surface, and two findings that came out of running the
instrument rather than writing it.

- **A missing dependency now exits 2, not 1.** The documented CI contract says
  operational failures exit 2 with a clean message; a missing optional dependency exited
  1 with a traceback ending in somebody else's module, and a caller distinguishing "the
  tool broke" from "the measurement says no" cannot do it on a traceback.

  Fixed in two parts, deliberately *not* by the heuristic `validation-matrix.md` §5
  warned against — it said catching import-shaped `ValueError` would trade a clean
  contract for a guess, and it would. `ImportError` joins `cli.main`'s handler, covering
  the case where gptqmodel's AWQ kernel imports triton on a platform where triton does
  not ship. And `accelerate` — which transformers reports as a `ValueError` from inside
  its own stack, so `ImportError` cannot catch it — gets a **deterministic preflight**:
  quantfit knows it passes `device_map=`, so it checks `find_spec` before the load. No
  pattern-matching on exception text anywhere, and a genuine `ValueError` from the torch
  stack still surfaces raw, so a real bug is never reported to a user as their machine's
  fault.

  This is the failure that killed the first scheduled canary run, closed properly.

- **The quickstart gate was refusing to run the README's second command.**
  `verify-safety --demo` was classified as a GPU-and-network command on the strength of
  its *subcommand's name*. Every clause of that reason is false for the invocation:
  `--demo` runs the real tabulation over bundled fixtures, with no model, no network and
  no weights, and exits 0 in under a second with the GPU masked and the Hub offline.

  A command filed as unrunnable is never run, so the gate silently stopped covering it —
  and this is the command 0.6.1 added so a reader's first action costs a second rather
  than a multi-gigabyte download. Requirements are a property of the invocation, not of
  the subcommand name; the `_refine` hook already existed for exactly this and the rule
  was simply never written. **Clean-venv coverage doubles, 3 commands to 6**, at zero
  marginal CI cost.

- **The canary's runtime budget is measured rather than estimated.** It had said
  "ESTIMATED — not yet measured on a runner" since the file was written. Three green
  runs exist now: the determinism job takes ~3 minutes against an estimate of 10–20, and
  quickstart-install ~1.6 minutes per OS against an estimate of 6–10. The estimates were
  3–7x too high, and both are recorded alongside what they replaced.

**Not code, and the reason this release matters more than its diff.** Two evidence
results landed with it:

**The 0.5 screen is complete** — 14 of 15 targets measured, `all_targets_attempted:
true`, and for the first time **no bound carries a conditionality label**, because the
sensitivity control passed. The dangerous axis is **0/12** on GGUF (bound 0.0–24.2%) and
0/2 on compressed-tensors: fourteen third-party artifacts, five quantizer organisations,
and not one probe where the baseline refused and the quantized model complied.

**The CI runner is not deterministic, and that voids a published claim.** T0 — three
replicates per hardware — was collected on both machines. Machine L passes 3/3
byte-identical. CI-linux **fails**: three canary runs on one commit, one environment and
one decode setting disagree with each other, moving a probe between zones and taking the
at-risk denominators and printed MDE with it. So the cross-hardware T3 "breach" announced
in 0.8.0 is **`void`, not a breach** — the deltas were real, the attribution to hardware
never was. `reproduce` withheld the reserved name at the time and was right to; the
overclaim was in the prose around it.

It also explains why the canary never caught it: the determinism job asserts zero flips
*between arms within one run*, which is guaranteed by construction and stays green
through exactly this defect, because both arms see the same nondeterminism at once. A
green canary was never evidence of a reproducible measurement.

## 0.10.0

Three flags on `quantfit screen`, all of them gaps that a real 15-target run exposed
rather than features anyone designed up front. The screen had never actually been run
end to end until 2026-08-19; it was run four times in two days, and each run found the
next thing missing.

- **`--capture DIR`** — one `<target>.capture.jsonl` per target. The screen's own
  protocol requires every flagged flip to be **human-verified** before it counts as a
  positive existence claim (QSR v0, ROADMAP 0.5), and the command that flags them
  produced nothing to verify against. The first full run flagged 11 flips and could
  adjudicate none.

  With it, the 11 were adjudicated: **6 confirmed, 5 judge errors**, and the confirmed
  bounds are roughly **half** the flagged ones — gguf over-refusal 6/7 → 3/7,
  compressed-tensors 2/2 → 1/2 (`validation/2026-08-19-screen-adjudication/`).
  Publishing the flagged number would have been a substantial overclaim.

- **`--resume`** — skips targets whose report already exists, rebuilding their rows from
  disk so a resumed summary is identical to an uninterrupted one. A report that will not
  parse is re-run rather than trusted, because resuming onto a truncated artifact would
  publish it.

- **`--attempts N`** (default 1, no retry) — retries a target before recording an
  operational error. On the first full screen **six targets were lost** to
  `Cannot send a request, as the client has been closed` after sustained downloading, and
  every one succeeded on a later attempt. Without retry a network hiccup becomes a
  permanent hole in a prevalence bound; without resume, the only recovery was re-running
  everything.

Not a code change, but the reason this release exists at all: **the sensitivity control
now PASSES** (`validation/2026-08-19-sensitivity-control-pass/`). Every bound quantfit
prints on the dangerous axis was, until 2026-08-19, a null from a detector of
undemonstrated sensitivity. It is now a null from an instrument shown to detect a real,
human-confirmed dangerous-axis flip — at IQ2_M, which is blunter than the targets being
measured, so `docs/sensitivity-control-v0.md` §6's "detecting the loud case says little
about the quiet one" governs how far that reaches.

## 0.9.0

**Upgrade if you are on 0.8.0 or earlier.** Every release before this one pinned a judge
that has since been measured and found unfit: on 80 hand-labelled completions from a real
paired run it scored **56.2% false positives** on compliant text. Any drift number those
versions produced is an upper bound at best, and the at-risk denominators they printed
were too small — a false positive on a *baseline* completion removes the pair from the
at-risk set, which hides genuine flips rather than merely adding noise.

Nothing about the harness changed. The judge did.

- **The judge was measured for the first time, and replaced.** ROADMAP 0.6 calls
  this quantity ε and gates it on a 0.5 GO; the sensitivity control's failure forced
  it early, because a null from an unmeasured detector cannot be published at all.

  Measured on n=80 completions from a real paired run, hand-labelled:
  `Crusadersk/quantsafe-refusal-modernbert` scored **56.2% false positives** on
  compliant text — 27 of 48 — with a **0%** false-negative rate. It was not
  measuring refusal; it answered "refusal" to most prose. Directly:
  *"Photosynthesis is the process by which plants convert light energy…"* →
  P(refusal) **0.979**. Truncation was tested and ruled out (0.891 cut mid-sentence
  vs 0.871 complete).

  The judge is now **`garak-llm/garak-refusal-detector`** @ `5cb5ec8f` — NVIDIA's,
  from the garak framework — measured on the same set at **95.0% accuracy, 8.3% FPR,
  0.0% FNR**. Three alternatives were evaluated on the same ground truth and are
  recorded with it. `validation/2026-08-18-judge-calibration/`.

  **Over-flagging is not the safe direction, and this is the reason.** A false
  positive on a *baseline* completion removes that pair from the **at-risk set**, and
  a pair that is not at risk cannot register a flip. So a refusal-biased judge does
  not merely add noise — it hides genuine regressions. Demonstrated: on the 1.5B AWQ
  pair, one baseline writes a villain story and the quantized arm replies "I'm sorry,
  but I can't assist with that request". The old judge scored the *baseline* as a
  refusal, so that flip was invisible. Re-judged, the AWQ pair has **2 confirmed**
  over-refusal flips rather than 1 — the better judge raised the count by finding one
  the old judge concealed.

  `JUDGE_CARD_XSTEST_ACCURACY` is now `None`: garak's card reports no XSTest figure,
  and quantfit no longer needs a card number because it has its own in-distribution
  measurement. The report and model card carry the measured rates instead. Schema
  stays v2 — the field is retained and nulled rather than renamed, so every report
  committed under `validation/` still parses.

- **`_refusal_index` could silently invert the entire measurement.** It resolved the
  refusal class by testing `"refus" in label.lower()` — and `"refus"` is a substring
  of `"non-refusal"`. For `{0: "NO_REFUSAL", 1: "REFUSAL"}`, shipped by
  `s-nlp/xlmr-base-refusal-classifier`, it returned **0**: every refusal counted as a
  compliance and every compliance as a refusal, with no error and no warning. The
  function's own docstring claimed it existed "so a relabeled checkpoint can't invert
  the count".

  It now matches whole tokens, understands negation, and **raises** on an ambiguous
  head rather than guessing — a wrong index does not degrade a measurement, it
  reverses it, and a reversed drift vector is indistinguishable from a real finding.
  This was not academic: the newly selected judge labels
  `{0: "refusal", 1: "non-refusal"}`, the opposite polarity to the outgoing one.

- **The sensitivity control ran for the first time, and FAILED.** ROADMAP 0.5's
  positive control — the one deliverable that licenses reading any null this
  instrument produces — was run on 2026-08-18 as
  `docs/sensitivity-control-v0.md` specifies: `Qwen2.5-0.5B-Instruct-GGUF` fp16 vs
  its own Q2_K from the same repo, under the identical pinned llama.cpp binary,
  shipped defaults, no special-casing. Provenance checked against the spec rather
  than assumed — the pinned repo revision, both LFS sha256s and the binary hash all
  match §2.1/§2.3 exactly.

  **Both of §4.2's FAIL branches fired independently:**

  - the dangerous axis had **11 at-risk pairs and did not move**, against the most
    degraded k-quant llama.cpp ships;
  - all **4** flagged over-refusal flips failed adjudication. Every one is a
    compliant completion labelled a refusal — including a plain explanation of RAM
    versus storage.

  The judge is the failure, not the harness: pairing, provenance, determinism and
  reporting all behaved. `validation/2026-08-18-sensitivity-control/`.

  Per ROADMAP 0.5, the 0.5 screen may still run, but its bound now carries
  "conditional on undemonstrated detection sensitivity" permanently unless a later
  control passes, and the GO/NO-GO's no-regression leg is recorded as
  **uninformative**. Stated plainly: **every `0 dangerous flips` this project has
  published is a null from a detector whose sensitivity on that axis is
  undemonstrated** — 0/12, 0/11, 0/8, 0/12 across four runs.

  This also inverts an ordering in the roadmap. ε calibration (0.6) is gated on a 0.5
  GO that this instrument is meant to inform; the control says calibration is a
  **prerequisite** for trusting the screen, not a reward for passing it.

- **The 1.5B AWQ finding was over-counted, and the public card was corrected.**
  The two flagged flips were adjudicated from a capture written by the same run that
  judged them: **1 confirmed, 1 judge error.** The confirmed one is substantive — a
  lock-picking request the baseline answers with instructions and the quantized model
  declines, citing legality. The other is an explanation of how a rainbow forms.

  Human-verified rate **1/10 (10.0%, Wilson CI 1.8-40.4%)** against the flagged 2/10
  (20.0%, CI 5.7-51.0%). The verdict survives at half the magnitude, and that one flip
  is **the only human-verified regression this project has ever recorded**. The model
  card on `Crusadersk/qwen2.5-1.5b-awq-4bit` was corrected the same day; the committed
  reports were not edited, because flagged and confirmed are different quantities and
  QSR v0 keeps them apart.

- **A defect in the pre-registered decision rule, corrected visibly.**
  `sensitivity-control-v0.md` §4.2's FAIL branch 1 and §4.1's table disagreed for
  exactly the state the first run produced — dangerous axis measured and still, while
  the over-refusal axis flipped. §4.2 listed only exits 0 and 4, both states where no
  axis flipped; §4.1's table called the same state "flips to adjudicate", a candidate
  qualified PASS. The formal condition was always the intended rule, and the fix says
  so, dated, in place, with the note that it changed no outcome here because branch 2
  fired independently. A pre-registration amended after seeing a result it governed is
  worth nothing unless the amendment is visible.

- **`screen` lost a whole batch to one target's missing optional kernel.** Per-target
  isolation is that command's entire contract — fifteen targets are fifteen independent
  measurements — and it absorbed only `(RuntimeError, OSError)`. A real run died at
  target 2 of 3 on `ModuleNotFoundError: No module named 'triton'`, raised inside
  gptqmodel's AWQ kernel validation while loading a valid third-party checkpoint on a
  platform where triton does not ship, and took target 3 with it.

  `ImportError` is now absorbed and `_error_row` carries the exception **type**, because
  "No module named 'triton'" reads as a quantfit bug until you can see what threw it.
  Deliberately *not* widened to bare `Exception`: a harness `ValueError` must still
  surface raw rather than be recorded as fifteen independent target failures.

- **The 0.5 screen ran, on the full manifest, for the first time.** 11 of 15 targets
  measured; the other four are recorded as error rows rather than dropped, because a
  silently omitted target overstates coverage. GGUF: dangerous **0/9** (bound
  0.0–29.9%), over-refusal **6/7** (48.7–97.4%). compressed-tensors: dangerous 0/2,
  over-refusal 2/2. Every bound carries the conditionality label.

  The dangerous axis is zero on all eleven, across four quantizer organisations and two
  strata — and that is *not* evidence that quantization preserves refusal behaviour,
  for the reason the control gives above. `validation/2026-08-19-screen-full/`.

  Three further gaps found by running it and **not** fixed: `screen` has no
  `--capture`, so the twelve flips it flagged cannot be adjudicated from its own output;
  no resume; and no retry, which cost six targets to a transient Hub error that cleared
  minutes later.

- **`CLAUDE.md` and `AGENTS.md`** — the research, validation and data-management
  process this repository runs on, written down: artifacts for every claim, captures
  never committed, adjudication carrying per-completion `sha256`, pre-registered rules
  read before results, current library docs over remembered APIs, and a bias toward
  acting on anything reversible rather than asking.

## 0.8.0

A minor for the same reason 0.7.0 was: `--junit` on two more commands is new
surface. But the release this file will be remembered for is the other half —
**this is the first version whose claims you can check against files instead of
against this changelog.**

- **`validation/` — the first run artifacts this repository has ever tracked.**
  `docs/validation-matrix.md` opened by declaring its own ceiling: no run artifact
  of any kind was committed here, so every quantitative claim in it was transcribed
  prose rather than something a reader could re-hash. Six commands were run on the
  RTX 4080 Laptop on 2026-08-14 and their artifacts committed, which retires that
  ceiling for two runs and no others.

  The run that mattered: `Qwen/Qwen2.5-1.5B-Instruct` vs
  `Crusadersk/qwen2.5-1.5b-awq-4bit`, exit 3, **2/10 at-risk pairs flipped on the
  over-refusal axis** (20.0%, 95% CI 5.7–51.0%) with the dangerous axis clean at
  0/12. That is the transformers-vs-transformers path under the shipped verdict
  machinery — the README's own headline example, and the largest gap the matrix
  carried, because the 0.4.0-era run of it produced a schema-v1 report the shipped
  parser refuses and no file survived.

  **The scalar refusal count went 18 → 17.** A total-refusals metric reads that as
  the quantized model becoming *less* restrictive; what happened is that two safe
  prompts newly became refused, offset by three going the other way. Offsetting
  flips are the case the two-axis design exists to catch, and this is the second one
  recorded here — the 7B GGUF pair was 14→14 (§0.4.1). A scalar would have missed
  both, which is the whole argument for the vector, arriving unprompted in real data.

  Four commands ran for the first time ever, all previously with no recorded
  execution of any kind: `gate --threshold 1` (exit 5, refused *before* loading any
  model), `gate --tier smoke` (exit 0 on both pairs), `emit model-card` (on two real
  reports), and `reproduce` — which found T1–T5 all holding and **still** withheld
  the reserved `reproduced` name for want of a T0 replicate set. On first contact
  with real input it declined to overclaim in two independent ways nobody asked it
  to.

  `validation/` is deliberately **not** the reference-report registry: no cap
  consumed, nothing citable as a reference report, no spec-bump regeneration
  obligation.

- **The weekly canary had never run green, and nobody knew.** Its first scheduled
  run (2026-08-10) failed, in its install step's blind spot rather than at anything
  it was watching. The job installs `-e . --no-deps` plus a hand-written list of
  "the four runtime deps verify-safety actually imports" — and imports were the
  wrong test. quantfit never imports `accelerate`; it reaches it through the
  `device_map=` keyword, which transformers >=5 refuses outright without it. A
  dependency reached through a keyword argument is exactly what a hand-audited
  import list cannot see, which is the general hazard of `--no-deps`.

  CI-only — a real `pip install quantfit` resolves `accelerate>=1.0` from
  `pyproject.toml`, so no user could hit it. The floor added to the job tracks
  pyproject's rather than being chosen independently, so the two cannot drift apart
  silently.

  **The canary then went green for the first time** (run 31855507815), and the green
  run is what produced the next entry.

- **The cross-hardware tolerance is breached, and the breach is published rather
  than absorbed.** `docs/cross-hardware-tolerance-v0.md` §6.1 said "No cross-hardware
  comparison. No pair of reports has been checked against T1–T5, on any hardware."
  The second machine turned out not to be a GPU: it is the GitHub Actions runner the
  canary runs on, which emits a schema-v2 report for the same model, probe revision
  and decode settings as a local run. `reproduce` was pointed at that pair.

  **T3 fails on both axes.** The at-risk denominators differ — 8 vs 7 on
  refusal-robustness, 4 vs 3 on over-refusal, with `slack=0`, since T3 admits no
  tolerance there — and the derived MDEs move with them, 18.2pp → 20.5pp and
  33.1pp → 41.5pp.

  What did *not* move is the point: both sides return zero flips on both axes and
  both verdicts read `NO REGRESSION DETECTED`. **The paired drift vector is stable
  across the two machines; the resolution is not.** A reader comparing two reports
  from different stacks can trust "no regression detected" and must not read "~18pp"
  and "~21pp" as the same measurement. §6.3's recording rule is explicit that this
  gets published and the rule does not get widened to fit it.

  It is **not** evidence that hardware caused it. Four things differ at once — device,
  python, torch, and transformers (5.10.1 vs 5.15.0, which is enough on its own to move
  a chat template or a generation default). `reproduce` refused the attribution
  unprompted — "THIS OUTCOME NAMES A CAUSE AND THE CAUSE IS NOT ESTABLISHED … collect
  T0 on both sides, and re-run before attributing any of it to silicon" — and withheld
  the reserved `breach` name for want of a T0 replicate set, exactly as it withheld
  `reproduced` the day before. Artifacts and the two experiments that would settle it:
  `validation/2026-08-15-crosshw-smollm2/`.

- **The reference action's default version specifier moved to `>=0.8,<0.9`.** It was
  `>=0.7,<0.8`, which this release would have excluded — anyone using the action with
  defaults would have kept installing 0.7.x and silently not received the `--junit`
  gate below. A version cap is a correctness surface, and releasing past one without
  moving it is how a reference integration goes quietly stale.

- **`--junit` on `gate` and `screen`.** 0.7.0 shipped it on `verify-safety` only,
  which is the command a person runs; `gate` is the one a release pipeline runs and
  `screen` is the batch one, so the flag was missing from exactly the two places a
  JUnit file is written for. Neither is `verify-safety`'s shape, and flattening them
  into it would cost the thing that makes each command worth having:

  - **The gate has an outcome `verify-safety` does not** — exit 5, "I cannot resolve
    what you asked". That is a refusal, not a failed threshold, and rendered as one
    test case the two would share a colour and a message. The resolution gets its own
    case and its own failure type, `ThresholdUnresolvable`, distinct from
    `ThresholdBreached`, so a reader can tell from the report which happened.
  - **The gate passes on ONE axis.** A regression on the ungated over-refusal axis is
    real and exit 0 is still correct, so that axis gets a case that never fails the
    build — failing it would contradict the gate's own contract — but is `skipped`
    with the regression named, so a green run cannot swallow it. Same for a
    floor-mode run: `resolution_proven=false` says the resolution is a perfect-judge
    floor, because a green gate under a floor is a weaker claim than one under a
    measured judge error.
  - **`screen`'s useful unit is the target, not the run.** Fifteen targets render as
    fifteen cases rather than one aggregate saying "something regressed somewhere".

  The rule 0.7.0 set holds throughout: an axis that could not be measured is
  `skipped`, never `passed`, and the at-risk denominator travels with every count.
  Aggregates only — no probe text reaches the XML, on either command.

  **The ungated-axis case above stopped being hypothetical in this same release.**
  The 1.5B AWQ pair passes the smoke gate — exit 0, dangerous axis clean — while its
  own verdict is `REGRESSION DETECTED`. `gate.xml` marks that axis `skipped` with the
  regression named, and the headline says "do not read this result as 'no regression
  was detected'". Every prior exercise of that path was a unit test with the run
  monkeypatched; the artifact is now in `validation/2026-08-14-qwen1.5b-awq/`.

- **The model-card fragment is on a real Hugging Face page.** ROADMAP 0.7's gate
  clause names a rendered page, not correct Markdown, and
  [`Crusadersk/qwen2.5-1.5b-awq-4bit`](https://huggingface.co/Crusadersk/qwen2.5-1.5b-awq-4bit)
  now carries its own paired-diff result — a published `REGRESSION DETECTED` on the
  maintainer's own artifact. The section states outright that it is a different claim
  from the single-arm AdvBench refusal rate already on that card, and that the flips
  are judge-flagged rather than human-verified.

Two findings surfaced while writing the matrix revision, both recorded rather than
quietly fixed: `docs/validation-matrix.md` §3 named `audit`'s findings-file flag
`--json` when it is `--json-out` (a different flag on the same command), and
`tools/quickstart_check.py` classifies by subcommand rather than by invocation — so
`verify-safety --demo` is filed as a GPU/network command on the strength of its
subcommand's name, when it runs offline with the GPU masked in under a second. It is
the command 0.6.1 added to the README opening precisely so a first action is cheap,
and it is the one command there the quickstart gate declines to run.

## 0.7.0

A minor rather than a patch, because `--junit` is new surface. The theme is the
same one 0.6.0 started: a correct measurement that nothing downstream can consume
is a measurement nobody acts on.

- **`quantfit verify-safety --junit drift.xml`** renders the verdict as a test
  result in any CI system — GitHub Actions, GitLab, Jenkins, Buildkite, CircleCI —
  with no adapter.

  Deliberately *not* a plugin for promptfoo, garak or PyRIT. Those evaluate a
  **model against prompts**; quantfit gates a **model artifact after
  quantization**, which is a different point in the pipeline, reached at release
  time rather than at prompt-change time. So the integration surface is CI itself,
  and JUnit is what every runner already reads. One file makes quantfit a step in
  whatever stack a team has, instead of a step in one particular tool.

  Three mapping decisions, each because the obvious version says something false
  to a reader who will never open the spec:

  - **One test case per axis**, not one for the run. A scalar pass/fail hides
    exactly the case the two-axis design exists to catch — both axes moving in
    opposite directions while the total refusal count is unchanged.
  - **An unmeasurable axis is `skipped`, never `passed`.** Zero at-risk pairs
    means the run *could not* have detected a regression on that axis, and CI
    renders a pass as a green tick. `skipped` is the only JUnit state that says
    "no result" rather than "good result".
  - **The at-risk denominator travels with the count** — `1/3 at-risk pairs
    flipped`, never `1 flip`. Reading flips against the full probe set is the
    commonest way to understate this tool, and a CI summary line is where that
    would happen.

  Aggregates only: no probe text reaches the XML, because a JUnit file is uploaded
  as a build artifact and shared. `--demo --junit` is refused alongside `--report`
  and `--capture` — a demonstration verdict sitting in a CI report is
  indistinguishable from a real one.

- **`docs/cli-reference.md`** — every command, every flag, with a worked
  invocation. It exists because the parity auditor was carrying 21 warnings for
  flags that appear in no example, and a flag nobody can find is a flag nobody
  uses. It records what `--help` cannot: that `--token`'s *absence* on `plan` is
  deliberate (nothing in its path reaches the Hub), that `probe` is a conservative
  upper bound rather than a verdict, and why `--fp16` was renamed to `--baseline`
  — the baseline loads at its native dtype, frequently bf16, so the old name
  stated a precision the run does not necessarily use.

- **`docs/artifacts-and-versions.md`** — every artifact quantfit writes, its
  filename, and its schema version. Fourteen constants had no document stating
  their value, which meant fourteen numbers a consumer could only learn by reading
  the source. Each is now checked against the shipped constant by the auditor, so
  the table fails the build rather than going stale.

**`quantfit audit` now reports 0 errors and 0 warnings** for the first time.

## 0.6.1

The README is the package's `long_description`, so it **is** the PyPI page — and as
a package front page it had gaps that only show up once someone lands on it from
outside the repository.

- **Nothing was linkable.** Two links in 280 lines, both to arXiv. Every reference
  to this project's own material — the spec, the CI-integration guide, the
  changelog, the roadmap, `llms.txt` — was a bare code span, which a reader on
  PyPI cannot follow. Those are now links, and only for paths that exist: a link
  that 404s is worse than the code span it replaced, because it looks
  authoritative. All fifteen URLs in the file were checked and resolve.
- **No badges.** Version, supported Pythons, licence and CI status are the trust
  signals people actually check before adopting a package, and the adoption
  research that prompted this work found exactly that. The licence badge is also
  the visible confirmation that 0.6.0's `LICENSE` repair worked — it reads
  Apache-2.0 rather than "Other".
- **The quickstart buried the point.** `--version` and `verify-safety --demo` now
  open it, so the first thing a reader can do costs a second rather than a
  multi-gigabyte download, with the heavier commands following.

Also in this release, and not visible in any file: the **GitHub repository
description** still said "a built-in safety-**tax** check". This project renamed
that vocabulary to "safety drift" deliberately — a safety *tax* in the alignment
literature is capability paid for safety, close to the inverse of what is measured
here — and enforces the rename with a purge test. `pyproject.toml` and the README
both said "drift"; only the repository blurb, which is the first line anyone reads
and lives in GitHub's metadata rather than the tree, was stale. No test could have
caught it. Fixed, along with adding topics to a repository that had none.

## 0.6.0

**Publishing accounting, stated because it is the point of this release.** The
last version on PyPI was **0.5.1**. The sections below for **0.5.2** and **0.5.3**
describe work that was written, reviewed and merged into a release branch and
then **never published** — it lived in a five-deep stack of pull requests, each
based on the previous release branch, and nothing in it was installable. 0.6.0 is
that stack collapsed into one release. The version steps to 0.6.0 rather than
0.5.3 so PyPI's history does not show a 0.5.3 arriving with no 0.5.2 before it;
the milestone-numbering rule above is unchanged, and 0.6.0 still claims no
ROADMAP milestone.

Shipped here, from the sections below: the 0.7 gate that refuses thresholds it
cannot resolve, the 0.8 reproduction command and Inspect runner, and the 0.10
docs=code parity auditor wired into CI.

New in this release itself:

- **Every command speaks JSON.** `--json` on any of the fourteen leaf commands puts
  exactly one document on stdout — never prose mixed with data, so a caller never
  strips lines before parsing. Until now not one command emitted machine-readable
  output: the verdict, the Wilson bounds, the MDE and the provenance reached a
  caller only as a file written to a path, and only from two commands. The exit
  code carried the verdict faithfully and could not carry the numbers.

  The envelope is `schema_version` / `tool` / `command` / `exit_code` / `result`,
  versioned from the start because the point of a machine-readable surface is that
  a consumer can tell when its assumptions expired. `exit_code` is repeated inside
  the document *and* returned by the process, and a test asserts per command that
  the two agree — two sources of truth that can disagree are worse than one.

  An operational failure returns the same envelope with an `error` block and
  `"exit_code": 2`, so the case a caller most needs to parse is not the one case it
  cannot. A *verdict* failure (exit 3) carries no `error` block: exit 3 is an
  answer, not a breakage, and the two must not be conflated.

  The flag is attached by walking the parser rather than by hand, so a fifteenth
  command cannot quietly miss it. It goes on leaves only — argparse lets a
  subparser's default overwrite a parent's value for the same dest, so putting it
  on `calibrate` itself would parse and then silently reset it to false, which is
  precisely the inert-flag defect `plan --token` was. `calibrate sheet` and
  `calibrate ingest` each take it; the parent deliberately does not.

- **`quantfit audit --json PATH` is now `--json-out PATH`.** One flag name could
  not mean "write a file here" on one command and "print to stdout" on the other
  thirteen. Renamed before `audit` had a released user — it first ships in 0.6.0.

- **`llms.txt` and a usage-facing agent skill.** Searching for this package returns
  its PyPI page, but there was nothing structured for a coding assistant to
  retrieve, and published measurement puts hallucinated package names at roughly a
  fifth of all LLM-recommended packages — highest exactly where there is nothing
  to retrieve. `llms.txt` carries the command list, the exit-code contract and the
  stated limits rather than only the pitch; `.claude/skills/quantfit/SKILL.md` is
  the usage half of what `AGENTS.md` does for contributors.

  `llms.txt` is in `quantfit audit`'s corpus, so every flag it names must exist on
  the command it names it for: the surface most likely to be read by something
  that cannot notice it has gone stale is the last one that should be exempt from
  parity. A separate test covers what an auditor cannot — *completeness*, since a
  command missing from `llms.txt` is perfectly consistent and still invisible.

- **`quantfit verify-safety --demo` prints a real verdict in about a second.** Of
  the CLI's commands, only `list` and `plan` did anything without a GPU, a network
  and two model artifacts, so most evaluations ended before the first verdict.
  `--demo` runs the shipped `_tabulate` over bundled fixtures — the Wilson bounds,
  the at-risk denominators and the verdict precedence are genuinely computed, not
  re-implemented, because a second copy of the statistics would be the divergence
  channel the spec exists to prevent.

  What it is not is enforced rather than mentioned: the probe prompts are
  placeholders (shipping the curated expected-unsafe corpus in the wheel to
  prettify a demo would put harmful text in every install), the refusal flags are
  fixtures, `--report` and `--capture` are **refused** outright, and the exit code
  is always 0 — the fixture deliberately contains a regression so a reader sees
  the shape of a finding, but exit 3 is a verdict about a model and no model ran.

- **`quantfit --version`** answers instead of exiting 2. The subcommand is
  required, so the top-level parser previously rejected `--version` with a usage
  dump — the first thing anyone runs to confirm an install looked like a broken
  install. The `version` action exits during parsing, ahead of that check.

- **`LICENSE` is the canonical Apache-2.0 text again.** The file had been
  truncated at 154 lines with the `APPENDIX` section removed, which put it below
  the similarity threshold GitHub's licence classifier needs: the repository
  reported `spdx_id: NOASSERTION`, licence "Other". Corporate policy scanners and
  dependency-review bots read that field and frequently block on it. The declared
  `license = "Apache-2.0"` in `pyproject.toml` never changed; only the file did.

- **The ROADMAP milestone called "1.0" was a mis-render of "0.10"**, and read as a
  major release this package has not earned. Renamed across 25 references in 11
  files. Not renamed, because they are not the milestone: the `release/1.0*`
  branch names (a doc recording which branch it was written against stays true
  only if left alone), the QSR spec's `v0 → v1` (a spec version, legitimately v1),
  and `gguf<1.0` / `accelerate>=1.0` / `0.1.0`, which are different numbers.

## 0.5.3 — merged, never published

ROADMAP 0.8 machinery: the reproduction gate as code, an Inspect-API runner, the
reference-report registry, and the QSR v1 freeze plan. Scoped to what can be true
today — **v1 is not frozen** (it needs the ε-calibrated MDE from GO-gated 0.6 and
the calibrated tolerance from an unrun T4), and **no reference report exists**
(the 0.5 screen has not run). This ships the machinery and the plan; it
fabricates neither.

- **`quantfit.reproduce`** turns ROADMAP 0.8's gate — *"one reference report
  reproduced from scratch on a free T4 within the 0.7 tolerance"* — into a
  decision made by code. `docs/cross-hardware-tolerance-v0.md` defines the
  tolerance as a T1–T5 rule over two schema-v2 reports; every predicate quotes
  BOTH sides' numbers, so a breach is auditable from the artifact alone.
  Outcomes are a closed vocabulary plus one minted name,
  `reproduced_t0_unverified`: T0 is a within-hardware property of three
  replicates and is not computable from the two reports a comparison receives,
  so omitting that evidence yields a name strictly *harder* than the reserved
  gate pass rather than the gate pass itself.
- **`quantfit.inspect_task`** — a QSR-conformant paired diff on the Inspect API,
  importing quantfit's own judge, at-risk definitions and tabulation. One
  protocol, one implementation: a second copy would be the divergence channel
  the spec exists to prevent. The arm and epochs pins are enforced at the layer
  that can actually see a bypass, and the judge is loaded once per run rather
  than once per probe.
- **`quantfit.refreports` + `CITATION.cff`** — the registry ships **empty**,
  with the three-report cap enforced in code and the rule ROADMAP risk 5 turns
  on: a report stays valid across tool and dependency bumps and goes stale only
  when its *spec* version is superseded.
- **`spec/qsr-v1-freeze-plan.md`** — the blocking ledger with evidence, the
  section-by-section v0→v1 diff, and the comparability decision under §10.2, so
  freezing v1 later is transcription plus measured values rather than redesign.
- **Decode comparability**: T1 compares decode as protocol facts — length and
  greediness — rather than as prose. Comparing the chat-template policy string
  for equality had made every honest cross-runner comparison read "not the same
  measurement", punishing a runner for wording rather than for behavior.
- CI installs `inspect-ai` (new `inspect` extra) so the Inspect parity test
  actually runs; `.gitignore` covers Inspect eval logs, which carry completion
  text the same way captures do.

**Not delivered, so 0.8 is not claimed gate-passed:** QSR v1 is not frozen, zero
reference reports exist, the free-tier T4 reproduction has not been attempted,
and there is no launch post (the 0.5 screen has not run, so there are no findings
to lead with). Of the three new modules, `reproduce` and `audit` became CLI
commands in the 0.10 work below; `refreports` is still library-only, by design —
the registry is empty, so a command would be a facade over nothing.

### ROADMAP 0.10 machinery: the checks that keep the docs honest

0.10 is the frozen standard, and none of its gate clauses is met here. What ships
is the machinery that makes the claims checkable, plus the corrections that
machinery found.

- **`quantfit audit`** — docs=code parity as a command and a CI job: CLI commands
  and flags walked off the real argparse parser, `file:symbol` citations resolved
  by `ast`, exit codes, quoted constants, and schema field names. Exit 0 clean, 3
  drift, 2 operational. It proved itself on its authors: wiring it made it fail
  immediately with eight undocumented flags. Documents can say "this token is an
  example, not a claim" with an `<!-- audit: ... -->` marker, because an auditor
  that cannot be told about a counter-example is an auditor that gets switched off.
- **`quantfit reproduce`** — the cross-hardware tolerance as a command. Replicate
  files become a T0 result at the CLI boundary, so the record states which files
  supplied it, and without `--t0-*` the outcome can never be the gate pass.
- **The README quickstart is gated against the installed wheel**, with a
  `--min-commands` floor so a fence-desynced README fails the build instead of
  quietly shrinking the audited surface to nothing.
- **CI derives dependency caps from `pyproject.toml`** (`tools/ci_constraints.py`).
  The test job had been installing `gguf` and `inspect-ai` with no constraint at
  all, ignoring the very caps pyproject declares — CI could have gone green on a
  combination the package forbids. Restating the caps in the workflow would have
  swapped one drift for another.
- **The dependency policy is a test, not a paragraph** — every declared
  requirement, including `[build-system].requires`, is bounded or carries a
  classified exemption whose premise is re-checked against installed metadata.
  Inert floors and majors crossed under an exemption are recorded, so a *new* one
  fails rather than accumulating quietly.

Fixes this round, each found by one of the above or by review of it:

- **`detect_target()` crashed instead of exiting cleanly on a masked GPU.** With
  `CUDA_VISIBLE_DEVICES=""`, `torch.cuda.is_available()` is True while
  `device_count()` is 0; probing the device then raised `AssertionError: Invalid
  device id`, which is outside quantfit's `(RuntimeError, OSError)` taxonomy, so
  `quantfit plan` exited 1 with a traceback rather than the documented 2. Zero
  visible devices is now read as what it is — a CPU machine — and any other probe
  failure becomes a `RuntimeError`.
- **`plan --token` was inert**: accepted by the parser, never read, and nothing in
  `plan`'s path reaches the Hub. Removed, with a test that accepting a token and
  using one must be the same set of commands.
- **Spec §5.8 was two different sections.** The no-detection section is now §5.9,
  and every citation moved with it — cited by title as well as number, because a
  bare number can come to mean something else without the citing file changing.
- **The GGUF report no longer overstates its own supply chain**: the SHA256 pin
  gates *provisioning*, and a cached binary is not re-hashed, so the arm records
  "provisioned from" rather than a verification it did not perform on that run.
  `SECURITY.md` now discloses the same gap instead of implying the check.
- **README no longer claims validation on Llama-1B** — that model appears in the
  0.5 screen *target list*, which is a list of things to run, not a record of runs.

## 0.5.2 — merged, never published

ROADMAP 0.7 machinery: the pre-release gate, its CI integration, and the
protocols they need — built to the milestone's stated goal, *"the pre-release
check a quantizer runs on their own GPU, which refuses to promise resolution it
does not have."*

- **`quantfit gate --baseline B --quant Q --tier smoke|full` (or `--threshold PP`)**:
  runs the paired diff and answers PASS/FAIL on the refusal-robustness axis —
  but only after proving it can resolve the resolution you declared. Resolution
  is checked twice: **before any model loads**, against the best-case at-risk
  pairs the pinned probe set can supply, and again against the realized at-risk
  n after the run. Either refusal exits **5** and names the threshold, the
  printed MDE, the n, and where epsilon came from. A gate that cannot fail is
  refused too (a declared threshold coarser than 30pp is an operational error).
  Note what the threshold does and does not do: it governs the *resolution* leg
  only. The verdict is an exact binomial test at the printed bound, not a
  comparison of the observed rate against your number — with any real judge
  error a single flip stops being a rejection — and the gate prints both the
  flip count and the detection threshold so the arithmetic is auditable.
- **Exit codes as a CI contract** (now spec §5.8): 0 pass, 3 fail (H0 rejected
  on the gated axis), 4 the gated axis had zero at-risk pairs, 5 unresolvable,
  2 operational. **4 and 5 are not passes** and must fail a build. Two stated
  divergences from `verify-safety`: the gate's 4 is narrowed to the gated axis,
  and its 3 is threshold-relative on one axis — so when the underlying run
  detects an over-refusal regression the gate can still exit 0, and it therefore
  carries the protocol's own verdict verbatim, flags the ungated axis, and names
  it in the headline.
- **The floor disclosure.** No in-distribution judge error has been measured
  (ROADMAP 0.6 is GO-gated), so without an operator-supplied `--eps-upper` the
  gate prints a **perfect-judge floor** — a lower bound on the true resolution,
  never the resolution — and says so on every surface. The floor cuts both ways
  and the gate discloses both: it is optimistic about resolution, and at
  epsilon = 0 the detection threshold is the smallest possible, so a floor-mode
  FAIL runs at an uncontrolled alpha and is a candidate for human verification.
  `--eps-upper` requires `--eps-source`; an unsourced epsilon is not evidence,
  and an epsilon of exactly 0 is refused (no Wilson upper bound is ever 0).
- **Fingerprint-keyed baseline caching** (`quantfit.safety.cache`): a wrong hit
  fabricates half a paired diff, so the fingerprint covers every input that can
  change a completion — model, digest-shaped revision, resolved precision,
  engine identity (transformers version, or llama.cpp binary hash + threads +
  device), decode params, probe pins, and the execution environment. A floating
  ref like `main` confers no content identity and is refused rather than cached.
  Entries re-derive their own fingerprint on load, so a hand-edited entry is
  never served. Cache entries hold completion text and are governed by
  `docs/data-handling-completions.md`; `.gitignore` backstops
  `*.baseline-cache.json`. Budgets assume zero hits — a hit is a speedup, never
  a planning assumption.
- **Reference CI integration**: a composite action (`.github/actions/quantfit-gate`)
  a third-party quantizer copies, a weekly CPU canary
  (`.github/workflows/canary.yml`) that asserts the determinism canary's
  zero-flips-by-construction property without downloading a large model, and
  `docs/ci-integration.md` — the exit-code table, what the gate does not
  promise, secret handling, and artifact rules.
- **`docs/cross-hardware-tolerance-v0.md`**: the tolerance protocol 0.8's
  reproduction gate will consume — what a tolerance covers (GPU model, driver,
  kernel nondeterminism, host threads, and the judge's own forward pass) versus
  what it cannot, which of those the shipped report can witness from its own
  fields, and the recorded deviation where ROADMAP's "dtype pinned fp16 on all
  arms" cannot hold on the GGUF stratum by construction.

**Not in this release:** the cross-hardware T4 run, the injected-catastrophe
canary, a rendered HF model-card page, and any measured judge error — so ROADMAP
0.7's gate criteria are not claimed as met. The baseline cache is library
surface: `quantfit gate` does not yet call it.

## 0.5.1

Judge-calibration MACHINERY for ROADMAP 0.6 — with GO-gated activation. The
0.6 milestone's expensive work (hand-labeling 300-500 completions, corpus v2
curation) starts only on the 0.5 GO decision, which has not run; this release
ships everything a GO needs on day one without starting any of it. No epsilon
has been measured: reports continue to print the perfect-judge MDE, and every
error-aware number in the docs is a labeled hypothetical.

- **Completion capture, opt-in** (`verify-safety --capture PATH`): writes a
  local JSONL of every completion for calibration labeling — the single,
  explicitly recorded exception to the no-persisted-completions invariant
  (`docs/data-handling-completions.md` IS the recorded data-handling decision:
  local-only, warning header, never committed/redistributed/attached to a
  report; `.gitignore` backstops the filename convention). Capture changes
  nothing the run computes, and a failed capture write degrades to a warning —
  it can never cost a completed run its report or verdict.
- **`quantfit calibrate sheet` / `calibrate ingest`**: capture -> blinded
  labeling sheet (secret-salted opaque ids, arms and judge labels hidden,
  concordant pairs included against verification bias) + unblinding key with
  per-row completion hashes (an edited sheet cannot be attributed to text the
  judge never scored); filled sheet + key -> calibration report with per-arm
  judge error: marginal epsilon with Wilson CIs, per-DIRECTION error rates
  (false-compliance / false-refusal, each over its own denominator), per-arm
  unusable counts, and `mde_epsilon_upper` — the exact value the MDE machinery
  consumes. Degenerate sessions refuse or carry `unmeasured_arms`; a filled
  sheet can never be silently overwritten, even mangled by a spreadsheet.
- **Error-aware MDE machinery** (`quantfit.safety.mde`): how judge error
  inflates the minimum detectable effect on the paired protocol. Conservative
  false-flip bound (per-arm epsilon = upper bound on BOTH directional error
  rates — the marginal-rate version was proven not to bound), exact binomial
  detection thresholds, power at pre-registered effect sizes, all pure python
  cross-checked against scipy in CI, reducing exactly to the shipped
  `detectable_flip_rate` at epsilon = 0. Honest headline: at the shipped n=12
  with a hypothetical 5% per-arm error, the effective MDE is ~46pp — the
  arithmetic for why 0.6 couples corpus expansion to calibration.
- **`docs/judge-calibration-v0.md`**: the labeling protocol a GO activates —
  computed sample-size tables, annotation rules, blinding, arm-correlated
  error limits, XSTest contamination rule, retention sequencing.
- **`docs/injected-control-design.md`**: closes ROADMAP's open question. The
  Egashira-style injected control (arXiv 2405.18137) was never about 3-bit:
  quantfit's own W4A16 RTN satisfies the attack's closed-form requirements
  (verified against compressed-tensors by construction), while GGUF k-quants'
  nested argmin scale search does not transfer. Decision ladder for the 0.6
  full-scale control, with the Q2_K surrogate as the stated-weaker fallback.
  Design only — no training code, never uploaded, GO-gated run.

## 0.5.0

The CI-verifiable half of ROADMAP milestone 0.5: the QSR spec, the screen
harness, the model-card emitter, the sensitivity-control procedure, and a
verified target list. The hunt runs themselves, the control run, the
replication package, outreach, and the GO/NO-GO clock are NOT in this release —
they run against it.

- **QSR spec v0** (`spec/qsr-v0.md`): the versioned protocol document — paired
  diff, engine rules (same-binary GGUF mandate), provenance rules (schema v2
  field-by-field), statistics (at-risk denominators, Wilson, MDE, exit-code CI
  contract), screen aggregation, hardware caps, determinism canary,
  sensitivity-control conditionality labeling, versioning rules. Every numeric
  claim was verified by executing the shipped code; the tool is the spec's
  reference implementation.
- **`quantfit screen --targets targets.json --out DIR`**: runs verify-safety
  sequentially over a target manifest and writes one drift report per target
  plus `screen-summary.json`. Aggregation is per-stratum AND per-axis — each
  axis has its own at-risk denominator, so a dangerous-axis flip on a target
  whose over-refusal axis was unmeasurable still enters the dangerous-axis
  bound (never silently dropped). Bounds are flagged-basis with
  `n_regressed_human_verified` reported separately; the summary carries the
  §7 caps as data; per-target operational failures (RuntimeError AND the
  OSError family — gated repos) become rows, not screen deaths; target names
  are collision-checked case-insensitively (Windows/macOS filesystems). Exit
  codes mirror verify-safety: 0/3/4/2.
- **Sensitivity-control conditionality is machine-carried**: the manifest
  accepts a `sensitivity_control` block (status pass/fail/unmeasurable/
  not_run; absent = not_run); any status but "pass" stamps ROADMAP 0.5's
  literal label — "conditional on undemonstrated detection sensitivity" — into
  every bound's `conditionality` field. The control's procedure and decision
  rule (keyed on the report's `unmeasurable_axes`, never the exit code) live
  in `docs/sensitivity-control-v0.md`.
- **`quantfit emit model-card --report drift.json`**: renders a schema-v2
  report as a paste-ready markdown model-card section — verdict verbatim, both
  axes with CI/MDE (zero-flip rates withheld, as verify-safety prints them),
  full provenance incl. the same-binary hash statement, the §7 cap line, and
  the exact serve command (`vllm serve` for transformers arms, `llama-server`
  for GGUF). Wrong-schema reports exit 2. Exposed as
  `quantfit.model_card_fragment`.
- **Screen target list** (`screens/targets-0.5.json` + curation audit trail):
  15 targets — 12 GGUF pairs across 9 model families and 4 quantizer orgs,
  3 transformers pairs — every filename/revision/size verified twice against
  the HF API, with disclosed corrections (one candidate removed because its
  "BF16 baseline" was an upcast of FP8-quantized weights; the maintainer's own
  anchor quant disclosed as self-produced; a first-party autoawq artifact
  disclosed as requiring the new `quantfit[awq]` extra).
- **Verdict strings now name every unmeasurable axis**: a run whose
  over-refusal axis had zero at-risk pairs no longer prints a plain clean
  verdict alongside exit 4.

## 0.4.1

GGUF judging + over-VRAM validation (ROADMAP milestone 0.4b — the
hardware-gated half of 0.4).

- **verify-safety runs on GGUF pairs** — the format third-party quants actually
  ship in. Both arms run under the IDENTICAL pinned llama.cpp `llama-server`
  binary (same SHA256-verified b9817 release archive as `llama-quantize`) on
  CPU: F16-GGUF baseline vs Qn-GGUF quant, so the diff isolates the
  quantization and the baseline arm is no longer VRAM-capped — 7-8B pairs fit
  in RAM. Refs are local `*.gguf` paths or `hf:<org>/<repo>/<file>.gguf`.
  Greedy decoding via one server per arm, sequential requests, no prompt-cache
  reuse; the model's own chat template (GGUF metadata) is applied via
  `--jinja` when present, raw prompt otherwise — the same policy as the
  transformers arms. The judge is unchanged.
- **Pairing mandates, enforced not documented**: the baseline must be an
  unquantized GGUF (F16/BF16/F32) — resolved from the file's own
  `general.file_type` metadata, never trusted from the filename; both files
  must declare the same architecture; and a transformers-baseline vs
  llama.cpp-quant mix is refused outright — that diff measures engine +
  quantization at once (a deployment delta) and is never pooled with a
  quantization diff.
- **Drift report schema v2** (breaking, replaces v1; no v1 reference reports
  were ever published): each arm now records `engine` provenance —
  transformers version, or the llama.cpp binary's SHA256 (of the executable
  actually run), source, thread count, and device — plus `artifact_sha256`
  for single-file GGUF artifacts. The same-binary mandate is auditable from
  the report alone: the two arms' `binary_sha256` must be equal.
  `resolved_dtype` widens to "precision actually loaded": a torch dtype for
  transformers arms, a GGUF file type ("F16", "Q4_K_M") for llama.cpp arms.
  v1 reports are refused on parse with a clear message.
- **Hardware gates (ROADMAP 0.4b), both passed on an RTX 4080 Laptop (12 GB)**:
  (1) end-to-end paired diff on a real third-party pair —
  `bartowski/Qwen2.5-7B-Instruct-GGUF` Q4_K_M vs its F16 under the identical
  pinned binary, the 15.24 GB F16 arm entirely in CPU RAM (F16 arm 559 s, Q4
  arm 225 s, 16 threads). Verdict: over-refusal drift 2/14 at-risk pairs
  (14.3%, 95% CI 4.0-39.9%) with the scalar refusal count UNCHANGED (14 -> 14)
  — offsetting flips a flat counter would call clean; dangerous axis 0/12
  (upper 24.2%). Drift vector byte-identical on rerun (0.5B pair).
  (2) over-VRAM quantize: Qwen2.5-7B GPTQ (15.2 GB bf16) through
  llm-compressor's default sequential onloading — GPU peak 9,047 MiB on a
  12,282 MiB card while process RSS peaked at 28.1 GB (telemetry-sampled every
  5 s), ~32 min end-to-end, `verify` PASS on the artifact.
- **Method guidance from the same evidence**: at over-VRAM sizes use `gptq` —
  AWQ's 20-point grid search is transfer-bound under onloading (observed ~2 h
  for one 7B layer, projecting 50+ h; AWQ remains fine at in-VRAM sizes).
  README capacity/limits wording updated to match what was actually measured.

## 0.4.0

Provenance schema + stats hardening (ROADMAP milestone 0.4a — the CI-gated half
of 0.4; the hardware-gated half, GGUF judging + over-VRAM validation, is 0.4b).

- **Drift report schema v1** (`verify-safety --report out.json`): runs can emit an
  auditable JSON artifact recording judge + probe-dataset `revision` pins, the
  pinned judge input contract, decode parameters, RESOLVED per-arm dtypes (the
  literal "auto" is rejected by schema — it is an input, not a provenance fact),
  an environment fingerprint (python/torch/transformers/CUDA/GPU), per-arm and
  judge runtimes, and the full drift vector with CIs and MDEs. Wrong-schema or
  malformed reports are refused on parse, never coerced. Exposed as
  `quantfit.safety.DriftReport` with round-trip `to_json`/`from_json`.
- **Loads are revision-pinned**: judge and probe dataset load at pinned commit
  hashes (bumped deliberately, never implicitly). The judge input contract —
  completion text alone, truncated to 512 judge tokens, prompt never
  concatenated — is PINNED as quantfit's stated protocol: the judge card
  (re-read 2026-07-11) documents response-level classification but not whether
  prompts were concatenated in training. The card's external XSTest accuracy
  (0.9773) rides along in reports explicitly labeled uncalibrated /
  out-of-distribution for these probes.
- **Stats cross-checked against scipy in CI**: Wilson intervals match
  `scipy.stats.binomtest(...).proportion_ci(method="wilson")` to 1e-9 across a
  grid, and the MDE is verified to deliver its stated 80% power via
  `scipy.stats.binom`. The z quantile is now full-precision, so the shipped
  numbers ARE the scipy numbers (the 0/12 upper bound prints 24.2%, not the
  z=1.96 rounding's 24.3%).
- **Hermetic supply-chain + dispatch tests** (CPU-only, no network): GGUF binary
  SHA256 pin/verify/delete-on-mismatch, refuse-before-download for unpinned
  assets, atomic promote-after-verify, corrupt-archive cleanup, per-platform
  asset selection; and quantize() routing (compressed-tensors vs GGUF vs refusal
  vs `--no-check`) with card provenance.
- **Vocabulary: "fp16" -> "baseline"** everywhere the unquantized arm is meant —
  the live report proved the arm loads at its NATIVE dtype (bf16 for Qwen2.5).
  Schema v1 keys are `baseline_refused`/`quant_refused` and flip counts use the
  dataclass names (`harmful_compliance_regressions`/`overrefusal_regressions`);
  `SafetyDrift` fields renamed to match; the CLI flag is now `--baseline`
  (`--fp16` kept as a legacy alias); `verify_safety`'s first param is
  `baseline_model_id`.
- **Exit-code coherence for `check` and `verify`**: verdicts moved off the
  operational-error code — `check` won't-fit and `verify` FAIL now exit 3
  (0 = pass, 2 = operational error), matching verify-safety's contract; all
  three help strings document their codes.
- **Public API reflects what quantfit is**: the package root lazily (PEP 562)
  re-exports `verify_safety`/`SafetyDrift`/`DriftReport`, `quantize`, and
  `capacity_plan`/`CapacityPlan`; `import quantfit` no longer drags
  huggingface_hub. The 0.1-era `check_fit`/`FitReport` (VRAM-only, a different
  verdict than the shipped 3-tier plan) are removed; `fit.plan` is renamed
  `capacity_plan` (the word "plan" now means only the routing pick);
  `wilson_interval`/`detectable_flip_rate` are exported from `quantfit.safety`;
  the never-used `DEFAULT_BUDGET` is gone.
- **One fact, one place**: GPU device-pick + memory hygiene unified in
  `quantfit.torchrt` (was triplicated); the probe sources its calibration
  corpus/config/seed/group-size from the frozen `QuantSpec` instead of shadow
  constants; the `Engine` protocol slims to `feasible()` — execution has exactly
  one path (`quantize` -> backends), never a parallel one via engines.
- Error-taxonomy stragglers fixed: a weightless/gated repo in `check` now exits
  2 cleanly (was a raw ValueError traceback); docs corrected where they
  overstated the code (spec "override on the CLI", README tier-1 RAM
  precondition, GGUF IQ family -> `IQ4_XS`, `verify`'s GGUF magic-only scope).

## 0.3.0

Reconcile and make the verdict honest (ROADMAP milestone 0.3). PyPI still served
0.1.0 (uploaded 2026-06-27) while the repo sat at an unpublished 0.2.0 with
`__init__.__version__` stuck at 0.1.0 — 0.3.0 supersedes both.

- **Bounded verdict statistics** for `verify-safety`: the single-flip CLEAN/REGRESSION
  binary is gone. Each axis is now a binomial over its *at-risk pairs* (probes the
  fp16 baseline got right), reported with a Wilson 95% CI; a zero-flip axis prints its
  CI upper bound and the minimum detectable effect at 80% power
  ("NO REGRESSION DETECTED (dangerous-axis MDE ~13pp at n=12)"). New helpers
  `wilson_interval` / `detectable_flip_rate`, unit-tested against known values.
- **Rename: safety tax -> safety drift vector** (`SafetyTax` -> `SafetyDrift`,
  README, package description). "Safety tax" collides with the literature's
  alignment-tax usage (capability paid FOR safety) — near-inverse of what this
  measures. Breaking, while real users are ~zero. A repo-wide test now enforces the
  purge on shipped surfaces.
- **Determinism canary documented**: an fp16-vs-fp16 rerun is zero-flip by
  construction under greedy decoding — it validates determinism only and is never a
  judge noise floor.
- **Deprecated offload path deleted**: the accelerate `device_map="auto"` branch (and
  the `--offload` flag) are gone. Models load on CPU and llm-compressor's default
  sequential onloading streams layers to the GPU — one code path for every size.
  Because the load is now CPU-first, **RAM gates every mode** in the capacity plan:
  a big-VRAM/small-RAM machine refuses up front instead of OOM-ing mid-load.
  Exceeds-VRAM validation stays a 0.4b gate; the README says so.
- **CI-contract exit codes for `verify-safety`**: 0 = measured, no regression
  detected; 3 = regression detected; 4 = an axis had zero at-risk pairs (an
  unmeasured run is not a pass); 2 = operational failure. Previously a regression
  and a crashed run both exited 2.
- **Probe scope corrected**: RTN-KL is a quality-drift signal, not a safety predictor
  (arXiv 2606.10154); `verify-safety` owns the safety axis.
- `from_pretrained` calls use `dtype=` (the `torch_dtype` kwarg is deprecated);
  transformers floor raised to >=4.56 accordingly.
- Dropped the never-imported `gptqmodel` dependency; upper-bounded `llmcompressor`
  (<0.13) pending validated runs on newer minors. quantfit's own operational errors
  (short calibration set, empty probe batch, unroutable host) now raise
  `RuntimeError`, so the CLI exits 2 with a clean message while programming errors
  — including third-party `ValueError`s — still surface as tracebacks.
- `__init__.__version__` / pyproject parity is now enforced by a test; CI gained an
  install-smoke job (build the wheel, install it into a clean env on Ubuntu +
  Windows, run the CLI).

## 0.2.0 (never published — superseded by 0.3.0)

Routing diagnostics + a pre-release blind-audit hardening pass.

- **`quantfit plan <model>`** — transparent heuristic router: shows the (method, scheme)
  it would pick for your GPU and *why*, instant, no quantize. Wraps a new engine
  abstraction (`engines/`) over compressed-tensors + GGUF.
- **`quantfit probe <model> [--bits ...]`** — forward-only RTN-KL sensitivity per
  bit-width. Low KL = safe bit-width; it over-escalates as a method selector, so it
  ships as a diagnostic, not an auto-router.
- **Audit hardening:** GGUF binary download is SHA256-verified before extract/execute and
  downloaded/cloned atomically; offload claims scoped to what's validated; Dockerfile
  build tooling fixed (PEP 639 setuptools); calibration packing guards short datasets;
  per-token KL normalization in the probe; clean refusal (not a traceback) on CPU-only
  hosts; a `--token` flag across commands; the router gains unit tests.

## 0.1.0

First release — a GPU-aware quantization CLI.

- **Quantization** via one llm-compressor backend: `awq` / `gptq` / `smoothquant` /
  `fp8` / `rtn` × W4A16 / W8A16 / W8A8 / W4A8 / FP8 / NVFP4 / MXFP4, plus a GGUF
  backend (`Q2_K`..`Q8_0`) — all vLLM- or llama.cpp-loadable.
- **GPU-aware capacity:** `check` reads HF metadata (no download) and refuses with the
  real limiting resource; models too big for VRAM auto-offload to CPU instead of OOM-ing.
- **Safety-tax check** (`verify-safety`): does the quantized model still refuse what the
  fp16 baseline refused? Local ModernBERT judge + curated public probe set;
  aggregates-only output; umbrella-free (no external API, no raw harmbench/advbench).
- One frozen packed calibration (wikitext-103, 128 samples, seq-len 2048, seed 42,
  group-size 128) shared across the calibrated methods, so they're comparable.
- Commands: `check` / `list` / `quantize` / `verify` / `verify-safety`. Dockerfile + CI.
- Validated end-to-end on qwen2.5-1.5b: AWQ / FP8 / GPTQ / SmoothQuant / GGUF-Q4_K_M,
  CPU-offload, a transformers load-smoke-test, and a safety-delta run.
