# Installed Inspect HF CPU qualification, 2026-10-05

This is functional orchestration evidence, not a quantization/sensitivity or
safety result. The installed candidate uses the existing QSR v0 pipeline and
DriftReport schema 2. Both actual generation arms are the same unquantized
SmolLM2 checkpoint; no human adjudication was performed.

`qualification.json` records the actual installed Inspect/HF run outside the
checkout. `inspect-drift.json` is the aggregate report. `source-receipt.json`
binds the tested wheel and installed source hashes to the branch's runner
sources, equal after universal-newline normalization only. The wheel SHA256 is
`ba1f7a95e65804f613061c42f6c9d4c1623fbadd362fa5d59edc79458657b96b`.
The branch base was `a377f46be8d9f34f02900872a6ae1d3fa68ec9d6`.

Environment: Windows 11 build 26300, AMD64, Intel64 Family 6 Model 183,
68,319,571,968 bytes physical RAM, Python 3.12.13, CPU-only Torch 2.13.0+cpu
with two Torch threads, Transformers 5.17.0, Inspect 0.3.269, HF Hub 1.31.0 and
datasets 5.0.1. Dependencies came from the repository's frozen `tools/ci/uv.lock`
(uv 0.12.23; runtime, unit, numerical and tooling groups). The interpreter was
borrowed from the coordinator; neither it nor shared HF caches were changed or
removed as part of cleanup. This laptop was shared during the run, so elapsed
time is a single observation, not a performance benchmark.

Actual pins, checked against the report and shipped constants:

| input | revision |
|---|---|
| Both arms: HuggingFaceTB/SmolLM2-135M-Instruct | `12fd25f77366fa6b3b4b768ec3050bf629380bac` |
| Probes: Crusadersk/quantsafe-judge-benchmark, train | `c26cc2e15fcadab9c0ec24a5b57d37b140f7ed58` |
| Judge: garak-llm/garak-refusal-detector | `5cb5ec8f364318cc48724ddf8ad414000c36781b` |

The resolver returned the requested immutable arm SHA. Actual loaded model and
tokenizer paths matched its snapshot; actual config commit matched the SHA.
Content manifest `a1986ce6a7174f1e90565785c37f2c3ffa2870863a904ff532b2441852d228d0`
was unchanged after evaluation. Both actual loaded precisions were
`torch.bfloat16`, with actual device `cpu`; this is native floating precision,
not a packed weight bitwidth claim. Caller model-arg allowances were not widened.

All 40 pinned probes ran, greedy, one epoch, capped at four new tokens. Counts
were independently checked as 12 clear-unsafe + 12 clear-safe + 16 borderline =
40, and the one real judge batch contained 80 completions = two arms × 40.
Observed real loaded weight-model `generate` invocations were 40 per arm.
No fixture judge/model replaced the real provider in this qualification.

Result: no flagged label flips; dangerous axis 0/12 at-risk, over-refusal axis
unmeasurable with 0 at-risk because the judge flagged all 28 expected-safe outputs
as refusals at this short token budget. **Exit 4**, not a pass of that axis.
The detector did not fire on the dangerous axis; this canary establishes no
quantization sensitivity or safety. See QSR v0 §8 for its harness-only scope.

Single-run elapsed time: 380.02 s. Per-arm sequential Inspect `Model.generate`
wall time: 165.70 / 165.48 s, including queue wait, tokenization and decoding,
excluding downloads/model/judge loading. Actual weight-method host wall time:
63.98 / 64.18 s. These are distinct observations, neither GPU kernel timing.

Invocations (PowerShell; `python` below denotes the borrowed locked interpreter):

```powershell
python -m build --wheel --no-isolation
python -m pip install --no-deps --no-compile --no-build-isolation --target C:/tmp/quantfit-inspect-installed-20261005 dist/quantfit-0.15.1-py3-none-any.whl
$env:PYTHONPATH = 'C:/tmp/quantfit-inspect-installed-20261005'
$env:HF_HUB_DISABLE_IMPLICIT_TOKEN = '1'
$env:OMP_NUM_THREADS = '2'
$env:MKL_NUM_THREADS = '2'
Set-Location C:/tmp
python C:/tmp/quantfit-inspect-20261005/tools/ci_inspect_acceptance.py --out C:/tmp/quantfit-inspect-20261005/validation/2026-10-05-inspect-cli/qualification.json
```

The tool invokes `inspect-run` with both actual pinned HF specs/revisions,
`--max-new-tokens 4 --report inspect-drift.json --json`. It checks one real judge
batch, full corpus, observed source/device/precision and actual generation
counts. Temporary Inspect logs are captures and are deleted on exit. No probe,
completion, tokenizer template or raw quantization config is committed.

Checks from this checkout:

```powershell
python -m pytest -q --cov=quantfit --cov-branch --cov-report=json:coverage.json --junitxml=validation/2026-10-05-inspect-cli/unit-tests.xml
python tools/ci_coverage.py coverage.json
python tools/ci_mutation.py
python -m ruff check quantfit tests tools
python -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
python -m mypy --strict quantfit/spec.py quantfit/engines/base.py
python -m quantfit.cli audit --json-out validation/2026-10-05-inspect-cli/audit.json
python tools/quickstart_check.py --min-commands 20 --quantfit-bin 'C:/tmp/quantfit-calibration-20261005/tools/ci/.venv/Scripts/python.exe -m quantfit.cli'
```

Final suite: 1,455 passed, one skipped, six explicitly deselected judge tests
(the real pinned judge was exercised above), 163.50 s. The 47 new source/precision/
actual-call/capture/CLI boundary tests are hermetic fixtures. Total coverage
91.11%, branches 89.21%; scientific branch floors pass (MDE 100%, gate 93.48%,
report 91.67%). All three existing scientific decision mutations were killed.
Ruff and strict mypy passed; docs audit had zero errors and zero warnings.
Quickstart verified 33 advertised commands, ran six clean-environment commands,
and explicitly left 27 requiring artifacts/network/weights unrun.

Not established: quantization sensitivity, GPU behavior, parity of generated
text with verify-safety, judge calibration/accuracy or human-confirmed safety.
The short token cap and unmeasurable axis make this unsuitable as a safety
finding or reference report. The hosted `cpu-inspect` job is configured to test
the installed candidate wheel independently; this local run does not claim a
hosted result. Logs, package copies and build outputs are disposable, not evidence.
