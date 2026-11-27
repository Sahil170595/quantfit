# Offline reference target preflight

[`functional.json`](functional.json) records the installed Quantfit 0.71.0
candidate on Windows x86-64 with Python 3.12 and the `tools/ci/uv.lock` unit and
tooling groups. The target comes from `write_target` in
[`tests/test_reference_assessment.py`](../../tests/test_reference_assessment.py).
Use that fixture to produce `target.json` in a temporary directory and derive
its exact `SHA256` with the platform's file hash tool.

```bash
python -I -B -m quantfit.cli references target-verify --target target.json --json
python -I -B -m quantfit.cli references target-verify --target target.json --sha256 SHA256 --json
```

Run the second command again with 64 zeros as the pin to reproduce the mismatch
receipt. The outcomes cover schema admission and exact-byte digest handling.
The fixture's declared facts are inputs. This run does not verify any model,
execution, evidence label, publication criterion, or scientific claim.
