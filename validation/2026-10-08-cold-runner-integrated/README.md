# Combined cold-runner qualification — 2026-10-08

Immutable source `e139a4708c896a03cbb259ac24571f9594b2c604` is a genuine
two-parent merge of reviewed CPU/cold-runner `425bf92b96b8416caceda80bceb81744eee6243d`
and reviewed bundle correction `f684ddb0bb848b9e936718d3cd1a88a57c95ab9f`.
Only `.gitattributes` conflicted: all prior directory-specific rules were retained
and a new exact-JSON-byte rule added for this record. Production code/tests merged
without manual changes; original measured heads and dated artifacts stay intact.

`receipts.json` independently counts the available Windows suite's **1717 passed,
29 skipped** (1746 XML cases), two passing Hypothesis/SciPy properties, actual gate
exit statuses, hardware/installed versions and exact source-byte hashes. Final
Ruff check/exact format, exact mypy and audit exit0 passed. Ruff format warned that
its shared cache could not be written; it returned0 with104files formatted. The
approved environments were reused; no installs, model downloads or cache cleanup.
Working CRLF source bytes and canonical Git blobs are separately hashed and their
exact EOL equivalence verified. Native cold/gguf/verify/hosted CPU-consumer blobs
are unchanged from `b745506c49f017fc17ba6372629835d37fc535d7`; the typed numeric
calibration primitive equals the reviewed bundle parent's blob.

The first two WSL invocations failed **before Python/test entry**, with
`Wsl/Service/CreateInstance/MountDisk/HCS/ERROR_SHARING_VIOLATION`. Their original
UTF16 logs and decoded sanitized errors are preserved. Read-only inspection found
Ubuntu listed stopped while its `ext4.vhdx` was attached to PhysicalDrive1. No
shared WSL service, VM, disk or container was stopped/unmounted by this builder.
Actual combined WSL17 is **UNRUN**: zero tests started. Root explicitly reassigned
the combined POSIX cold-suite and real installed64/full40x3 qualification to hosted
Linux; both are pending publication. No further WSL retry/repair/shutdown/dismount.
Historical b745 WSL17 and the bundle correction's f684 Linux66pass1skip remain their
own dated evidence; neither is relabelled as a new combined WSL run.

From `C:\tmp\qf-release-0.16.0-20261008`, with `PYTHONDONTWRITEBYTECODE=1`:

```powershell
tools/ci/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-08-cold-runner-integrated/unit.xml
tools/ci/.venv/Scripts/python.exe -m pytest tests/test_numerical_properties.py -q -k 'not rtn' --junitxml=validation/2026-10-08-cold-runner-integrated/properties.xml
tools/ci/.venv/Scripts/python.exe -m ruff check quantfit tests tools
tools/ci/.venv/Scripts/python.exe -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
tools/ci/.venv/Scripts/python.exe -m mypy --strict quantfit/spec.py quantfit/engines/base.py
tools/ci/.venv/Scripts/python.exe -m quantfit.cli audit --json
wsl.exe -d Ubuntu --cd /mnt/c/tmp/qf-release-0.16.0-20261008 -- python3 -B -m pytest tests/test_cold_run.py -q -p no:cacheprovider --junitxml=validation/2026-10-08-cold-runner-integrated/wsl.xml
wsl.exe -d Ubuntu --cd /mnt/c/tmp/qf-release-0.16.0-20261008 -- python3 -B -m pytest tests/test_cold_run.py -q -p no:cacheprovider --junitxml=validation/2026-10-08-cold-runner-integrated/wsl-retry.xml
tools/ci/.venv/Scripts/python.exe validation/2026-10-08-cold-runner-integrated/record-receipts.py
tools/ci/.venv/Scripts/python.exe validation/2026-10-08-cold-runner-integrated/byte-check.py
```

Torch is absent locally, so its RTN property and hosted numerical/coverage/mutation
matrix remain pending, as does real installed GGUF default64/full40 three-run
qualification. This integration proves no model behavior, sensitivity, human
adjudication, GPU/crosshardware or independent reproduction/scientific GO. QSRv1
remains unfrozen. No public HF dataset was created/uploaded.

**PRESERVE:** shared worktree/env/local Quant3 ref remain under combined review.
Prior blocked dependency/cache cleanup is not retried. No task-owned native server,
container or new dependency/model/worktree copy remains; exact HEAD/tree supplied
at handback. No push or Quant4 implementation before combined approval.
