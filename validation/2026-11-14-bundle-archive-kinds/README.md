# Explicit native archive kinds — local source evidence

Unreleased source 0.64.0 is independently based on released main
`7a72944421d5c7d0087c6961728e8ff9f139e1f5`; public installation remains 0.61.0.
The existing pack/archive-verify/unpack commands and SDK functions accept explicit
aggregate/replay/screen kinds. Default aggregate success bytes, schema, results and
caps remain identical; a dated retained-stage error-category repair is intentional.

`functional.json` is the aggregate record: 682 passed / 18 declared Windows skips,
145 new archive-kind cases, followed by eight stricter dispatch/duplicate-warning
checks after a test-only change. Overlapping runs are not summed. Counts are derived
independently from JUnit testcases and pytest logs. Exact commands, source raw SHA256
and Git blob identities, actual ZIP hashes, native byte limits and adverse attempts
are included. The existing scoped Windows Python 3.13.1 environment, CPU identity and
pinned pytest/Ruff/mypy/UV versions are recorded; no GPU or new environment was used.

Actual native replay SDK/OS CLI pack-pin-verify-restore retains an adverse original
T0 and relocates only receiving labels honestly; producer labels never cause IO.
Screen SDK/OS CLI retains original populations/native3/4, optional untrusted summary
bytes and the empty reports directory for all-missing populations. Source holds are
once per role, with one native receiving validation and no directory verification
followed by reread. Native replay `_validate` is AST-identical to the accepted base;
whole source blobs for original T0/screen receiving primitives are unchanged.

The cap controls use genuine native payloads, with JSON whitespace padding only:
replay payload 33,619,968 bytes produces the exact maximum canonical archive
33,620,488 bytes; screen payload is exactly native 67,108,864 bytes including all
roles. One additional outer-manifest byte is refused. Separately, 256 original
ordered screen targets plus optional summary produce 259 ZIP entries and a maximum
77-byte safe member name. Pre-ZipFile count/central/ZIP64/bad-EOCD spies, exact raw
pin ordering, wrong-kind, hostile ZIP, source mutation and owned cleanup controls
are recorded without turning outer integrity into a scientific verdict.

The before witness preserves an actual pre-edit aggregate ZIP, SDK results and CLI
envelope. Default and explicit aggregate both reproduce its exact ZIP/result bytes
and CLI stdout/stderr/exit when only the intended tool version is frozen to 0.61.0.
The pin is `5a555ab51ccd433635a52d52cb8d250f02922086b7b1bfb2a4d5e8e8d31ebcec`;
its nested native gate remains exit 5. This comparison does not freeze new feature
math or replace any native report/T0 data.

Two review findings have separate deterministic RED records. A screen destination
created before failed first identity attestation was retained but reported a generic
error (1 failed/2 passing controls); the native publication now explicitly preserves
that unattested root. Three real stage replacement/unstatable/unlink-failure causes
across all three kinds retained uncertain stages and already linked outputs but
reported a generic error (9 failed/3 first-root controls passing). The uniform dated
repair reports `archive_stage_preserved`, with no caller policy flag, unsafe deletion
or additional success-path filesystem operations. The final selected suite contains
all 12 passing ownership controls. Earlier fixture mistakes and static diagnostics
remain distinct, unsummed evidence.

Reproduce using a **fresh** basetemp/output directory; the named original resources
are preserved for review. The exact recorded selected and focused commands are in
`functional.json`. CI's static commands are:

```powershell
$python = 'C:\tmp\qf-env-20261113\Scripts\python.exe'
& $python -B -m ruff check quantfit tests tools
& $python -B -m ruff format --check quantfit tests tools/ci_*.py tools/ci_gate_fixture tools/ci_corpus_fixture
& $python -B -m mypy --strict --follow-imports=skip --cache-dir '<fresh-cache>' quantfit/bundle_archive_kinds.py quantfit/bundle_transport.py quantfit/screen_bundle_publication.py
& 'C:\tmp\qf-env-20261113\Scripts\quantfit.exe' audit --json
& 'C:\tmp\sequential-delivery-20261113\qf-uv0137\bin\uv.exe' lock --check --offline --no-cache --directory tools/ci
```

The unchanged independent 174-package tools/ci graph is not the versioned project.
No root lock, dependency, new CI job or artifact upload is added. The existing four
clean wheel/sdist installed consumers select the new controls; the actual screen/CPU
consumer and historical replay installed seam use the same native receivers.

This is local editable-source command evidence, not hosted OS/matrix/CodeQL or clean
installed-wheel/sdist proof. Platform capability skips still require hosted execution.
It establishes no real model quality, authenticated human labels/producer paths,
independent execution, source/weight/host authenticity, sensitivity, safety PASS or
scientific GO. Restoration is manifest-last with partial visibility and conservative
owned cleanup, not a directory transaction or hostile-concurrent-rename guarantee.
The original local `qf-064-*` before/red/adverse/cap/native consumer witnesses are
preserved under `C:\tmp\sequential-delivery-20261113`; no private captures or labels
are committed. Source-qualified publication and all hosted gates remain separate.
