# Atomic campaign publication correction

Source `65005c59604a64bc6dc1ffad6b8aceb710c7aded` fixes the independently
demonstrated partial-write defect at `72c32123`. Public reports, cards and JSON
are staged in owned temporary files in their destination directory, closed,
then atomically replaced. Handled failures remove the temporary file. The
explicit Actions upload allowlist contains only final artifact names. Valid
negative reports and original private native observations remain unchanged;
qualification is revoked on terminal failure.

`atomic-actual-red.json` records execution of the exact original 72c controller
Git blob with the corrected new regression tests: separate real partial-stream
writes for report and card both fail the no-partial-final-file assertion. The
fixed suite has 44 cases, including post-publication interruption and persistent
storage failure at the actual atomic replacement boundary. Earlier test-harness
failures are preserved in `atomic-harness-red.*`, `atomic-red.*`,
`atomic-focused.*` and `atomic-adaptation-*`; their fd-wrapper/variable-shadowing
premises are not evidence that the final implementation fails.

`atomic-local-receipts.json` independently classifies JUnit and compares it with
the pytest summary; it records consumed source bytes and canonical Git blobs.
Final local qualification is 1,818 passing cases and 32 skips, plus two
numerical properties; exact lint/format/types/audit exit 0. The audit retains
two existing documentation warnings, not errors. `independent-atomic-pass.json`
records the consequential review of the exact frozen source and additional
short-write/close-flush/persistent-failure cases.
The earlier 1f and 72c runs remain historical, without rewriting their logs or
claimed counts. The assessment function is AST-identical to 1f.

Actual invocations from the shared worktree, using its existing Python 3.12.13
unit environment on Windows (hardware and installed versions in
`local-receipts.json`; no dependency or model installation):

```powershell
tools/ci/.venv/Scripts/python.exe -m pytest tests/test_reference_campaign.py -q --junitxml=validation/2026-10-09-reference-campaign/atomic-focused-final.xml
tools/ci/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-09-reference-campaign/atomic-unit.xml
tools/ci/.venv/Scripts/python.exe -m pytest tests/test_numerical_properties.py -q -k 'not rtn' --junitxml=validation/2026-10-09-reference-campaign/atomic-properties.xml
tools/ci/.venv/Scripts/python.exe -m ruff check quantfit tests tools
tools/ci/.venv/Scripts/python.exe -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
tools/ci/.venv/Scripts/python.exe -m mypy --strict quantfit/spec.py quantfit/engines/base.py
tools/ci/.venv/Scripts/python.exe -m quantfit.cli audit --json
```

These are actual local synthetic/aggregate tests, not native model execution,
human adjudication, sensitivity/absence/GO, independent reproduction,
crosshardware or public-download proof. No global WSL launch/repair was attempted.
Actual hosted Phi4 measurement and public immutable byte verification remain
pending. QSR v1 is unfrozen.
