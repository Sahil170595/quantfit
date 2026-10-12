# Portable bundle Windows/Linux correction — 2026-10-08

Hosted PR #121 at `3f1de493cfd1d0edc46a082db5b62c54f477f9b7` failed both Ubuntu
installed consumers while both Windows consumers passed. Actual jobs:
- https://github.com/Sahil170595/quantfit/actions/runs/37879024716/job/113654208695
- https://github.com/Sahil170595/quantfit/actions/runs/37879024716/job/113654208553

`cross-platform-red.json` records independent execution of the exact committed
bundle validator Git blob on Windows Python3.12.13 and existing Ubuntu WSL
Python3.12.3. Identical four input SHA256s accept on Windows and reject on Linux.
The only recalculated resolution difference is `perfect_judge_mde`:
0.1486600774792154 versus 0.14866007747921536. This is actual source-level
reproduction, not installed-package qualification or a model run. The validator
was compiled from the named Git blob in each isolated child; its unchanged
ancillary resolution/calibration/gate sources were imported normally.

Final implementation is `a5f3fb66d96f7d71bedd05896828430c8aaeb043`. It reuses the
existing calibration statistic comparator and its 1e-12 relative/absolute
floating-point tolerance. Booleans and strings now have exact type/value branches;
integer counts, nulls and recursive field sets remain exact. Resolution and native
gate computed statistics tolerate roundoff; hashes, provenance, messages, stage,
claims and decision thresholds are not relaxed. Bound gate calculations use the
validated calibration's canonical bounds, not a nearby serialized epsilon.
Inputs are copied and hashed as their original bytes, never rounded or regenerated.
The installed consumer now exposes its aggregate JSON refusal on a failed create.

`roundoff-red.*` retains five failing regressions: two adjacent-float refusals and
three previously accepted count/boolean type aliases. `gate-roundoff-red.*`
retains four analogous failures for derived gate values and types. Gate adjacent
floats are explicit synthetic perturbations, not a claim that this original Linux
gate differed. Fifteen new regression cases cover accepted roundoff and refused
count/type/hash/status/claim/material-statistic alterations. No scientific
threshold, protocol, CI floor or mutation sentinel was changed.

Final available Windows suite: **1699 passed,13 skipped**, independently counted
from1712 `unit-final.xml` cases. Existing WSL executes the whole bundle suite:
**66 passed,1 skipped** (Windows junction only). Two Hypothesis/SciPy numerical
properties pass; Torch RTN remains unavailable locally. Exact CI Ruff check/format,
mypy paths and audit exit0 pass. `gates.json` records actual argv/exit codes;
`source.json` records actual consumed source hashes, canonical Git blob hashes and
CRLF-to-LF equivalence. The first format check caught mixed EOL after patching;
Ruff corrected working EOL without changing canonical Git content. The earlier
uncommitted draft's1699-pass run remains `unit.xml`, distinct from final source
qualification. Initial bundle-only58-pass evidence predates the added gate cases
and canonical bound calculation and is not the final gate.

`cross-platform-fixed.json` records actual source CLI creation on Windows and
Linux with the unchanged original synthetic four-role input bytes. Both exit0;
eight copied members' hashes and sizes verify. These records still declare a
regression report and native pre-run UNRESOLVABLE5, with no observed gate match.
The two generated manifests and their four members are preserved. No raw captures,
labels, completion caches or model weights were produced. The new directory has
its own JSON `-text` rule; earlier archives are not edited or normalized.

Commands from the worktree, with `PYTHONDONTWRITEBYTECODE=1`, using the already
approved `C:/tmp/qf-release-0.16.0-20261008/tools/ci/.venv/Scripts/python.exe`:

```text
python -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-08-bundle-cross-platform/unit-final.xml
python -m pytest tests/test_numerical_properties.py -q -k 'not rtn' --junitxml=validation/2026-10-08-bundle-cross-platform/properties.xml
python -m ruff check quantfit tests tools
python -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
python -m mypy --strict quantfit/spec.py quantfit/engines/base.py
python -m quantfit.cli audit --json
wsl.exe -d Ubuntu --cd /mnt/c/tmp/qf-bundle-roundoff-20261008 -- python3 -B -m pytest tests/test_bundle.py -q -p no:cacheprovider --junitxml=validation/2026-10-08-bundle-cross-platform/linux-bundle.xml
```

This establishes aggregate format/relationship/byte portability only. It establishes
no authenticated origin, scientific GO, human confirmation, sensitivity,
independent reproduction, hardware/GPU residency, T0 or QSRv1 freeze. Hosted
installed wheel/sdist requalification is pending the corrected head's push.
No environment/dependency/model copies or containers were created; only existing
Windows/WSL runtimes were used. Task child commands exited; final worktree lifecycle
is supplied separately after the exact correction ref is safely published.
