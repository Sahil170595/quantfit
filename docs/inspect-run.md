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
