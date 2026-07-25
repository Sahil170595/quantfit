# Data handling for captured completions — the recorded decision

**Status:** this document **is** the decision. It is not a proposal, a plan, or a summary of one.
**Decided:** 2026-07-24, by the maintainer, for quantfit 0.6 machinery on branch `release/0.6`.
**Scope:** model **completions** produced by quantfit's own paired runs, and every artifact derived
from them that still contains the text. The probe corpus — the inputs — is governed by a different
and unchanged invariant (§2.1).
**Standing:** ROADMAP's non-goals bar exactly one thing here, verbatim:

> No raw harmful corpora or archived harmful long-form completions without an explicit recorded
> data-handling decision — never a silent reversal.

The clause bars the *silent* version. This file is the explicit recorded decision it names, and it is
the only thing that makes the capture path legitimate.

## 1. The decision

Effective 2026-07-24, for quantfit 0.6 and until superseded by a dated successor to this document:

1. **Completion capture exists.** `verify_safety(..., capture_path=...)` writes the run's generated
   completions to a local JSONL file: a header line, then one row per completion carrying `pair`,
   `arm`, `zone`, `expected`, `judge_refusal` and `completion` — both arms, every probe. It is
   reachable from the CLI as `quantfit verify-safety --capture PATH`, whose own help text repeats this
   document's handling rule and its filename convention. API and flag are governed identically.
2. **It is opt-in, and off by default.** Nothing is captured unless a caller passes a path. There is
   no config default, no environment variable, and no "on for screens" special case that would make
   capture the ambient behavior of a normal run.
3. **Capture cannot change a run.** The capture is written after the drift and the report, from
   values the run already computed — `verify.py`: *"Nothing above this call sees `path`"* — so a run
   with capture and the same run without it produce identical numbers. A data-handling choice must
   never be a measurement variable. **That holds in the failure case too:** if the capture cannot be
   written — unwritable path, full disk, permissions, a directory that does not exist — the run prints
   a warning and continues, and still returns its drift, its verdict and its report. An optional
   data-handling convenience is never allowed to cost a run its measurement, which would be the surest
   way to teach an operator to stop using it.
4. **Capture files are local artifacts.** Written to a path the operator names, on the operator's
   machine, and they stay there.
5. **Every capture file carries a warning header** stating what it holds and what may not be done
   with it (§5.2).
6. **The captured text is length-bounded.** `max_new_tokens` defaults to **64**
   (`DEFAULT_MAX_NEW_TOKENS` in `quantfit/safety/verify.py`; QSR v0 §2.3), applied identically to both
   arms. Sixty-four tokens is not long-form, and the bound is a property of the measurement protocol
   rather than a setting chosen for this decision — which is what makes it durable.
7. **Derived artifacts that still contain the text are covered identically.** The labeling sheet
   `calibrate.build_labeling_sheet` writes is a CSV with a `completion` column: it is the same text in
   a different file, and every clause here applies to it unchanged.

   The unblinding **key** is the case that needs stating against its **real inventory** rather than a
   remembered one, because the remembered one is shorter than the file. `build_labeling_sheet` writes:
   `key_schema`; a **`capture` provenance block** copied from the capture header — `created_utc`,
   `baseline`, `quant`, `n_pairs`; the per-sheet **`salt`**; and an `ids` map of
   `id → {pair, arm, judge_refusal, completion_sha256}`.

   **It still contains no completion text**, and `completion_sha256` does not change that: a SHA-256
   of the text is not the text and is not invertible to it. Its job is to let `ingest_labels`
   authenticate a returned sheet against the capture it was built from, which is an integrity control,
   not a copy. **A hash is not text.**

   **But `baseline` and `quant` are not hashes either — they are whatever named the arms**, and for a
   GGUF arm that may be a **local filesystem path** on the operator's machine rather than a Hub id.
   So the clause-8/9 exemption is **granted conditionally, not absolutely**: the key is exempt —
   retainable, and committable — **only once the operator has confirmed that `baseline` and `quant`
   name nothing they would not publish.** If either is a local path they would not publish, the key is
   either rewritten to identify that arm by Hub id or `artifact_sha256` before it leaves the machine,
   or it is handled under clause 8 exactly like the sheet. The default posture is unexempt: `.gitignore`
   ignores keys by pattern (§5.3), and a cleared key is added deliberately rather than swept in.
8. **Capture files and labeling sheets are NEVER:**
   - **committed to git** — not to this repository, not to any other;
   - **attached to a report** — no `DriftReport`, screen summary, model-card fragment, calibration
     report, issue, PR, or CHANGELOG entry carries completion text;
   - **redistributed** — not to a collaborator, not to a design partner, not as a replication asset.
     The single carve-out, stated below, covers **one named second annotator** and the **sheet only**;
   - **uploaded** — not to the Hub, not to a bucket, not to an LLM API, not to a pastebin, not to a
     cloud-synced folder used as a share.
9. **Retention is short and terminal.** A capture file and any sheet built from it are deleted once
   **every** artifact they existed to feed has been produced — the report *and* the recorded by-hand
   analyses that read the raw files, not the report alone (§3).
10. **The calibration report contains counts only, never text.** Verified against `ingest_labels`,
    which writes tallies, rates and intervals and nothing else: no completion, no prompt, no excerpt,
    no "illustrative example" field.

Clause 8 has no exception for redaction, truncation, or "just the benign ones". A capture file's value
is that it is the exact text the judge saw; a filtered copy is a different artifact with the same risk
profile and none of the auditability.

**Clause 8 has exactly one exception, and this is it: the named second annotator.**
`docs/judge-calibration-v0.md` §4.3 provides for a second annotator labeling a subsample, which
ROADMAP 0.6 asks for *"if one exists"*. Written as the carve-out it is:

> A **single, named** second annotator — named in the published record alongside the number their
> labels helped produce — may receive **the blinded labeling sheet**, and nothing else: never the
> capture file, never the key. They hold it under handling rules **identical** to the maintainer's:
> local to their own machine, deleted once their labels are returned, and **never redistributed
> onward** to anyone, for any reason. This is the only exception to clause 8. It does not extend to
> the capture, to the key, to a second recipient, to an unnamed one, or to any other artifact or
> purpose.

Three notes on why it is drawn this narrowly. **The name is the mechanism**, not a courtesy: an
unnamed helper is indistinguishable after the fact from a redistribution, so an annotator who will not
be named is one this protocol cannot use. **The sheet and not the capture**, because the sheet is
already blinded — it carries no arm, no pair, no judge label and no probe ground truth — so the
carve-out shares the minimum text the task requires and none of the structure. And **the rules travel
with the file**: "identical handling" means the recipient is bound by clauses 8 and 9 in full, and the
maintainer who sends it is responsible for saying so when they send it.

## 2. Scope — what this decision does and does not touch

### 2.1 The corpus invariant is untouched

quantfit's probe set stays **curated, public and redistributable — never raw harmbench/advbench**
(`quantfit/safety/verify.py` module docstring; QSR v0 §2.2). That invariant is about the *inputs* and
is part of the differentiator. Nothing here weakens it, and corpus v2's expansion in ROADMAP 0.6
inherits it verbatim ("curated and redistributable only").

This document is about **outputs**: what a model said when quantfit sent it a probe.

### 2.2 What this is for

Two consumers, both of which currently pay a real cost for the absence of capture:

- **Human verification of flagged flips** (QSR v0 §6.5) and the sensitivity control's adjudication
  (`docs/sensitivity-control-v0.md` §5). Today the maintainer must *reproduce* the run — restart
  `llama-server`, replay all 40 probes by hand — and then adjudicate text that is a reproduction of
  what the judge saw rather than the thing itself. §5.2 Step 5 of that document exists entirely to
  establish that the reproduction is faithful. Capture removes the reproduction step and with it a
  whole class of "did I adjudicate the same bytes?" doubt.
- **The blinded labeling sheet** for judge calibration (`docs/judge-calibration-v0.md` §2.5), which
  must present the labeler with byte-identical text to the judge's input or ε is not the judge's
  error rate.

The shipped code states the same scope from the other side, in `verify.py`'s own docstring:

> Completions are NOT persisted in reports — no raw harmful model output in an artifact meant to be
> published. `capture_path` is the single explicit, opt-in exception: judge calibration (ROADMAP 0.6,
> which runs only on a 0.5 GO) needs text a human can read.

### 2.3 What this decision does **not** authorize

**It does not start any gated work.** ROADMAP 0.6 runs only on a 0.5 GO, and the NO-GO clause is
explicit: *"On NO-GO, 0.6+ shrinks to maintenance mode: … corpus/judge/gate work does not start."*
Shipping the capture path is machinery; hand-labeling 300–500 completions and curating corpus v2 are
the gated work, and neither begins before the GO/NO-GO decision is recorded. `calibrate.py` says the
same of itself — *"It does **not** start it … Nothing here labels anything."*

Capture **may** be enabled during pre-GO runs — the 0.5 screen, the sensitivity control — at the
operator's discretion, because a captured file is exactly what the already-mandated human
verification needs. That is not the gated work; it is the existing human-verification rule being done
with better evidence. Every clause of §1 applies identically to those runs.

**It does not create an archive.** Clause 9 is the point: there is no growing store of captured
completions, no "keep them in case", no dataset. See §3.

## 3. Retention

**Rule:** delete the capture file, and any labeling sheet built from it, once **every** artifact they
exist to feed has been produced — which is the report *and* the by-hand analyses that read the raw
files, not the report alone.

- capture for **flip adjudication** → delete once the adjudication is recorded (probe `id`, zone,
  axis, verdict, flip class — `docs/sensitivity-control-v0.md` §5.2 Step 7; no text);
- capture and sheet for **calibration labeling** → the sequence, stated in full because getting it
  wrong destroys work:

  > **Delete the capture file and the labeling sheet only once the calibration report *and* every
  > by-hand analysis of `docs/judge-calibration-v0.md` §7.3 that will be recorded have both been
  > produced — not when the report is written.** The **key** may be retained under §1.7's condition.
  > A **text-stripped `id,human_label` extract** of the filled sheet may be retained indefinitely: it
  > is counts-and-identifiers, it is what keeps a key-joined recomputation possible after the text is
  > gone, and unlike the capture it holds work that no re-run regenerates.

  The reason for the ordering is that the calibration report does not carry everything the protocol
  needs — per-zone ε, flip-level bias, the at-risk-conditional rate `mde.py`'s A1 assumes — and every
  one of those is recomputed from the **capture** and the **filled sheet**, never from the report.
  Deleting at report time destroys the inputs to analyses that are still owed;
- capture for anything else → there is nothing else. A capture with no named consumer should not have
  been taken.

**Deletion of the capture is not lossy, and that is the load-bearing argument for keeping its
retention this short.** The runs are deterministic and pinned: greedy decoding (`do_sample=False` /
`temperature: 0`), judge and probe dataset at fixed revisions, the llama.cpp binary hashed in the
report, the weights identified by `artifact_sha256` or an HF commit. The same pair regenerates the
same completions. A capture file is therefore a **cache of a reproducible computation**, not a primary
record — so keeping one has ongoing cost and no evidentiary benefit that the report plus the pins do
not already provide.

**That argument covers the capture and stops there. It does not cover a filled sheet.** A sheet's
`completion` column is regenerable on exactly the same terms as the capture; its `human_label` column
is not. Those labels are irreproducible human work: re-running the model reproduces every byte of the
text and not one of the labels, and a second labeling pass is a **different measurement** rather than
a restoration of the first. That asymmetry is the whole reason for the text-stripped extract above —
the sheet's text is deleted on the capture's terms, and the sheet's labels survive as
counts-and-identifiers that contain no completion and can be kept indefinitely. Deleting a filled
sheet without taking that extract first is the one deletion in this document that genuinely loses
something.

The durable artifacts are the drift report, the screen summary, the calibration report, the labeling
key and the stripped `id,human_label` extract; all are counts and provenance, all contain no
completion, and all are publishable — the key subject to §1.7's condition on its `baseline` / `quant`
fields.

If a captured run cannot be regenerated — a Hub repo deleted, `main` moved under an unpinned GGUF
fetch (`docs/sensitivity-control-v0.md` §2.3) — that is a **provenance** problem to record in the
report, not a reason to retain text.

## 4. What changed, and why this is not a silent reversal

### 4.1 The prior state, stated exactly

Before this decision, quantfit persisted **no completion at all**. `SafetyDrift.summary()` is
documented "Aggregates only — never the raw probe prompts/completions"; the schema-v2 `DriftReport`
has no completion field; the screen summary carries per-target counts and verdicts. That was itself a
deliberate posture, and `docs/sensitivity-control-v0.md` §5.1 recorded it as one:

> Completions are not persisted … this is a deliberate data-handling decision, not an oversight:
> ROADMAP's non-goals bar "raw harmful corpora or archived harmful long-form completions without an
> explicit recorded data-handling decision — never a silent reversal." A control run does not get to
> reverse it.

**What changes:** completions may now be written to a local file, on purpose, when the operator asks
for it, and blinded into a labeling sheet that also holds the text.

**What does not change:** no shipped artifact gains a text field. Reports, screen summaries, model
cards and the calibration report are counts-and-provenance exactly as before, and clause 8 forbids
attaching capture files or sheets to any of them. The invariant that mattered publicly — *nothing
quantfit publishes contains model completions to harmful probes* — is unchanged, and is now enforced
at **four** points instead of one (§5: the off-by-default, the warning header, the `.gitignore`
patterns, and the reports' structural absence of a text field).

### 4.2 Why this is not the silent reversal the non-goal bars

Because the non-goal's condition is met, item by item:

| the non-goal's requirement | how it is met |
|---|---|
| "an explicit recorded data-handling decision" | this document, dated, decided, versioned in git alongside the code it governs |
| "never a silent reversal" | the prior posture is quoted verbatim in §4.1 and the delta is named in one sentence |
| "raw harmful corpora" | untouched — the corpus invariant stands (§2.1) |
| "archived … long-form completions" | neither archived (§3: deleted once every consumer is done, and no consumer is open-ended) nor long-form (§1.6: 64 tokens) |

The clause was written to prevent a capture feature appearing in a diff with a one-line commit
message and no stated policy. The test of compliance is not that capture never happens; it is that
when it does, someone wrote down what it is allowed to do, before it shipped, in a place a reviewer
finds. That is what this file is.

A future change to any clause of §1 supersedes this document with a **dated successor** that quotes
the clause it changes. Editing this file in place to loosen a clause, without a date and without
quoting what it replaced, would be the silent reversal — the mechanism the non-goal names, executed
one level up.

**One note on this document's own history, because the rule above applies to it.** Clause 8's
named-second-annotator carve-out, clause 7's conditional key exemption and §3's re-sequenced retention
were all written while this decision was still on the branch that introduces it — before any capture
file existed, before any sheet was built, and before the decision was in force anywhere. That is
drafting, not supersession. From the merge of that branch onward the rule is live: a change to any
clause of §1 needs a dated successor quoting what it replaced, and this paragraph marks where editing
in place stopped being available.

## 5. Enforcement points

Four, counting the default. Each is stated with what it does *not* cover, because a control described
as stronger than it is, is worse than no control.

**5.1 The default is off.** The strongest control is that a normal run produces no capture file. The
path is explicit and per-invocation, and there is no ambient way to turn it on.

**5.2 The warning header, in every capture file.** Written by `_write_capture` as the first line of
the JSONL, before any completion row, as the header's `warning` field. The shipped string
(`verify.CAPTURE_WARNING`), verbatim:

> may contain harmful model output; local artifact — never commit, redistribute, or attach to a report

The header also carries `capture_schema`, `created_utc`, `baseline`, `quant` and `n_pairs`, which is
enough to tie a file found later back to the run that produced it. Stated plainly rather than
implied: the header does **not** carry the retention rule, the judge/probe revisions, or
`max_new_tokens` — those live in this document and in the run's `DriftReport` — and adding them would
be a capture-schema change, not a documentation fix. `verify.py` gives the reason the warning is in
the file rather than only in the docs: *"so a file that gets copied away from the command that
produced it still states what it holds."*

What the header does **not** do is prevent anything. It is a label on a jar, and it exists so that a
file encountered out of context — six months later, in a stale working directory, by someone who did
not run it — announces its own handling rules. **The labeling sheet carries no such header at all**
(it is a three-column CSV, by design, so nothing leaks to the labeler); its handling rules live here
and in `docs/judge-calibration-v0.md`, and that asymmetry is a stated limitation, not an oversight.

**5.3 The `.gitignore` patterns.** Three, landing in the same change as this document, verbatim:

```
*.capture.jsonl
*.labels.csv
*.labelkey.json
```

They match a filename convention **this document mandates**, because no code supplies one: `--capture`,
`quantfit calibrate sheet` and `quantfit calibrate ingest` all take required, explicit paths and
invent no defaults. So the convention is the operator's obligation, stated here —

> Write captures to `<name>.capture.jsonl`, labeling sheets to `<name>.labels.csv`, and unblinding
> keys to `<name>.labelkey.json`.

— and the patterns are the backstop that convention earns. The CLI help text repeats the suffixes at
the point of use, which is a reminder, not an enforcement.

What this does **not** do, stated as plainly as the rest: it does not protect a file written outside
the convention. A capture at `foo.jsonl` is unignored, and the fault there is the operator's broken
convention rather than the pattern's reach — which is exactly why the convention is a mandate in the
decision and not a suggestion. `git add -f` defeats it entirely. It is a backstop against the most
likely accident — `git add -A` in a dirty working tree — **not a boundary**.

The key pattern is deliberately included even though a key may be committable under §1.7's conditional
exemption. Ignoring keys by default and `git add -f`-ing one the operator has actually cleared is the
right way round; the reverse would make an unreviewed key the default commit.

**5.4 The reports carry no text.** Structural, and verified: `DriftReport` (schema v2) has no
completion field; the screen summary is counts, verdicts and provenance; `SafetyDrift.summary()` is
documented aggregates-only; `calibrate.ingest_labels` writes only counts, rates and intervals.
Adding a text field to any of them is a schema bump **and** a supersession of this document — two
gates, not one.

## 6. Exposure

ROADMAP risk 6 scopes this: *"Solo burnout and labeling exposure — small milestone chunks; labeling
scoped and time-boxed with an explicit personal-exposure decision; measurement-layer-only surface."*

The exposure this decision creates is **at most two people**, and the second is optional, named, and
reading strictly less than the first.

The default is a single operator reading short completions to a curated, public, 40-item probe set —
twelve of which are `clear_unsafe` — on their own machine. Clause 8's one carve-out adds, *if and only
if* a second annotator exists, a single **named** person reading a subsample of the **blinded sheet**:
the same 64-token completions to the same curated public corpus, minus the arm, the pair partner, the
judge's label and the probe's ground truth. That is a bounded increase in *who* is exposed and none at
all in *what* — no extra text is generated, no extra corpus is touched, and their copy is deleted when
their labels come back.

It does not grow past that: the carve-out is one person and forbids passing the sheet onward (§1,
clause 8), retention is per-consumer and terminal (§3), length is bounded at 64 tokens (§1.6), and the
corpus is the curated public one (§2.1). Capture does not increase what is read; it changes *where it
is read from*, replacing a manual reproduction with the file the judge actually saw. The
personal-exposure decision itself — how much labeling, in what time box, and whether a second
annotator is asked at all — belongs to the 0.6 GO, not to this document.

## 7. Provenance

- **ROADMAP quotations** (standing note, §2.3, §6): copied verbatim from `ROADMAP.md` — the non-goals
  paragraph, the 0.5 NO-GO clause, and risk 6.
- **The prior posture** (§4.1): quoted from `docs/sensitivity-control-v0.md` §5.1, and verified in
  code on 2026-07-24 — `quantfit/safety/report.py` (`DriftReport` has no completion field),
  `quantfit/safety/verify.py` (`SafetyDrift.summary()` docstring: "Aggregates only — never the raw
  probe prompts/completions"), `quantfit/screen.py` (summary rows are counts, verdicts and provenance).
- **The capture path** (§1, §5.2): read from `quantfit/safety/verify.py` on 2026-07-24 — the module
  docstring's capture paragraph, `CAPTURE_SCHEMA`, `ARM_BASELINE` / `ARM_QUANTIZED`, `CAPTURE_WARNING`
  (quoted verbatim), and the body of `_write_capture` (header fields, JSONL row fields, and the
  "nothing above this call sees `path`" ordering). Cited by symbol: these landed on this branch today
  and line numbers would be stale on arrival.
- **The CLI surface** (§1.1, §5.3): `quantfit/cli.py` read on 2026-07-24 — `verify-safety --capture
  PATH` (whose help text carries this document's handling rule and the `*.capture.jsonl` suffix), and
  a `calibrate` subcommand with `sheet` (`--capture/--sheet/--key`) and `ingest`
  (`--sheet/--key/--out`). Every path argument is `required=True` with no default, which is the fact
  §5.3's "no code supplies one" rests on. An earlier draft of this bullet recorded the flag as unwired;
  it landed on this branch.
- **The sheet, the key, and the report's counts-only shape** (§1.7, §1.10, §3, §5.4): read from
  `quantfit/safety/calibrate.py` — `SHEET_COLUMNS = ("id", "completion", "human_label")`,
  `build_labeling_sheet` (writes the completion column; the key holds `key_schema`, the `capture`
  provenance block `created_utc` / `baseline` / `quant` / `n_pairs`, the `salt`, and
  `id → {pair, arm, judge_refusal, completion_sha256}`), and `ingest_labels` (writes counts, rates and
  Wilson intervals only). §1.7's inventory is that field list, not a paraphrase of it: the
  `capture` block and `completion_sha256` are the two items an earlier draft of §1.7 omitted, and the
  first is why the clause-8/9 exemption is now conditional.
- **The `.gitignore` patterns** (§5.3): read from `.gitignore` on 2026-07-24 — `*.capture.jsonl`,
  `*.labels.csv`, `*.labelkey.json`, under a comment naming this document. Quoted verbatim above.
  An earlier draft of §5.3 described a pattern that had not yet landed; it lands in this change.
- **Warn-and-continue on an unwritable capture** (§1.3): the capture write is the last thing a run
  does and its failure degrades to a printed warning rather than an exception, so the drift, the
  verdict and the report survive it. Cited by symbol (`_write_capture`'s call site in
  `verify_safety`), not line number.
- **`max_new_tokens = 64`**: `DEFAULT_MAX_NEW_TOKENS` in `quantfit/safety/verify.py`, and QSR v0 §2.3,
  which fixes it as the protocol default applied identically to both arms.
- **Determinism and pinning, for the §3 regeneration argument**: QSR v0 §2.3 (greedy on both arms),
  §2.6 (judge and probe revision pins), §3.2 and §4.2 (`binary_sha256`, `artifact_sha256`, `revision`).
  The one unpinned fetch — GGUF arms resolve HF `main` — is recorded in
  `docs/sensitivity-control-v0.md` §2.3 and is why §3's last paragraph exists.
- **No capture file, labeling sheet, key or calibration report exists** in this repository, and none
  was produced in writing this document.
