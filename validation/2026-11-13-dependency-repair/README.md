# Dependency repair evidence, 2026-11-13

The scheduled dependency audit failed on locked Soup Sieve 2.10. The daily
drift run also found locked OpenTelemetry API 1.45.1 advisories and selected
ACP 1.0.0, which removed the helpers imported by Inspect 0.3.269.

`result.json` records the original workflow IDs, a native import failure
with ACP 1.0.0 followed by success with ACP 0.12.1, and the all-version
lock advisory comparison. Official wheel bytes were verified against PyPI
SHA256 values before temporary extraction.

Local focused dependency, audit and real Inspect tests passed 298 cases
with three native skips. Ruff, formatting, strict contract typing, package
audit and an offline locked resolution passed. The complete default suite
was stopped after two visible failures in the pre-existing global graph, which
has no installed Quantfit distribution metadata. Failure causes were not
classified before stopping. Its partial output is retained outside Git. The
hosted complete suite remains required.

The fixed lock uses Soup Sieve 4.1 and OpenTelemetry API 1.45.2. Soup Sieve's
patched releases require Python 3.11.5, which now sets the public and
private source floor. The qualified Inspect SDK keeps ACP 0.x. uv 0.13.7
is the tool version explicitly supported by the failed Dependabot updater.

Reproduction uses the existing native commands from the repository root.

```powershell
uv lock --directory tools/ci --check --offline
python -m pytest tests/test_dependencies.py tests/test_ci_constraints.py tests/test_ci_dependency_audit.py tests/test_inspect_task.py tests/test_inspect_gguf.py -q
python -m ruff check quantfit tests tools
python -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture
python -m mypy --strict quantfit/spec.py quantfit/engines/base.py
python -m quantfit.cli audit
```

The local surrounding installed graph differs from the CI lock. Hosted
qualification must run the complete locked candidate workflow and dispatch
the existing fresh-resolution drift lane on the resulting commit. This
record does not establish model behavior, measurement validity, judge
accuracy, or scientific readiness.
