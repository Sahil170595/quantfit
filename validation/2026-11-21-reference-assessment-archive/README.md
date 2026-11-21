# Receiving assessment of a pinned replay archive

The Windows x86-64 run used the editable 0.70.0 candidate, Python 3.13 and the
locked dependencies from `tools/ci/uv.lock`. It assessed an existing public
historical aggregate fixture and deliberately labeled synthetic variants.
It compared original T0, native exits, report hashes and all 107 criteria
with the corresponding directory results. The receipt records process exits,
ZIP and receiving file digests, and JUnit counts parsed from the actual output.

Use the `scenario` fixture in `tests/test_reference_assessment_junit.py` with
`ready`, `historical`, or `unknown`. Produce the replay archive using the native
`pack` helper or the equivalent CLI. Use a temporary destination for each case.

```bash
python -I -B -m quantfit.cli bundle pack --bundle candidate --kind replay --out candidate-replay.zip --json
python -I -B -m quantfit.cli references assess --archive candidate-replay.zip --archive-sha256 SHA256 --target target.json --out archive-assessment.json --junit archive-assessment.xml --json
python -I -B -m quantfit.cli references assess --bundle candidate --target target.json --json
```

Use the expected SHA-256 from the pack receipt. Omitting or changing the digest,
or using the archive itself as the output file, returns exit 2 and preserves
the local inputs. Re-run the subprocess cases with
`python -B -m pytest tests/test_reference_assessment_junit.py -k actual_archive_cli`.

This run establishes direct offline receiving, source binding, and output
behavior. It establishes no new inference, independence, authentication of
weights or labels, new reference registration, or scientific verdict.
