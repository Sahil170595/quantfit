# Rerun the pinned judge on held completions

QuantFit 0.56 adds a private judge observation and a separate offline comparison.
Use the original native schema-2 report and capture with their bound v2 labeling
key. The observation runs the shipped pinned completion-only classifier over
every captured completion. It does not load a probe corpus or regenerate either
arm. If the classifier is not cached, its pinned checkpoint may need downloading.

```bash
quantfit calibrate observe-judge --report original.json --capture private.capture.jsonl --key private.labelkey.json --out private.judge-observation.json --json
```

Save the receipt's `result.observation.sha256` as the expected raw observation
hash. Then use the original three inputs and one complete native label set.

```bash
quantfit calibrate compare-observed-judge --report original.json --capture private.capture.jsonl --key private.labelkey.json --observation private.judge-observation.json --observation-sha256 FULL64 --sheet filled.labels.csv --out comparison.json --json
```

Replace `--sheet` with both `--retained-labels` and `--retention-receipt` to use
a native retained label set. The comparison requires no model or network.

## API

Import `observe_calibration_judge` and `compare_observed_judge` from
`quantfit.safety.calibration_judges`. The producer takes report, capture and key
paths, a required keyword-only `out_path`, and an optional `token` for the native
classifier. It returns a byte-hash/count receipt. The receiver takes the same
three paths followed by the observation path, required keyword-only
`observation_sha256` and `out_path`, plus `sheet_path` or the
`retained_labels_path` and `retention_receipt_path` pair. It returns the
descriptive aggregate it writes. Both raise `CalibrationJudgesError` with a
categorical message on refusal. The existing `calibrate compare-judges` command
still compares two supplied suites.

## Binding and interpretation

The producer holds each input, checks the key's raw capture hash, complete
pair-and-arm membership, per-cell completion hashes and original flags, and
matches the report's measurement identity and native drift to the actual capture.
Both bound Hub and local probe identities work. The classifier receives all
baseline completions in ascending pair order, followed by all quantized
completions in ascending pair order. Repeated text at different cells stays
distinct. The pinned tokenizer consumes completion text alone and truncates
at 512 judge tokens.

The private schema-1 observation contains positional flags, a commitment to
the ordered cells, the raw input hashes and byte counts, the original
measurement fingerprint, and the fresh configured judge pin and runtime. It
contains no completion text, unblinding IDs, label values or private paths.
The comparison verifies the expected observation hash and checks its exact
shape and bindings against the held originals. It uses one supplied ternary
truth population for both sides. Whole-arm flag tables include unusable rows.
Error tables use each arm's usable truth, and native directional denominators,
Wilson intervals and unmeasured values remain separate. A same-pin rerun is
valid and labeled in the aggregate. A zero observed difference does not
establish judge independence or sensitivity.

Keep the observation with the private capture, key and labels. Positional
flags can disclose information when linked back to the capture. The raw hash
can detect differences against a retained original pin. Coordinated rewriting
of files and pins can remain consistent, and the comparison cannot authenticate
source, judge execution or human labels. The aggregate does not change the
original report, yield a replacement calibration or qualify a gate.

## Limits and refusal

Input caps are 8 MiB for the report, 16 MiB for the capture, 2 MiB for the key,
and up to 4,096 pairs. Native full sheets allow 8 MiB subject to CSV admission.
Retained labels allow 2 MiB and their receipt allows 64 KiB. The observation,
comparison and corresponding CLI envelopes each have a 256 KiB encoded cap.
These are byte and population bounds. Native output admission requires a fresh
target and rejects unsafe links, input aliases and existing files. Success
means completion of the requested operation (exit 0). Invalid input, unsafe
output or classifier failure returns exit 2. See the controlled
[functional run](../validation/2026-11-04-held-judge-observation/) for evidence
and its scope.
