# Native report environment fixture — 0.51.0 candidate

The [C hosted run](https://github.com/Sahil170595/quantfit/actions/runs/41225246738) fixed the missing datasets profile and eliminated its 106 fixture errors. Its four thin unit jobs then each reported one failure, 3,650 passed and 17 skipped: the new custom-corpus GGUF software test reached the real delayed report writer, whose native environment fingerprint imports Torch. The numerical job contained Torch but not Transformers and reported the same test failure at the next native import (3,657 passed, 14 skipped, six deselected). All five completed logs and the exact C test/Git source representations are preserved locally; they supply the causal RED without a new local import-blocking framework.

Only that new test now follows the existing `test_actual_public_inspect_full_fixture_batch_closes_before_judge` pattern: a deterministic synthetic `report.environment_fingerprint` fixture. The real writer/receiver remain in use; complete population, loaded source, both server/arm call counts and owned closure assertions stay. Added assertions verify the fixture was used exactly once by the late writer and the parsed environment equals the fixture. This is software metadata isolation, not physical CPU/GPU provenance. No product, runtime dependency, skip, scoring rule, calibration or private profile is changed.

Regenerate only this new record from its scoped JUnit output:

```bash
python -m pytest tests/test_inspect_gguf.py tests/test_probe_corpus.py -q --junitxml=report-fixture.xml
python validation/2026-10-31-probe-corpus-report-fixture/regenerate.py --junit report-fixture.xml
```

The prior B [feature record](../2026-10-31-probe-corpus/README.md) and C [profile record](../2026-10-31-probe-corpus-unit-profile/README.md) remain byte-held and historical. Relative to B's 24 source hashes, 21 stay held and three intentionally differ: the two C profile files and this test. Native report/verifier/application and public package metadata remain held; B full/native results are not D executions. B's sdist includes the old test source, so it is not claimed that all D package/test inputs equal B. Fresh D hosted builds, installed/browser acceptance, full matrix and CodeQL are required.

Public install remains 0.46.0; candidate 0.51.0 is unreleased. Controlled fixtures do not establish real Hub/model/human, external-byte authenticity or scientific qualification. No old validation or changelog is rewritten.
