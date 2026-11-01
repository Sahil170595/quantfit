# Python 3.11 security compatibility correction

This is **unreleased quantfit 0.47.0** source validation, recorded on
Windows/Python 3.12. Public installation remains 0.46.0; old wheels and dated
validation records are not rewritten.

The universal validation lock previously retained filelock 3.20.3 for Python
3.10 even though the active Python 3.12 audit used 4.2.1. Both
[GHSA-8mx5-7m5m-r77g](https://github.com/advisories/GHSA-8mx5-7m5m-r77g) and
[GHSA-69hj-f68j-2879](https://github.com/advisories/GHSA-69hj-f68j-2879) include
that old branch. Official patched filelock distributions require Python 3.11;
[Python 3.10 reached EOL on 2026-10-01](https://peps.python.org/pep-0619/#310-lifespan).
This candidate withdraws 3.10 installation/source support, requires 3.11 in both
projects, removes only the 3.10 unit job, and retains the public
`filelock>=4.2.1,<5` range and private 4.2.1 pin. Numerical/runtime Python 3.12,
coverage, mutation, measurement rules and scientific criteria are unchanged.

`security.json` records the native supported-domain lock regeneration against
accepted source commit `b1e123a939c70710041aecc35ac160946830f578`:

- 176 full package entries/170 names become 170 entries/168 names; six old
  entries disappear, with no added/upgraded package.
- Native resolution simplifies 53 surviving full entries and prunes 273
  Python 3.10-specific wheel records. Surviving versions, sources, sdists and
  all retained wheel records remain exact. This does not assert that arbitrary
  wheels with a `cp310` filename are incompatible with newer Python: stable
  ABI compatibility must be considered separately. Every actually pruned file
  has only `cp310-cp310` or `pp310-pypy310_pp73` tags; no `abi3` wheel was pruned.
- The metadata policy test checks every advertised interpreter's filelock
  requirements, excluding disclosed affected versions and retaining 4.2.1.
  This is advisory-domain admission evidence, not an exploit demonstration.

The existing audit command now inventories both installed external pairs and
all universal registry lock versions, independent of environment/group markers.
`security.json` retains the exact pair roles and minimal lookup layers. Only
the known Torch `+cpu` release maps to its public version for advisory lookup;
the genuine installation lock stays unchanged by this projection. Unknown
schema/source/version and native layer failures fail closed. Tests preserve
both versions of a name, installed-only pairs and same-pair role sharing, and
prove all layers are attempted before aggregate failure. An actual native
`pip-audit --dry-run` control rejects conflicting pins in one file and accepts
their separate layers without querying advisories. The recorder likewise only
enumerates; the real fresh all-layer audit is the separate existing maintenance
command, with its own logs. Neither a mock nor collection-only run is represented
as a successful vulnerability-service query.

Regenerate the aggregate records from a checkout containing the baseline commit,
using its existing locked validation environment:

```bash
python validation/2026-10-31-python311-security/regenerate.py
```

The script overwrites only this directory's `security.json` and `functional.json`.
It never invokes a historical recorder or edits any older validation record.
`functional.json` is a fresh execution of the existing native adjudication
consumer: ten producer/synthetic-fill/apply/verify workflows, twenty adverse
controls, four auxiliary receiving controls and twenty capture-backed cards.
The consumer covers API and **in-process** CLI return values; API receipt/errors
map to harness 0/2. Its seventeen hashes bind the actual current raw source,
including the changed workflow. Different checkout line endings may produce
different raw hashes without changing the admitted native semantics.

Temporary fictional inputs are closed and removed after execution. Committed
records contain aggregates and source hashes only, with no captures, labels,
keys, sheets, queues or completions. Human labels are synthetic. The run does
not establish authenticated origin, real human correctness, model/judge
inference, scientific GO, GPU behavior, universal future vulnerability absence
or a repair to already-published artifacts. Active-environment advisory audit,
original/rebuilt installation, full source tests and fresh hosted acceptance
are separate gates; their actual executions are reported on the PR.
