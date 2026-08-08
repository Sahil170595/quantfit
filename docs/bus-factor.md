# Bus factor — what breaks if the maintainer stops

**Bus factor: 1.** One person. No co-maintainer, no organization account, no review rota.
ROADMAP risk 6 names the human half of this ("Solo burnout and labeling exposure … CONTRIBUTING
at 0.10"); this document is the *artifact* half — the concrete list of things that stop working,
ranked by what would actually stop a third party from reproducing the work.

**Ranked by reproduction impact, not by how alarming they sound.** The ordering is the point.
Losing PyPI is loud and nearly harmless. Losing one Hugging Face repository is quiet and
terminal for every measurement this project can make — and for every measurement it *has*
made, all of which are unpublished (§4). That the published set is currently empty is the
single fact keeping item 1 from being a realized loss rather than a pending one.

Every mechanism below was checked in this tree; the citation is where. Where a claim is
inferred from configuration rather than observed from a built artifact, it says so.

| # | asset | who controls it | if it goes | cheapest mitigation |
|---|---|---|---|---|
| 1 | judge model, revision-pinned | maintainer's personal HF account | **every run dies; every report that will ever cite these pins becomes unverifiable** — zero such reports exist yet (§4) | mirror the two repos under a second owner |
| 2 | probe corpus, revision-pinned | maintainer's personal HF account | same as 1 | same as 1 |
| 3 | the QSR spec | this repo only; not in the PyPI artifact | reports stay readable, become uninterpretable | it is already in-repo — keep it there, and get one fork |
| 4 | reference reports | do not exist yet | nothing to reproduce *against* | run the 0.5 screen; publish one |
| 5 | PyPI trusted publishing | maintainer's GitHub + PyPI project | no new releases; installs keep working | document the setup so a successor can rebuild it |
| 6 | pinned llama.cpp release assets | `ggml-org`, not the maintainer | GGUF arms cannot provision | already escapable via `QUANTFIT_LLAMACPP` |
| 7 | unwritten operational knowledge | maintainer's head | a successor re-derives what has and has not been run | the "not delivered" paragraphs already carry most of it |

---

## 1–2. The judge and the probe corpus, under a personal Hugging Face account

**This is the one that matters, and it is two repositories owned by one individual.**

```python
# quantfit/safety/verify.py:86-89
JUDGE_MODEL_ID          = "Crusadersk/quantsafe-refusal-modernbert"
JUDGE_REVISION          = "b34061f964619a5b6e0ff24be45a428124fa36bc"
PROBE_DATASET_ID        = "Crusadersk/quantsafe-judge-benchmark"
PROBE_DATASET_REVISION  = "c26cc2e15fcadab9c0ec24a5b57d37b140f7ed58"
```

Both are loaded at those exact revisions on every run — the judge in
`_classify_refusals` (`verify.py:604-605`), the corpus in `_load_probes`
(`verify.py:517`) — and both are recorded in every schema-v2 report
(`verify.py:397-413`). `spec/qsr-v0.md` carries the same two IDs and hashes as
**normative** rows (§ pinned-artifacts table and Appendix A). They are not
conveniences. They *are* the measuring instrument.

**Failure mode, concretely.** `Crusadersk` is a personal account. If it is deleted,
renamed, suspended, or simply abandoned and reclaimed:

- `quantfit verify-safety`, `screen`, `gate` and the Inspect runner all fail at load.
  Not degrade — fail. There is no fallback judge and no vendored corpus anywhere in
  this tree.
- **Every report that cites these pins becomes unverifiable — and today that is zero
  reports, which is the only good news in this section.** A report's whole
  auditability claim is that it names the artifacts it used by revision so a reader
  can re-fetch them; a pin pointing at a repository that no longer exists is a pin
  that proves nothing. Said in the tense the evidence supports: **nothing has been
  published** (§4 — `quantfit/refreports.py` ships its registry empty by design and
  says so in its own docstring), so the loss is entirely *prospective*. No published
  measurement becomes unverifiable, because there is no published measurement.
  Read that as a deadline rather than as comfort: the cost of losing these two
  repositories is at its lifetime minimum right now and only rises — with the first
  reference report, with the first outside citation, with the first adopted gate.
  **Mirror before publishing, not after.**
- The 0.5 screen, the 0.6 calibration and the 0.7/0.8 cross-hardware work all sit
  downstream of these two repos. None of them are re-runnable without both.

An account rename is worth stating separately because it is the *likely* version:
Hugging Face repo IDs are owner-scoped, so a rename silently breaks the string in
`verify.py:86` while the weights themselves still exist. The revision hashes would
still be correct and still be unresolvable.

**Cheapest mitigation, in order of cost:**

1. **Mirror both repositories to a second owner** — an org account the maintainer
   controls today, or a second individual. This is a clone-and-push; it costs an hour
   and it converts item 1 from terminal to inconvenient. Do this first. It is the
   single highest-leverage action in this document.
2. **Record the content hashes out of band.** The revisions are already pinned;
   pinning the *file* digests as well (the same discipline `backends/gguf.py`
   applies to the llama.cpp binary) would let a third party verify a mirror is the
   same artifact rather than trusting a second copy's name.
3. **Do not vendor the corpus into the repo.** It is deliberately a public curated
   set held outside git (`verify.py:44-46` — "curated public corpus only … never raw
   harmbench/advbench"), and copying 40 rows including twelve `clear_unsafe` prompts
   into the source tree would trade a bus-factor risk for a distribution problem the
   project has explicitly declined. Mirror, do not inline.

---

## 3. The spec as a single unforked copy — and it is not in the PyPI artifact

`spec/qsr-v0.md` is the protocol definition. Every conformance claim, every exit
code, every statistical rule and every normative constant is there and nowhere else.
`spec/qsr-v1-freeze-plan.md` is the ledger that says what v1 still needs.

**In-repo rather than only on a website — that part is already right.** A spec that
lived on a maintainer-controlled domain would die with the domain and take every
"QSR v0 §5.7" reference with it. Here it is a file in a git repository, so every
clone, every fork and every GitHub archive tarball carries the whole normative text.
Anyone who has cloned the repo has the standard.

**But it does not travel with the package.** There is **no `MANIFEST.in`** in this
repository, and `pyproject.toml:68-69` limits packaging to
`[tool.setuptools.packages.find] include = ["quantfit*"]`. The last locally built
manifest (`quantfit.egg-info/SOURCES.txt`) lists `LICENSE`, `README.md`,
`pyproject.toml`, the `quantfit/` sources and `tests/` — and **no `spec/`, no
`docs/`, no `CHANGELOG.md`, no `ROADMAP.md`**. (That artifact is stale — it predates
several of those files — so read it as confirming the *shape*: with no `MANIFEST.in`,
non-package directories are excluded by default. The configuration is the
verified part; the specific file list is illustrative.)

So `pip install quantfit` gives you a tool whose output cites `spec/qsr-v0.md §5.7`
and does not give you §5.7. Today that is fine, because GitHub is up. It is exactly
the coupling that hurts if the repo goes away and PyPI does not.

**Cheapest mitigations:**

1. **Get one fork.** Not a mirror the maintainer owns — a fork by someone else. One
   fork by an unrelated party is the whole mitigation, and it is also literally the
   0.10 gate's "≥1 third-party reproduction, citation, or gate adoption."
2. **Ship `spec/` in the sdist** via a three-line `MANIFEST.in`. It makes the PyPI
   artifact self-describing and costs nothing. (Not done here — this document owns
   no packaging file; see `CONTRIBUTING.md` §7 on stating what is not delivered.)
3. **Archive a version-tagged copy somewhere with a DOI** (Zenodo takes a GitHub
   release directly). `CITATION.cff` exists and is version-pinned, but it carries no
   DOI, so there is currently no citation target that survives the repo.

---

## 4. There is nothing published to reproduce yet

This is not a bus-factor risk in the usual sense; it is the reason the others bite.

`quantfit/refreports.py` — the registry of ROADMAP 0.8's three reference reports —
**ships empty, deliberately**, and its own docstring says so: *"No reference report
exists. None may be fabricated here."* `CHANGELOG.md:48` states the same in the
release notes: zero reference reports, no T4 reproduction attempted, the 0.5 screen
not run.

The consequence for succession is direct: **the project's evidence base is entirely
prospective.** A successor inherits machinery, a spec, and a plan — not a body of
published measurements they can check their own runs against. Every mitigation above
gets cheaper the moment one real report exists at a stable URL, because from then on
a third party can detect breakage without the maintainer.

**Cheapest mitigation:** publish one. One reproducible reference report, with its
pins, at a stable location, is worth more to the bus factor than any amount of
documentation about how a report would be produced.

---

## 5. PyPI trusted publishing

`.github/workflows/publish.yml` publishes on GitHub release via
`pypa/gh-action-pypi-publish@release/v1` with `permissions: id-token: write` and
`environment: name: pypi` — OIDC trusted publishing, no long-lived API token in the
repository. That is the right posture and it is also a single point of failure with
**no artifact in this repo describing it**: the trust relationship lives in PyPI's
project settings (publisher = this GitHub repo, this workflow, this environment) and
in the repository's environment configuration, neither of which is in git.

**Failure mode.** If the maintainer's GitHub or PyPI account is lost, nobody can cut
a release. Note the bound: **already-published wheels keep working**, and anyone can
build from a fork. This is a distribution inconvenience, not a reproduction blocker —
which is why it ranks below the spec and far below the judge.

A quieter variant is worth naming: the workflow asserts the git tag matches
`pyproject.toml`'s version (`publish.yml:25-31`), so a successor who does not know
about that check will see a release fail for reasons the error message explains
poorly.

**Cheapest mitigation:** write down the publishing setup — which PyPI project, which
publisher entry (repo / workflow filename / environment name), and that the `pypi`
GitHub environment must exist. Three lines in a release runbook turns "unrecoverable"
into "one afternoon for whoever inherits the project."

---

## 6. The pinned llama.cpp assets — the one dependency the maintainer does not control

`quantfit/backends/gguf.py` pins tag `b9817`, commit
`5397c3619479ef544e340e4b933929d1783de78b`, and the SHA256 of two release assets
(`_BINARY_SHA256`, `backends/gguf.py:52-55`). If `ggml-org` deletes or re-cuts those
release assets, the GGUF provisioning path stops — and it stops *correctly*, refusing
rather than silently fetching something else, because an asset with no pin is a hard
refusal (`_verify_or_die`, `backends/gguf.py:95-109`) and a moved tag is caught by the
commit check (`convert_script`, `backends/gguf.py:205-209`).

This one already has its escape hatch in code: `QUANTFIT_LLAMACPP` points at a local
llama.cpp checkout and bypasses provisioning entirely (`_llama_bin`,
`backends/gguf.py:148-150`; `convert_script`, `:181-183`). ROADMAP risk 7 tracks the
churn side of the same dependency.

**Cheapest mitigation:** none needed beyond what exists — but a successor must know
that `QUANTFIT_LLAMACPP` is the answer, which is why it is written here and in
`SECURITY.md` rather than only in a docstring.

---

## 7. What is only in the maintainer's head

Ranked last because the repo is unusually good at this already — the "not delivered"
paragraphs in `CHANGELOG.md`, the blocking ledger in `spec/qsr-v1-freeze-plan.md`, and
the empty-by-design registry in `refreports.py` all exist precisely so that *what has
not been run* is a documented fact rather than tacit knowledge.

What is still tacit, honestly:

- **Which hardware each validated claim came from.** README cites specific observed
  runs (Qwen2.5-7B GPTQ over-VRAM on a 12 GB card, ~32 min; AWQ's ~2 h single-layer
  behavior under onloading). Those are one person's box. A successor cannot tell
  which claims are hardware-general without re-running them — which is exactly what
  ROADMAP 0.10's "every advertised command hardware-validated" is for, and it is not
  satisfied today.
- **The judge/corpus construction.** The pinned artifacts' *provenance* — how the
  corpus was curated, how the judge was trained — is summarized in
  `verify.py:55-71` against the live HF cards but is not reconstructible from this
  repo. If the repos vanish, so does the recipe.
- **Why specific pins were chosen at specific dates.** The dates are in comments
  (`# pinned 2026-07-11`); the deliberation is not.

**Cheapest mitigation:** keep doing the "not delivered" paragraph on every release —
it is the single practice most responsible for this project's succession story being
recoverable at all — and add the hardware a claim came from wherever a claim names a
number.

---

## The short version

If exactly one thing gets done from this document: **mirror
`Crusadersk/quantsafe-refusal-modernbert` and `Crusadersk/quantsafe-judge-benchmark`
under a second owner.** Everything else on this list degrades gracefully. Those two do
not, and they take every past measurement down with them.
