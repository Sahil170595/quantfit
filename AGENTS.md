# AGENTS.md — how to work in this repository

*This file is identical in intent to `CLAUDE.md`; both exist so any agent tooling finds
the rules under the name it looks for. Edit them together.*

quantfit is a measurement instrument. Its value is that its numbers are checkable and
its claims are bounded. Work here is therefore judged by whether a stranger can verify
what you assert, not by how much of it you produced.

---

## 1. Research and validation process — non-negotiable

**Every claim traces to an artifact.** A number in a doc, a CHANGELOG line, or a commit
message must cite a file in this repository, a CI run URL, or a source line. "It works"
is not a result; a report with provenance is.

**Runs produce committed artifacts.** A run that leaves nothing behind did not happen as
far as this repo is concerned. Record it under `validation/<date>-<slug>/` with:

- the machine-readable outputs (schema-v2 report, gate artifact, JUnit, comparison record),
- a `README.md` giving hardware, pinned versions, exact invocations, and — required —
  **what the run does not establish**,
- structured adjudication (`adjudication.json`) whenever a human judged anything.

`validation/` is evidence-that-a-command-runs. It is **not**
`docs/reference-reports-v0.md`'s three-report registry; adding to it consumes no cap and
creates no spec-bump regeneration duty.

**Pre-registered rules are read before the result, not after.** Protocols in `docs/`
(`sensitivity-control-v0.md`, `cross-hardware-tolerance-v0.md`, `qsr-v0.md`) fix the
decision rule in advance. When a rule turns out to be ambiguous for an observed state:

1. state both readings and which one the text intends,
2. check whether they differ *for this result* — often they do not,
3. fix the rule text **in the same commit as the result**, marked as a dated defect.

Never silently pick the reading that flatters the outcome. An amended pre-registration
is worthless unless the amendment is visible.

**Flagged is not confirmed.** The judge flags; a human confirms. Keep the two counts
separate everywhere — reports, cards, changelogs — and never let a flagged count be
published as a verified one. When adjudication changes a number that is already public,
correct the public copy the same day.

**A null needs a passing positive control to mean anything.** Until the sensitivity
control passes, every `0/n` on the dangerous axis is "the detector did not fire", not
"nothing is there". Say so in that many words.

**Negative results ship.** A failed control, a breached tolerance, a defect in our own
rule — these are the results with the highest information content in this project.
Publish them at the same volume as successes and do not soften them.

---

## 2. Data management

**Counts are committable; completions are not.** Schema-v2 reports, gate artifacts and
JUnit carry aggregates only (`spec/qsr-v0.md` §4.1). Verify that before committing
rather than assuming it — walk the JSON for any key matching
`prompt|completion|response|text|generation`.

**Captures never enter git.** `*.capture.jsonl`, `*.labels.csv`, `*.labelkey.json`,
`*.baseline-cache.json` are local-only under `docs/data-handling-completions.md` and are
backstopped in `.gitignore`. To make an adjudication auditable without publishing text,
record a per-completion `sha256` in `adjudication.json` — the record is then re-checkable
against a regenerated capture by anyone.

**Provenance is checked, not assumed.** Confirm the revision pins, `artifact_sha256` and
binary hashes in a report against the protocol document that specified them, and say in
the record that you did. HF `main` moves; the sha is the ground truth.

**Personal exposure is scoped deliberately.** Adjudicating over-refusal flips on safe
probes is low exposure. Adjudicating dangerous-axis flips is not. Note which you did.

---

## 3. Libraries and tools — current, not remembered

**Do not write API code from memory.** Check current documentation before using a
library's API — `context7` for library docs, the installed package's own `--help` and
source otherwise. This stack moves fast: transformers 5.x hard-refuses `device_map=`
without `accelerate`, and that broke CI while every local run passed.

**Prefer the project's own primitives over hand arithmetic.** Use
`quantfit.safety.verify.wilson_interval` and `quantfit.safety.mde` rather than computing
a CI or an MDE by hand, so published numbers and tool output cannot diverge.

**Pins are load-bearing.** Judge and probe-dataset revisions, the llama.cpp binary
sha256, and the dependency caps in `pyproject.toml` are part of the measurement. When
you bump a version, bump every place that states it — including
`docs/ci-integration.md` and `.github/actions/quantfit-gate/action.yml`'s
`quantfit-version` default, which a release can otherwise silently exclude itself from.

**Verify before reporting.** `quantfit audit`, `pytest -q`, and `ruff check`/`format`
on CI's exact paths, before saying it is done. Re-derive any count you are about to
publish by a second method.

---

## 4. Working style — be decisive

**Default to acting.** Anything reversible — code, docs, local runs, branches, commits,
PRs, artifacts — is yours to do. Do it, then report what you did and what it showed.
Do not ask permission to do the work you were asked to do.

**Do not escalate judgement calls that are yours.** Ambiguity in a spec, a naming
choice, which of two readings to record, whether to fix a stale doc: decide, act, and
state the reasoning so it can be overridden. Escalating these is not caution, it is
offloading the work.

**Confirm only for the genuinely irreversible and outward-facing**: publishing to PyPI,
posting publicly under the maintainer's identity, entering credentials (never — that is
the maintainer's to do), deleting data. One confirmation covers the action authorised,
not a standing licence for the next one.

**Finish the whole thing.** Run, record, update the docs the result falsifies, correct
any public copy that is now wrong, commit, open the PR. A result sitting in a scratch
directory is not delivered.

**Push back with evidence, not hedging.** If the plan is wrong — including a plan the
maintainer proposed, or one you proposed an hour ago — say so plainly, cite the file or
run that shows it, and propose the alternative. Read the design doc before asserting
what it says: `injected-control-design.md` §0 says do *not* build the injected control
for 0.5, which is the opposite of what "the design exists" suggests.

**State confidence explicitly**: verified from `<file>:<line>`, inferred from
`<evidence>`, or hypothesis-not-yet-checked. Never fill a gap with a plausible guess.
"I have not checked X yet — checking" then the tool call, in that order.
