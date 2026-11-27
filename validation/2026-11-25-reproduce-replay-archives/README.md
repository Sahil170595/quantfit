# Direct reproduction from pinned replay ZIPs

[`functional.json`](functional.json) records the installed Quantfit 0.75.0
candidate on Windows x86-64 and Python 3.12 with the locked unit and tooling groups.
Generate one temporary scenario at a time with `make_bundle` from
[`tests/test_reproduce_bundles.py`](../../tests/test_reproduce_bundles.py).
Use `reference` with `foreign=True`, and `candidate` with default values,
`flips=1`, or `disagreement=True`.

```bash
python -I -B -m quantfit.cli reproduce --reference-bundle reference --candidate-bundle candidate --json
python -I -B -m quantfit.cli bundle pack --bundle reference --kind replay --out reference.zip --json
python -I -B -m quantfit.cli bundle pack --bundle candidate --kind replay --out candidate.zip --json
python -I -B -m quantfit.cli reproduce --reference-archive reference.zip --reference-sha256 REFERENCE_SHA256 --candidate-archive candidate.zip --candidate-sha256 CANDIDATE_SHA256 --out comparison.json --junit reproduction.xml --json
```

Move the original directories out of the receiving paths before the last call.
Use the exact archive digests from the pack results. The recorded exits, native
predicates and test case counts demonstrate transport parity for synthetic saved
aggregates. This run does not establish independent execution, actual hardware,
authenticated evidence, a scientific reproduction or a safety result.
