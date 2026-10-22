# Strict screen resume: bounded aggregate protocol validation

The inputs are **synthetic aggregate fixtures**, not model measurements. The actual
CLI parser, dispatch, strict native receiver, resume logic, JSON emission and JUnit
renderer consume them. A generation trap rejects unexpected execution. In the
missing-one case a single bounded hook writes the declared native aggregate bytes;
it does not load or run a model or judge.

The three original schema-v2 reports and original manifest are under `inputs/`.
The fixtures were constructed with `tools/ci_screen_resume.py::synthetic_fixture`,
using the structural template from
`validation/2026-08-21-screen-complete/reports/gguf-gemma3-270m-lmstudio.json` and
`SafetyDrift.to_dict()` for native statistics. Every weight revision, weight SHA256
and executable SHA256 in these new reports is explicitly fictional. They do not
authenticate a real repository, executable, hardware configuration or measurement.
The old validation record was read without modification.

| Target | Dangerous at-risk / flips | Over-refusal at-risk / flips | Expected row |
| --- | --- | --- | --- |
| clean | 12 / 0 | 28 / 0 | no_regression |
| flagged | 12 / 1 | 28 / 0 | regression |
| unmeasured | 0 / 0 | 0 / 0 | unmeasurable |

The resulting target denominators are two measured dangerous targets with one
judge-flagged target, and two measured over-refusal targets with zero flags. No
human confirmed any flag. The declared sensitivity-control `pass` in the manifest
is deliberately unauthenticated: receiving conditionality and resolution caveats
must remain. For a zero-flip result, the detector did not fire; this is not a safety
certification or evidence of detection sensitivity.

The current protocol pins in the fixture match the strict receiver:

- Judge: `garak-llm/garak-refusal-detector`, revision
  `5cb5ec8f364318cc48724ddf8ad414000c36781b`, completion-only input contract.
- Probe dataset: `Crusadersk/quantsafe-judge-benchmark`, revision
  `c26cc2e15fcadab9c0ec24a5b57d37b140f7ed58`, split `train`, all 40 probes.
- Greedy decode, `max_new_tokens=64`, current
  `model-default when present, raw prompt otherwise` template policy.

The fixture producer version is `synthetic-bounded-aggregate-fixture`; it is
preserved in the receiving receipt and does not claim a native inference run.

## Execution and reproduction

Recorded host: Windows 11 build 26300, Intel Core i9-13980HX (24 physical cores,
32 logical processors), AMD64, Python 3.12.13. Source and editable distribution
versions were both 0.32.0. The unit environment contained `huggingface_hub` 1.31.0
and pytest 9.0.3; Torch and Transformers distributions were absent, recorded as
`null` rather than inferred from the synthetic report declarations. These CLI paths
validate saved aggregates without those optional runtime imports. Exact receiving
source-file byte hashes and sizes are in `receipt.json.runtime.source_files`.

Run from the repository checkout with the candidate source on `PYTHONPATH`:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = (Get-Location).Path
python validation/2026-10-18-screen-resume/run_validation.py --out C:/tmp/qf-screen-resume-validation
```

The recorded isolated-worktree invocation used the same script with an explicit
origin assertion and an external working directory:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = 'C:/tmp/qf-screen-resume-delivery-20261018'
C:/tmp/sequential-delivery-20261017/qf-unit-env/Scripts/python.exe C:/tmp/qf-screen-resume-consumers-20261018/validation/2026-10-18-screen-resume/run_validation.py --expected-source C:/tmp/qf-screen-resume-delivery-20261018 --out C:/tmp/sequential-delivery-20261017/qf032-screen-resume-validation-original-bytes
```

The output directory must not exist. The script invokes `quantfit.cli.main` with
the following real CLI arguments in its output directory, captures stdout as
exactly one JSON document, and retains aggregate outputs:

```text
screen --targets all-present/manifest.json --out all-present/reports --resume --max-new-tokens 64 --json --junit screen.xml
screen --targets missing-one/manifest.json --out missing-one/reports --resume --max-new-tokens 64 --json
screen --targets refused/manifest.json --out refused/reports --resume --max-new-tokens 64 --json
screen --targets alias/manifest.json --out alias/reports --resume --max-new-tokens 64 --json --junit alias/manifest.json
```

All-present resumes must skip all three rows and retain their original SHA256 and
byte lengths. Missing-one must execute only `clean` and skip the other two reports.
Both retain exit 3 because the existing flag takes precedence over an unmeasured
row. JUnit must contain three cases, one failure and one skipped case. A favourable
producer `screen-summary.json` is supplied in the all-present case and ignored.

The corrupt-last case omits the first target and corrupts the final present report;
it must refuse with exit 2 before any hook runs, preserving the corrupt bytes. The
output-alias case must refuse exit 2 while preserving every original manifest and
report byte. `receipt.json` records primitive-count projections, raw bindings,
runtime versions and explicit proof limits. `.gitattributes` prevents JSON/XML
newline translation from invalidating the original-byte bindings.
The runner copies the original manifest bytes into every case before admission;
it does not rely on the host's JSON newline convention. The stored original
manifest has CRLF endings and the stored original native reports have LF endings.

| Recorded case | CLI exit | Skipped / executed | Additional check |
| --- | --- | --- | --- |
| all-present | 3 | 3 / 0 | Original native bytes and flags retained |
| missing-one | 3 | 2 / 1 | Only `clean` written by the bounded fixture hook |
| corrupt-last | 2 | No native calls | Original corrupt member bytes retained |
| JUnit aliases manifest | 2 | No native calls | Every original input byte retained |

JUnit independently contains three cases, one flagged failure, one unmeasured
skip and zero errors. A second count method sums `by_zone` populations and compares
the explicitly constructed one-direction refusal counts: it reproduces dangerous
2 measured / 1 flagged and over-refusal 2 measured / 0 flagged. This count method
is valid for these constructed fixtures; marginal refusal differences do not in
general recover paired flips. Every JSON file was walked for keys matching
`prompt|completion|response|text|generation`; there were zero matches. The public
values contain configuration declarations and aggregate counts, not actual text.

## What this does not establish

This package does not establish model safety, judge quality, positive-control
sensitivity, human-confirmed regressions, independent execution, authentic model
weights or hardware, repeatability, speed or memory performance. The fixture
engine, environment and weight identities are declarations. No weights, binaries
or models were downloaded or executed. No captures, probe text, completions,
label sheets, adjudication keys or private cache files are included.

Source CLI acceptance, installed-wheel acceptance and hosted real CPU acceptance
are separate evidence. The installed coordinator runs the same dedicated consumer
tests under its existing application-origin guard. The CPU coordinator reuses the
first report from its already-existing cold run under a generation trap; this
synthetic source record does not claim that hosted lane ran.
