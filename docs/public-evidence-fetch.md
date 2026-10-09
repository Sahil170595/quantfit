# Fetch the approved public aggregate snapshot

Candidate `evidence fetch` downloads the fixed public dataset
`Crusadersk/quantfit-reference-reports` at immutable commit
`3a4ff4e086f9d72ad828134873b01fa19b550059`. It is unreleased and requires the
candidate checkout/wheel. There is no repository, endpoint, revision or manifest
override. The installed package owns twelve independent path/size/SHA256 pins;
the downloaded publication manifest cannot authorize itself or new members.

```bash
quantfit evidence fetch --out public-evidence --timeout-seconds 120 --json
```

The typed API is `quantfit.evidence.fetch_evidence(out_path: str, *,
timeout_seconds: float = 120) -> dict`. The target must be new, with an existing
parent. The timeout must be a finite positive number at most 600 seconds. The
synchronous API refuses an already-running event loop before creating a coroutine.

The twelve originals total 78,390 bytes; the largest is 22,783 bytes. Retrieval
uses supported Hub URL/header APIs with `token=False` and an owned HTTPX client:
TLS verification stays enabled, environment proxy/credential configuration is
ignored, cookies are not replayed, and the Hub disk cache/global client is unused.
Only HTTPS redirects to the exact approved repository/revision/member resolve or
resolve-cache paths are followed, up to three hops. A single deadline covers all
twelve requests with finite per-operation timeouts. Raw bounded chunks cannot
extend the held buffer past its independent file cap. Compression is refused
before decoding; Content-Length is advisory. Exact size and SHA256 must match.

All twelve buffers are validated before any target is published. Original report
privacy/statistical validators stay unchanged; the native T0 is recomputed over
the same ordered held report bytes with producer paths treated only as labels.
Other JSON files have strict duplicate/nonfinite parsing and fixed closed
key/type/list-population profiles. Their only private-field exceptions are exact
root `/human_labels_authenticated: false` markers on assessment, campaign,
manifest and native cold-run, plus `/completion_cache_requested: false` on native
cold-run. Boolean false is required; zero, strings, true, nesting or objects are
refused. Counts, statistics, native exits, report/manifest membership and hashes
are checked against those same buffers. The generated installed shape shares
repeated records and is derived from the byte-verified approved publication by
`validation/2026-10-09-evidence-fetch/generate-shape.py`.

Independent byte pins are the primary boundary for substitutions into string
fields, README and model cards. The closed shape is specific to this snapshot;
it is not a generic privacy validator or source-authentication proof. Registered
reference count stays integer zero, human-confirmed flips stay null, and
registration/authentication/independence/sensitivity/GO claims remain false.

Original paths and bytes are preserved under the new target. Receiving-path full
comparison/native T0/per-run facts are returned as **separate** `receiving_analysis`,
never written over producer T0 or assessment. The three original Phi4 runs each
flag two unconfirmed over-refusal flips out of 20; dangerous 0/12 means **the
detector did not fire**. Fetch integrity exits 0 while receiving analysis retains
exit 3. Nothing is newly generated or judged, and counts are not pooled.

Publication stages only the fixed original members in an exclusively owned
sibling directory, checks short writes/flush/close/persisted bytes, then promotes
it atomically without replacing an existing target. Windows uses its native
nonreplacement rename; Linux requires `renameat2(RENAME_NOREPLACE)` support.
Other platforms are refused before HTTP. Unsupported filesystem promotion is
operational exit 2, with owned staging cleanup; arbitrary existing directories
are never removed. Links, junctions and nonregular outputs are refused. Output
receiving paths canonicalize after link checks; producer locators are never resolved.

Exit 0 means the approved bytes and aggregate relationships were retrieved and
published. Exit 2 means malformed/unsupported input, bounded HTTP, integrity,
deadline or publication failure. Argument errors rejected by argparse retain
usage on stderr; dispatched errors use the selected JSON/prose mode.

Local fake-HTTP source CLI/adverse evidence is in
`validation/2026-10-09-evidence-fetch/`. Actual anonymous download/installed shape
loading will be qualified through the existing Ubuntu/Windows wheel/sdist
consumer, without another CI job, model download or measurement campaign.
These hosted results remain pending until the feature batch is pushed.
