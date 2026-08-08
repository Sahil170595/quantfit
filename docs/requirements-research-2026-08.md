# Requirements research & patch impact ranking — 2026-08-08

What the public needs from a tool of this kind, what assistants encounter when they try to
use this one, and which patches buy the most. Companion to the same audit run against
Chimeraforge (`Chimeraforge/docs/ax-audit-2026-08.md`).

**Method.** quantfit `0.5.1` installed from PyPI into a clean venv — what a new user actually
gets — probed across all ten commands, then compared against the local `0.5.3` tree. Plus 9
web searches over the 2026 quantization-safety literature, four competing tools and the
regulatory position. Claims are labelled `[V]` verified by running it, `[R]` from published
sources, `[I]` inferred.

**Headline.** quantfit does not have Chimeraforge's problem. Its exit codes, refusals and
provenance are the most disciplined part of either codebase, and the 2026 literature has
caught up with its thesis and states it more sharply than the README does. What it lacks is
every affordance that lets someone *else* act on the measurement.

---

## 1. The thesis is now better supported than the README claims `[R]`

Recent work documents refusal behaviour collapsing sharply past a model-specific bit-width
threshold — Qwen flipping 90.3% at 4-bit, Mistral-7B 15.2% at 4-bit, Llama and Gemma holding
until 2-bit, Mixtral-8x7B degrading gradually then collapsing 93.1% at 2-bit. Standard RTN and
GPTQ post-training quantization is reported dropping SafetyBench scores by more than 20 points
in categories like Offensiveness and Illegal Activities. Models with strong baseline alignment
are found robust while weakly aligned ones are not.

That last result is the argument for quantfit's *paired* design specifically: an absolute
safety score cannot separate "this model was never well aligned" from "quantization broke it".
A baseline-versus-quant diff can.

**Implication for effort.** The premise no longer needs proving. Spend on distribution.

### 1.1 A direct methodological challenge to the protocol `[R]`

The same literature says safety claims should report multi-sample stability across multiple
benchmarks rather than rely on a single benchmark at greedy decoding. quantfit pins greedy
decoding and one curated probe set — deliberately, for determinism, reproducibility and a
defensible at-risk denominator.

This is a real tension and the v1 freeze is where it gets settled. The strong answer is not to
abandon greedy: state why a paired design at fixed decode measures something a multi-sample
absolute score cannot, and state what the result does not cover. A frozen spec that answers a
published critique in advance is worth more than one unaware of it.

### 1.2 An axis quantfit cannot see `[R]` `[V]`

There is now dedicated work on **alignment collapse under KV-cache quantization**, on the
basis that it degrades precisely the activations alignment depends on. quantfit measures
weight quantization only `[V]`. A deployment with FP16 weights and a Q4 KV cache — an ordinary
llama.cpp configuration, and one Chimeraforge already models with `--kv-quant` — is invisible
to it.

Treat KV-cache precision as a first-class arm dimension: the same paired diff with weights
held constant and cache precision as the treatment. The GGUF arm already runs both sides under
one pinned binary, so the mechanism exists.

---

## 2. What blocks anyone else from using it

### 2.1 Not one command emits machine-readable output `[V]`

Probed for structured-output flags across all ten commands of 0.5.1:

```
command        --json  --report  --out
check            no      no       no
list             no      no       no
plan             no      no       no
probe            no      no       no
verify           no      no       no
verify-safety    no     YES       no
screen           no      no      YES
emit             no     YES       no
calibrate        no      no       no
quantize         no      no      YES
```

The verdict, the Wilson bounds, the MDE, the provenance — the entire product of this tool —
reaches a caller only as a file written to a path, and only from two commands. Chimeraforge
accepts `--json` on all ten of its commands.

The unreleased tree does not change this, and the way it doesn't is instructive: at 0.5.3
there are thirteen commands and exactly one `--json`, on `audit` — the docs-parity checker
`[V]`. The only part of quantfit built to be consumed by a machine is the part that checks
your documentation, not the part that measures safety.

**Patch.** `--json` on every command: one document on stdout, schema-versioned, diagnostics on
stderr. Largely serialisation of structures that already exist. This is the change that turns
quantfit from a thing a person runs into a thing a pipeline runs.

### 2.2 The differentiator cannot be tried without a serious commitment `[V]`

Of ten commands, exactly two do anything useful with no GPU, no network and no weights:
`list` and `plan` `[V]`. Both print prose. Everything that demonstrates why quantfit exists
requires two model artifacts plus a judge download first.

The funnel is therefore: read a claim about safety drift, install, run `list`, then face a
multi-gigabyte download before seeing a single verdict. Most evaluations end there. The
competing tools people already have installed print something within a minute.

**Patch.** A first-run path producing a real verdict in under two minutes: a tiny pinned pair
with a cached capture, or `--demo` running the full pipeline over fixture completions and
printing the same report shape marked as a demonstration. The test suite already runs the
whole tabulation on fixtures; it simply is not reachable from the CLI.

### 2.3 GitHub cannot detect the licence `[V]`, because the file is truncated `[I]`

`pyproject.toml` declares `license = "Apache-2.0"`. GitHub's API reports
`spdx_id: NOASSERTION`, name `Other` `[V]`. The file is 154 lines with the `APPENDIX` section
absent, against 202 for the canonical text `[V]` — below the similarity threshold GitHub's
classifier needs `[I]`.

Cheapest item on the list, and it gates the most conservative adopters: corporate policy
scanners and dependency-review bots read that field, and "Other" is frequently an automatic
block.

**Patch.** Restore the full canonical Apache-2.0 text including the appendix; confirm with
`gh api repos/:owner/:repo/license` that `spdx_id` returns `Apache-2.0`.

### 2.4 `quantfit --version` is an error `[V]`

Exits 2 with an argparse usage dump — the subcommand is required and no version flag exists.
Still true in the unreleased tree, whose top-level parser flag set is exactly `--help` / `-h`
`[V]`. Confirming an install is the first thing a human or an agent does, and the documented
alternative (`python -c "import quantfit; print(quantfit.__version__)"`) is what our own CI
uses because the CLI cannot answer.

### 2.5 What is already strong `[V]`

Recorded because the fixes should aim at it, not disturb it:

- **Errors teach.** Every wrong invocation returns exit 2 with a specific, actionable message
  naming the missing argument or the valid choices.
- **Exit codes are a real contract** — 0/2/3/4/5, specified, tested, and separating verdict
  from operational failure from unmeasurable. Nothing else in this space does this.
- **Discovery works.** Unlike Chimeraforge — whose name resolves to a different package —
  searching for quantfit returns its PyPI page first with an accurate description of the
  safety-drift claim.

---

## 3. Market position

### 3.1 Nobody does the paired diff `[R]`

garak (NVIDIA, ~8.1k stars, 120+ probes), PyRIT (Microsoft, ~3.4k), promptfoo (~17k, acquired
by OpenAI in March 2026), DeepTeam. All scan a model for vulnerabilities in the absolute. None
compares a baseline against its own quantization with an at-risk denominator and statistical
bounds. The ground is empty.

### 3.2 Be a step in the pipeline, not a rival to it `[R]`

The recommended 2026 stack is garak plus PyRIT for offence and promptfoo for CI regression.
Teams have those installed. quantfit's win condition is being the quantization-specific gate
*inside* that pipeline — which needs machine-readable output (2.1) far more than more probes.
Re-running a fixed set after every model change and blocking a merge on the delta is already
established practice, so the concept needs no selling; only the plumbing.

### 3.3 Hugging Face verifies nothing `[R]`

Anyone can publish a GGUF quant; there is no pre-upload verification and the community relies
on publisher reputation. A quantfit report attached to a quant repo is a credential in a space
that has none. An adjacent project already ships bit-exact derivation attestation for GGUF
quants — a complement and a natural integration, not a competitor.

### 3.4 Regulation is not the near-term driver `[R]`

EU AI Act enforcement of GPAI obligations began 2 August 2026, but free and open-licence
models are exempt from the technical-documentation duties unless they carry systemic risk. The
pull comes from systemic-risk providers and downstream deployers — not from the hobbyist
publishing a Q4_K_M. Position around this honestly rather than overclaiming compliance value.

### 3.5 Shipping is the bottleneck, again `[V]`

PyPI serves 0.5.1. The tree carries 0.5.3 plus the entire 1.0 machinery stack. The repo is
1 star, 0 forks, 0 subscribers, created 26 June 2026. Both CLIs in this family are several
releases ahead of what anyone can install, which is a strange position from which to judge
adoption.

---

## 4. Ranking

Ordered by expected return, not effort.

| # | Patch | Why it ranks here | Effort |
|---|---|---|---|
| 1 | `--json` on every command | Zero of ten emit structured output; nothing downstream can consume a verdict | S |
| 2 | Make `verify-safety` trialable in 2 minutes | The differentiator needs two artifacts plus a judge download before it says anything | M |
| 3 | Repair `LICENSE` | GitHub reports `NOASSERTION`; enterprise scanners filter on that field | XS |
| 4 | Ship what is already built | PyPI is on 0.5.1; the tree is 0.5.3 plus the 1.0 stack | S |
| 5 | Add `--version` | Exits 2 today; first thing any caller runs | XS |
| 6 | Measure KV-cache quantization | The literature now locates alignment collapse there | L |
| 7 | Answer the greedy-decoding critique in spec v1 | Published guidance calls single-benchmark greedy claims insufficient | M |
| 8 | Plug into the garak/PyRIT/promptfoo pipeline | Be a step in the stack teams already run | M |
| 9 | Ship `llms.txt` + a usage-facing skill | No agent-facing file exists in the repo root | S |
| 10 | Publish one reference report | The registry ships empty by design; one real report converts the argument | M |

---

## 5. Reproduction

```bash
python -m venv /tmp/qf && /tmp/qf/bin/pip install quantfit   # 0.5.1, what users get

# 2.1 - structured-output flags across every command
for c in check list plan probe verify verify-safety screen emit calibrate quantize; do
  printf '%-14s' "$c"
  /tmp/qf/bin/quantfit $c --help 2>&1 | grep -qE '\-\-json'   && printf ' --json' || printf '       '
  /tmp/qf/bin/quantfit $c --help 2>&1 | grep -qE '\-\-report' && printf ' --report' || printf '         '
  /tmp/qf/bin/quantfit $c --help 2>&1 | grep -qE '\-\-out'    && printf ' --out'   || printf ''
  echo
done

# 2.2 - what runs with no GPU, no network, no weights
/tmp/qf/bin/quantfit list; /tmp/qf/bin/quantfit plan --model Qwen/Qwen2.5-7B-Instruct

# 2.3 - licence detection
gh api repos/Sahil170595/quantfit/license -q '.license.spdx_id'   # -> NOASSERTION
wc -l LICENSE; grep -c APPENDIX LICENSE                            # -> 154, 0
curl -s https://www.apache.org/licenses/LICENSE-2.0.txt | wc -l    # -> 202

# 2.4 - version flag
/tmp/qf/bin/quantfit --version; echo "exit=$?"                     # -> exit=2
```
