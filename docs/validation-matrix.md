# Validation matrix — what has actually been run, on what, with what evidence

**Status:** audit. ROADMAP milestone 1.0 requires *"every advertised command
hardware-validated"*. **That is not true today, and this document is the list of why
not.** It exists to be uncomfortable: every row that says UNVALIDATED is a claim
quantfit currently makes on the strength of unit tests and prose alone.

**Method.** Every row below is transcribed from an artifact in this repository —
`CHANGELOG.md`, a `docs/` protocol file, a workflow in `.github/`, or a test file —
and cites it. Nothing is included because it "obviously works". Where a run is
*implied* by a bug fix rather than *recorded* with numbers, the row says so and does
not count as validation.

**Scope note, stated first.** No run artifact of any kind is committed to this
repository: `out/` and `.benchmarks/` are empty, `quantfit/refreports.py:REGISTRY` is
`()`, and no drift report, gate artifact or screen summary is tracked. Every
quantitative claim below is therefore **transcribed CHANGELOG prose**, not a file you
can re-hash. That is itself a finding, and it is the ceiling on how strong any row can
be until the 0.5 screen runs and a reference report exists
(`docs/reference-reports-v0.md`, front matter).

---

## 0. Definitions, so the table cannot be read charitably

### 0.1 How the command list was enumerated

`quantfit --help` declares 11 subcommands: `check, list, plan, probe, verify,
verify-safety, screen, emit, calibrate, gate, quantize`. Two of them are parents:
`emit` takes a `choices=("model-card",)` positional and `calibrate` has the subparsers
`sheet` and `ingest`. **Leaf command paths = 11 − 2 parents + 3 leaves = 12.** Flags
are audited separately in §3, because a validated command with an unvalidated flag is
an unvalidated flag.

### 0.2 The evidence ladder

| level | means | counts as "hardware-validated"? |
|---|---|---|
| **E1** | a recorded run on named hardware **with numbers** (timings, memory, verdicts) | yes |
| **E2** | executed by a CI job on a named runner, exit status asserted | yes, for commands that need no GPU |
| **E1‑weak** | a run asserted in the CHANGELOG with **no hardware named and no numbers** | no — unreproducible, and often under superseded semantics |
| **E0‑implied** | a run is *implied* by a fixed defect ("X used to traceback"), nothing recorded | no |
| **E3** | hermetic unit tests, heavy paths mocked | no — proves logic, not that the command runs |
| **E0** | nothing | no |

E3 is not a weak form of E1. `tests/test_gate.py` monkeypatches `verify_safety`
outright; it proves the decision rule, and says nothing about whether the gate can
load a model.

### 0.3 Every machine that has ever run this tool

| id | hardware | what ran on it | evidence |
|---|---|---|---|
| **L** | RTX 4080 Laptop (Ada, sm_89, 12 GB), 68.3 GB RAM, 32 logical cores, Windows | both 0.4b hardware gates; the only GPU any recorded quantfit run has used | `CHANGELOG.md` §0.4.1; `docs/cross-hardware-tolerance-v0.md` §"L"; `docs/sensitivity-control-v0.md` §3.1 |
| **CI** | GitHub-hosted `ubuntu-latest` + `windows-latest`, x86‑64, **no GPU** | `pytest` on py3.10–3.14; wheel build + clean-venv install + `quantfit --help` / `list` / `gate --help` | `.github/workflows/ci.yml` (`test`, `install-smoke`), `.github/workflows/canary.yml` (`quickstart-install`) |
| **W** | this checkout's box, Windows 11, py3.13.1, torch 2.11.0+cu128, GPU masked | one `quantfit plan` run, 2026‑08‑07, via `tools/quickstart_check.py` | §2 `plan` row |

Never used, by anything: **Tesla T4, Colab, Kaggle, any free tier**
(`docs/cross-hardware-tolerance-v0.md` §6.1 — "no T4, Colab or Kaggle run of any kind
has happened"), **Ampere, Hopper, Blackwell, A100/H100/L4**, **macOS**, **ARM**,
**multi-GPU**, **any non-Windows GPU host**. Every GPU number this project has ever
published comes from one laptop.

### 0.4 The weekly canary is not evidence of anything yet

`.github/workflows/canary.yml` asserts real properties (zero flips under identical
arms; `gate --threshold 1` must exit 5). It is **not cited as validation anywhere
below**, because no run of it is evidenced: its own header says the runtime budget is
"ESTIMATED — not yet measured on a runner; the first scheduled run replaces these
numbers", and GitHub runs `schedule:` triggers only on the default branch. Whether it
has ever executed cannot be established from this repository. When a run exists,
several E0 rows below become E2 and this section is what should be edited.

---

## 1. Headline verdict against ROADMAP 1.0

> "every advertised command hardware-validated"

**NOT MET.** Of 12 leaf command paths (§0.1):

- **3 have an E1 run on real GPU hardware**: `quantize`, `verify`, `verify-safety` —
  all on machine **L**, all from the 0.4b gates, and all **partially** (see §2).
- **2 more have a recorded no-GPU execution** that is the right validation for them:
  `list` (E2, both OSes) and `plan` (E2‑pending / one E1‑weak local run).
- **7 have no recorded execution at all**: `check`, `probe`, `screen`,
  `emit model-card`, `calibrate sheet`, `calibrate ingest`, `gate`.

Filter used for that count: the 12 leaf paths of §0.1; a path counts as "run" only if
some artifact in this repo asserts an execution of *that path*. 3 + 2 + 7 = 12.

Two further clauses of the same milestone, for the record: the **spec cannot be
frozen** (`spec/qsr-v1-freeze-plan.md` — v1 needs the ε‑calibrated MDE from GO‑gated
0.6 and a calibrated tolerance from an unrun T4), and the **1.0 gate cannot be met**
here (no third-party reproduction, citation or gate adoption exists; no two
cross-release runs have been compared; the 0.5 screen has not run).

---

## 2. Per-command matrix

### `quantfit list`

| | |
|---|---|
| **Validated** | E2. Runs on `ubuntu-latest` and `windows-latest` from a clean-venv install of the built wheel, exit status asserted (`shell: bash` runs `bash -e`). |
| **Hardware** | CI (no GPU needed — the catalog is a constant table in `quantfit/registry.py`). |
| **Evidence** | `.github/workflows/ci.yml` (`install-smoke` → "CLI smoke"); `.github/workflows/canary.yml` (`quickstart-install` → "CLI smoke"); `tests/test_registry.py` (8 tests), `tests/test_cli.py::test_list_runs_and_prints_methods`. |
| **NOT validated** | That the catalog it prints matches what `quantize` can actually produce — every non-default scheme in the table is emitted but never load-tested (§3, `--scheme`). |
| **Advertised in README?** | **No.** The README never shows `quantfit list` (§4, finding 2). |

### `quantfit plan --model <id> [--prefer ...]`

| | |
|---|---|
| **Validated** | **E1‑weak.** One recorded execution: 2026‑08‑07 on **W**, `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CUDA_VISIBLE_DEVICES=-1`, exit 0, via `tools/quickstart_check.py`. That exercised the **CPU-only branch** (`route()` rule 1 → GGUF Q4_K_M) from the **source tree**, not the built wheel. |
| **Hardware** | W (GPU masked). Never recorded on a GPU, so the `device=cuda` branch of `detect_target()` — the one the README's example actually hits on a reader's box — has **no recorded run**. |
| **Evidence** | this PR's `tools/quickstart_check.py` run; `tests/test_route.py` (8), `tests/test_engines.py` (5), `tests/test_target.py` (1) — all E3. |
| **NOT validated** | The CUDA branch; `--prefer speed` on an FP8-native arch; `--prefer size`; the rationale strings on any real GPU; behavior on a CUDA host with zero visible devices — where it is **known broken** (§5, defect 1). |
| **Becomes E2 when** | the orchestrator wires `tools/quickstart_check.py` into `install-smoke` / `quickstart-install` (proposed in this PR's report). |

### `quantfit check --model <id>`

| | |
|---|---|
| **Validated** | **Nothing.** E0‑implied only: 0.4.0 fixed "a weightless/gated repo in `check` now exits 2 cleanly (was a raw ValueError traceback)", which implies someone ran it once; no hardware, no numbers, no artifact. |
| **Hardware** | none recorded. |
| **Evidence** | `CHANGELOG.md` §0.4.0 (the fix); `tests/test_fit.py` (6 tests, E3 — the capacity arithmetic against synthetic sizes). |
| **NOT validated** | The 3‑tier verdict against a real Hub model on any machine; the disk/RAM/VRAM thresholds against a real OOM; the exit‑3 "won't fit" path; `--token` on a gated repo. The README leads with this command. |

### `quantfit probe --model <id> --bits ...`

| | |
|---|---|
| **Validated** | **Nothing.** E0‑implied: 0.2.0's audit pass fixed "per-token KL normalization in the probe", implying a run; nothing recorded. |
| **Hardware** | none recorded. |
| **Evidence** | `CHANGELOG.md` §0.2.0; `tests/test_probe.py` (3 tests, E3). |
| **NOT validated** | Any KL number this command has ever printed. No probe output is recorded anywhere in this repo, so the "RTN‑KL is a conservative upper bound" framing has no measured example behind it, on any model, at any bit-width. |

### `quantfit quantize --model <id> --method <m> [--scheme ...] --out <dir>`

| | |
|---|---|
| **Validated** | **E1, partial.** Over‑VRAM `gptq` on **L**: Qwen2.5‑7B (15.2 GB bf16) through llm-compressor sequential onloading, GPU peak 9,047 MiB on a 12,282 MiB card, process RSS peak 28.1 GB (telemetry sampled every 5 s), ~32 min end-to-end, `verify` PASS on the artifact. **E1‑weak** for the in‑VRAM path: 0.1.0 asserts end-to-end validation on qwen2.5‑1.5b for `awq` / `fp8` / `gptq` / `smoothquant` / GGUF‑Q4_K_M — no hardware named, no numbers, and under 0.1‑era code. |
| **Hardware** | L (over‑VRAM gptq). In‑VRAM: unnamed. |
| **Evidence** | `CHANGELOG.md` §0.4.1 ("Hardware gates (ROADMAP 0.4b)"), §0.1.0; `tests/test_dispatch.py` (7, E3 — routing, `--no-check`, card provenance), `tests/test_gguf_supply_chain.py` (9, E3 — binary SHA256 pin/verify/atomic promote). |
| **NOT validated** | **`--method rtn` — never in any validated list** (0.1.0's list omits it) while the README's method table advertises it. **AWQ at over-VRAM sizes is a recorded FAILURE, not a validation**: ~2 h observed for a single 7B layer, projecting 50+ h. Every non-default `--scheme` (§3). `--push` / `--private` (no upload has ever been recorded). FP4 schemes on Blackwell — no Blackwell exists in §0.3. |

### `quantfit verify --model <path>`

| | |
|---|---|
| **Validated** | **E1, narrow.** `verify` PASS on the 7B GPTQ artifact produced by the 0.4b over‑VRAM gate, on **L**. E1‑weak: 0.1.0's "transformers load-smoke-test". |
| **Hardware** | L. |
| **Evidence** | `CHANGELOG.md` §0.4.1, §0.1.0; `tests/test_verify.py` (3, E3). |
| **NOT validated** | The GGUF branch (structural magic-bytes check only — scope corrected in 0.4.0 after the docs overstated it, but no GGUF `verify` run is recorded). The exit‑3 FAIL path on a genuinely broken artifact — nothing has ever been observed failing. |
| **Advertised in README?** | **No** (§4, finding 2). |

### `quantfit verify-safety --baseline B --quant Q [--max-new-tokens N] [--report P] [--capture P]`

| | |
|---|---|
| **Validated** | **E1, GGUF stratum only.** On **L**: `bartowski/Qwen2.5-7B-Instruct-GGUF` Q4_K_M vs its F16 under the identical pinned llama.cpp binary, both arms CPU, F16 arm (15.24 GB) 559 s, Q4 arm 225 s, 16 threads. Verdict: over-refusal 2/14 at-risk (14.3%, 95% CI 4.0–39.9%) with the scalar refusal count unchanged (14→14); dangerous axis 0/12 (upper 24.2%). Drift vector byte-identical on rerun (0.5B pair). |
| **Hardware** | L, **CPU** (that is the GGUF path's design — one binary, both arms). |
| **Evidence** | `CHANGELOG.md` §0.4.1; `tests/test_safety.py` (18), `tests/test_gguf_arm.py` (17), `tests/test_report.py` (12), `tests/test_stats_scipy.py` (2, scipy cross-check) — all E3. |
| **NOT validated** | **The transformers-vs-transformers path under the shipped verdict machinery** — i.e. the README's own headline example. A transformers-arm run is *implied* by 0.4.0 ("the live report proved the arm loads at its NATIVE dtype"), but that produced a **schema‑v1** report, which the shipped parser now refuses outright; no artifact survives. Also unvalidated: `--capture` (never run: `docs/judge-calibration-v0.md` — "No completion has been labeled"), `--max-new-tokens` at any value but the default, any GPU-resident arm on any GPU but L, and every model family outside Qwen2.5. |

### `quantfit screen --targets <manifest> --out <dir>`

| | |
|---|---|
| **Validated** | **Nothing. The 0.5 screen has never run.** |
| **Hardware** | none. |
| **Evidence (of non-run)** | `docs/reference-reports-v0.md` front matter — "The 0.5 existence-proof screen has not run either, so no report of any pair exists to publish"; `CHANGELOG.md` §0.5.0 — "The hunt runs themselves, the control run, the replication package, outreach, and the GO/NO-GO clock are NOT in this release". `screens/targets-0.5.json` is a **curated target list, not results**. E3: `tests/test_screen.py` (20, `verify_safety` monkeypatched). |
| **NOT validated** | Everything: aggregation over a real manifest, the per-stratum bounds, the conditionality labeling in a real run, per-target operational-failure recovery, and the wall-clock/disk budget for 15 targets. The sensitivity control that would license the bounds has also not run (`docs/sensitivity-control-v0.md`, front matter). |

### `quantfit emit model-card --report <drift.json>`

| | |
|---|---|
| **Validated** | **Nothing.** No run recorded, and there is no report to feed it: zero drift reports are committed. |
| **Hardware** | none (it needs none — it is a pure renderer; "hardware validation" for this command means "run once on a real report"). |
| **Evidence** | `CHANGELOG.md` §0.5.0 (shipped); `tests/test_modelcard.py` (21, E3, synthetic reports). |
| **NOT validated** | Rendering a report produced by an actual run; the `vllm serve` / `llama-server` command strings it emits have never been executed. |

### `quantfit calibrate sheet` / `quantfit calibrate ingest`

| | |
|---|---|
| **Validated** | **Nothing, by design.** The labeling work is GO-gated on a 0.5 decision that has not been made. |
| **Hardware** | none. |
| **Evidence (of non-run)** | `docs/judge-calibration-v0.md` front matter — "machinery, **not started** … No completion has been labeled, no ε has been measured"; `CHANGELOG.md` §0.5.1. E3: `tests/test_calibrate.py` (53). |
| **NOT validated** | The round trip through a real spreadsheet (the blinded CSV has never been opened by a labeler, and spreadsheet mangling is the documented threat model), and every ε‑consuming number downstream. |

### `quantfit gate --baseline B --quant Q (--threshold PP | --tier T) [--eps-upper R --eps-source S]`

| | |
|---|---|
| **Validated** | **Nothing.** No gate has been run on hardware. `CHANGELOG.md` §0.5.2 states it outright: "Not in this release: … any measured judge error — so ROADMAP 0.7's gate criteria are not claimed as met." |
| **Hardware** | none. (`gate --help` is exercised by `quickstart-install`; a help string is not the command.) |
| **Evidence** | `tests/test_gate.py` (60, E3 — `verify_safety` monkeypatched, so no model is ever loaded); `tests/test_mde.py` (34), `tests/test_stats_scipy.py`. |
| **NOT validated** | Both resolution refusals against a real run; the exact-binomial verdict at a realized `n`; the exit‑5 pre-run refusal on real hardware (asserted only in the unrun canary); `--eps-upper` (no ε exists to supply — supplying one today is a hypothetical, per `quantfit/gate.py`); `--report` / `--out` artifacts from a live gate. **The baseline cache (`quantfit/safety/cache.py`) is not called by `gate` at all** — §0.5.2, "The baseline cache is library surface: `quantfit gate` does not yet call it." |

---

## 3. Major flags

| flag | command(s) | validation | evidence / gap |
|---|---|---|---|
| `--model` | check, plan, probe, quantize, verify | E1 for quantize/verify on L; E0 elsewhere | §2 |
| `--method` | quantize | `gptq` E1 (over‑VRAM, L); `awq`/`fp8`/`smoothquant`/`gguf` E1‑weak (0.1.0, 1.5B); **`rtn` E0** | `CHANGELOG.md` §0.1.0 omits `rtn` from the validated list |
| `--scheme` | quantize | **defaults only.** `quantfit/registry.py`: "The per-method DEFAULT schemes are validated end-to-end; the other presets are accepted and emitted, not each individually load-tested" | `quantfit/registry.py:SCHEMES` advertises 9; the 5 methods' defaults cover 4 distinct ones (`W4A16`, `W4A16_ASYM`, `W8A8`, `FP8_DYNAMIC`), so 5 of 9 schemes have never been produced by a validated run; `NVFP4`/`MXFP4` need Blackwell to serve and no Blackwell has run anything |
| `--out` | quantize, screen, gate, calibrate | E1 for quantize (L); E0 elsewhere | §2 |
| `--push` / `--private` | quantize | **E0** — no upload to the Hub has ever been recorded | no CHANGELOG entry claims one |
| `--no-check` | quantize | E3 only (`tests/test_dispatch.py`) | never exercised against a real too-big model |
| `--token` | check, plan, probe, verify-safety, screen, gate, quantize | **E0** — no gated/private model run is recorded | parser-level only (`tests/test_cli.py`) |
| `--prefer` | plan | E3 (`tests/test_route.py`) | no recorded run of any value |
| `--bits` | probe | **E0** | parser-level only |
| `--baseline` / `--fp16` | verify-safety, gate | E1 for the GGUF arm on L; the legacy `--fp16` alias is parser-tested only | `CHANGELOG.md` §0.4.0 (rename), §0.4.1 |
| `--quant` | verify-safety, gate | E1 (GGUF, L) | §2 |
| `--max-new-tokens` | verify-safety, screen, gate | **only the default (64) has ever run** | the canary's 32 is unrun (§0.4) |
| `--report` | verify-safety, gate | E1‑implied for the 0.4b GGUF run (schema v2 numbers are quoted from it); **the file is not committed** | `CHANGELOG.md` §0.4.1 |
| `--capture` | verify-safety | **E0** | `docs/judge-calibration-v0.md`: nothing captured, nothing labeled |
| `--eps-upper` / `--eps-source` | gate | **E0, and unusable**: no ε has been measured for this instrument | `quantfit/gate.py` "Epsilon: the number nobody has measured"; `CHANGELOG.md` §0.5.1 |
| `--targets` | screen | **E0** | the screen has not run |
| `--tier smoke` / `--tier full` | gate | tier CONSTANTS are asserted by `quickstart-install` (threshold 0.30, the ">=30pp" disclosure); the tiers have never gated a real quant | `.github/workflows/canary.yml` (`quickstart-install`, "smoke tier OK") |

---

## 4. Advertised-but-unevidenced claims found while writing this

These are docs=code findings, not command rows. Each is a claim on a shipped surface
with no artifact behind it.

1. **`README.md`:158 claims validation "on small models (Qwen‑1.5B, Llama‑1B)".**
   There is **no Llama‑1B validation anywhere in this repository.** `CHANGELOG.md`
   §0.1.0's validated list names qwen2.5‑1.5b only. Every other Llama‑1B string in the
   repo is a *screen target* (`screens/targets-0.5.json`) — a curated candidate, and
   the screen has not run. Either a run is recalled but unrecorded (then it is not
   evidence) or the claim is wrong; either way it must not stand as written.
2. **`quantfit list`, `quantfit verify` and `quantfit calibrate` never appear in the
   README.** Reverse drift: shipped commands with no advertised entry point.
   (Machine-checked: `tools/quickstart_check.py` reports them under
   "CLI subcommands the README never shows".)
3. **The README quickstart contains exactly one command a clean venv can run**
   (`plan`). ROADMAP 1.0's gate clause — "scripted README-only quickstart passes in a
   clean venv" — is therefore satisfiable today but nearly vacuous. See this PR's
   report for the proposed README/CI change.
4. **`quantfit.reproduce`, `quantfit.refreports` and `quantfit.inspect_task` are not
   reachable from the CLI** (`CHANGELOG.md` §0.5.3 discloses this: "none of the three
   new modules is reachable from the CLI"). They are library surface with E3 coverage
   only (`tests/test_reproduce.py` 75, `tests/test_refreports.py` 41,
   `tests/test_inspect_task.py` 79) and are therefore **out of scope for "every
   advertised *command*"** — but they are advertised in the CHANGELOG.
5. **`quantfit/safety/cache.py` is dead weight at runtime**: 53 tests, no caller.

---

## 5. Defects found by running the advertised commands

**Defect 1 — `detect_target()` trusts `torch.cuda.is_available()` alone, and the
resulting crash escapes quantfit's error taxonomy.**

Observed 2026‑08‑07 on **W** (Windows 11, py3.13.1, torch 2.11.0+cu128) while running
`quantfit plan --model Qwen/Qwen2.5-7B-Instruct` with `CUDA_VISIBLE_DEVICES=""`:

```
  File "quantfit/policy/target.py", line 43, in detect_target
    major, minor = torch.cuda.get_device_capability()
AssertionError: Invalid device id
```

Measured directly: with `CUDA_VISIBLE_DEVICES=""`, `torch.cuda.is_available()` is
**True** while `torch.cuda.device_count()` is **0**; with `CUDA_VISIBLE_DEVICES="-1"`
availability is False and the CPU branch is taken. `quantfit/policy/target.py:41`
branches on `is_available()` only, so on a host in that state it enters the CUDA
branch and reaches line 43. `AssertionError` is neither `RuntimeError` nor `OSError`, so
`quantfit/cli.py:main`'s handler does not catch it: the user gets a traceback and
**exit 1**, violating the documented contract that operational failures exit 2 with a
clean message. `tools/quickstart_check.py` therefore masks the GPU with `-1` rather
than `""`, and this row records why.

---

## 6. What would move each row, cheapest first

| cost | action | rows it fixes |
|---|---|---|
| minutes, CI | wire `tools/quickstart_check.py` into `install-smoke` + `quickstart-install` | `plan` → E2 on two OSes |
| minutes, local | run `check`, `probe`, `emit`, `calibrate sheet/ingest` once each and record the output in the CHANGELOG | 5 rows E0 → E1‑weak |
| one GPU hour, L | one transformers-vs-transformers `verify-safety` at 1.5B **with `--report`**, artifact committed | closes the biggest gap in §2 — the README's headline example |
| one GPU hour, L | one `gate --tier smoke` end-to-end against that pair, `--out` artifact committed | `gate` E0 → E1 |
| one GPU day, L | `quantize --method rtn` and one non-default `--scheme`, each `verify`-checked | `--method rtn`, `--scheme` |
| the 0.5 GO | the screen, the sensitivity control, then ε calibration | `screen`, `calibrate`, `--eps-upper`, and QSR v1's preconditions |
| a free T4 | the 0.8 reproduction | `docs/cross-hardware-tolerance-v0.md` §6.1, and the second machine this project has never had |

---

## 7. Provenance of this document

Written 2026‑08‑07 against branch `release/1.0`. Sources, in the order they were
consulted: `CHANGELOG.md` (all sections), `README.md`, `quantfit/cli.py` (the command
and flag enumeration, read from `_build_parser`), `quantfit/registry.py`,
`quantfit/policy/route.py`, `quantfit/policy/target.py`, `quantfit/fit.py`,
`.github/workflows/{ci,canary}.yml`, `docs/{reference-reports-v0,cross-hardware-tolerance-v0,judge-calibration-v0,sensitivity-control-v0}.md`,
`spec/qsr-v1-freeze-plan.md`, and `tests/` (test counts derived by grepping
`^def test_` per file). The `plan` run and the torch measurement in §5 were performed
while writing it; nothing else here is a new run, and no row was upgraded on the
strength of code review alone.
