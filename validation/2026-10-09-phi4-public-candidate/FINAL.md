# Final integration qualification

Actual installed/native measurement was source `2997c930`, CI
[37890682118](https://github.com/Sahil170595/quantfit/actions/runs/37890682118).
The separately qualified final integration source is
`d15a436f9da2c106def5c265c5fea30c88887ec2`. The actual hosted campaign was not
rerun for documentation/receipt changes. All 45 other package module blobs and
the campaign controller/workflow are unchanged; only the registry status prose
changed in `quantfit/refreports.py`, with the remaining module AST identical.
The actual producer source/wheel identities are retained rather than relabeled
as measurements of the final metadata head.

`final-local-receipts.json` independently classifies 1,850 JUnit cases:
**1,818 pass, 32 skip, zero failures/errors**. Two available SciPy numerical
properties pass. The focused reference/campaign suite passed 115 cases on the
unchanged working bytes before the source commit; the full final suite ran on
frozen d15. Exact lint, formatting (110 files), strict selected type checks and
audit exited 0; audit has zero errors and two existing documentation warnings.
Local Windows has no Torch runtime; full numerical/native/Linux candidate
qualification is the hosted graph, not a local claim. No new dependencies,
models, environments or WSL launch/repair were used.

The actual final local commands and outputs are `final-*.log`, `final-unit.xml`,
`final-properties.xml`, and `final-audit.json`:

```powershell
tools/ci/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-09-phi4-public-candidate/final-unit.xml
tools/ci/.venv/Scripts/python.exe -m pytest tests/test_numerical_properties.py -q -k 'not rtn' --junitxml=validation/2026-10-09-phi4-public-candidate/final-properties.xml
tools/ci/.venv/Scripts/python.exe -m ruff check quantfit tests tools
tools/ci/.venv/Scripts/python.exe -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
tools/ci/.venv/Scripts/python.exe -m mypy --strict quantfit/spec.py quantfit/engines/base.py
tools/ci/.venv/Scripts/python.exe -m quantfit.cli audit --json
```

`independent-integration-pass.json` records the consequential review of exact
d15. `final-byte-check.json` checks exact staged Git bytes and all ten producer
hashes/sizes while preserving the earlier `byte-check.json`. The public dataset
commit and actual anonymous round-trip are fixed in
`public-reference-publication.json`. Final exact-head PR checks are pending at
record creation; the branch-specific heavy campaign runs only on explicit
workflow dispatch and will not repeat for this evidence commit/PR.

The public negative/unconfirmed candidate remains outside the reference
registry. No human labels are authenticated, no fresh sensitivity/absence/GO,
independent hardware, free-T4/GPU, Inspect parity or QSR v1 freeze is claimed.
