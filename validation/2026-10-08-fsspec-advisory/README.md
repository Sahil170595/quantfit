# Newly disclosed fsspec advisory blocks the release candidate

The exact candidate CI run [37852886308](https://github.com/Sahil170595/quantfit/actions/runs/37852886308)
failed its dependency job [113570110203](https://github.com/Sahil170595/quantfit/actions/runs/37852886308/job/113570110203):
the full installed graph contained `fsspec==2026.4.0`, reported vulnerable to
`CVE-2026-104851` with fixed version `2026.6.0`. Installation and `pip check`
passed; the advisory gate failed correctly. `failure.json` preserves the
sanitized diagnostic and installed/current package metadata used to select the fix.

The [upstream fix](https://github.com/fsspec/filesystem_spec/commit/86438783f93b1398ef245b92f0e6063b445b611c)
changes reference-file template rendering. Existing `s3fs==2026.4.0` pinned the
affected fsspec exactly; current `s3fs==2026.6.0` requires `fsspec>=2026.6.0,<2026.6.1`.
The pinned datasets 5.0.1 and Inspect 0.3.269 permit the fixed version. Only
fsspec and s3fs were upgraded in `tools/ci/uv.lock` using uv 0.12.23:

```powershell
uvx --from uv==0.12.23 uv lock --directory tools/ci --upgrade-package fsspec==2026.6.0 --upgrade-package s3fs==2026.6.0
uvx --from uv==0.12.23 uv sync --directory tools/ci --locked --no-default-groups --group unit --group tooling --python 3.12
tools/ci/.venv/Scripts/python.exe -m pip install -e . --no-deps --no-build-isolation
tools/ci/.venv/Scripts/python.exe -m pip check
tools/ci/.venv/Scripts/python.exe tools/ci_dependency_audit.py
tools/ci/.venv/Scripts/python.exe validation/2026-10-08-fsspec-advisory/run_checks.py
```

Fresh Windows x86-64 / CPython 3.12.13 unit/tooling checks and JUnit are
recorded here with installed versions and the corrected lock hash. The earlier
release record is retained unchanged because it used the previous lock.
Hosted candidate and exact-tag release CI qualify the full runtime graph.

The change preserves the dependency gate and all existing caps, tool/runtime
pins, source behavior, model/corpus pins and data definitions. This unit graph
has no Torch runtime; local checks do not establish CPU model or numerical
acceptance. Neither these checks nor hosted CPU functional acceptance establish
GPU behavior, human calibration, sensitivity, cross-hardware tolerance,
independent execution/reproduction, a QSR v1 freeze or research GO.

After editable installation, local `pip check` exits 1 because the intentionally
light unit/tooling graph omits accelerate, datasets, llmcompressor, Torch and
transformers. The recorder checks that exact missing set and preserves the
diagnostic; this is not full-runtime dependency acceptance. The hosted installed
and dependency jobs install the complete runtime graph and require `pip check`
to exit 0. The earlier failed hosted candidate already passed that check before
the newly disclosed fsspec advisory stopped its audit.
