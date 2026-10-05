# Standalone T0 source-path regression

This record uses synthetic aggregate schema-v2 reports. It checks the functional
path binding of T0 evidence and does not represent inference, human calibration,
independent execution, physical-host verification or a safety/research GO.

On Windows, the regression first creates passing T0 artifacts using relative
source filenames, then consumes them from a different directory using absolute
artifact and comparison-report paths. An invalid namesake report in the consumer
directory must not be read. The fixed producer records canonical absolute paths;
positive consumption still rechecks the original source hashes and identities.
An additional compatibility test keeps existing relative-path artifacts readable
when consumed from their original directory.

Validation command:

```powershell
tools/ci/.venv/Scripts/python -m pytest tests/test_t0.py tests/test_reproduce.py -q --junitxml=validation/2026-10-05-t0-path-fix/pytest.xml
```

The environment follows `tools/ci/uv.lock` (unit and tooling groups): CPython 3.12.13
and pytest 9.0.3, on Windows 11 AMD64 with an Intel Core i9-13980HX. No inference
runtime or GPU was used. The checked-in JUnit record contains 179 passing cases,
independently counted from its testcase elements, with zero failures or skips.
The pre-fix directory-change
case returned operational exit 2 by reading the consumer's invalid namesake; the
fixed case returns the protocol's `reproduced`/0 on these declared fixtures.
