# Inspect GGUF provider

Install `quantfit[inspect,gguf]` (pinned Inspect0.3.269) and use `quantfit_gguf/<local-file.gguf>` or
`quantfit_gguf/hf:<org>/<repo>/<file>.gguf` on Linux with `/proc` process observation.
Hub arms need each immutable40hex revision; local arms omit revision flags and
are bound by actual file SHA256. Mixed providers, quantized baseline, mismatched
architectures, sampling/tools/system/multimodal overrides and unsupported pins
refuse with operational exit2. Existing [HF usage](inspect-run.md) stays supported.

```bash
quantfit inspect-run --baseline quantfit_gguf/base.f16.gguf \
  --quant quantfit_gguf/model.Q4_K_M.gguf --max-new-tokens 64 \
  --report inspect-drift.json --json
```

Inspect resolves this provider through its public `ModelAPI`/`modelapi` extension
and the wheel's `inspect_ai` entry point. The executable is compiled llama.cpp,
not llama-cpp-python. Both arms share actual executable hash/thread count and
explicit CPU controls `--device none --n-gpu-layers 0 --no-op-offload`. Served
`/props` model path, context/slots, build and template hash are checked against
the owned load; weight/executable bytes are rechecked before publishing. These
are observations of this owned process, not independent host authentication or
GPU-residency measurements. Generation parity with native verify-safety is unproven.

The paired solver alternates arms, so this extension retains **two model servers**.
Admission requires observed available RAM at least `2*sum(GGUF bytes)+2 GiB` before
either starts. This conservative estimate is not measured peak RSS; actual load
can still fail. Use native `cold-run` for one resident arm at a time or larger
pairs; no equivalence to its T0 campaign is claimed. Both groups close before
the single pinned judge batch. Native responses/server output never enter aggregate
artifacts; default Inspect logs are temporary captures removed on failure/cancellation.
Async HTTP has fixed600second socket and900second load deadlines. SDK timeout/
attempt-timeout overrides are refused. Owned POSIX groups are terminated and direct
children waited/reaped; grandchild reaping is not claimed.

The managed QSR runner uses fresh `get_model(..., memoize=False)`, explicit SDK
`cache=False,max_retries=0`, one connection/nonadaptive concurrency and its own
serial guard. It requires one actual native request per arm/probe and all40probes/
one80-label judge batch. **Standalone Inspect SDK caching happens before ModelAPI
invocation**: the provider alone cannot prevent a caller requesting an SDK cached
response. Standalone consumers must manage that layer; only the managed runner
checks the complete observation contract. No successful generation fallback/retry.
Native token-limit termination maps to Inspect `max_tokens`; missing or unknown
endpoint termination metadata stays `unknown` rather than claiming a clean stop.
Public `qsr_eval` selects this managed route for GGUF even when local revision
slots are omitted; Hub revision omissions refuse before loading weights/probes.
Lower-level standalone `qsr_paired_diff` tasks/SDK callers own provider closure.
Report destinations that canonically or by inode alias a local arm refuse before
model contact. Observed library report writes also protect both resolved weight
files and native executables (including Hub cache files); unrelated existing
report files remain replaceable.
Bare GGUF `write_drift_report` calls require explicit resolved `protected_inputs`;
the supported observed `QsrRun.write_report` supplies these automatically. The
writer does not download/re-resolve models to guess a Hub cache or executable.

Aggregate reports retain original verdict/counts, measured call totals, loaded
hashes/served facts and a companion RAM/process receipt. Calibration binding and
bundles recognize the exact new engine schema; integrity/binding cannot prove human
labels, sensitivity, safety GO or independent reproduction. QSRv1 is unfrozen.
The actual installed small pinned GGUF/full40/real80judge hosted consumer is configured
in `tools/ci_inspect_gguf_acceptance.py`; local fixture proof and pending hosted model
qualification are recorded separately in `validation/2026-10-09-inspect-gguf/`.
