# The external-signal baseline, taken before the clock starts — 2026-09-05

ROADMAP 0.5's NO-GO rule counts *"fewer than 3 independent external signals (substantive
issue, citation, dataset reuse, replication)"* within the 8 weeks after outreach lands.
**Without a before, that count has nothing to be measured against.** This record is the
before. Outreach has not happened; the clock has not started.

Every number here was derived by running the command named beside it, on 2026-09-05.

## What was measured

| signal | value | how |
|---|---|---|
| stars | **1** | `gh api repos/Sahil170595/quantfit` — and the stargazer list is `["Sahil170595"]`, so **0 excluding the owner** |
| forks | **0** | same |
| watchers | **0** | same |
| issues (excluding PRs) | **0** | `gh api .../issues?state=all` filtered on `pull_request == null` |
| pull requests | **79, all by the owner** | `gh pr list --state all --limit 200`, grouped by author |
| citations of arXiv 2606.10154 | **0** | OpenAlex `W7164209198`, `cited_by_count` |
| upstream tracker hits | **0** on llama.cpp, vLLM, llm-compressor, unsloth | `gh search issues --repo <r> "quantization refusal safety"` |
| Hacker News, "quantization refusal" | **0 stories** | Algolia `search?tags=story` |

Repository age at capture: **71 days** (created 2026-06-26).

## Two things recorded as *not* results

**The Hacker News query for "quantfit" returned 2,623 stories and is uninterpretable.**
Algolia prefix-matches, so those are `quantitative` hits — "Ask HN: Has Google search become
quantitatively worse?" and similar. A large number that means nothing is more dangerous
than a zero, so it is written down as uninterpretable rather than quietly dropped or
counted.

**PyPI download counts were not obtained.** `pypistats.org` returned HTTP 429 on two
attempts. This does not weaken the baseline: ROADMAP 0.5 already rules that raw pypistats
counts are treated as mirror/bot noise unless decomposed, so the number was never going to
count as a signal.

**The zeros are load-bearing only because the same commands return non-zero elsewhere.**
`gh search issues --repo ggml-org/llama.cpp "quantization"` returns hits up to the limit,
so the four zeros above are a property of the query, not of a broken command. A zero from
an unexercised tool is worth nothing, which is the same rule this project applies to its
own detector.

## What this record does NOT establish

- **It is not evidence that demand is absent.** quantfit has never been announced. Zero
  signals after zero outreach is *no evidence either way*, and reading it as a null would
  be the same error as reading `0/12` as a bound. The wider search for demand — whether
  anyone is asking this question at all — is a separate question this record does not touch.
- **It does not start, pause, or bear on the 8-week clock.** Only outreach starts it
  (`ROADMAP.md`, 0.5 decision rule). This is a measurement taken beforehand so the later
  count is checkable.
- **It is not a complete census of channels.** Reddit and HF forum search were not run here;
  the four trackers, OpenAlex, HN and GitHub are what this record covers, and adding a
  channel later means adding it to the *before* as well or saying it was not baselined.
- **It says nothing about the instrument.** No run, no probe, no judge, no bound.
