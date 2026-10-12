# Offline replicate agreement acceptance — 2026-10-09

This record consumes historical Phi4 aggregates and separately named synthetic
policy fixtures. No model was loaded, nothing was newly judged, and no Hub
request was performed. `functional.json` records seven actual source CLI
invocations at source `424babb3f6b185c8ff563f5cafce023653eb4202`.
Historical direct/relocated analysis has full-report and native T0 agreement,
but retains native exits 3/3/3 and overall exit 3. Dangerous 0/12 means **the
detector did not fire**; each original over-refusal result flags 2/20 and is not
human confirmed. Named synthetic inputs separately exercise 0/3/4/2.

`run.json` contains hardware, exact installed versions, Git source blob hashes
and independently derived XML counts. The approved pre-existing Windows 11
environment uses Python 3.12.13, 32 logical CPUs and 68,319,571,968 RAM bytes.
Torch is absent. No new environment, dependency/model copy, worktree or
container was created. The typed source/test implementation is frozen at
`61c9de4754098ea7bc1042775f9f044f193a9ef5`; the later `424babb` commit changes
only two documentation lines describing the existing parser boundary. The first
whole-unit run started at `61c9de4` and found one omitted assistant retrieval
entry. Final source `c131b3eb4fa06fe531ecb8ab68ed9c248222fd75` adds only
`llms.txt` and usage-skill candidate entries; product/tests are unchanged. The
final whole-unit lane runs this immutable source. Prior validation is unchanged.

From the checkout, using `tools/ci/.venv/Scripts/python.exe`:

```powershell
python -m pytest tests -q --ignore=tests/test_numerical_properties.py --junitxml=validation/2026-10-09-repeatability/unit-final.xml
python -m pytest tests/test_numerical_properties.py -q -k 'not rtn' --junitxml=validation/2026-10-09-repeatability/properties-final.xml
python -m ruff check quantfit tests tools
python -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
python -m mypy --strict quantfit/spec.py quantfit/engines/base.py
python -m quantfit.cli audit --json
python tools/quickstart_check.py --no-run --min-commands 20 --quantfit-bin 'C:/tmp/qf-release-0.16.0-20261008/tools/ci/.venv/Scripts/python.exe -m quantfit.cli' --json validation/2026-10-09-repeatability/quickstart-final.json
python validation/2026-10-09-repeatability/run-functional.py
```

The functional script creates new named input directories and is intended for
a fresh destination; it refuses to replace the committed synthetic inputs.
Six output JSON files match their real CLI envelopes; each paired JUnit has
eight actual cases. `historical-prose.log` preserves the seventh invocation.
The static README inventory parses 50 commands and executes zero. Configured
mypy checks only two existing strict modules; it is not a claim of whole-package
typing. Two available SciPy properties pass; the RTN/Torch property is deselected
and awaits the existing hosted numerical lane.

`development-summary.json` preserves earlier failures and their actual causes:
TDD missing-module collection; a wrong positional argument in a new test; a
nonexistent test-path invocation; and incorrect new test expectations about
argparse/selected JSON mode. The preserved first whole-unit failure exposed
the missing `llms.txt` command and was fixed in retrieval docs, with the existing
inventory test unchanged. These were corrected without weakening production
decisions or existing checkers. Initial Ruff named nonexistent paths; exact CI
paths subsequently passed. Development working-file runs are not presented as
immutable-head qualification. `independent-review.json` records separate bounded
reviews of the exact source, original campaign parity and held-byte behavior.

`aggregate-scan.json` walks all recorded JSON keys for the repository's private
payload patterns. Its only allowances are exact public README syntax at
`quickstart-final.json:/commands/N/text`; aggregate reports/results have no
allowance. `members.json` binds every other dated member's canonical bytes/size.

This establishes offline source instrument behavior. It does not establish new
execution, source/host authenticity, independent physical hosts or statistical
replicates, human-label accuracy, detection sensitivity, cross-hardware
reproduction or scientific GO. Counts are not pooled. JSON/JUnit replacements
are individually atomic, not one multi-file transaction. Installed wheel/sdist,
Linux-only filesystem and full Torch numerical qualification remain pending
until the hosted batch. Root-owned checkout/environment are PRESERVE resources;
earlier automatically blocked cleanup has not been retried.
