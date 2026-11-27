# Declared identity requirement for screen comparison

[`functional.json`](functional.json) records the installed Quantfit 0.73.0
candidate on Windows x86-64, Python 3.12, with the locked unit and tooling groups.
Generate a separate directory for each case using `pair` in
[`tests/test_screen_compare.py`](../../tests/test_screen_compare.py). Use the
default fixture, `unknown=True`, and `unknown=True` with `reference=(1, None)`.

```bash
python -I -B -m quantfit.cli screen-compare --reference-bundle reference/bundle --candidate-bundle candidate/bundle --require-compatible-identity --out comparison.json --junit comparison.xml --json
```

The run compares saved JSON to stdout and counts JUnit outcomes. It checks that
an unresolved declaration prevents exit 0 and that an original flag retains
exit 3. These are synthetic declaration and gate controls. The run does not
establish real execution identity, model authenticity, human adjudication, or
scientific validity.
