# Hosted CI acceptance

The required merge check is `CI required`. The reusable candidate workflow checks
all prerequisite conclusions; failure, cancellation, and unexpected skips fail it.
All jobs use GitHub-hosted Linux or Windows CPU runners. No credentials, paid models,
GPU, or self-hosted machines are prerequisites.

Every PR checks the declared Python versions, required CPU Torch numerical tests,
deterministic generated properties against SciPy, selected mutation failures, branch
coverage floors, Ruff, strict typing on the spec/engine data contract, docs parity,
workflow linting, and the installed dependency graph for known vulnerabilities.
`tools/ci/uv.lock` fixes the complete validation dependency graph and artifact hashes
for Python 3.10-3.14 unit, numerical and tooling groups on hosted Linux/Windows.
The complete `runtime` group requires Python 3.11+ because Pillow 13 drops 3.10; hosted
runtime qualification uses Python 3.12. The 3.10 matrix establishes hermetic source
contracts, not complete runtime compatibility. `uv sync --locked` selects these groups; package builds use the locked build tooling without
PEP 517 isolation. Artifact installs use `--no-deps --no-build-isolation` into that
graph, followed by `pip check`. The scheduled drift lane deliberately resolves the
supported package graph afresh. The validation manifest does not alter PyPI metadata.

The locked runtime uses Torch 2.13.0, llmcompressor 0.14.0.1, Accelerate 1.15.0 and
Pillow 13.0.0, with advisory patches aiohttp 3.14.5, certifi 2026.10.19 and
opentelemetry-api 1.45.1. The compressor hotfix removes the Pillow upper cap; direct
package ceilings retain the previously admitted datasets 5.0.1 / Accelerate 1.15.0
boundary. The dated security maintenance in `docs/dependency-policy.md` §5 preserves
the hosted CPU evidence scope and keeps GPU AWQ/GPTQ qualification open. CPU Torch's local `+cpu` suffix is normalized
to its public release version for advisory lookup; Torch remains included in the audit.

The 2026-10-25 maintenance additionally excludes the affected filelock and setuptools
releases. Conditional filelock 3.20.3 on Python 3.10 / 4.2.1 on Python 3.11+ retains the
unit/source matrix; setuptools 84.1.0 is required by both public build and runtime
metadata and pinned in tooling. These are bounds on existing Hub/Torch transitives.
The fresh local installed-graph audit passes; hosted candidate acceptance and publication
still qualify their own exact bytes. See `validation/2026-10-25-release-dependencies/`.

On 2026-10-08 the release-candidate dependency audit correctly rejected fsspec
2026.4.0 for CVE-2026-104851. The lock now selects fixed fsspec 2026.6.0 and
matching s3fs 2026.6.0 without changing the pinned datasets or Inspect versions.
Sanitized failure evidence and fresh local checks are in
`validation/2026-10-08-fsspec-advisory/`; the full hosted graph must pass
requalification before merge and publication.

The candidate wheel and sdist are built once. Linux and Windows independently install
each candidate with full dependencies and run CLI/report/gate/JUnit/statistical behavior
from a temporary directory. The import check refuses source shadowing. Source-tree unit
tests continue separately. The composite consumer action runs on the candidate wheel
with the checkout package moved aside, and checks actual action outcomes and CLI/JUnit
outputs for exit codes 0, 2, 3, 4, and 5. Its refusal labels are explicitly fixtures:
this proves propagation and fail-closed integration, not detector sensitivity.

Every PR, main push, merge queue, scheduled and manual candidate check runs real public
pinned models:
compressed-tensors RTN W4A16 on Qwen2.5-0.5B-Instruct and GGUF Q4_K_M on SmolLM2-135M.
They require packed/integer tensors, read the emitted format metadata, reload the
artifact, and generate. Outputs contain metadata, versions, durations, and hashes;
weights and generated text are temporary and never uploaded. The CT path checks backend
serialization and CPU decompression/inference; the product's router still requires CUDA
for compressed-tensors deployment. It does not qualify AWQ/GPTQ/FP8, GPU kernels,
cross-hardware tolerances, large-model offload, quality, or safety sensitivity.

The same required lane explicitly runs the adjudication-backed judge cases,
including the known written-decline and short-completion limitations. The existing weekly
same-model determinism canary remains independent. Neither set is a new calibration
study or a passing sensitivity control; a null remains "the detector did not fire".

Publishing requires an existing version tag on both release-event and manual paths.
The caller must run from that same tag, already an ancestor of main. Its exact commit
enters candidate validation with backend and judge qualification
enabled. Publication consumes the exact distributions accepted in that same run rather
than rebuilding them. GitHub provenance attests those same bytes before PyPI Trusted
Publishing, whose PyPI attestations remain enabled. This CI
change does not publish a release. Candidate artifacts retain three days, fixture action
evidence one day. Logs and job summaries carry routine checks and dependency findings.

Reproduce numerical checks locally with the compatible CPU runtime and test dependencies:

```sh
python -m pytest tests -q --cov=quantfit --cov-branch --cov-report=json:coverage.json
python tools/ci_coverage.py coverage.json
python tools/ci_mutation.py
```

Coverage enforcement uses actual branch percentages for the MDE, gate, and report modules,
plus whole-package combined and branch floors. The Windows baseline and its limitations
are in `validation/2026-10-04-hosted-ci/`; hosted receipts should be read separately.
