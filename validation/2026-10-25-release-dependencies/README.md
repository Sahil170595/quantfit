# Quantfit 0.37 dependency maintenance — 2026-10-25

The actual installed-graph audit rejected filelock 4.0.10 for three newly published
advisories and setuptools 84.0.0 for GHSA-xmj3-9gf7-h52w. `audit.json` records the
versions, advisory IDs, authoritative sources, lock identities and observed results.
No ignore list or broad upgrade was used.

The native command was `python tools/ci_dependency_audit.py`, using the existing
Windows Python 3.12 validation environment populated by the hash-locked
`tools/ci/uv.lock` runtime, numerical and tooling groups. The original run exited 1;
the maintained graph exited 0 with no known vulnerabilities, and `python -m pip check`
exited 0. CPU Torch remained included via its existing `+cpu` normalization.

Native targeted resolution changed filelock and setuptools only. Conditional filelock
3.20.3 preserves the Python 3.10 unit/source branch because the fixed 4.2.1 release
requires Python 3.11. Public runtime requirements carry the same branch boundary and
setuptools security floor; a build-system floor alone cannot constrain Torch's
separate runtime dependency. The complete runtime still requires Python 3.11+.

The original manual constraints CLI rejected valid disjoint Python marker declarations
with exit 2. The maintained helper uses packaging's native marker evaluator for its
interpreter, preserves unmarked bounds, and still rejects conflicting active bounds.
Missing manual bootstrap parsers fail with a short operational diagnostic. The focused
marker/dependency-policy suite passed 48 tests, including disjoint branches, active
overlap, native CLI and isolated-build-domain controls. New API-signature RED cases are
new-interface tests, not evidence of an old evaluator defect.

Reproduction commands (use the same approved environment for generation and consumption):

```sh
uv lock --directory tools/ci --upgrade-package filelock --upgrade-package setuptools
uv sync --directory tools/ci --locked --no-default-groups --group runtime --group numerical --group tooling --python python
python -m pip install -e . --no-deps --no-build-isolation
python -m pip check
python tools/ci_dependency_audit.py
python -m pytest tests/test_ci_constraints.py tests/test_dependencies.py -q
```

The lock update is a historical command; reproducing the committed graph uses
`uv sync --locked`. Python 3.10 coverage here means native lock/marker contracts,
not a local full-runtime run. Full hosted candidate checks, installed wheel/sdist
qualification and versioned publication are separate requirements. This record does
not establish vendor binary integrity, absence of undisclosed vulnerabilities, GPU
execution, model behavior, label authenticity or scientific GO. No inference or
labeling campaign ran.
