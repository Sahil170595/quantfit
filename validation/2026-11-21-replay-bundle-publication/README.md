# Replay bundle publication and rollback

The Windows x86-64 run used the 0.71.0 editable candidate, Python 3.13
and the locked dependencies in `tools/ci/uv.lock`. Inputs were local copies
of public saved aggregate evidence from the existing replay fixture.
`functional.json` records real process exit codes, output digests, and
isolated fault-injection outcomes through CLI dispatch. It rechecks
member byte equality independently from native `replay-verify`.

Generate three report files and the exact T0 with `inputs` in
`tests/test_replay_bundle.py`. At a private scratch destination, run:

```bash
python -I -B -m quantfit.cli bundle replay-create --reports rep-1.json rep-2.json rep-3.json --t0 t0.json --out handoff --json
python -I -B -m quantfit.cli bundle replay-verify --bundle handoff --json
python -B -m pytest tests/test_replay_bundle.py -k replay_cli_removes_only_attested_owned_files
```

The test uses an interrupted owned write, an existing expected-name entry,
and an unrelated entry introduced before or during the manifest write.
The first case rolls back and retries with success. The three foreign entries
are preserved and no readiness manifest survives. This establishes file
publication behavior for these controlled cases. It does not establish
crash durability, behavior under every simultaneous directory rename,
independent model execution or a new scientific verdict.
