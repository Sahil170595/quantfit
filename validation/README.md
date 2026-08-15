# Validation artifacts — runs you can re-hash

Every file under this directory is the **output of a command that actually ran**, kept
so that a claim in `docs/validation-matrix.md` can cite a file rather than prose.

`docs/validation-matrix.md` §0 opened with this scope note:

> No run artifact of any kind is committed to this repository: `out/` and
> `.benchmarks/` are empty, `quantfit/refreports.py:REGISTRY` is `()`, and no drift
> report, gate artifact or screen summary is tracked. Every quantitative claim below
> is therefore **transcribed CHANGELOG prose**, not a file you can re-hash. That is
> itself a finding, and it is the ceiling on how strong any row can be.

This directory is that ceiling being lifted, for two runs. It is not lifted for the
rest, and the matrix still says so per row.

## What this is NOT

**These are not reference reports.** `docs/reference-reports-v0.md` governs those: at
most three, versioned to the spec, published on Hugging Face, regenerated at spec
bumps, and `quantfit.refreports.REGISTRY` stays empty until one exists. A reference
report is a *product* that other people cite. A validation artifact is *evidence that
a command runs*, and carries no such promise — nothing here is registered, nothing
here is citable as a reference report, and adding files here never touches the
three-report cap.

The distinction matters because it decides what regeneration costs. A reference
report must be regenerated when the spec version bumps. A validation artifact is a
record of what happened on a date with a pinned stack, and it stays valid as history
even after the code moves — at which point the honest response is a new dated
directory, not an edit to an old one.

**Files here are never edited after the fact.** If a rerun disagrees, that is a
finding and it gets its own directory.

## Data handling

Schema-v2 drift reports carry **counts only** — no prompts, no completions, no probe
text (`spec/qsr-v0.md` §4.1). The same holds for the JUnit XML and the gate decision
artifact. That is what makes these committable at all, and it was verified rather
than assumed before the first commit here: every JSON in this tree was walked for any
key matching `prompt|completion|response|text|generation`, and there were none.

Artifacts that *do* carry completion text — `*.capture.jsonl`, `*.labels.csv`,
`*.labelkey.json` — are local-only under `docs/data-handling-completions.md` and are
backstopped in `.gitignore`. None of them belong in this directory, and the naming
conventions there are what keeps that accidental rather than a matter of discipline.

## Layout

One directory per run session, named `<date>-<slug>`. Each carries its own README
recording the hardware, the pinned versions, the exact invocations, and — the part
that matters most — **what the run does not establish**.
