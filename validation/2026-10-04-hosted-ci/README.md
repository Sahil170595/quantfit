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
Compressor 0.13.0 then passed hosted RTN/GGUF CPU lifecycle and the preserved canary
(run 37196951699, including datasets 5.0.1), but its audit exposed affected Accelerate
1.14.0 and Pillow 12.2.0. Compressor 0.13 caps Accelerate at 1.14.0. The final proposed
baseline therefore uses compressor 0.14.0 / compressed-tensors 0.19.0 / Torch 2.13.0,
Accelerate 1.15.0 and Pillow 12.3.0. The <0.15 cap passed the hosted CPU backend and
preserved canary qualification on candidate e68ac8e09c27a28d40a1cb49003a955d2a85f0e3; the dated security exception is explicit
in docs/dependency-policy.md §5. The complete
transitive graph and build tooling are locked in tools/ci/uv.lock; source unit tests
remain separate from installed-artifact and backend acceptance.

Hosted patched-runtime receipts: `hosted/ct.json`, `hosted/gguf.json`, and
`hosted/canary/{drift,gate}.json`. CI run
https://github.com/Sahil170595/quantfit/actions/runs/37197264106 passed every reusable
candidate prerequisite, including all five action outcomes, all four installed artifacts,
judge cases and all declared Python versions. Required numerical tests passed:
1,404 passed / 5 skipped / 6 judge-deselected; branches 89.15%, combined 90.81%,
MDE 100%, gate 93.48%, report 91.67%; all three selected mutations killed. The exact
runtime + tooling graph had zero known vulnerability findings. This run's outer
aggregate correctly failed when live drift found vulnerable ambient runner setuptools
78.1.0; the final drift workflow uses a clean external venv and upgrades its live tooling.

Canary run https://github.com/Sahil170595/quantfit/actions/runs/37197266074 passed
both OS wheel installs, cold pinned judge/probe/model downloads with datasets 5.0.1,
40 probes on identical arms, zero flips, byte-identical drift blocks across two replicates,
and pre-run resolution refusal. These two replicates do not meet the three-replicate
protocol count and are a smoke check. Counts are independently checked from the schema-v2
report and job log; model and corpus pins match the acceptance script and QSR pins.
No raw completion/prompt text, caches, model weights or package binaries are committed.

Final workflow review removed generic caller-supplied checkout refs: the reusable
workflow inherits the immutable caller commit. Publishing requires tag identity,
main ancestry and resolved tag SHA equal to the caller SHA. Ordinary PR/main/merge-queue
checks now require both real CPU backends and judge tests, alongside the fast parallel
source checks. Final candidate run URLs remain distinct from these dated receipts.
