# Hosted CI implementation validation — 2026-10-04

Local environment: Windows, Python 3.13.1, Torch 2.11.0+cu128, transformers 5.10.1,
llmcompressor 0.12.0, inspect-ai 0.3.269, GGUF 0.19.0, SciPy 1.15.3, pytest 9.0.3,
pytest-cov 7.1.0, coverage 7.14.0, Hypothesis 6.152.5, Ruff 0.16.2.

Invocation: `python -m pytest tests -q --cov=quantfit --cov-branch
--cov-report=json:C:/tmp/quantfit-coverage-20261004.json`. Machine-readable result:
`coverage-baseline.json`. The complete suite passed with the CPU numerical/property
tests enabled. The single skipped test is recorded as skipped rather than folded into
the pass count; judge-marked network tests were deliberately deselected here.

The coverage floor policy was chosen from that baseline: whole-package combined 88%,
branches 85%; MDE branches 95%, gate branches 90%, report branches 90%. The floors leave
small headroom for platform-dependent paths, while protecting the critical scientific
decision logic. They are regression floors, not a scientific-validity score.

`python tools/ci_mutation.py` killed the three selected mutations by test assertions:
inverted binomial rejection boundary, floor instead of nearest rounding, and bit-depth
independent quantization scale. This is a focused decision check, not a whole-project
mutation score. The runner rejects missing mutation anchors, collection errors and
survivors. Local Ruff, scoped strict mypy, docs audit, and Windows actionlint also passed.

First real CT qualification attempt was negative: SmolLM2-135M has 576-column linear
weights and the published group-128 W8A16 scheme rejects non-divisible dimensions.
No bypass or weakened recipe was introduced. The final CT qualification model is pinned
Qwen2.5-0.5B-Instruct, whose 896 columns support the published RTN W4A16 recipe. This
change of acceptance model is explicit; SmolLM2 remains the GGUF qualification model.
The Qwen recipe then initialized successfully on local CPU but upstream
compressed-tensors 0.17.1 called `os.sysconf`, unavailable on Windows. CPU backend
qualification therefore runs on hosted Linux; no Windows platform shim was added.

What this local record does not establish: hosted Linux/Windows acceptance, release
publication, a safety sensitivity control, judge calibration, GPU/backend kernel
qualification, large-model scaling or cross-hardware tolerances. Hosted results are
separate receipts; no completion text, model weights or baseline caches are committed.

The first hosted qualification of compressor 0.12.0 on Linux succeeded, but the new
dependency audit exposed GHSA-rrmf-rvhw-rf47 (PyPI advisory metadata and GitHub advisory:
Torch through 2.12.1 affected, fixed in 2.13.0). Compressor 0.12.0 caps Torch at 2.12.0.
The final baseline therefore uses compressor 0.13.0 / compressed-tensors 0.18.0 / Torch
2.13.0. The proposed <0.14 cap must pass the hosted CPU backend and preserved canary
qualification before merge. The complete
transitive graph and build tooling are locked in tools/ci/uv.lock; source unit tests
remain separate from installed-artifact and backend acceptance.
