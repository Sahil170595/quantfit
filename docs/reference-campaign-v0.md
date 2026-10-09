# Bounded hosted Phi4 publication campaign

This is the execution plan written before the new measurement. It applies
`docs/reference-reports-v0.md` §5 and the existing native T0 protocol without
changing the QSR v0 decision rule. Historical Phi4 flags are planning evidence,
not confirmation of new flags or a result of this campaign.

The existing `CI` workflow is dispatched once on `codex/qsr-v0-publication`.
The branch-specific campaign job waits for candidate validation, installs the
exact candidate wheel into the locked CPU runtime, and executes outside the
checkout. Pull requests and report/documentation commits do not run this heavy
job. An explicit second dispatch is a new campaign, never a metadata update.

| input | immutable value |
|---|---|
| repository | `unsloth/Phi-4-mini-instruct-GGUF` |
| revision, both arms | `78eb92a46fc37e6b524df991ed9aca9bc6aa7b80` |
| baseline | `Phi-4-mini-instruct.BF16.gguf`, 7,680,694,240 bytes |
| baseline SHA256 | `1a179f22f1efe409c6517805400c4f07f93fe1f5783e47231d35f933565dff20` |
| quantized arm | `Phi-4-mini-instruct-Q4_K_M.gguf`, 2,491,874,272 bytes |
| quantized SHA256 | `88c00229914083cd112853aab84ed51b87bdf6b9ce42f532d8c85c7c63b1730a` |
| native engine | supported SHA-verified `b9817` Ubuntu release archive; actual executable hash recorded |
| judge / probes | existing `verify.JUDGE_REVISION` / `verify.PROBE_DATASET_REVISION`; full 40 probes |

The public invocation intentionally omits `--max-new-tokens` to observe the
shipped default. All three actual native child argv and reports must apply 64,
greedy decoding, and the existing explicit CPU offload controls. Native threads
are the actual `_threads()` value; there is no override. Each arm is resident
sequentially, and the real judge loads after native servers close. The job records
CPU model/flags, total/available RAM and disk after installing the runtime and
after downloading the actual files. It does not assert peak RSS or invent a RAM
admission multiplier. Weight caches can be reused; completion caches/captures
are never requested. Each fresh child has a 3,600-second deadline; the job is
bounded at 240 minutes. No GPU, paid machine or local model download is used.

The existing cold-run T0 is retained unchanged and recomputed from its sources.
Full report repeatability is a separate requirement: compare all payload fields
and permit differences only at `/created_utc`, `/judge_runtime_s`,
`/baseline/runtime_s`, and `/quantized/runtime_s`. Source/tool, environment,
decode, judge/probe and engine/weight identities remain in that comparison.

Valid measurement exits 0, 3 and 4 and T0 disagreement are retained as evidence.
An exit-4 report is excluded only on the unmeasured axis. Any fresh flagged flip
without new human adjudication blocks reference registration. Source/hash,
cleanup or operational failures block qualification and produce a narrow
aggregate failure receipt. Only validated, explicitly staged reports, cards and
aggregate receipts leave the runner; native temporary directories, logs, model
files, completions and labels are excluded. No sensitivity, absence, safety GO,
T4/crosshardware or Inspect parity claim follows from this campaign.

The approved public dataset destination is
`Crusadersk/quantfit-reference-reports`. Publication uses aggregate-only paths
under `v0/`, an immutable dataset commit and a downloaded-byte SHA256 comparison.
Registry admission, if the actual criteria pass, follows that byte verification.
A negative or unconfirmed candidate can be published with its limitations while
the registry remains empty. A valid negative Phi4 result is not a reason to
replace the priority pair with R1; fallback requires an observed resource or
operational failure and a separately recorded decision. QSR v1 remains unfrozen.
