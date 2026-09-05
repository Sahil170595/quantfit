# Reference reports v0 — the publication procedure, the cap, and the regeneration rule

**Status:** protocol. **Zero reference reports exist.** Nothing in this document has been
run: no report has been published to the Hub, `quantfit/refreports.py:REGISTRY` is `()`, and
the 0.8 gate ("one reference report reproduced from scratch on a free T4 within the 0.7
tolerance") has not been attempted — `docs/cross-hardware-tolerance-v0.md` §6.1 records that
no T4, Colab or Kaggle run of any kind has happened. The 0.5 existence-proof screen has not
run either, so **no report of any pair exists to publish**.

This file is therefore the *procedure* and the *criteria*, written before the runs so the
criteria cannot be tuned to the results. Where it names candidate pairs (§3) those are
shortlist entries drawn from `screens/targets-0.5.json`, which exists as a curated **target**
list — not as results.

**Written:** against quantfit 0.5.3 (`quantfit/__init__.py:__version__`, `pyproject.toml`),
report `schema_version` 2, QSR spec **v0**, on branch `release/0.8`. §9 says which facts here
were read out of this tree and which were not.

**Scope:** ROADMAP 0.8's second bullet, verbatim:

> **Three** reference reports on HF — capped at three; reports are versioned to the spec and
> regenerated only at spec-version bumps, so dependency pin bumps do not invalidate published
> artifacts (regeneration is the budgeted cost, not an accident).

---

## 1. What a reference report is, and what it is not

A reference report is **one schema-v2 `DriftReport` JSON file** (`quantfit/safety/report.py`),
produced by `quantfit verify-safety` on a real pair, published on the Hub at a pinned commit,
and registered in `quantfit/refreports.py` by slug, pair, stratum, spec version, tool version,
sha256 and location.

It **is**: an auditable artifact. Every input that determines its numbers is in it — judge and
probe-dataset revision pins, decode parameters, the resolved precision of each arm, per-arm
engine provenance (including `binary_sha256` for GGUF arms, which is how the same-binary
mandate is checkable from the file alone), the environment fingerprint, per-arm runtimes, and
the full drift vector with its Wilson intervals and its MDE (QSR v0 §4.1–§4.3).

It **is not**:

- **a certification.** A no-detection reference report says exactly what QSR v0 §5.9 says it
  says: no flip was observed among the at-risk pairs, and the printed MDE is a **lower bound**
  on the resolution that run had. At the shipped probe set's dangerous-axis ceiling of n = 12
  the two-sided 95% Wilson upper is **~24.2%** and the perfect-judge floor is **~12.6pp**
  detectable at 80% power (QSR v0 §5.3's table) — and **neither is a bound on reality**: the
  interval carries sampling error alone, and the floor assumes a judge that never errs.
  Publishing it as a reference does not upgrade that.

  **Corrected 2026-09-04**, with §5.9 itself. The two sentences above previously read "the
  run's resolution was the printed MDE" and "that bounds the true harmful flip rate below
  ~24.2%", quoting a §5.9 that said the same thing. At the ε measured on 2026-08-18 the
  effective MDE is 1.0 for every n ≤ 34 (`validation/2026-08-22-measured-eps-mde/`), so at
  n = 12 nothing was detectable at any prevalence and `0/12` bounded nothing about the world.
- **a prevalence claim.** A reference report is one pair. It carries the uncalibrated-judge
  label and its stratum's caps, and it does **not** carry the screen's conditionality label —
  that is a screen-level obligation on prevalence claims, and stamping it on a per-pair
  artifact would assert something about a screen the report is not part of (QSR v0 §9 scope,
  §10.4).
- **a record of what the model said.** Reports carry counts and provenance and no completion
  text, structurally (§6).
- **a reproduction hash.** The registry's sha256 pins *bytes*. A faithful rerun produces a
  **different file** — `created_utc`, `runtime_s` and `judge_runtime_s` all differ by design —
  so re-running never reproduces the hash and was never meant to. Reproduction is judged
  against the T1–T5 tolerance rule (`docs/cross-hardware-tolerance-v0.md` §1.3), the hash is
  for authenticating a download.

---

## 2. Three, and only three — and when they are regenerated

**The cap is three, enforced in code.** `quantfit/refreports.py:MAX_REFERENCE_REPORTS = 3`,
checked on every registration, with the rationale in the refusal message. ROADMAP risk 5 is
the reason and it is a cost argument, not an aesthetic one:

> **Report regeneration burden** — pinning discipline guarantees recurring regeneration.
> Mitigation: reports capped at three, valid as-of their spec version, regenerated only at
> spec bumps.

A fourth reference report is a decision to raise the cost of every future spec bump. It is
therefore a budget decision made deliberately, not a line appended to a list — which is why
the registry refuses it rather than warning.

**The regeneration rule.** A published report is **VALID as-of the spec version it is bound
to**, and becomes **STALE** only when that spec version is superseded:

| event | effect on a published reference report |
|---|---|
| quantfit release (0.5.3 → 0.6.0 → …) | **none.** Still valid. |
| dependency pin bump (torch, transformers, llmcompressor) | **none.** Still valid. |
| judge / probe-dataset / llama.cpp pin bump (QSR v0 §4.4) | **none.** Still valid — and reports under different pins MAY be compared but MUST NOT be pooled. |
| **QSR spec version bump (v0 → v1)** | **STALE.** Regeneration is owed. |

That asymmetry is implemented, not just written down: `refreports.validity(entry,
current_spec_version)` decides from the spec version alone and never reads
`entry.quantfit_version`, and `tests/test_refreports.py` asserts both directions on entries
that differ in exactly one field.

**STALE is not RETRACTED.** QSR v0 §10.3: *"A published report is valid as-of the spec version
it was produced under and stays citable at that version — a bump dates it, it does not
retroactively invalidate it."* A stale report keeps backing a citation at its own spec
version; what it stops doing is representing the current one. Whether its numbers may appear
in one table alongside current-spec numbers is the **bump's** comparability statement to make
(QSR v0 §10.3 requires the bump to say so), not the registry's.

**A spec bump therefore costs exactly three reruns**, which is the number the cap exists to
fix. Budget them with the bump; do not discover them afterwards.

---

## 3. Candidate pairs, and the criteria that pick them

### 3.1 The criteria, stated before the candidates

1. **The run must already be budgeted.** Reference reports come out of the 0.5 screen's
   targets (`screens/targets-0.5.json`), not out of a separate campaign. A pair not in the
   screen is a new download and a new run.
2. **The 0.8-gate report must fit a free T4 runtime's *system RAM*.** On the GGUF stratum both
   arms run on CPU under one pinned binary, so the binding resource is RAM, not VRAM
   (`docs/cross-hardware-tolerance-v0.md` §4.3): the 0.4b gate's 15.24 GB F16 arm does **not**
   fit a free Colab runtime's community-reported ~12–13 GB, and ~3B at F16 (~6 GB) is the
   practical ceiling. That excludes the 7–8B class — where third-party quants actually live —
   from the *gate*, and §4.4's consequence (1) must be published with the result: a T4
   reproduction of a 1.5B report does not reproduce an 8B-class report.
3. **A third party must be able to fetch and rerun both arms.** Ungated repos; permissive
   licences on both sides preferred, because a reader who must accept bespoke terms before
   reproducing is a reader who mostly will not.
4. **The three should not be three of the same thing.** Strata are separate instruments at
   separate caps (QSR v0 §6.2, §7) and a reference set that covers only one says nothing about
   the other.
5. **A human-verified positive finding outranks a null.** If the screen produces a flip that
   survives human verification (QSR v0 §6.5), that pair becomes a reference candidate ahead of
   any null — a published existence proof is the more useful artifact, and it is the one
   ROADMAP 0.5's hunt exists to find.

### 3.2 The shortlist

All figures below are read from `screens/targets-0.5.curation.json` (curated and
double-verified against the HF API at curation time; `repo_revision` there records `main` **at
curation time**, and quantfit's `hf:` loader resolves whatever `main` points at when the run
happens — so the report's own `artifact_sha256` is the identity that matters, not the curation
row).

| candidate | stratum | baseline / quant | licence | why it is on the list |
|---|---|---|---|---|
| `gguf-r1-distill-qwen-15b-unsloth` | `gguf` | BF16 3.56 GB / Q4_K_M 1.12 GB | apache-2.0 on the GGUF repo, MIT on the DeepSeek base, both ungated | **The 0.8-gate candidate.** The baseline arm clears criterion 2 with a wide margin (3.56 GB against a ~13 GB runtime), both sides are permissive and ungated, and the pair is the direct tie to the R1-1776 8-bit re-censorship incident class ROADMAP 0.5 names in its outreach. |
| `gguf-smollm3-3b-bartowski` | `gguf` | bf16 6.16 GB / Q4_K_M 1.92 GB | apache-2.0, ungated, fully open weights + data + recipe | The most *reproducible* artifact in the set — a reader can inspect the training data, not just the weights. Sits **at** the free-tier ceiling (~6 GB), so it is a second T4 candidate, not the first. |
| `ct-qwen25-15b-official-awq` | `compressed-tensors` | `Qwen/Qwen2.5-1.5B-Instruct` 3.10 GB / first-party AWQ 1.61 GB | apache-2.0, first-party | The only stratum-coverage candidate: without it the reference set is GGUF-only. Note the constraint — a T4 reproduction of a transformers-arm report is **blocked on the fp16 dtype pin** (`docs/cross-hardware-tolerance-v0.md` §3.3 Option A, §4.4): on sm_75 a `resolved_dtype` of `torch.bfloat16` would record a pin the hardware did not honour. So it can be a reference report today and the **gate** report only after Option A lands. Loading it needs `pip install 'quantfit[awq]'`. |

### 3.3 Named exclusions, so the shortlist is auditable rather than assertive

- `gguf-qwen3-8b-unsloth` — the highest-download both-arm repo in the set (318,290 30d) and
  the only 8B-class entry, and **excluded from the gate** by criterion 2: a 16.39 GB BF16
  baseline arm does not fit a free runtime. It remains the strongest candidate for a reference
  report that is *not* the one reproduced on T4, if the third slot is spent on deployment
  relevance rather than stratum coverage.
- `gguf-llama32-1b-bartowski` — 227,693 30d downloads and a 2.48 GB baseline; the best
  alternate to candidate 1 on every criterion except licence (Llama 3.2 Community License; the
  GGUF repo is ungated but the upstream `meta-llama` repo is gated).
- `gguf-gemma3-270m-lmstudio`, `gguf-gemma2-2b-it-bartowski` — Gemma Terms of Use govern
  redistribution of derived outputs; the 270m pair is also the smoke-test pair (510 30d
  downloads), which is the wrong signal for a citable artifact.
- `gguf-ministral-8b-bartowski`, `gguf-lfm25-12b-unsloth` — `other` licences (Mistral Research
  License; LiquidAI LFM Open License) that must be read before anything derived is
  redistributed.
- `ct-qwen25-15b-anchor-crusadersk` — **the maintainer's own quant**, carried in the screen as
  the known-finding anchor with a disclosure. It is not a third-party artifact, and a reference
  set led by a self-produced quant answers a weaker question than one led by what the ecosystem
  published. If it is ever published as a reference, the disclosure travels with it verbatim.
- `gguf-qwen25-15b-uncensored-mradermacher` — the most safety-informative base in the set (an
  already-de-aligned fine-tune) but no licence is stated on the quantizer card; provenance is
  flagged as unstated in the curation file. Unstated provenance is the wrong footing for a
  citable artifact.

### 3.4 What defers the decision

**The pick is not made here, and cannot be.** A reference report is a *published run*, and no
run has happened. Three things resolve before the three slots are spent:

1. **the screen runs**, and each candidate row either completes or ends as an operational-error
   row (QSR v0 §6.1 — a gated repo or a mispaired architecture costs one row);
2. **any flagged flip is human-verified** (QSR v0 §6.5), because criterion 5 promotes a
   verified positive over a null;
3. **the dtype question is settled** (`docs/cross-hardware-tolerance-v0.md` §3.3), because it
   decides whether the compressed-tensors candidate can ever be the gate report.

---

## 4. What every published reference report must carry

Nothing in this section is new machinery: it is the set of things a reader must be able to
find, listed so a publication can be checked against it.

1. **`schema_version: 2`, all eleven top-level fields.** Enforced on parse
   (`report.py:DriftReport.from_json`); a v1 report is refused, never coerced (QSR v0 §4.5),
   and there is no v1 → v2 migration path.
2. **The pins, in the artifact:** `judge.id` / `judge.revision`, `probe_dataset.id` /
   `.revision` / `.split` / `.n_probes`, and — on a GGUF pair — `engine.binary_sha256` **equal
   on both arms**, which is the machine-checkable form of the same-binary mandate (QSR v0
   §4.2). `resolved_dtype` is the precision actually loaded on each arm; the literal `"auto"`
   is rejected by the schema.
3. **The uncalibrated-judge label, verbatim.** The report writes it itself
   (`safety/verify.py:_measured_judge_label`), and it is quoted unchanged wherever the accuracy
   figure appears:

   > `card-reported, external XSTest/GPT-4 responses — uncalibrated, out-of-distribution for these probes`

   **Corrected 2026-08-28:** that is the *retired* judge's label and the report has not emitted
   it since the judge was replaced. The shipped judge's card carries no XSTest figure
   (`verify.JUDGE_CARD_XSTEST_ACCURACY is None`), and the label written today reports quantfit's
   own in-distribution measurement instead.

   **Corrected again 2026-09-04, and the second correction is the interesting one.** The
   sentence above went on to give that measurement as *"accuracy 95.0%, false-positive rate
   8.3%, false-negative rate 0.0% at n=80, single-rater"* — the exact wording 0.12.9 removed
   from the label itself, reprinted inside a note whose whole job was to say the old wording
   was retired. n=80 is the denominator of neither rate (it splits **48 compliant / 32
   refusal**), and a bare `0.0%` on the false-**negative** side reads as a judge that never
   misses a dangerous flip. The measurement is: accuracy **95.0%**, **4 false positives in 48
   compliant completions** (95% Wilson upper **19.6%**), **0 false negatives in 32 refusals**
   (95% Wilson upper **10.7%**), single-rater, one model, one probe set
   (`validation/2026-08-18-judge-calibration/calibration.json`). Quote
   `safety/verify.py:_measured_judge_label` rather than paraphrasing it — paraphrase is how
   both of these corrections became necessary.

   In-distribution judge error ε is therefore **measured but not applied** (2026-08-18; ROADMAP
   0.6's planned 300–500 has not run, and no code path folds ε into a printed MDE). No MDE, CI or
   bound in a reference report is corrected by any judge figure, and quoting a card accuracy as
   this protocol's accuracy remains a conformance violation (QSR v0 §2.7).
4. **The caps — carried by the surfaces around the report, because the report has no caps
   field.** QSR v0 §7 states this asymmetry as a limitation rather than papering over it:
   *"`DriftReport` schema v2 has no caps field at all… a reader holding only a report JSON
   cannot read its cap out of the artifact."* So the cap **must** be published in the model
   card next to the file and in the repo card that hosts it, verbatim from
   `quantfit/screen.py:SPEC_CAPS`:

   - `gguf` — *unquantized baseline arm <= 16.5 GB on disk (~8B-class) in CPU RAM; both arms
     under one pinned llama.cpp binary, CPU-only*
   - `compressed-tensors` — *<= 3B parameters in-GPU on 12 GB VRAM; transformers-loadable
     quantized checkpoints (compressed-tensors format or AWQ)*

   Moving the cap into the report is a **schema bump** (QSR v0 §7, §10.2), not a documentation
   fix, and until that bump the publication procedure is what carries it.
5. **The MDE, printed.** Every report prints its own; a bound quoted without its MDE is not
   QSR-conformant (QSR v0 §5.3). Every published bound also names its **method and sidedness**
   — "two-sided 95% Wilson, upper limit" (QSR v0 §6.3).
6. **The model-card fragment** (`quantfit emit model-card --report PATH`), which renders the
   drift vector, the CIs, the provenance and the caps line. A report too thin to render raises
   `ReportError` and exits 2 rather than printing a card with a hole in it — so a fragment that
   renders is itself a check on the report.
7. **No completion text.** Structural, and it stays structural (§6).

---

## 5. The publication procedure

Eight steps, in order. Steps 1–3 happen before anything leaves the machine.

**Step 1 — run the pair and write the report.** Shipped defaults only; `--max-new-tokens`
stays at 64, because a report produced at a different decode length is not a report of the
thing the screen runs (QSR v0 §2.3).

```bash
quantfit verify-safety \
  --baseline hf:<org>/<repo>/<model>-f16.gguf \
  --quant    hf:<org>/<repo>/<model>-<qtype>.gguf \
  --report   refreports/<slug>.json
```

Record the exit code (0 / 3 / 4, QSR v0 §5.7). **Exit 4 is not a pass** — an unmeasurable axis
means nothing was measured there — and an exit-4 run is not a reference-report candidate on
that axis.

**Step 2 — rerun it once, on the same machine, and diff.** Two consecutive runs of the same
pair must be identical minus timestamps and runtimes (QSR v0 §8's rerun, distinct from the
determinism canary). A report that does not survive its own rerun is not publishable, and
finding that out after upload is worse in every way.

**Step 3 — confirm the artifact carries no text.** Structural rather than hopeful: schema v2
has no completion field. If the run was taken with `--capture` (permitted, opt-in, off by
default), the capture file is a **local artifact** and is never uploaded, attached or committed
(§6).

**Step 4 — render the model card** and keep it with the file:

```bash
quantfit emit model-card --report refreports/<slug>.json
```

**Step 5 — hash the exact bytes that will be uploaded.**

```bash
python -c "from quantfit.refreports import sha256_file; print(sha256_file('refreports/<slug>.json'))"
```

Hash **before** upload and re-hash the downloaded copy after (step 7). Hashing only the local
file proves the local file.

**Step 6 — upload.** The Python API is pinned here rather than a CLI invocation because the
Hub CLI's entry-point name has changed across `huggingface_hub` majors while this API has not.
*(Signatures verified locally against `huggingface_hub` 1.19.0 — §9.)*

```python
from huggingface_hub import HfApi, create_repo

REPO = "<org>/quantfit-reference-reports"   # one repo for all three; a dataset repo
create_repo(REPO, repo_type="dataset", exist_ok=True)

info = HfApi().upload_file(
    path_or_fileobj="refreports/<slug>.json",
    path_in_repo="v0/<slug>.json",          # the spec version is in the path, deliberately
    repo_id=REPO,
    repo_type="dataset",
    commit_message="reference report <slug> (QSR spec v0, quantfit <version>)",
)
print(info.oid)   # the commit sha -> the entry's hf_revision
```

Two conventions this document mandates rather than infers:

- **The spec version is a path segment** (`v0/<slug>.json`). When v1 lands, the regenerated
  report goes to `v1/<slug>.json` and the v0 file **stays where it is** — a bump dates a
  report, it does not delete one (QSR v0 §10.3), and a citation to the v0 file must not start
  404-ing because a newer spec exists.
- **One repo, three files.** Three repos would triple the surface that has to stay alive for a
  citation to resolve.

The repo card carries, at minimum: the caps for every stratum represented (§4.4), the
uncalibrated-judge label, the "not a certification" sentence from QSR v0 §5.9, and a pointer to
`spec/qsr-v0.md`.

**Step 7 — download the uploaded copy and verify it round-tripped.**

```python
from huggingface_hub import hf_hub_download
from quantfit.refreports import sha256_file

local = hf_hub_download(REPO, "v0/<slug>.json", repo_type="dataset", revision="<oid from step 6>")
print(sha256_file(local))   # must equal step 5's digest
```

**Step 8 — register the entry, in source, and let import validate it.** Add a
`ReferenceReport` to `_REGISTRY_ENTRIES` in `quantfit/refreports.py`:

```python
ReferenceReport(
    slug="<slug>",
    baseline="hf:<org>/<repo>/<model>-f16.gguf",
    quant="hf:<org>/<repo>/<model>-<qtype>.gguf",
    stratum="gguf",
    spec_version="v0",
    quantfit_version="<the report's own quantfit_version field>",
    report_sha256="<step 5 / step 7 digest>",
    hf_repo_type="dataset",
    hf_repo="<org>/quantfit-reference-reports",
    hf_path="v0/<slug>.json",
    hf_revision="<oid from step 6>",
)
```

`validate_registry` runs at import, so a fourth entry, a duplicate slug, **two entries carrying
the same `report_sha256`** (one file registered under two names — and equal digests can only
mean that, since even a rerun of one pair produces a different file), a second entry for the
same pair at the same spec version, an unknown spec version, an unknown stratum, an `hf_path`
that is not a plain relative repo path ending in `.json`, or a non-64-hex digest **fails the
import**, not a later read.

*The registry is code, and that has one stated cost.* Code is reviewed, versioned with the
tool, and validated at import — which is why it is code. The cost is that registering a report
rides a quantfit release: a report published between releases is registered in the next one.
That is acceptable because a reference report is not urgent by construction, and the alternative
(a JSON file the package reads at runtime) trades review for immediacy in the artifact whose
whole value is that it was reviewed.

**Then:** CHANGELOG entry naming the slug, the spec version and the sha256; and the report's
existence stated in `spec/qsr-v0.md`'s reference-report section when v1 freezes.

---

## 6. Data handling — what may not be uploaded, and why it is already true

`docs/data-handling-completions.md` is **the recorded decision** and governs this procedure
without modification. The clauses that bind here:

- **Clause 8:** capture files and labeling sheets are **never** committed to git, attached to a
  report, redistributed, or uploaded — *"not to the Hub, not to a bucket, not to an LLM API,
  not to a pastebin, not to a cloud-synced folder used as a share."* Publishing a reference
  report is an upload; the capture that may have accompanied the run is not part of it.
- **Clause 10 / §5.4 (the structural enforcement):** reports, screen summaries, model cards and
  the calibration report contain **counts and provenance only**. `DriftReport` schema v2 has no
  completion field, so "the published report contains no model output" is a property of the
  schema rather than of the uploader's care. Adding a text field is a schema bump **and** a
  supersession of that document — two gates, not one.
- **Clause 9 (retention):** a capture taken to human-verify a flagged flip is deleted once the
  adjudication is recorded. Publishing a reference report is not a reason to keep one; the
  runs are deterministic and pinned, so a capture is a cache of a reproducible computation, not
  a primary record.
- **The corpus invariant** (QSR v0 §2.2, unchanged): the probe set stays curated, public and
  redistributable. The published report names the probe dataset and its revision; it does not
  republish it.

One consequence worth stating because it is a question people ask: **the licence terms on the
weights govern derived *outputs*, and a reference report is not one.** A report is counts and
provenance about an artifact, containing none of its text. Where a candidate's licence is
flagged in §3.3 ("read before redistributing completions"), that flag is about the completions
this project does not publish — but the pair's terms still govern anyone who reproduces the
run, which is criterion 3's actual reason for preferring permissive both-sides licences.

---

## 7. How a third party verifies a published report

Three things a reader can check, in increasing order of what they establish.

**7.1 Authenticity — the bytes are the registered artifact.** Cheap, offline after the
download, and it is the only thing the registry's hash claims:

```python
from huggingface_hub import hf_hub_download
from quantfit.refreports import find, verify_published

entry = find("<slug>")
local = hf_hub_download(entry.hf_repo, entry.hf_path, repo_type=entry.hf_repo_type,
                        revision=entry.hf_revision)
result = verify_published(entry, local)
print(result["matches"], result["statement"])
```

`verify_published` returns the comparison; a mismatch is a **return value**, not an exception,
because "these bytes are not the registered bytes" is the finding an auditor needs to print. It
raises only when the file cannot be read (operational, exit 2). A match authenticates the
artifact and nothing else: it does not verify the numbers, and the uncalibrated-judge label and
the stratum cap survive verification untouched.

**7.2 Conformance — the report is internally checkable.** From the JSON alone, with no access
to the machine (QSR v0 §3.4): `resolved_dtype` on both arms is a real precision and not
`"auto"`; for a GGUF pair `baseline.engine.binary_sha256 == quantized.engine.binary_sha256`;
`judge.revision` and `probe_dataset.revision` are the pinned hashes in QSR v0 §2.6; the drift
block's flip counts, at-risk denominators, Wilson intervals and MDE are consistent with
`safety/verify.py:wilson_interval` and `detectable_flip_rate` at the reported n. One field is
**not** an audit surface and QSR v0 §3.4 says so: `engine.device` on a GGUF arm is a constant
the runner writes, asserted rather than observed.

**7.3 Reproduction — the measurement travels.** The strongest check, and a different one:
re-run the pair and compare the two reports under the T1–T5 rule
(`docs/cross-hardware-tolerance-v0.md` §1.3, which stays the authority for the rule itself;
`quantfit/reproduce.py` — present in this tree as a sibling 0.8 deliverable — decides those
clauses over two report files so a breach is not adjudicated by eye). **Do not compare hashes
for this** (§1). T1 is the precondition (same pins, same weights, same decode); T2 is
verdict-class agreement computed from fields rather than from the verdict string; T3 gives the
at-risk denominators **zero** slack; T4 allows ±1 on each axis's flip count; T5 bounds the
refusal totals per axis and per zone.

**A failure is not automatically a breach, and which failure it is decides the verdict.** The
normative statement is `docs/cross-hardware-tolerance-v0.md` §6.3's outcome table — §1.3's
headline sentence ("any single failure is recorded as a breach") is a summary that §1.3's own
T1 clause immediately refines, in the same section, by saying a T1 failure makes the record
`void`, *"never `breach` and never `reproduced`"*. `quantfit/reproduce.py` implements §6.3, and
a verifier should read the outcome out of it rather than eyeballing the clause list:

| what failed | `outcome` | exit | what it means |
|---|---|---|---|
| nothing (T1–T5 all pass) | `reproduced` | 0 | **the only outcome that meets the 0.8 gate**, for *this* report at *this* cap |
| **T1** | `void` | 4 | the two files are not two runs of one measurement, so the tolerance is undefined. **Not a breach and not a pass** — nothing was compared. Fix the mismatch or stop calling them the same measurement |
| **T3**, by ≤ 1 on the at-risk denominator **on exactly one axis**, with T1/T2/T4/T5 passing | `reproduced_with_denominator_drift` | 3 | an informative near-miss: the *resolution* moved while the published verdict did not. The gate is **not** met; publish it with both printed MDEs side by side and the baseline-side divergence named as the cause |
| **T2, T4 or T5** — or **T3 by more than 1, or on both axes** | `breach` | 3 | the tolerance is breached. Publish the deltas and the affected axis; do **not** widen the rule to fit them |
| nothing, but **no T0 evidence was supplied** for a side | `reproduced_t0_unverified` | 3 | T1–T5 hold, but §6.3 defines `reproduced` as T0 on both sides *then* T1–T5, and T0 is not computable from two reports. Minted by `quantfit/reproduce.py` rather than reusing the reserved name — and mapped to 3, strictly *harder* than `reproduced`, so a missing precondition can never buy a pass. Supply `t0_reference` / `t0_candidate` from `within_hardware_identical()` to reach exit 0 |

Two things this table is deliberate about. **`void` is not a soft pass** — it exits 4 precisely
so a build script cannot read "nothing was compared" as "it reproduced" (the same rule QSR v0
§5.5 applies to unmeasurable axes). And **the near-miss shares exit 3 with `breach`**, because
a CI consumer needs one bit — did the gate hold? — and both answer no; the distinction is
preserved in `outcome` and in the failing predicates, which is where a reader who wants it
looks. Exit **2** is operational only (unreadable, malformed or wrong-schema input), never a
verdict. A **0 → 1 flip divergence on an axis with no reference flips fails T2 and is a
`breach` by design** — it moves the published verdict and `verify-safety`'s own exit code — and
it has no softer name (§1.3's fourth note, §5.3).

The rule is pre-registered and the outcome vocabulary is closed: §6.3's four names —
`reproduced`, `reproduced_with_denominator_drift`, `breach`, `void` — plus exactly one minted
by the implementation, `reproduced_t0_unverified`, which §6.3's own amendment requires be
recorded as minted, mapped into the four exit codes, and never mapped to 0 without T0 on both
sides. Neither the rule nor the vocabulary may be widened to fit a result — that would convert
a measurement into a ratification. Note the asymmetry that makes the mint safe: a new name is
admissible only where it is *stricter* than an existing one.

**Validity is a separate question from all three.** `refreports.validity(entry, "v0")` answers
"is this report current?", and it is decided by the spec version alone (§2). A report can be
authentic, conformant, reproducible **and stale**, all at once.

---

## 8. The 0.8 gate: one report reproduced on a free T4

ROADMAP 0.8's gate is a single sentence — *"one reference report reproduced from scratch on a
free T4 within the 0.7 tolerance"* — and every term in it is defined elsewhere:

- **"one reference report"** — a specific one, named in the record. QSR v0 §6.6's
  no-extrapolation rule applies to reproduction claims exactly as it applies to prevalence
  claims: a T4 reproduction of a 1.5B GGUF report does not reproduce an 8B-class report, and
  the claim's reach stops at the reproduced report's stratum and cap
  (`docs/cross-hardware-tolerance-v0.md` §4.4).
- **"from scratch"** — cold on both arms. If a cached-baseline path ever reaches
  `verify-safety`, a cached replicate cannot serve as a T0 replicate: it would be
  byte-identical trivially and would turn the determinism precondition into a tautology
  (`docs/cross-hardware-tolerance-v0.md` §3.2). On this branch `quantfit/safety/cache.py`
  exists and no command imports it, so every run is cold anyway.
- **"on a free T4"** — say **which** free tier, with the §3.4 hardware fingerprint attached.
  Colab publishes no guaranteed specs, so the fingerprint *is* the hardware claim
  (`docs/cross-hardware-tolerance-v0.md` §4.1). Whether Kaggle's larger host RAM makes the
  8B-class GGUF reproduction feasible is an open question there with the resolving command
  already written down (§4.5).
- **"within the 0.7 tolerance"** — T0 first (three replicates per hardware, byte-identical
  `drift` blocks, no slack), then T1–T5 once across hardware. The outcome vocabulary is fixed
  in advance: `reproduced`, `reproduced_with_denominator_drift`, `breach`, `void`
  (`docs/cross-hardware-tolerance-v0.md` §6.3), plus the implementation's
  `reproduced_t0_unverified`, and the record shape is defined there too. T0 is not computable
  from two reports, so its result must be *supplied* to `compare()`; omitting it yields
  `reproduced_t0_unverified` at exit 3, never the gate pass.

**The dependency order, stated so the gate is not attempted out of sequence:** the 0.5 screen
runs → a candidate pair completes and its report is published and registered (§5) → that
report is reproduced on the free tier under T1–T5 → the reproduction record is published with
the report named, the stratum named and the cap named. **Every one of those steps is
outstanding.**

**And the gate cannot be met by a compressed-tensors report until the dtype pin lands.** On a
T4 (sm_75, not bf16-native) a bf16 checkpoint would record `resolved_dtype:
"torch.bfloat16"` on both sides while the two machines ran different arithmetic — T1 would pass
on a pin the hardware did not honour, which is exactly the silent mismatch the milestone exists
to refuse (`docs/cross-hardware-tolerance-v0.md` §3.3, §4.2).

---

## 9. Provenance — what in this document was read, and what was not

**Read from this working tree (branch `release/0.8`):** ROADMAP 0.8's reference-report bullet
and gate, and risk 5, quoted verbatim from `ROADMAP.md`; the QSR v0 clauses cited by section
number, quoted from `spec/qsr-v0.md` (§2.2, §2.3, §2.6, §2.7 including the label string
verbatim, §3.4, §4.1–§4.5, §5.3's n = 12 row — 12.6pp MDE, 24.2% Wilson upper — §5.7, §5.9,
§6.1, §6.3, §6.5, §6.6, §7, §8, §9, §10.2, §10.3, §10.4); `SPEC_CAPS` verbatim from
`quantfit/screen.py`; the schema-v2 field list and the `"auto"` rejection from
`quantfit/safety/report.py`; the clauses of `docs/data-handling-completions.md` cited in §6;
every tolerance clause cited to `docs/cross-hardware-tolerance-v0.md` (§1.3, §1.5, §3.2, §3.3,
§3.4, §4.1, §4.3, §4.4, §4.5, §6.1, §6.3); the candidate pairs, sizes, download counts and
licence notes from `screens/targets-0.5.json` and `screens/targets-0.5.curation.json`; the
shipped version 0.5.3 from `pyproject.toml` and `quantfit/__init__.py`; the registry behaviour
from `quantfit/refreports.py` and `tests/test_refreports.py` in this change; the CLI surfaces
in §5 (`verify-safety --baseline/--quant/--report/--capture`, `emit model-card --report`) read
from `quantfit/cli.py`; `quantfit/safety/cache.py` present and imported by no command (a search
over `quantfit/` for `safety.cache` matches only the module itself); and `quantfit/reproduce.py`
present in the tree as a sibling 0.8 deliverable implementing T1–T5. §7.3's outcome table is
`docs/cross-hardware-tolerance-v0.md` §6.3's, cross-read against `reproduce.py`'s `_decide` and
its `OUTCOME_EXIT_CODES` (`reproduced` 0, `reproduced_t0_unverified` 3,
`reproduced_with_denominator_drift` 3, `breach` 3, `void` 4, operational 2) — read from the
module in this tree, not inferred from §6.3 alone. The fifth name and the one-axis narrowing of
the near-miss both landed after this section was first drafted and were re-read from the module
afterwards, not carried over from the draft.

**Verified by running, on this machine:** the `huggingface_hub` API shapes in §5 —
`HfApi.upload_file(*, path_or_fileobj, path_in_repo, repo_id, repo_type, revision,
commit_message, …) -> CommitInfo`, `CommitInfo.oid`, `create_repo(repo_id, *, repo_type,
exist_ok, …)` and `hf_hub_download(repo_id, filename, *, repo_type, revision, …)` — inspected
against the installed `huggingface_hub` **1.19.0**. The project floor is `>=0.25` with no upper
bound, so a much older install may differ; the snippets are pinned to the API rather than to a
CLI for that reason, and an implementer should re-inspect before running.

**NOT verified, and not claimed:** that any of the candidate repos still resolves, that any
candidate pair runs to a verdict, any free-tier RAM/vCPU/disk figure (§3.1's ~12–13 GB is
community-reported and stale-by-default per `docs/cross-hardware-tolerance-v0.md` §4.1), and
anything at all about a published reference report — **because there is not one**. No file has
been uploaded, no hash has been registered, and `REGISTRY` is `()`.
