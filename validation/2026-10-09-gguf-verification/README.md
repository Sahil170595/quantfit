# GGUF bounded verification acceptance — 2026-10-09

Observed source is `60ee5a10922d9f8eaaf06d477348ae2060e5b510`, tree
`017f5b5d1ad9b55f6516528c067da13432cc84ae`, based on QF4 `03036e0`.
This record contains complete crafted zero-filled binaries and synthetic
HTTP/server lifecycle fixtures. No model inference, native binary provisioning,
external request, new environment/model/dependency copy or container occurred.
The Windows platform cannot qualify native process-group inference locally.

`functional.json` records seven actual source CLI invocations: complete crafted
structure JSON/prose 0, four-byte magic-only invalid 3, version-1 unverified 2,
deadline-without-runtime operational 2, malformed timeout parser 2 and actual
Windows runtime refusal 2 before provisioning. The rich records keep structural
pass separate from unverified native usability. Zero-filled tensor storage does
not establish meaningful weights, quantization quality or safety.

The approved pre-existing sparse Windows 11 environment uses Python 3.12.13,
32 logical CPUs and 68,319,571,968 total RAM bytes. `run.json` records exact
installed versions, Git source byte hashes and independently derived XML counts.
Torch is absent. From the checkout using `tools/ci/.venv/Scripts/python.exe`:

```powershell
python -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-09-gguf-verification/unit-final.xml
python -m pytest tests/test_numerical_properties.py -q -k 'not rtn' --junitxml=validation/2026-10-09-gguf-verification/properties-final.xml
python -m ruff check quantfit tests tools
python -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
python -m mypy --strict quantfit/spec.py quantfit/engines/base.py
python -m quantfit.cli audit --json
python tools/quickstart_check.py --no-run --min-commands 20 --quantfit-bin 'C:/tmp/qf-release-0.16.0-20261008/tools/ci/.venv/Scripts/python.exe -m quantfit.cli' --json validation/2026-10-09-gguf-verification/quickstart-final.json
python validation/2026-10-09-gguf-verification/run-functional.py
```

The functional script writes its own named tiny binary fixtures/receipts and
should run only in a fresh destination. The required unit lane passes; the
README static inventory parses 53 commands and executes zero. Configured mypy
checks only two existing strict source modules. The two available SciPy
properties pass; the RTN/Torch property remains deselected and awaits hosted
numerical qualification. Windows symlink/POSIX-only cases are skipped locally;
SDK/cache-path syntax and fake runtime cancellation/cleanup are separate proofs.

The installed `gguf` 0.19.0 constants were inspected: Q4_0 block 32/18 bytes,
Q4_K block 256/144, and LlamaFileType code 15 names MOSTLY_Q4_K_M. Declared
`ne0` `(32,2)` is valid; `(16,2)` cannot acquire a valid row by its total product.
The parser uses no GGUFReader/mmap/NumPy product and no tensor payload allocation.
Known syntax/extent violations fail 3; chosen budgets, BE, nested arrays and
legacy/future versions remain unverified 2. IEEE nonfinite binary float metadata
is accepted; padding/gaps and empty unique tensor names are not invented faults.

Fake native cases verify deadline, cancellation, served metadata, model/binary
changes, RAM/platform admission before provisioning, identity-encoded bounded
HTTP and required exact cleanup flags. The existing Inspect class/helper and
InspectTaskError imports remain shared aliases. Ordinary existing Inspect
provider/task tests pass. Their real socket/POSIX test is not local Windows
execution. The hosted converted pinned Smol F16/Q4 consumer replaces its one
four-token native slot, retaining observed Q4_K_M declaration and packing checks;
it adds no generation, model, binary download or job.

`development-summary.json` retains missing-module TDD red, working-file focused
runs, and the sole later test defect: a fixture expected budget refusal exactly
at the allowed limit. The fixture was corrected to exceed the boundary, without
changing production policy. Ruff import fixes and the existing CONTRIBUTING
symbol citation were updated to the moved lightweight definition. No checker,
coverage or protocol waiver was introduced. Independent exact-source challenges
are recorded separately from actual local execution.

`members.json` binds canonical staged Git bytes; observed original Windows
receipt bytes and hash mappings are retained by `byte-normalization.json`.
`aggregate-scan.json` permits only public README command syntax in its static
inventory; no raw model output is present. Model/binary before/after hashes
detect observed changes but do not attest precisely which bytes a native process
served. Unknown termination remains unknown, and grandchildren are not claimed
reaped. This establishes source syntax/usability-control behavior, not actual
Linux native execution, installed distribution behavior, model quality,
refusal safety, sensitivity or scientific GO. These hosted proofs remain pending
until batch publication. Root checkout/environment are PRESERVE resources; prior
automatically blocked cleanup has not been retried.
