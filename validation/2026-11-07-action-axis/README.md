# Selected-axis reference action software controls

This 0.57.0 source record covers the optional `axis-thresholds` action input,
quoted argv, named per-axis output, job-summary rendering and explicit upload
opt-out. The public baseline is 0.56.0. `summary.json` records the observed local
source suite and hashes of its inputs. The installed distribution consumers and
actual GitHub composite execution are qualified by the candidate's hosted CI.

Run from the repository using the existing development environment:

```bash
python -m pytest -q tests/test_action_axis.py tests/test_action_calibration.py tests/test_axis_gate.py tests/test_axis_gate_cli.py tests/test_axis_gate_receiving.py tests/test_ci_axis_gate.py tests/test_meta.py tests/test_refreports.py
ruff check quantfit tests tools
ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture tools/ci_corpus_fixture
mypy --strict --follow-imports=silent quantfit/axis_gate.py quantfit/gate_axis.py quantfit/axis_gate_live.py quantfit/axis_gate_receiving.py quantfit/axis_gate_junit.py quantfit/gate_receiving.py tools/ci_axis_gate.py tools/ci_axis_gate_record.py tools/ci_action_axis.py
python -m quantfit.cli audit
```

The five parameterized saved-action controls execute the action's real validation,
preflight, argv, artifact reader and terminal-exit shell against native saved
reports. The harness selects its owning Python interpreter. The native CLI and
strict bundle receiver handle the report and JSON/JUnit. Assertions require actual
exits 0, 2, 3, 4 and 5, original-source SHA retention, per-axis fields and unchanged
legacy scalar meaning. Case 0 retains a flagged unselected dangerous axis. Case 3
flags over-refusal while the legacy dangerous-only policy passes the same report.
Case 4 has no at-risk safe probes. Case 5 retains the native preflight refusal.
These individual results are asserted inside pytest; the quiet log does not print
five independent scientific receipts.

Other controls cover both selected axes, conditional operator epsilon, LF/CRLF,
duplicates, unknown axes, mode conflicts, unsupported numeric values, typed output,
private extra fields, nonfinite/oversized display values, shell syntax as a literal
argument and existing-output preservation. The unchanged legacy action controls
remain in the same suite. Five additional action calls in the existing nine-job
consumer matrix use the candidate wheel and `artifact-name: ""`; no new job or
upload is added.

The first causal run passed its native saved-report positive and failed only the
missing action admission/output controls (1 passed, 2 failed). The same three tests
then passed. The first expanded run had an overstrict new JSON-key-order assertion
and Windows harness UTF-8 decoding warnings. Native JSON sorts its object keys.
The test now checks complete policy membership and values, and the harness uses
explicit UTF-8. That adverse log and its actual test before-image remain in the
parent's named local evidence. A separate Mypy invocation failed while attempting
to create `NUL/3.12`; the supported rerun used an owned ordinary temporary cache.

All inputs are fictional native counts or existing controlled fixtures. These
checks establish software propagation, receiving and privacy boundaries. They
establish no real generation, judge accuracy, human truth, detection sensitivity,
GPU behavior, joint-error guarantee, independent reproduction or scientific GO.
Native MDE calculations, report schemas and the default gate policy are unchanged.
