# Completed Inspect report recovery (0.60.0 candidate)

Windows / existing Python3.12.13 source checks run native Inspect eval/scoring
against existing controlled GGUF server/file fixtures and one controlled judge
batch. No real model, GPU, Hub, engine performance or human annotation ran.
Checkpoints and raw Inspect logs stay in owned temporary directories; only counts,
byte pins and software outcomes enter this record.

Initial actual TDD was1 native completed40-pair report PASS +2 API/CLI absence
FAIL, then3PASS. Regression cohorts retain retry receipt loss, statistical-tolerance
misuse on copied declarations and preserved-stage categorization failures before
minimal fixes. Cohorts overlap and early drafts used0.56 source metadata; they are
not additive or combined current qualification.

Exact focused invocation with the existing interpreter and an owned temporary base:

```text
python -B -m pytest -q -p no:cacheprovider --basetemp OWNED_TEMP/tests tests/test_inspect_recovery.py tests/test_inspect_task.py tests/test_inspect_cli.py tests/test_inspect_hf.py tests/test_inspect_gguf.py tests/test_calibration_binding.py tests/test_json_envelope.py tests/test_meta.py tests/test_refreports.py tests/test_ci_installed_imports.py
python -B -m ruff check quantfit tests tools
python -B -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture tools/ci_corpus_fixture
python -B -m mypy --strict --follow-imports=silent quantfit/inspect_recovery.py
python -B -m quantfit.cli audit
```

`summary.json` records current software controls, native byte bindings and a
separate actual offline CLI recovery of an unchanged historical observed-HF
report. Its original0.15.1 metadata is retained; it is not a new model run. Four
existing hosted installed profiles select the new native controlled producer and
actual recovery CLI tests, plus that historical-byte control. They have not run
locally as installed distributions. No full local suite, hosted CI, current engine,
calibration, authenticity, human truth, sensitivity or scientific GO is claimed.
The SDK still runs then explicitly writes; its sink admission is at write time.
Only CLI known sinks are preadmitted before model work. Old source/protocol/native
math and all prior validation records remain held.
