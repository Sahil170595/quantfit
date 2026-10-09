# Bounded GGUF structure and optional native usability

Candidate `verify` replaces the old four-byte magic check with bounded binary
validation. Its optional native CPU request is a separate question. The candidate
checkout/wheel is required; no version or scientific milestone is implied.

```bash
quantfit verify --model model.GGUF --json
quantfit verify --model model.gguf --runtime --timeout-seconds 120 --json
```

The legacy `quantfit.verify.verify(path, max_new_tokens=8) -> tuple[bool, str]`
retains Transformers load/generate behavior and ignores its legacy token argument
on the structural GGUF branch. The rich typed API is
`quantfit.gguf_verify.verify_gguf(path: str, *, runtime: bool = False,
timeout_seconds: float = 120, max_new_tokens: int = 8) -> dict`. New runtime
options require exact types, finite positive timeout at most 1,800 seconds and
integer token budget 1..64. CLI `--timeout-seconds` requires `--runtime`.

Exit 0 means the requested supported check passed, 3 means a demonstrated invalid
supported binary/extent, and 2 means unavailable capability, operational failure
or an unverified outside-profile input. JSON separately reports `structure` and
`runtime`; requesting runtime can never be labeled `not_requested`. Argument
errors rejected by argparse retain usage on stderr. Non-GGUF Transformers
verification keeps its existing tuple/error behavior.

The structural profile supports nonempty little-endian GGUF versions 2 and 3,
scalar/non-nested typed arrays and tensor ranks 1..4. One resolved readonly regular
file descriptor is checked with `fstat`; symlinked Hub-cache inputs can resolve
to canonical blobs without suffixes or model copies. The rich API does not depend
on filename suffix. Legacy/CLI directory selection accepts case-insensitive GGUF
names and refuses immediately on a second matching member.

The scanner uses stdlib exact reads and installed optional `gguf` constants,
without GGUFReader, mmap, NumPy products or tensor allocation. Before loops or
allocation it bounds directory bytes to 128 MiB, metadata/tensor populations to
100,000 each, aggregate array items to 2,000,000 and a metadata value string to
1 MiB. Exceeding those chosen limits is unverified 2. Unknown formats/types,
big-endian forms, version 1 and nested arrays are unverified, rather than declared
corrupt. Missing constants clearly name `pip install 'quantfit[gguf]'`.

Known syntax checks include UTF8 strings, hierarchical ASCII lower_snake_case
metadata keys and the standardized decimal-indexed `general.base_model.{id}` /
`general.dataset.{id}` lineage fields, with the specified 65,535-byte maximum, duplicate keys/names,
boolean encodings 0/1, tensor names at most 64 bytes, UINT32 nonzero power-of-two
alignment, positive dimensions, row divisibility, aligned nonoverlapping positive
tensor intervals and complete extents within EOF. Declared dimensions use `ne0`
as the quantized row: Q4_0 `(32,2)` is valid and `(16,2)` is invalid even though
its product is 32. Extent arithmetic uses Python integers. SDK-reported
`general.file_type` and tensor-type counts remain distinct observations.

IEEE NaN/Inf metadata floats are valid binary encodings; JSON's finite-number
rule is not imposed on GGUF. Gaps/trailing padding and an empty unique tensor
name are not invented corruption. Zero-filled valid tensor storage can pass
structure and still be meaningless weights. Generic aligned extent validity
does not promise native b9817's stricter contiguous layout or architecture rules.

2026-10-09 format-profile defect: interpreting the specification's generic
snake-case prose literally rejected its explicitly standardized indexed lineage
keys. The pinned producer emitted these keys in the hosted qualification. The
scanner now admits only their known source fields; arbitrary numeric namespaces,
malformed indices and duplicate keys remain refused.

Optional runtime requires Linux with `/proc` before binary provisioning. The
existing conservative RAM admission requires available RAM at least twice model
size plus 1 GiB, without claiming that is a measured memory estimate. It reuses
the owned llama.cpp server/lifecycle used by Inspect, without importing optional
`inspect_ai`: CPU/no-offload, context 4096, one slot, temperature 0 and no prompt
cache. A single deadline covers load plus one fixed small request. Responses
request identity encoding, refuse unsolicited compression and cap raw metadata
and result bytes before JSON decoding. Async cancellation closes HTTP contexts
before terminating/reaping the owned group. Direct child reaping and no live
group members observed are required before qualification; grandchildren are
not claimed reaped.

The runtime consumes parser-held selected metadata, not GGUFReader. Model and
binary hashes before/after detect observed changes and retain provenance; they
do not attest exactly which bytes were served. Served path/context/slot/build
facts are required. Receipts retain structure, hashes, output character count,
termination and cleanup, with no generated text/digest or raw server errors.
Unknown termination remains unknown, rather than a fabricated clean stop.

The existing hosted Smol F16/Q4 qualification replaces its one four-token native
slot with this helper, keeping its observed Q4_K_M scheme assertion. It adds no
model, generation, download or CI job. Existing Inspect aliases, error identity
and ordinary behavior remain covered. Actual Linux/native and installed
Ubuntu/Windows wheel/sdist results await the hosted feature batch. Local crafted
binary/source-CLI and fake HTTP/server evidence is in
`validation/2026-10-09-gguf-verification/`. None establishes model quality,
refusal safety, sensitivity or scientific GO.

Format/protocol sources: [GGUF specification](https://github.com/ggml-org/ggml/blob/master/docs/gguf.md),
[pinned native b9817 loader](https://github.com/ggml-org/llama.cpp/blob/b9817/ggml/src/gguf.cpp).
