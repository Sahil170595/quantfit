# Native CPU enforcement — 2026-10-08

This is a new corrective record; the original cold-runner validation is unchanged.
Source is `b745506c49f017fc17ba6372629835d37fc535d7`. The review identified that
the native engine declared CPU while its argv omitted offload controls. The pinned
llama.cpp `5397c3619479ef544e340e4b933929d1783de78b` defaults GPU layers to auto.
`supported-flags.json` records read-only official pinned source hashes/lines and
actual cached b9817 executable version/help, which accepted the supported trio:
`--device none --n-gpu-layers 0 --no-op-offload`. No weights were loaded.

The one failing `argv-red.xml` is a real pre-fix assertion of the missing native
argv flag with fake process/local HTTP/tiny GGUF fixtures. It does not reproduce
GPU execution. The corrected test asserts both actual constructed argv and the
flat engine fields. Those fields bind through existing calibration/cache/T0
identity. Legacy aggregate reports remain readable; newly observed cold reports
require the complete CPU trio. Partial, mistyped or conflicting declarations fail.

All final runs used the unchanged immutable source commit above. `receipts.json`
records actual hardware/installed versions and independently counts XML cases:
**1702 passed,29 skipped** in the available Windows suite (1731 cases); **17 passed**
on existing Ubuntu WSL. The focused suite has **91 passed,21 skipped**. Two
Hypothesis/SciPy properties passed; the Torch RTN property is unrun locally because
Torch is absent. Ruff check/exact format, exact mypy paths and audit exit0 passed.
Windows Python3.12.13 and Ubuntu Python3.12.3 use the existing approved environments;
no dependencies or models were installed. Legacy CRLF working source bytes and
canonical LF Git blobs are separately hashed and their EOL equivalence checked.
Every new JSON is protected before hashing by a directory-specific `-text` rule;
`byte-check.py` verifies actual index/committed bytes and report/T0 member hashes.

From `C:\tmp\qf-release-0.16.0-20261008`, with `PYTHONDONTWRITEBYTECODE=1`:

```powershell
tools/ci/.venv/Scripts/python.exe -m pytest tests/test_gguf_arm.py tests/test_bundle.py tests/test_baseline_cache.py tests/test_cold_run.py -q --junitxml=validation/2026-10-08-native-cpu-enforcement/focused.xml
tools/ci/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-08-native-cpu-enforcement/unit.xml
tools/ci/.venv/Scripts/python.exe -m pytest tests/test_numerical_properties.py -q -k 'not rtn' --junitxml=validation/2026-10-08-native-cpu-enforcement/properties.xml
tools/ci/.venv/Scripts/python.exe -m ruff check quantfit tests tools
tools/ci/.venv/Scripts/python.exe -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
tools/ci/.venv/Scripts/python.exe -m mypy --strict quantfit/spec.py quantfit/engines/base.py
tools/ci/.venv/Scripts/python.exe -m quantfit.cli audit --json
wsl.exe -d Ubuntu --cd /mnt/c/tmp/qf-release-0.16.0-20261008 -- python3 -B -m pytest tests/test_cold_run.py -q -p no:cacheprovider --junitxml=validation/2026-10-08-native-cpu-enforcement/wsl.xml
wsl.exe -d Ubuntu --cd /mnt/c/tmp/qf-release-0.16.0-20261008 -- python3 -B validation/2026-10-08-native-cpu-enforcement/run-functional.py --source-head b745506c49f017fc17ba6372629835d37fc535d7
tools/ci/.venv/Scripts/python.exe validation/2026-10-08-native-cpu-enforcement/record-receipts.py
tools/ci/.venv/Scripts/python.exe validation/2026-10-08-native-cpu-enforcement/byte-check.py
```

The copied functional driver writes exclusively into this new directory. It makes
9 actual outer CLI calls/27 fresh children using explicitly synthetic aggregates:
native regressions/nulls/unmeasured outputs, T0 disagreement, operational failures,
deadline expiry and invalid binary/thread/baseline claims. All direct children are
waited/reaped and no live owned group members observed. This is process/aggregate
acceptance, not model execution or grandchild reaping/host authentication.

The existing hosted GGUF CPU qualification now includes an installed candidate
default64/full40 three-run consumer. It uses the pinned small Smol source, creates
a fresh supported F16 conversion because quantization removes the earlier one,
checks converter pin/hash and installed measurement module bytes against Git blobs.
Negative native findings and T0 disagreement qualify functional correctness and
retain aggregate evidence. Operational failure fails qualification; unsafe partial
directories are not uploaded. Only recursive qualification JSON is uploaded, never
weights or transient server output. This new real-model path is **pending hosted
execution**; it is not a local result or a sensitivity/GO/reproduction claim.

The separately published bundle PR's installed failure is independently isolated
as Windows/Linux one-ULP recomputation drift; root owns its narrow fix and replay.
This CPU commit does not include that fix. No push or later feature begins before
the review/stack failure is resolved. QSRv1 remains unfrozen. Human adjudication,
sensitivity, GPU/crosshardware measurement and independent reproduction are absent.

**PRESERVE:** shared worktree/environment stay under sequential batch review with
unpublished local Quant3 ref. Prior blocked cleanup is not retried. No new worktree,
dependency copy, model or container; no task-owned native child remains live.
