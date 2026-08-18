# Security policy

quantfit downloads and **executes** a prebuilt binary, downloads and **loads** third-party
model weights, and runs a language model on prompts designed to elicit unsafe output. Its
security posture is therefore mostly a supply-chain posture, and this file states it as one:
what runs, what is fetched, what is checked, and — the part that matters most — **what is
not checked.**

A control described as stronger than it is, is worse than no control. Every mechanism below
is cited to the file that implements it. Where quantfit does not check something, this file
says so instead of implying otherwise.

---

## 1. What quantfit executes

**A downloaded `llama.cpp` binary.** The GGUF path provisions and runs
`llama-quantize` and `llama-server` from a pinned upstream release
(`quantfit/backends/gguf.py`). This is arbitrary native code running on the operator's
machine, and the module is written accordingly:

- **The release tag, the commit, and the asset hashes are all pinned in source**:
  `LLAMACPP_TAG = "b9817"`, `LLAMACPP_COMMIT = "5397c361…"`, and per-asset SHA256 in
  `_BINARY_SHA256` (`backends/gguf.py:30-31,52-55`).
- **Every fetched archive is SHA256-verified before it is extracted or run.**
  `_verify_or_die` (`backends/gguf.py:95-109`) hashes the file and compares it to the
  pin; on mismatch it **deletes the file** and raises. `_download_verified`
  (`:112-124`) downloads to a temp path and only `os.replace`s it into the cache
  *after* the hash passes, so a partially downloaded or tampered archive never
  appears at the cache path at all.
- **An asset with no pin is a hard refusal, not a warning.** `_verify_or_die` raises
  before the download is even attempted if the asset name is absent from
  `_BINARY_SHA256`, telling the operator to build llama.cpp themselves and point
  `QUANTFIT_LLAMACPP` at it. Adding a platform means adding its hash.
- **An already-cached archive is re-verified before extraction** (`_llama_bin`,
  `backends/gguf.py:158-159`): existence is not integrity.
- **The pin gates *provisioning*, not *execution* — and an already-extracted binary is
  returned without being re-hashed.** Everything above is a statement about the
  **archive**, and stopping there would overstate the control, so: `_llama_bin`
  (`backends/gguf.py:_llama_bin`) checks `QUANTFIT_LLAMACPP` first, then looks for the
  executable already sitting in `~/.cache/quantfit/llamacpp-bin-<tag>/` (or
  `$QUANTFIT_CACHE`) and **returns it immediately if it is there** — before any of the
  archive logic runs. Only on a miss does it reach the download → `_verify_or_die` →
  `_extract` path. So the chain is `download → verify → extract`, and after that first
  successful extraction the SHA256 pin is never consulted again: `llama_server_bin()`
  and `llama_quantize_bin()` hand back a cached executable on trust. **An attacker who
  can write to your cache directory can replace that binary and quantfit will run it.**
  There is no pinned hash of the *extracted* executable to compare against — only of
  the archive it came out of. Note also that a `QUANTFIT_LLAMACPP` binary is never
  hashed at all, by design: you supplied it, so quantfit does not second-guess it
  (`_binary_source` records it as `user-provided build; tag not verified by quantfit`,
  so the report says which case applied).

  **What you actually have here:** (1) treat write access to the quantfit cache
  directory as equivalent to code execution on your machine, and keep it on a
  filesystem no other account can write — this is the real control; (2) to force
  re-provisioning from the verified archive, delete
  `~/.cache/quantfit/llamacpp-bin-<tag>/` (the archive alongside it is re-verified on
  the next run, so this is cheap and safe to do routinely); (3) **detection, not
  prevention** — every GGUF arm hashes the `llama-server` it actually executed and
  writes it into the report as `engine.binary_sha256`
  (`safety/gguf_arm.py:generate_completions`, `_sha256(server)` at `gguf_arm.py:228`),
  so a swapped binary shows up as a changed value across runs and across the two arms
  even though nothing compares it to a pin.
- **The convert-script clone is verified at the pinned commit, because tags are
  mutable.** `convert_script` (`backends/gguf.py:195-212`) shallow-clones into a temp
  directory, checks `git rev-parse HEAD` against `LLAMACPP_COMMIT`, refuses if the
  tag moved, and only then atomically promotes the clone.
- **This behavior is pinned by hermetic tests** — `tests/test_gguf_supply_chain.py`
  exercises the hash, the mismatch-delete, and the no-pin refusal without touching the
  network or executing anything.

`QUANTFIT_LLAMACPP` bypasses provisioning entirely and uses a local checkout
(`backends/gguf.py:148-150,181-183`). If you do not want quantfit downloading a binary,
that is the supported way to say so.

**A local `llama-server` on loopback.** GGUF arms generate through a server subprocess
bound to `--host 127.0.0.1` on an ephemeral free port (`quantfit/safety/gguf_arm.py:196-197`,
port from `_free_port` at `:259`), and quantfit talks to it over `http://127.0.0.1:<port>`
(`:272,291,299`). It is not exposed off the machine, and no remote inference endpoint is
contacted for any part of the measurement.

**`git`** — invoked as a subprocess for the pinned shallow clone above
(`backends/gguf.py:195-198`).

---

## 2. What quantfit downloads

| what | from | pinned how |
|---|---|---|
| the refusal judge | Hugging Face, `garak-llm/garak-refusal-detector` | exact revision `b34061f9…` (`safety/verify.py:87`) |
| the probe corpus | Hugging Face, `Crusadersk/quantsafe-judge-benchmark`, split `train` | exact revision `c26cc2e1…` (`safety/verify.py:89`) |
| the model under test + its baseline | Hugging Face, or a local path you pass | whatever you named; the resolved revision is recorded in the report |
| `llama.cpp` binaries + convert script | `github.com/ggml-org/llama.cpp` release `b9817` | SHA256 per asset + pinned commit (§1) |

The judge and the corpus are loaded at those revisions on every run
(`safety/verify.py:517,604-605`) and both IDs and revisions are written into every
schema-v2 report (`safety/verify.py:397-413`), so a report names the artifacts it
actually used. Those pins are normative in `spec/qsr-v0.md`; changing one changes what
past numbers mean (see `CONTRIBUTING.md` §4).

Hugging Face access uses `--token` or the ambient `HF_TOKEN` for gated or private
models. quantfit does not store, log, or transmit the token anywhere other than to the
Hub client.

---

## 3. What quantfit does not do

- **No telemetry, no analytics, no phone-home.** There is no usage reporting of any
  kind. The only outbound network destinations in the package are the Hugging Face
  Hub, `github.com` for the pinned llama.cpp release, and `127.0.0.1` for the local
  server.
- **No automatic upload of anything.** Reports, screen summaries, gate decisions,
  captures, caches and model cards are written to paths you name, on your machine, and
  stay there. **The one upload path in the entire tool is explicit and operator-driven:**
  `quantfit quantize --push <repo-id>` calls `HfApi.upload_folder` on the quantized
  output directory you just produced (`quantfit/quantize.py:106-113`). Nothing else
  uploads, and nothing uploads without that flag.
- **Model output is never executed.** Completions are generated, passed to the judge
  tokenizer for classification, and tabulated as booleans. Nothing in the tree
  `eval`s, `exec`s, shells out to, deserializes, or otherwise interprets generated
  text.
- **`trust_remote_code` is never enabled.** quantfit passes it nowhere, and the
  Inspect runner refuses it explicitly as a forwardable model argument, with the reason
  recorded in source: *"it lets the checkpoint ship the code that defines the model and
  its generation; that is a different thing generating, and it is also arbitrary code
  execution on the operator's box"* (`quantfit/inspect_task.py:413-414`). That refusal
  sits inside an **allowlist**, not a denylist — `MODEL_ARG_ALLOWLIST`
  (`inspect_task.py:349-360`) — so a new upstream argument is refused by default rather
  than forwarded by accident.
- **Reports contain no model completions.** Schema-v2 `DriftReport` has no completion
  field, screen summaries are counts and provenance, `SafetyDrift.summary()` is
  aggregates-only, and `calibrate.ingest_labels` writes counts, rates and intervals.
  This is structural, not a convention.

### The three surfaces that *do* persist completion text

Stated in full, because "quantfit does not store model output" would be false:

1. **`--capture PATH`** — opt-in, off by default, one JSONL per run. Governed by
   [`docs/data-handling-completions.md`](docs/data-handling-completions.md), which is
   *the recorded data-handling decision itself*, not a summary of one. Every file
   carries its own warning header (`safety/verify.py:110`), the capture is written
   after the report from values the run already computed so it cannot change a
   measurement (`safety/verify.py:427-481`), and retention is short and terminal
   (that document, §3).
2. **The gate's baseline cache** (`quantfit/safety/cache.py`) — cached baseline-arm
   completions, keyed by a derived fingerprint. Every entry header repeats the
   completion-text warning verbatim — `safety/cache.py:COMPLETION_TEXT_WARNING`, cited
   by symbol rather than by line because line citations rot. Local-only; never
   committed or shared.
3. **Inspect eval logs** — `logs/` and `*.eval`, which hold completions the same way a
   capture does.

All three are covered by `.gitignore` (`*.capture.jsonl`, `*.labels.csv`,
`*.labelkey.json`, `*.baseline-cache.json`, `logs/`, `*.eval`). That is a **backstop
against `git add -A`, not a boundary** — `git add -f` defeats it, and a file written
outside the mandated naming convention is unignored. Do not commit one, and do not
attach one to an issue, a PR, or a report.

The cache's integrity check deserves the same honesty its own docstring gives it: `load`
re-derives the fingerprint from the entry's stored inputs and refuses the entry unless it
matches both the stored digest and the key it was filed under — but **this is an integrity
check against editing and misfiling, not authentication.** There is no secret, so someone
with write access to your cache directory who edits the inputs, recomputes the digest and
renames the file can forge an entry. What bounds that risk is that the cache is local-only
(`safety/cache.py`, module docstring).

---

## 4. The honest limit: a quantized artifact is arbitrary code to a loader

quantfit's job is to run **third-party model weights** on your machine. That is the
threat surface, and no amount of pinning inside quantfit changes it.

**What quantfit checks about an artifact:**

- GGUF arms read `file_type` and `architecture` **from the file's own metadata, never
  from the filename**, and refuse a quantized baseline or an architecture mismatch
  before any server starts (`quantfit/safety/gguf_arm.py`, `resolve_pair`).
- `quantfit verify` on a GGUF path reads **four bytes** — the `GGUF` magic — and does
  not load or execute the file (`quantfit/verify.py:_verify_gguf`). The help text says
  "structural magic check only" for exactly this reason.
- Artifact identity is recorded for audit: a GGUF arm carries the file's own
  `artifact_sha256` (`safety/gguf_arm.py:101,239`); a transformers arm carries the
  resolved HF commit instead, with `artifact_sha256=None` because a snapshot is a
  directory (`safety/verify.py:554,573`). The GGUF arms also record
  `binary_sha256` of the `llama-server` actually run (`gguf_arm.py:228`), which is
  what makes the same-binary mandate auditable from the report alone.

**What quantfit does not check, and what that means:**

- **A malicious GGUF is untrusted input to llama.cpp's C++ parser.** When you run a
  GGUF arm, `llama-server` memory-maps and parses a file you obtained from a third
  party. quantfit verifies the *binary* it runs; it does nothing to validate the
  *model file* beyond the metadata reads above. Malformed-GGUF parser bugs are a real
  class of upstream vulnerability, and quantfit's pinning means you are running a
  specific, possibly not-latest llama.cpp against that file.
- **A transformers artifact is loaded and generated from.** `quantfit verify` on a
  directory calls `AutoModelForCausalLM.from_pretrained(...)` and generates
  (`quantfit/verify.py:_verify_transformers`). `trust_remote_code` is off, so a
  checkpoint cannot ship Python that defines the model — but **quantfit does not pass
  `use_safetensors=True` anywhere**, so a repository that ships only
  `pytorch_model.bin` will be deserialized by `transformers`/`torch` through pickle.
  Pickle deserialization is arbitrary code execution. Prefer safetensors-only
  checkpoints, and treat any `.bin`-only artifact as untrusted code, not data.
- **The judge is a model, not an oracle.** Its in-distribution error rate has never
  been measured (ROADMAP 0.6, gated on a 0.5 GO). Every resolution claim quantfit
  prints without `--eps-upper` is labeled a perfect-judge *floor*. This is a
  correctness limit rather than a security one, but it belongs in the same list of
  things not to over-read.

**Practical guidance:** run screens of untrusted artifacts in a container or a VM. The
repository ships a `Dockerfile` for an isolated CUDA image, and for GGUF work the
official `ghcr.io/ggml-org/llama.cpp:full` image carries the convert and quantize
tooling. Quantization and GGUF arms are CPU work and containerize cleanly.

---

## 5. Reporting a vulnerability

**The intended channel is GitHub's private vulnerability reporting** on
[`Sahil170595/quantfit`](https://github.com/Sahil170595/quantfit) — repository
**Security** tab → **Report a vulnerability**. It keeps the report private until there
is a fix, and it is where a report should go if it is available to you.

**Stated honestly: nothing in this repository proves that it is turned on.** Private
vulnerability reporting is a GitHub repository setting, not a file, so it cannot be
verified from a clone or a release tarball — including by whoever wrote this sentence.
If the Security tab shows no "Report a vulnerability" button, the setting is off and
the paragraph above is aspirational rather than actionable.

**The fallback, which always works:** open a public issue containing **only** the words
"requesting a private channel for a security report" — no details, no reproduction, no
affected file. That discloses nothing exploitable and gets a private channel opened.
Use it whenever the private path is unavailable *or* you are unsure.

Please do not open a public issue with details for anything that would let someone else
exploit users before a fix exists.

**What is useful in a report:** the affected file and function, the version or commit,
what an attacker controls (a model repo? a GGUF file? a cache directory? a report
JSON?), and the smallest reproduction you have. Reproductions that require network
access or a real model download are fine — say so, and describe the artifact rather
than attaching one.

**In scope:** anything in this repository — the pinned-hash verification path, the GGUF
provisioning and clone-verification logic, subprocess invocation, report and cache
parsing, the capture and calibration files, and the CI workflows and reference Action.

**Out of scope, and why:** vulnerabilities in upstream dependencies
(`torch`, `transformers`, `llama.cpp`, `huggingface_hub`) belong upstream — though a
report that quantfit's *pin* points at a version with a known vulnerability **is** in
scope and welcome, because moving that pin is quantfit's decision. Harmful *content*
produced by a model under test is not a vulnerability in quantfit; eliciting it is what
the probe corpus is for.

**Expectations, stated honestly:** quantfit has **one maintainer** and offers **no
response-time commitment** — no SLA is claimed here or anywhere else in this repository,
and none should be inferred. See [`docs/bus-factor.md`](docs/bus-factor.md) for what that
means in practice. Reports are read and acted on as capacity allows; a fix for a
verified issue will be noted in `CHANGELOG.md` with the same "what was and was not
delivered" discipline every other change gets.
