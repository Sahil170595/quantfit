# Indexed annotation collection

The Windows x86-64 run used the editable 0.69.0 candidate with Python 3.13
and the dependencies selected by `tools/ci/uv.lock`. The installed
consumer generated 18 fictional local annotations across four original
parts. Four rows were marked unusable. The original receipts and private
files stayed outside the repository. The aggregate receipt records actual
CLI subprocess exit codes, canonical ordering and exact byte equality
with ordered collection.

```bash
python -B tools/ci_annotation_chunks.py --checkout . --out /tmp/annotation-test.json
python -B -m pytest tests/test_ci_annotation_chunks.py tests/test_annotation_chunks.py tests/test_annotation_returns.py
```

Use a private scratch destination for the first command. The consumer invokes
`python -I -B -m quantfit.cli calibrate chunks collect` with the original sheet,
key and manifest, two fresh outputs and repeated `--indexed-part INDEX=PATH`.
It tests the input orders 4/3/2/1, 4/2/1, 4/3/2/2 and the original indices
misbound to returns 4/3/2/1. The complete run produces byte-identical files.
The three refusals preserve the original inputs and create neither output.
The SDK test also collects a complete all-unusable population and checks the
subsequent native ingest refusal.

These are collection and ingest behaviors for fictional inputs. This run
establishes no human judgment, authenticated identity or scientific verdict.
