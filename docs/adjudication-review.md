# Private offline review — unreleased 0.50.0

```python
from quantfit.safety.adjudication_review import render_adjudication_review

receipt = render_adjudication_review(
    "private.adjudication.csv", "preparation.json",
    out_path="private.adjudication.html",
)
```

The two inputs are the exact native **blank** nine-column queue and its preparation,
not a filled review, report, capture, key or human record. The API holds each role
once (queue 16 MiB, preparation 64 KiB), checks native closed metadata and typed
counts, actual queue SHA/size, complete unique in-range selected indices, native
axis/zone/explicit expected values, exact empty decision cells and all declared
axis counts. Original probe count is 1..4096; selection may be 0. This proves supplied
preparation consistency only. Producer capture/tabulation checks remain declarations.

```bash
quantfit adjudicate prepare --report report.json --capture private.capture.jsonl --review private.adjudication.csv --receipt preparation.json --json
quantfit adjudicate review-page --review private.adjudication.csv --preparation preparation.json --out private.adjudication.html --json
# Open the private page locally in a browser you control, choose every decision,
# and save the fixed-name filled.adjudication.csv download privately.
quantfit adjudicate apply --report report.json --capture private.capture.jsonl --review filled.adjudication.csv --preparation preparation.json --out declarations.json --json
```

All selected rows remain visible with fixed Pair/Axis/Zone/Expected/Baseline/Quantized
captions and programmatic associations. Both labels and class begin blank. Actual
expected outcome, rather than inferred zone, defines a directional flip. Native
legal triplets require substantive/degenerate for a usable true flip, not-a-flip
for a usable nonflip, and unresolved when either label is unusable. The page never
chooses a judgment. Zero selection exports only the quoted native header after an
explicit click; it does not invent zero-probe evidence.

Six original strings are parsed once from ASCII-escaped JSON with less-than escaped,
then frozen in a private closure. Display uses textContent; downloaded originals
never come from displayed DOM or textarea values. Export quotes every cell, doubles
quotes and writes explicit CRLF record separators. Embedded CR/CRLF/LF, NUL, Unicode,
whitespace and formula-like strings are preserved exactly, without rewriting.
TextEncoder bytes feed Blob, with a fixed private filename. Object URLs remain alive
for download and are owned until page teardown. No requests, remote assets, storage,
telemetry, automatic apply, screenshots, traces, video or private uploads are used.

Worst permitted filled CSV is admitted before HTML publication under the native
16 MiB profile, including quoted header/cells and CRLF separators. The browser
rechecks actual encoded export bytes. Exact escaped HTML is independently bounded
to 32 MiB; a valid 16 MiB queue need not fit either output profile. Every row is kept
or the whole page is refused. These are encoded-input/output limits, not browser
heap, scalar allocation or execution-time guarantees.

Output must be a NEW file ending exactly in `.adjudication.html`, with an existing
parent directory. Native input/ancestor/alias checks and exclusive publication apply;
no existing target is replaced. `.gitignore` is a backstop, not confidentiality.
Product stdout contains only an aggregate/hash receipt, never private HTML/paths.
Successful preparation consistency/page creation is 0; invalid/unsafe/excessive is 2.
No API integer-return or paired-file transaction is claimed.

Unchanged native apply with the actual report/capture and original preparation is
authoritative for original selected membership, both protected text hashes and
native statistics. A coordinated fabricated queue/preparation can be consistent
without being a true source; the page explicitly sets source/human/scientific
verification false. Existing native flags, Wilson/MDE, calibration, control,
sensitivity and model-card proof limits stay unchanged.

Native ordinary/bare-CR/NUL prepare→read→exact regeneration→apply controls ran on
actual Python 3.11.9 (stdlib-only full source imports) and 3.12.13 before any writer
change. No writer workaround was needed; default queue/preparation bytes are held.
The [regenerable source record](../validation/2026-10-31-adjudication-review/)
uses explicit fictional choices and a stdlib CSV transport. Real browser qualification
is separate: only existing hosted Linux original/rebuilt installed profiles select
the private nondefault browser-ci group, pinned Playwright 1.64.1/matching Chromium,
perform actual downloads and pass saved bytes to unchanged native apply/cards.
The SDK controller imports no application, saves before closing the context and
publishes no private browser artifacts. See [native download lifetime](https://playwright.dev/python/docs/downloads).
Neither software fixture is authentic human reading, judge/model execution,
independent evidence or scientific GO. Public install remains 0.46.0/Python>=3.11.
