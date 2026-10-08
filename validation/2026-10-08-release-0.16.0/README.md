# quantfit 0.16.0 aggregate release candidate

The release branch retains the exact reviewed heads of #114–#118 as ancestors:
calibration `7232e6b1`, resolution `45d27469`, T0 `bb1d5f4b`, Inspect
`4f843a3e`, and references `4cc5eb66`. The release changes only load-bearing
software/action version locations and the current changelog section.

Local validation uses Windows x86-64 and CPython 3.12.13, with the complete
`tools/ci/uv.lock` unit/tooling graph installed by uv 0.12.23. The command
outputs and exit codes are recorded in `checks.json`, and `unit.xml` records
individual test outcomes. Commands run from this release checkout:

Final local checks passed: 1,614 unit cases passed and eight skipped, independently
counted from the JUnit testcase records and checked against its suite totals.
Ruff check/format, the strict spec/engine typing check and `quantfit audit` passed.
`checks.json` preserves the initial format failure and successful correction of
mixed line endings introduced while changing the package version.

```powershell
uvx --from uv==0.12.23 uv sync --directory tools/ci --locked --no-default-groups --group unit --group tooling --python 3.12
tools/ci/.venv/Scripts/python.exe -m pip install -e . --no-deps --no-build-isolation
tools/ci/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-08-release-0.16.0/unit.xml
tools/ci/.venv/Scripts/ruff.exe check quantfit tests tools
tools/ci/.venv/Scripts/ruff.exe format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
tools/ci/.venv/Scripts/mypy.exe --strict quantfit/spec.py quantfit/engines/base.py
tools/ci/.venv/Scripts/quantfit.exe audit
```

The format command's glob is expanded by the validation recorder on Windows.
The separate hosted release workflow validates the exact merged tag and consumes
the same candidate wheel/sdist bytes it tested, including numerical properties,
Linux/Windows installed acceptance, consumer-action failures, dependency audit,
real pinned CPU GGUF/CT/Inspect generation, judge cases, and provenance.

This local unit environment has no Torch runtime. Its skips do not establish
numerical or backend acceptance. Synthetic functional cases do not establish
human label truth, independent judge error, sensitivity-control success, GPU
behavior, cross-hardware tolerance, physical-host identity, independent execution,
QSR v1 freeze, independent reproduction, or a research GO. A detector null
continues to mean "the detector did not fire" without a passing positive control.
