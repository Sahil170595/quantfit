# Calibration-aware output functional record — 2026-10-08

**Synthetic aggregates only.** No model, judge, human calibration, or control ran.
`drift.json`/`calibration.json` are newly generated fixtures using
`tests/test_calibrated_modelcard.py:card_fixture` and
`tests/test_calibration_binding.py:calibration_fixture`, with this record's creation
time and current package version. Their declared engine/environment and label counts
are synthetic scope inputs, not measurements of the machine running this record.
`action-drift.json`/`action-calibration.json` deliberately widen the synthetic corpus
to 2,000 probes (1,500 unsafe, 500 safe) so the post-run binding path is reachable.
`tools/ci_gate_fixture/sitecustomize.py` applies this only under the explicit CI fixture
environment; the production protocol/corpus is unchanged. No captures or labels exist.

Implementation validated: `8bdb0a6dd4cf54860f02c73e7891622f4edeb55e`.
`run.json` records this exact source head, actual machine details, dependency versions,
and action invocations. This is source acceptance; installed candidate wheel/sdist and
the full locked hosted runtime/numerical graph remain pending the five-ref batch push.

Machine: Windows 11 build 26300, Intel family 6/model 183, 24 physical/32 logical CPUs,
68,319,571,968 bytes RAM; Python 3.12.13. Reused `tools/ci/.venv`, pytest 9.0.3,
Ruff 0.16.2, mypy 1.20.2, Inspect 0.3.269, HF SDK 1.31.0; no Torch/runtime install.

## Exact local invocations

From the repository root, using PowerShell and the existing environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& tools/ci/.venv/Scripts/python.exe validation/2026-10-08-calibration-aware-outputs/run.py
& tools/ci/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-08-calibration-aware-outputs/unit-tests.xml
& tools/ci/.venv/Scripts/python.exe -m pytest tests/test_numerical_properties.py -q -k 'not rtn' --junitxml=validation/2026-10-08-calibration-aware-outputs/local-numerical.xml
& tools/ci/.venv/Scripts/python.exe -m ruff check quantfit tests tools
& tools/ci/.venv/Scripts/python.exe -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
& tools/ci/.venv/Scripts/python.exe -m mypy --strict quantfit/spec.py quantfit/engines/base.py
& tools/ci/.venv/Scripts/python.exe -m quantfit.cli audit --json
```

The driver executes the action's actual Validate inputs, Preflight, and Run gate Bash
blocks with the real source CLI, then its actual Python reader. `pre-run/` records exit 5,
unobserved scope and `actual-run-matched=false`; `observed/` records synthetic exit 0
and `actual-run-matched=true`. Both preserve `assumptions-verified=false` and
`human-labels-verified=false`, consumed-byte hashes, and explicit conditional summaries.
The widened case establishes fixture propagation, not detector sensitivity.

## Observed checks and preserved failures

- Unit command matches the hosted unit job: **1,633 passed, 8 skipped**, 1,641 cases.
  `unit-tests.xml` suite totals and individual testcase nodes were independently counted.
- Two available SciPy numerical properties passed. The Torch RTN property remains a
  full hosted numerical requirement; it was not suppressed in the workflow.
- Exact-path Ruff check/format, strict typing and audit pass; audit has zero findings.
- Focused TDD first showed seven missing card-input failures and three missing reader
  output failures before implementation. Tests cover scope/count/calibration/legacy
  statistic tampering, zero at-risk, MDE sentinel, deterministic bytes, same-buffer
  rendering, Bash contract skew/JUnit alias/operator conflict, and missing bound fields.
- `initial-full-tests.*` retain the earlier draft run: 1,631 passed, 8 skipped and three
  failures. Two were emit monkeypatch compatibility regressions, fixed by retaining the
  old one-argument call when no calibration is requested. One was absent Torch in this
  unit/tooling environment. This earlier draft is not the final candidate qualification.

`public-*-help.log` and `public-version.log` came from the previously verified isolated
public-PyPI 0.16.0 install outside the checkout. It exposes gate calibration, but no new
model-card calibration flag. No installation or dependency copy was made for this work.
The root review independently ran this exact action preflight with the public install,
PYTHONPATH removed and public Scripts first in PATH: exit 0, site-packages origin;
`root-public-preflight.json` records the sanitized result. This establishes the released
gate capability and actual preflight, not full runtime or calibrated-card execution.
The action invokes only gate and retains its usable published version default; hosted
installed acceptance uses the exact candidate wheel through `quantfit-path`.

## Limits

These records establish conditional presentation and fail-closed control propagation.
They establish no human-confirmed flips, authenticated human labels, A1/A2/A3 validity,
sensitivity-control result, research GO, safety certification, GPU/cross-hardware
behavior, independent reproduction, qualified reference report, QSR v1 freeze, or public
dataset publication. Original counts/verdict/floors remain distinct from conditional
MDEs. A null means the detector did not fire; no passing positive control is inferred.
All JSON was walked for prompt/completion/response/text/generation keys: none found.
No prior dated validation record was edited.
