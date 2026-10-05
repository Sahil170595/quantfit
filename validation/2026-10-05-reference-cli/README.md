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
