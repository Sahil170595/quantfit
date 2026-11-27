# Selected original annotation returns

[`functional.json`](functional.json) records the installed Quantfit 0.74.0
candidate on Windows x86-64, Python 3.12, with the locked unit and tooling groups.
Use `prepare` and `fill` from
[`tests/test_annotation_chunks.py`](../../tests/test_annotation_chunks.py) to
generate the fictional sheet, key, manifest and filled parts in a temporary
directory. Map the resulting paths into the invocation below.

```bash
python -I -B -m quantfit.cli calibrate chunks validate --sheet SHEET --key KEY --manifest MANIFEST --part 2=PART2 --part 4=PART4 --require-part 2 --require-part 4 --out inspection.json --junit inspection.xml --json
```

With new output paths, repeat using `--require-part 1` in place of
`--require-part 2` to retain one missing required part. The receipt compares the
overall coverage results, selected coverage and resulting JUnit case counts.
This is a fictional file-census fixture. It does not establish collection,
calibration, human labels, rater identity, or scientific validity.
