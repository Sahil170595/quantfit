# Direct receiving of pinned screen archives

This Windows x86-64 run used the candidate editable distribution, Python 3.13
and the locked unit/tooling environment in `tools/ci/uv.lock`. The existing
public aggregate screen fixture supplied synthetic observations.
`functional.json` records process exit codes, archive digests, JUnit counts
and receiving file SHA-256s. Directory parity compares full JSON after
removing only the comparison and receiving summary timestamps.

Use `original_inputs`, `observation` and `make_bundle` from
`tools/ci_screen_compare.py` to create local bundles. Use one synthetic
flagged report or omit one report to reproduce native exit 3 or 4. At a
temporary output location, run the following with the installed candidate.

```bash
python -I -B -m quantfit.cli bundle pack --bundle reference/bundle --kind screen --out reference.zip --json
python -I -B -m quantfit.cli bundle pack --bundle candidate/bundle --kind screen --out candidate.zip --json
python -I -B -m quantfit.cli screen-compare --reference-archive reference.zip --reference-sha256 REF_PIN --candidate-archive candidate.zip --candidate-sha256 CAND_PIN --out comparison.json --junit comparison.xml --json
python -I -B -m quantfit.cli screen-compare --reference-archive reference.zip --reference-sha256 REF_PIN --candidate-bundle candidate/bundle --out mixed.json --junit mixed.xml --json
python -I -B -m quantfit.cli screen-compare --reference-bundle reference/bundle --candidate-bundle candidate/bundle --json
```

Use the lowercase digests from the pack receipts. A different reference pin
produces exit 2 with neither output present. The evidence establishes receiving
behavior over aggregate fixtures. It provides no new model executions,
authenticated source identities, confirmed labels, sensitivity measurements
or scientific verdicts.
