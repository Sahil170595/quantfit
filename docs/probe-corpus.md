# Pinned alternative probe corpus — unreleased 0.51.0

Public installation remains 0.46.0. This candidate adds a frozen `ProbeCorpus(id, revision, split)` (also lazily exported at `quantfit.ProbeCorpus`) and keyword-only `probe_corpus=None` to `verify_safety`, `qsr_paired_diff` and `qsr_eval`. Existing positional inputs and the default source are unchanged. An explicit alternative is a supplied noncanonical distribution, not curated or authenticated by this tool.

```python
from quantfit import ProbeCorpus, verify_safety

source = ProbeCorpus("org/probes", "1111111111111111111111111111111111111111", "validation")
drift = verify_safety("org/base", "./out", probe_corpus=source, report_path="drift.json")
print(drift.summary())
```

Both native CLI entry points accept the same all-or-none flags:

```bash
quantfit verify-safety --baseline org/base --quant ./out --probe-dataset org/probes --probe-revision 1111111111111111111111111111111111111111 --probe-split validation --report drift.json --json
quantfit inspect-run --baseline hf/org/base --quant hf/org/quant --baseline-revision 2222222222222222222222222222222222222222 --quant-revision 3333333333333333333333333333333333333333 --probe-dataset org/probes --probe-revision 1111111111111111111111111111111111111111 --probe-split validation --report drift.json --json
```

These are operator requests, not dataset/model runs established here. All invalid options, corpus rows or operational loading failures are 2. Native detected-regression 3 outranks unmeasurable 4, otherwise 0; zero means the detector did not fire and never certifies safety. A valid one-axis population retains its native missing-axis/unmeasurable result.

## Exact source and whole admission

- Exact string ID, namespaced and validated by the supported Hub validator, at most 256 strict UTF8 bytes. Caller URLs, local paths, packaged aliases and exact reserved `buckets/` namespace are refused. The SDK itself treats that namespace specially even after stripping its dataset prefix; it is not an alternative supported transport.
- Revision is exactly 40 lowercase hexadecimal characters. Split is one ASCII literal 1..64 characters matching `[A-Za-z0-9_][A-Za-z0-9_.-]*`; `all` (case-insensitive), whitespace, concatenations and slices are refused. No curation/canonical boolean is accepted.
- One public `load_dataset_builder("hf://datasets/" + id, revision=pin, token=...)` selects the SDK's remote-only route. Its actual hash must exactly equal the pin BEFORE `as_streaming_dataset(split).select_columns(["prompt", "zone", "expected"])`. Missing/wrong/`auto` cached fallback hashes refuse; there is no plain-ID or cached-latest fallback in the application.
- Admit the whole yielded population in native order, 1..4096. The 4097th, empty input, malformed final row or late iterator/EOF error refuses BEFORE any observer, model resolver/construction/generation or judge call on direct HF/GGUF and unobserved/observed Inspect routes. No first-acceptable prefix, filtering, sorting, deduplication or `str()` coercion.
- Every actual prompt/zone/expected is a string. Prompt is nonempty strict UTF8 and at most 65,536 bytes. Zone is `clear_safe`/`clear_unsafe`/`borderline`; expected is independently explicit `safe`/`unsafe`, never inferred from zone. Sum UTF8(prompt)+UTF8(zone)+UTF8(expected) across the whole population is at most 8,388,608 bytes; no truncation or trimming.

Actual type checks apply to the SDK-yielded values: the SDK may decode/coerce underlying storage before yielding, so this is not independent raw-file schema validation.

These are limits on application-retained selected strings/population. They do NOT bound earlier SDK metadata/downloads, parser/chunk/scalar allocation, heap, network bytes, latency, filesystem/cache effects or authentication. Projection is not promised storage pushdown. Matching a builder hash establishes its selected Hub module revision, not curation, authenticity, scientific suitability or immutability of every externally referenced data byte. Actual admitted strings are the measured population.

## Provenance, cache and interpretation

The actual ID/revision/split/count flows through ordinary reports and capture-only report binding, Inspect dataset name/location and task/log metadata, completed `QsrRun` and delayed writers. Low-level `write_drift_report(..., probe_corpus=source)` requires the operator to declare the source; outcomes alone do not authenticate it. New private source carriers remain outside generic dataclass/asdict data; copy/deepcopy/replace retain the triple and native math/to_dict projections stay unchanged.

GGUF-only baseline caching keeps its existing protocol and adds no Inspect/HF cache. Its existing identity uses actual source triple and ordered prompt digest/count: changing ID, revision, split, one prompt, order or population misses. A cache hit changes no measured number. Defaults keep their bytes/order/native Wilson/MDE and exact full-source tuple. Same default ID with a different revision/split is noncanonical even if it yields 40 identical rows. Canonical reference execution additionally requires the existing actual 40-row/recipe conditions BEFORE model work; a custom 40 source cannot qualify.

Custom API summaries/cards/Inspect metadata disclose supplied/noncanonical scope, including calibrated and capture-backed/adjudicated card paths. Historical default-corpus judge accuracy/error and the fixed n<=34 detectability paragraph are not validation of a new distribution or a conclusion about its actual n. Actual per-axis native statistics remain; bound calibration must match the same type-sensitive full identity/fingerprint and its assumptions remain unverified. No pooling, independence, human authentication, sensitivity, null clearance or scientific GO is added.

## Qualified SDK compatibility

The public dependency is deliberately narrowed to `datasets==5.0.1`, already installed and locked; no unrelated package update is needed. Installed 5.0.1 `datasets/load.py` SHA256 `ea755fddc5a1d3f56179d4ed9a376cfa7289162c2aab8c8e0e533d0b46365fb6` supplies native `remote_only` URI handling (1046–1048; documented 1267/1548). [Official 3.0.0 source](https://github.com/huggingface/datasets/blob/3.0.0/src/datasets/load.py#L1450-L1583) has no such stripping and its relative-path remote branch does not admit this URI. That older-version incompatibility is source inference, not an executed older-SDK result. Do not fallback to unsafe local/plain-ID behavior to retain the old range.

Actual 5.0.1 metadata requires Hub>=0.25,<2; the existing application Hub>=0.25 floor is retained because no newer Hub API is used. The 174-node private lock, browser-ci group, active 160 external environment and fixed filelock/Python 3.11 policy stay held. Original wheel, sdist and rebuilt wheel must declare the qualified datasets pin.

## Evidence boundary

[Regenerable aggregate controls](../validation/2026-10-31-probe-corpus/README.md), native tests and installed original/rebuilt provenance gates use controlled SDK factories/fictional strings and synthetic generation/judging. Actual native Dataset/IterableDataset, Inspect pipeline, cache, report/capture/calibration/card and OS module entrypoint behavior are exercised. There is no actual Hub corpus download, real provider/model/judge inference, GPU/paid call, human review or scientific qualification. Raw captures, prompts, Inspect logs and temporary calibration inputs remain private and uncommitted.
