# Pinned archive verification receipt

[`functional.json`](functional.json) records the installed Quantfit 0.72.0
candidate on Windows x86-64, Python 3.12, with the `tools/ci/uv.lock` unit and
tooling groups. Generate the replay directory with
`replay(Path("fixture"), adverse=True)` from
[`tests/test_bundle_archive_kinds.py`](../../tests/test_bundle_archive_kinds.py).
Use the expected `FULL64` digest from the pack result.

```bash
python -I -B -m quantfit.cli bundle pack --kind replay --bundle fixture/bundle --out replay.zip --json
python -I -B -m quantfit.cli bundle archive-verify --kind replay --archive replay.zip --sha256 FULL64 --out verification.json --json
```

Try the verification with 64 zeros before the successful call, repeat it with
the existing receipt, and use `replay.zip` as the output. The run compares the
saved receipt with the same verification's stdout and checks that refusals
preserve both existing files. The synthetic replay's adverse protocol result
survives successful transport verification. This run establishes receipt and
integrity behavior only. It does not authenticate the producer or establish a
measurement, reproduction across hosts, or scientific verdict.
