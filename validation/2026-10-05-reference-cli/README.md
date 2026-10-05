# Offline reference CLI functional acceptance

This record exercises an explicitly synthetic external registry and count-only
fixture bytes. It does not represent a published reference report. The official
registry remains empty. No model, judge, GPU workload, human label, reproduction,
QSR v1 freeze or publication occurred.

Host: Windows 11, Python 3.12.13. A local RTX 4080 Laptop GPU was present and was
not used. Pinned tooling comes from `tools/ci/uv.lock`, synchronized with uv
0.12.23 using unit/numerical/runtime/tooling groups. `environment.json` records
the installed versions and runtime environment.

Invocations from this branch using the shared pinned interpreter:

```powershell
python -m quantfit.cli references list --json
python -m quantfit.cli references list --registry validation/2026-10-05-reference-cli/synthetic-registry.json --json
python -m quantfit.cli references verify --registry validation/2026-10-05-reference-cli/synthetic-registry.json --slug fixture --report validation/2026-10-05-reference-cli/synthetic-bytes.json --json
python -m quantfit.cli references verify --registry validation/2026-10-05-reference-cli/synthetic-registry.json --slug fixture --report validation/2026-10-05-reference-cli/synthetic-changed-bytes.json --json
python -m pytest tests -q
python -m pytest tests -q --cov=quantfit --cov-branch --cov-report=term-missing --cov-report=json:coverage.json
python tools/ci_coverage.py coverage.json
python tools/ci_mutation.py
python -m quantfit.cli audit
ruff check quantfit tests tools
ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
```

The output envelopes record the actual match/mismatch exits. Independently,
SHA256 over `synthetic-bytes.json` equals the manifest digest, while the changed
file's digest differs. This establishes an offline byte-checking command path,
not the validity, authenticity or publication of any measurement claim. An
external manifest is operator-supplied and can itself be fabricated.

`test-summary.json` records the final local suite, coverage floors and separate
installed-wheel/rebuilt-sdist checks outside the checkout. Installed acceptance
borrows the locked dependency environment but installs the candidate package into
an isolated environment. Hosted CI performs independent installs on its runners.
The JSON key walk reviewed the `regeneration_required` match as boolean spec-refresh
metadata; it contains no completion content. Each CLI record now has per-entry
publication flags and makes no authenticated citation claim.

The dated 2026-10-05 correction to the stale registry-state prose is grounded in
`validation/2026-08-21-screen-complete/README.md`; that historical record is unchanged.

After integration onto the four prerequisite branches, `integration.json` and
`integration-tests.xml` record the combined source qualification separately from
the standalone results above. The suite passed 1,623 tests; the pass count was
also derived from JUnit. Combined coverage was 91.66% overall and 89.96% of
branches, with all scientific module floors passing. Installed wheel and rebuilt
sdist each passed 423 acceptance tests. The installed README check recognized
36 commands and ran seven clean-environment commands; its other 29 commands were
not executed. These counts describe this local instrument qualification only.

Exact additional commands (same hardware and locked interpreter as above):

```powershell
python -m pytest tests -q --cov=quantfit --cov-branch --cov-report=term-missing --cov-report=json:C:/tmp/quantfit-stack-coverage-20261005.json --junitxml=C:/tmp/quantfit-stack-tests-20261005.xml
python tools/ci_coverage.py C:/tmp/quantfit-stack-coverage-20261005.json
python tools/ci_mutation.py
python -m mypy --strict quantfit/spec.py quantfit/engines/base.py
C:/tmp/actionlint-quantfit-20261004/actionlint.exe -color
python -m build --no-isolation --outdir C:/tmp/quantfit-stack-dist-20261005
python -m twine check C:/tmp/quantfit-stack-dist-20261005/*
uvx --from uv==0.12.23 uv pip install --python C:/tmp/quantfit-resolution-installed-env-20261005/Scripts/python.exe --no-deps --no-build-isolation --reinstall C:/tmp/quantfit-stack-dist-20261005/quantfit-0.15.1-py3-none-any.whl
C:/tmp/quantfit-resolution-installed-env-20261005/Scripts/python.exe tools/ci_installed.py --checkout C:/tmp/quantfit-reference-20261005
uvx --from uv==0.12.23 uv pip install --python C:/tmp/quantfit-resolution-installed-env-20261005/Scripts/python.exe --no-deps --no-build-isolation --reinstall C:/tmp/quantfit-stack-dist-20261005/quantfit-0.15.1.tar.gz
C:/tmp/quantfit-resolution-installed-env-20261005/Scripts/python.exe tools/ci_installed.py --checkout C:/tmp/quantfit-reference-20261005
C:/tmp/quantfit-resolution-installed-env-20261005/Scripts/python.exe tools/quickstart_check.py --min-commands 20 --quantfit-bin 'C:/tmp/quantfit-resolution-installed-env-20261005/Scripts/python.exe -m quantfit.cli' --json C:/tmp/quantfit-stack-quickstart-20261005.json
```

Candidate package installation was isolated; dependencies were borrowed through
a `.pth` from the shared locked environment. This is distinct from hosted CI's
fresh runner installations. Production Inspect provider files were unchanged
by integration; the prior actual CPU record is preserved, not rerun or promoted
to GPU or sensitivity evidence here. Hosted checks must qualify the published
heads before this stack is declared ready for review.

## Hosted exact-byte fixture correction

The Linux installed-wheel job
[111782812735](https://github.com/Sahil170595/quantfit/actions/runs/37315947731/job/111782812735)
correctly refused the synthetic match case: the recorded local fixture digest
was for CRLF bytes, while Git checked out LF bytes. This does not license newline
normalization in the verifier. The installed acceptance harness now copies the
runner's exact bytes into its temporary sandbox and declares their digest in a
fresh synthetic registry. Historical envelopes and their local-run digests above
remain unchanged; they are local observations, not portable fixture declarations.

`newline-cases.json` records four actual installed CLI cases: LF and CRLF each
match their own declared digest, and each refuses the other byte representation
with exit 3. `installed-byte-fixture.json` records subsequent installed-wheel
acceptance from outside the checkout with the locked numerical/tooling graph.
This check runs no model workload and does not authenticate any publication.
Hosted Linux/Windows wheel and rebuilt-sdist jobs still qualify the final head.

```powershell
uvx --from uv==0.12.23 uv sync --directory tools/ci --locked --no-default-groups --group numerical --group tooling --python 3.12 --reinstall
tools/ci/.venv/Scripts/python.exe -m build --no-isolation --outdir build/candidate-dist
uvx --from uv==0.12.23 uv pip install --python C:/tmp/quantfit-resolution-installed-env-20261005/Scripts/python.exe --no-deps --no-build-isolation --reinstall build/candidate-dist/quantfit-0.15.1-py3-none-any.whl
C:/tmp/quantfit-resolution-installed-env-20261005/Scripts/python.exe tools/ci_installed.py --checkout C:/tmp/quantfit-reference-bytes-ci-20261005
tools/ci/.venv/Scripts/python.exe validation/2026-10-05-reference-cli/reproduce_newlines.py C:/tmp/quantfit-resolution-installed-env-20261005/Scripts/python.exe
```

The isolated installed environment borrows dependencies from this worktree's
locked environment through a `.pth`; it contains its own candidate package.
The newline comparison cases run from a temporary directory outside the checkout
using the same installed interpreter, the fixture registry metadata and raw
`write_bytes` inputs. Each case independently hashes the input bytes and compares
both digest fields returned by the CLI. The raw synthetic JSON is not a model
completion or a published reference report.
