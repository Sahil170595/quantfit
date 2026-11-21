# Single-calibration and supplied-control composition — local source evidence

This unreleased 0.63.0 candidate composes the existing complete supplied-control
triplet, single `--calibrations-dir` and optional scalar
`--require-conditional-resolution`. The recorded base is released 0.61.0
`7a72944421d5c7d0087c6961728e8ff9f139e1f5`; this branch does not depend on the
unmerged per-axis option. Public install guidance remains 0.61.0.

`functional.json` records 417 selected passes, one Windows symlink-capability skip,
and a separate three-test final actual SDK/OS CLI consumer check. These overlapping
runs are not added together. Counts were independently derived from both JUnit cases
and pytest's log; the new composition module contributes 52 passing cases. It also
records literal source SHA256/Git blob identities, actual output hashes and six
frozen legacy JSON/human/JUnit parity results.

The native reuse spy admits two targets, reads five screen/calibration roles and
holds three private control roles once, parses two target reports and one control
report, builds one base summary and performs two existing native analyses (288 native
work units). Control does not change native/calibration qualification or JUnit.
The actual OS CLI case publishes complete JSON and JUnit and retains native exit 3;
it is an adverse native report, not a passing safety result.

Runs used Windows, Python 3.13.1 and the existing scoped editable-source environment;
exact installed pytest/Ruff/mypy versions are in `functional.json`. Runtime/audit and
the scoped editable distribution are 0.63.0; the in-checkout metadata lookup first
finds an ignored inherited 0.56.0 egg-info, which is preserved rather than repaired
in this shared environment. No model, judge,
Hub/provider call, new environment or global dependency change was used.

Reproduce the recorded selected scope with a fresh temporary directory (the original
`qf-063-final-01` is preserved for review):

```powershell
$python = 'C:\tmp\qf-env-20261113\Scripts\python.exe'
& $python -B -m pytest -q -p no:cacheprovider tests/test_screen_control_calibration.py tests/test_screen_control_evidence.py tests/test_ci_screen_resolution.py tests/test_ci_screen_requirement.py tests/test_screen_resolution.py tests/test_screen_resolution_cli.py tests/test_screen_requirement.py tests/test_screen_requirement_cli.py tests/test_saved_screen.py tests/test_meta.py tests/test_audit.py tests/test_refreports.py --basetemp='<fresh-directory>' --junitxml='<fresh-junit-path>'
& $python -B -m ruff check quantfit tests tools
& $python -B -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture tools/ci_corpus_fixture
& 'C:\tmp\qf-env-20261113\Scripts\quantfit.exe' audit --json
& 'C:\tmp\sequential-delivery-20261113\qf-uv0137\bin\uv.exe' lock --check --offline --no-cache --directory tools/ci
```

The final three-test command is recorded verbatim in `functional.json`; its original
log/JUnit and all earlier red/adverse records remain under
`C:\tmp\sequential-delivery-20261113\qf-063-*`. The before witness uses the same
held fictional inputs and frozen time/version for six old paths: plain, control,
single calibration, scalar, named variants and named variants plus scalar. Each
JSON/human/JUnit result is byte-identical. Original witnesses and private fictional
captures/adjudication files stay local; only aggregate counts/hashes are committed.

One regression intentionally changed the held capture during native verification:
15 controls passed and one failed because MDE started before the next stamp check.
The narrow repair rechecks the held control roles after all calibration preparation,
before native analysis; the focused 16 controls then passed. The initial unsupported
composition red run and a corrected test-import ordering check are retained separately.
A same-scope strict skip-import typing comparison has the same three accepted-base
`no-any-return` diagnostics in `saved_screen.py`; the two changed core implementation
files are clean. No cast, ignore, dependency repin or environment workaround hides it.

This is local command evidence. It does not establish clean wheel/sdist installation,
hosted OS/matrix/CodeQL/canonical typing qualification, real model behavior, authenticated
human labels, independence, source/weight authenticity, sensitivity or scientific GO.
The Windows symlink test still requires hosted execution. Outputs remain individually
atomic rather than a pair transaction: an ownership change between writes can leave
the first output. Original screen/calibration buffers retain their existing inventory
rechecks; only held private controls carry the native stamp checks. Public release and
all four clean installed-profile qualifications remain separate delivery gates.
