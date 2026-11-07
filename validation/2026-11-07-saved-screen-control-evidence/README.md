# Saved-screen supplied control evidence — source validation

Unreleased software 0.61.0, Windows, existing Python 3.12.13 tooling environment.
The published baseline is 0.56.0. `summary.json` records aggregate outcomes and
current source hashes; private fictional captures/records and raw test diagnostics
are retained outside the repository and are not uploaded.

The native fictional producer writes a real aggregate/capture, prepares and fills
a manufactured adjudication queue, applies the native record writer, then removes
the queue/preparation before intake. These labels are controlled declarations, not
human judgments. API and actual `python -m quantfit.cli screen-summary` paths verify
the held triplet; the fixture is also selected by the four existing installed
Linux/Windows wheel/sdist consumers. That wiring is not installed execution proof.

Commands (task-owned temporary paths are placeholders):

```text
python -B -m pytest tests/test_screen_control_evidence.py tests/test_saved_screen.py tests/test_meta.py tests/test_agent_surfaces.py tests/test_quickstart.py tests/test_json_envelope.py tests/test_refreports.py tests/test_screen_resolution.py tests/test_screen_requirement.py tests/test_calibration_choices.py tests/test_screen_adjudication.py tests/test_adjudication_verification.py tests/test_ci_installed_imports.py tests/test_calibration_binding.py tests/test_calibrated_modelcard.py -q --tb=short --basetemp TEMP/tests --junitxml=EVIDENCE/current-focused.xml
python -B -m ruff check quantfit tests tools
python -B -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture tools/ci_corpus_fixture
python -B -m mypy --strict --follow-imports=silent --cache-dir TEMP/mypy quantfit/saved_screen.py quantfit/screen_control_evidence.py
python -B -m mypy --follow-imports=silent --check-untyped-defs --cache-dir TEMP/mypy quantfit/safety/calibration_binding.py
python -B -m quantfit.cli audit
git diff --check
```

The native at-least-one dangerous criterion includes degenerate and mixed
confirmed/unresolved/incorrect declarations. Safe-only flags, zero risk, missing
reports, unsupported protocols and entirely unresolved declarations stay explicit.
Default outputs, native JUnit, rows, counts, exits and scientific flags are held.
Tests include custom revision/local SHA differences, every held report's complete
native decode declaration, per-stratum applicability, CWD locator comparison,
whole capture/record tampering, role budgets, duplicate/aliased sinks and changed
inputs. Unsupported calibration combinations refuse before IO.

The qualified initial RED is one native positive plus two failures for absent SDK
and actual CLI roles; first GREEN is three passes. A later causal two-case RED
showed optional supported decode declarations were lost by the existing coarse
protocol projection. The same controls pass after the new annotation compares
the complete native normalized decode for every actual report. Setup mistakes,
earlier typing/import diagnostics and their actual scopes remain in `summary.json`
and external raw/XML; none is relabeled a passing product run.

Review then demonstrated that full measurement identity was too strict for saved
reports with unknown arm pins. The same nullable-HF regression fails before and
passes after extracting only the previous native decode normalization verbatim.
All other native calibration-binding function/class ASTs are held; restoring the
inlined decode body yields the exact original measurement-identity AST. A separate
intra-stratum fixture initially duplicated arm content SHA and correctly hit the
existing duplicate-evidence refusal; distinct fictional digests correct that setup.

Broad focused result: **598 passed, 5 capability/platform skips, 0 failed/errors**
(603 XML cases). After the final typing-only change from an indirect `_report`
re-export to its defining native import, all **49 affected cases passed again**.
Current Ruff/format, strict two-file typing, the original native binding typing
policy, audit and Git whitespace checks pass. The 49 new cases are all unskipped.
Source runs and earlier focused/cause cohorts overlap and are never added together.

No new model generation, judge execution, Hub access, browser, paid work or human
labeling occurred. This does not prove historical association, control transfer
across degradation levels, sensitivity, independence, source authentication,
performance or scientific GO. Existing native statistics and all older validation
records remain unchanged. Current hosted/installed and actionlint results are
separate future qualification; local source runs are not substituted for them.
