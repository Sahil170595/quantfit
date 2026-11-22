# Independent Quantfit hotfix checks

This run used Quantfit 0.66.1 installed editable on Windows x86-64 with
Python 3.13 and the locked tooling and unit graph in `tools/ci/uv.lock`.
`functional.json` records the observed CLI exit codes, categorical errors
and sink outcomes. The source fixtures use public aggregates and synthetic
local data. Only aggregate outcomes are committed.

```bash
python -B -m pytest tests/test_screen_control_calibration.py -k nonaggregate_report_keys
python -B -m pytest tests/test_reference_assessment.py -k overflowing_runtime
python -B -m pytest tests/test_bundle.py tests/test_replay_bundle.py -k "competing_replacement or replay_cli_removes_only_attested_owned_files"
```

The saved-screen fixture compares control-only and combined control/calibration
receiving, including a valid combined control. Rejected targets publish neither
JSON nor JUnit. The reference fixture binds a deliberately unrepresentable
runtime into native T0 and runs `references assess` with and without XML.
Bundle regressions inject controlled write failures through the real CLI
dispatch and check foreign bytes, readiness markers and safe retry.

These checks establish offline admission and filesystem behavior. They provide
no new inference, authenticated labels, sensitivity or scientific verdict.
