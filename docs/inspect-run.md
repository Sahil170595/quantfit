# Observed Inspect HF runs

`quantfit inspect-run` runs the existing `qsr_eval` pipeline through Inspect's HF
provider. Both arms use the full pinned 40-probe corpus, greedy single-epoch
generation and one real pinned judge batch. The QSR v0 statistics and DriftReport
schema 2 are unchanged. This is a separate generation engine from verify-safety;
identical generated text across those engines has not been established.

The CLI requires `hf/org/repo` specs and immutable 40-character lowercase commit
SHAs for both arms. It resolves each SHA through the Hub and downloads that
immutable snapshot. The model and tokenizer load from the same snapshot path;
their actual loaded `name_or_path` values must match it. A content manifest hash
is checked before loading and after evaluation. The report records the resolved
commit, actual model dtype/device, snapshot manifest, tokenizer commit and
template hash, and a hash/method of observed quantization configuration when
present. Raw tokenizer templates and quantization config content are omitted. A local
snapshot's config may have no `_commit_hash`; that null remains null rather than
being rewritten into invented model metadata. Revision evidence comes from the
resolver receipt, observed load paths and unchanged snapshot bytes.

The trusted source adapter constructs its own narrow arguments. Arbitrary
`model_path`, revision, tokenizer, template, dtype, device or quantization model
args remain refused by the existing public `check_model_args` contract. Missing
source/precision observations, changed source bytes and unsupported provider or
Inspect version fail with exit 2. Loaded dtype is floating runtime precision,
not proof of packed quantization bitwidth or a sensitivity result.

The adapter is confined to Inspect **0.3.269**, exactly locked in `tools/ci/uv.lock`.
Its official wheel SHA256 is
`cdd8ec3210da3874d4b3a01f482d36b66398b1e9685cc4aa0722b37e607e1512`.
The inspected source is `inspect_ai/model/_providers/hf.py` in that wheel:
its `revision` model argument does not reach `AutoTokenizer.from_pretrained`,
and its module-global `batch_queue` processes a batch with the first item's
model/tokenizer regardless of other items' model identity. These are contained
by immutable local snapshots and **max_samples=1**, sequential arm calls, and a
process-wide lock rejecting concurrent observed evaluations. Run the CLI in its
own process; unrelated callers of raw Inspect HF APIs in the same process are
outside this containment contract.

Each real loaded weight model's `generate` method is observed once per arm/probe.
Wrong-weight routing, cached returns, retries and overlapping observed arm calls
are refused. Memoized identical model objects share one observation wrapper,
while counters remain separate for each logical arm. `ArmRun.runtime_s` sums wall
time around sequential `Inspect Model.generate` calls, including provider queue
wait, tokenization and decoding, excluding downloads, model loading and judging.
`engine.weight_generate_host_wall_s` separately measures host wall time inside
the actual loaded model's method. Neither is GPU kernel timing or a controlled
performance benchmark. The report records actual device; qualification is CPU.

Inspect logs contain probe and completion text. Without `--log-dir`, they live in
a temporary directory deleted after success or failure. Explicit `--log-dir`
keeps local-only captures with a warning; never commit or attach them. Only the
optional `--report` aggregate artifact is suitable for sharing. Exit meanings and
precedence match verify-safety: 3 regression flagged, then 4 axis unmeasurable,
otherwise 0 no regression detected; 2 is operational failure, never a verdict.

`tests/test_inspect_hf.py` and `tests/test_inspect_cli.py` use synthetic objects
and outputs for boundaries. `tools/ci_inspect_acceptance.py` uses actual installed
Inspect, the pinned SmolLM2-135M model on **both** CPU arms, all pinned probes and
the real pinned judge. It counts one real judge batch and 40 actual weight
generation calls per arm. This is the QSR v0 §8 identical-arm orchestration
canary. It establishes neither quantization sensitivity, judge calibration,
human-confirmed safety, GPU behavior nor generation parity with verify-safety.
Committed local evidence is in `validation/2026-10-05-inspect-cli/`; the hosted
`cpu-inspect` job independently qualifies the installed candidate wheel.

The Linux `quantfit_gguf` extension and its two-resident memory/process contract
are described in [Inspect GGUF](inspect-gguf.md); HF is the existing provider path.

Primary source: [official Inspect model documentation](https://inspect.aisi.org.uk/models.html)
and [the exact official wheel](https://files.pythonhosted.org/packages/a2/85/216d937d1fd6d3f93f4f63d46defc9e8b11fa94ecafd83b80511cd4c7e71/inspect_ai-0.3.269-py3-none-any.whl).

## Completed report recovery (0.60.0 candidate)

The unreleased 0.60 source candidate can preserve a completed corrected native
aggregate if final report publication fails. Public installation remains 0.56.0.
This is an explicit separate sink, not an Inspect log/scored-log import command:

```bash
quantfit inspect-run --baseline hf/org/base --quant hf/org/quant --baseline-revision FULL40 --quant-revision FULL40 --report drift.json --recovery-out completed-inspect.json --json
quantfit inspect-recover --checkpoint completed-inspect.json --sha256 FULL64 --out recovered-drift.json --json
```

Both checkpoint/report parents must already exist when opting in. The checkpoint
must be absent; the live final report may still replace an unrelated regular
file under the existing atomic-report contract. Known CLI sinks are admitted
before source/model work, including each other, known local GGUF/probe inputs
and explicit private log-directory roles. Known live GGUF model symlinks use the
existing resolved-file identity guards while their original execution refs remain
unchanged; native local-probe file guards still apply. Source/asset guards are repeated at
publication. The default `--recovery-out` omission retains prior run/report
behavior and output shape.

The native assembler runs once, followed by the existing Inspect decode
correction/schema roundtrip. Only its **completed corrected report buffer** is
checkpointed, after source checks and before final output recheck/replace. A
checkpoint write/validation failure prevents final replacement. A subsequent
final-sink failure exits 2 and returns `result.recovery_receipt` with the saved
checkpoint's full raw SHA256/size, original report byte binding, counts and
observed runtimes. `report_published` is false. Retain that expected pin; do not
rerun a completed model or judge just to recreate publication. If the final
error is followed by a temporary-file cleanup failure, the receipt still carries
the pin and `temporary_cleanup: preserved`; do not retry destructive cleanup.

```python
run = qsr_eval(...)  # unchanged: executes then returns; raw log remains capture-class
try:
    run.write_report("drift.json", *run.observed_arms, 64, recovery_out="completed-inspect.json")
    receipt = run.recovery_receipt
except InspectPublicationError as error:
    receipt = error.receipt
# After success, run.recovery_receipt contains the aggregate receipt.
restored = recover_inspect_report("completed-inspect.json", receipt["checkpoint"]["sha256"], out_path="new-drift.json")
```

Import the exception and recovery API from `quantfit.inspect_recovery`. The
low-level `write_drift_report` also accepts optional `recovery_out`. SDK admission
occurs at explicit writing, after the caller's run; it does not promise that a
separate earlier `qsr_eval` knew those future paths. A refused retry never changes
a prior checkpoint or clears its last committed receipt. The receipt property is
outside dataclass fields and returns a copy. This does **not** make `asdict(run)`
safe: its existing log/outcomes remain capture-class.

Checkpoint eligibility is deliberately limited to complete native **observed HF
or owned GGUF** reports. Generic operator-supplied ArmRun/mockllm reports retain
their old writer behavior without recovery; they are not promoted to observed
identity. The checkpoint's closed schema 1 carries the exact UTF-8 report string,
its SHA/size, native measurement identity/fingerprint and derived count/runtime/
exit facts. None/default, immutable Hub identity 1 and local SHA identity 2 remain
as recorded. No Probe, PairOutcome, EvalLog, prompt/completion text, raw observer
receipt, protected-input list or additional asset path is serialized. The exact
native report's model locators remain; this is not redaction or authentication.
Keep checkpoints local under the report's existing handling rules.

Receiving requires a lowercase 64-hex expected raw checkpoint SHA. It holds that
file once, refuses duplicate keys/nonfinite JSON/extra fields/wrong schemas, and
uses native aggregate statistics and observed identity validation. Copied identity,
pinned decode and observation fields compare with exact typed canonical values;
statistical roundoff tolerance is not used on these declarations. Bare reports,
unscored logs, partial/mixed count/identity facts and malformed wrappers refuse.
The receiver never reassembles report metadata or reopens source/model locators.
It publishes the **same bytes**, preserving original created/version/environment,
runtimes, source identity, verdicts and unknowns.

Report bytes are capped at 8 MiB; the separately encoded checkpoint cap is 16 MiB +
64 KiB. Encoded size is checked before publication; these are bounded profiles,
not a hard heap-allocation guarantee or a promise every maximal report fits the
checkpoint profile. Checkpoint/recovered output publication stages and fsyncs
complete file contents, then uses an exclusive same-parent hard link. Unsupported
linking refuses; no overwrite fallback is used. Parent directories are not
fsynced, so this is not a power-loss name-durability or hostile-concurrent-rename
guarantee. Unattested stage ownership is preserved as `recovery_stage_preserved`;
never recursively clean uncertain resources. Inputs and prior outputs are retained.

`inspect-recover` requires a **fresh** output, distinct from its held checkpoint.
Successful restoration returns the original native exit: 3 for detected regression,
else 4 for an unmeasurable axis, else 0. Invalid inputs/pins/roles or publication
failures exit 2. Neither byte integrity nor restored 0 establishes human-confirmed
safety, calibration, sensitivity, source authenticity or scientific GO.
[Controlled source evidence](../validation/2026-11-07-inspect-recovery/README.md)
includes actual native Inspect with fictional server/judge fixtures, forced final
failure, offline traps and real CLI recovery. Four hosted installed profiles are
extended; current installed/engine qualification is separate.
