# Three fresh native GGUF runs

Native llama-server argv explicitly applies `--device none --n-gpu-layers 0
--no-op-offload`, including for a user-provided GPU-capable build. Its engine records
`offload_device: none`, `n_gpu_layers: 0`, `op_offload: false`; these causal controls
participate in calibration, cache and T0 identities. They are observed invocation
controls, not a measurement of GPU residency. A binary that rejects them fails
operationally. Pinned b9817 defaults can offload automatically, so `device: cpu`
alone was insufficient; the dated red/fix record is
`validation/2026-10-08-native-cpu-enforcement/`. Older run records are untouched.

`quantfit cold-run` creates a new aggregate-only directory, starts exactly three
sequential native `verify-safety` Python processes, and applies the existing
`within_hardware_identical` T0 checker to their actual report files. It supports
POSIX process sessions (the hosted Linux campaign path); Windows refuses before
creating output. Native `verify-safety` remains available on Windows.

```bash
quantfit cold-run --baseline hf:org/repo/model-f16.gguf \
  --quant hf:org/repo/model-q4.gguf \
  --baseline-revision <40-lowercase-hex-commit> \
  --quant-revision <40-lowercase-hex-commit> \
  --out cold-runs --timeout-seconds 3600 --max-new-tokens 64 --json
```

The same optional revision flags are available on `verify-safety`. They are
supported for `hf:` GGUF file refs only. The commit is passed to the installed
Hub downloader and checked against its returned snapshot path before metadata
or generation is consumed. An absent/different resolved commit, moving branch
name, unsupported transformers ref or revision attached to a local GGUF fails
closed. Local GGUF files retain observed byte hashes and no Hub revision.

Every run performs inference afresh: there is no demo, capture, arbitrary-command
or completion-cache option. Downloaded weight/binary caches may be reused. The
native pinned corpus/judge and greedy decode are unchanged. Stdout/stderr are
discarded; transient server logs stay in an owned temporary directory removed
after process-group termination. Existing environment credentials may be consumed
by native loaders; they are absent from argv and receipts.

`run-1/report.json` through `run-3/report.json` retain validated aggregate reports,
including flagged regressions and unmeasurable axes. `cold-run.json` records actual
child PIDs, invocations, elapsed times, per-child native exits, source report hashes,
companion hardware/resources and cleanup actions. `t0.json` is written only after
the T0 checker reconsumes all three sources and those hashes match the observed
buffers. Its original distinct-file, distinct-byte, uncached, identity and exact
drift requirements are unchanged.

| Cold-run exit | Meaning | Native measurement exits remain separate |
|---|---|---|
| 0 | Three valid runs and T0 protocol agreement | Child 0, 3 or 4 are retained; agreement is no scientific GO |
| 3 | Three valid runs and T0 drift disagreement | Negative T0 is retained without a tolerance change |
| 2 | Unsupported invocation, child operational failure/timeout, invalid report or T0 operational refusal | Partial validated reports/receipts remain; no positive T0 artifact |

Cancellation keeps its partial receipt and closes the active child session; the
interrupt itself propagates. Each session is signalled with TERM then KILL, including
descendants whose Python parent already exited, and the direct child is waited/reaped.
On Linux, `/proc` observations distinguish live group members from zombies. The
runner does not claim to wait/reap grandchildren, authenticate a physical host or
contain a process that deliberately leaves the owned session. Native llama-server
inherits the session. Group-cleanup failure prevents starting another run.
Reports are validated/removed on cancellation and cleanup failure as well as normal
exit. A cleanup-failed partial directory must never be qualified or published: a live
writer has not been excluded. Only validated aggregate negative evidence is portable.

CPU model/flags, total/available RAM, disk, actual native thread calculation and
reported device/arm-thread facts are companion observations. They do not modify
native `report.env`, whose full block participates in T0. GPU driver/toolkit/capability
are explicitly unobserved here. Observed fresh processes are not independent host
authentication, human adjudication, sensitivity evidence or reproduction. QSR v1
remains unfrozen.

Functional evidence is in `validation/2026-10-08-cold-replicate-runner/`. It substitutes
synthetic aggregate measurement output inside actual fresh native CLI children. It
does not execute models. Hosted installed model qualification is pending the later
reference campaign, which must identify unchanged runner/resolver/native source blobs.

The existing hosted `cpu-backend (gguf)` job also contains an installed cold consumer:
SmolLM2-135M at its pinned revision, a fresh F16 conversion (the quantizer removes
its own intermediate), and the Q4 artifact, default64/full40 across3 fresh children.
It accepts measured T0 disagreement and native negative exits as evidence, while
operational failures fail qualification. It checks installed origin/canonical source
bytes and CPU controls and retains aggregate JSON only. Execution is pending push.
