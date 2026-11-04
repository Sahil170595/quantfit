# Aggregate reconciliation of two private synthetic label sheets

This records actual CLI operations on **fictional local labels**, not a human
study or judge calibration. Eight descriptive commands return exit 0, including
disagreements, all-unusable labels and self-controls. Five invalid/unsafe commands
return operational exit 2. No model, judge, asset download or calibration ingestion
runs. There is no CPU inference addition for this feature.

Only aggregate JSON, whole-input hashes, recorder code and documentation are
published. Private captures, blinded sheets, unblinding keys, row identifiers,
per-row hashes, salts and contents are intentionally absent from Git. The native
SDK produces those files in separate private temporary storage using its real
fresh random blinding salt. No RNG is replaced or seeded.

The generator uses `_write_capture` and `build_labeling_sheet`, with fictional
scope declarations based on the earlier public synthetic clean-report fixture.
It declares nine pairs and constructs local placeholder values and label plans.
It does not fetch the declared probe dataset or judge. The native input hashes
bind the exact private buffers used locally; they do not authenticate a rater,
human truth, weight identity or original capture provenance.

**Fresh salts mean reruns reproduce the count plans, not the original private
input hashes.** Without the intentionally unpublished private files, the committed
whole-input hashes cannot independently authenticate or recover those sheets or
their key. Local verification compared 39 logical input occurrences against 35
distinct preserved private buffers without printing or publishing their contents.
That local verification is separate from what a public reader can establish.

## Matrices and outcomes

Every case has nine rows per arm and 18 rows overall. Matrix rows are sheet A;
columns are sheet B, ordered `refusal`, `compliance`, `unusable`. Arms remain
separate. The directed fictional plan is deliberately asymmetric:

| Arm | refusal/refusal | refusal/compliance | refusal/unusable | compliance/refusal | compliance/compliance | compliance/unusable | unusable/refusal | unusable/compliance | unusable/unusable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 2 | 1 | 0 | 0 | 1 | 2 | 1 | 0 | 2 |
| quantized | 0 | 1 | 2 | 2 | 0 | 1 | 1 | 2 | 0 |

Baseline therefore has four both-usable rows, three usable agreements, one usable
disagreement, three one-unusable rows and two both-unusable rows; its descriptive
usable agreement rate is 3/4. Quantized has three both-usable rows, zero usable
agreements, three usable disagreements and six one-unusable rows, with rate 0/3.
Neither rate is an error estimate or evidence of independent human raters.

| Actual CLI case | Exit | Result |
| --- | --- | --- |
| `directed` | 0 | The two matrices above |
| `swapped` | 0 | Each matrix transposed; input roles exchanged |
| `agreement` | 0 | Diagonal 3/3/3 per arm; six usable agreements; rate 1 |
| `all-unusable` | 0 | Nine both-unusable per arm; zero usable denominator; rate null |
| `self-control` | 0 | Same sheet path twice; diagonal 3/3/3 and no independence claim |
| `bom-reordered` | 0 | UTF-8 BOM, quoted multiline fields and reversed rows preserve the directed counts |
| `unbound-v2` | 0 | Unbound native schema-2 key, with complete population |
| `legacy-v1` | 0 | Legacy native key, with complete population |
| `missing-id` | 2 | A sheet omits a key member |
| `changed-value` | 2 | A private value fails the native key hash binding |
| `invalid-legacy-population` | 2 | Boolean pair count refused before native key parsing |
| `record-budget` | 2 | First CSV record beyond the 16,385-record budget refused |
| `output-alias` | 2 | Output aliases the private key; original bytes retained |

Agreement and all-unusable fixture sheets are also byte-identical by construction.
`identical_sheet_bytes` records this fact. Rater identity, human labels,
independence, consensus calibration and scientific GO remain explicitly false in
every successful report. Exit0 means descriptive receiving completed, including
when the labels disagree. No consensus labels or calibration report are produced.

## Execution and reproduction

Recorded on 2026-10-18 UTC with source/editable distribution 0.36.0. Consumed
application buffers match the independently reviewed frozen
`1bd80861dc84655f721521618a6a5c35475a88b9`; the root also included PR139 history
through merge `eb79b358a16a517edcf0d8c96a0a657694d68e2e`, which left those
buffers unchanged. `receipt.json` records six selected
raw source buffers. Those historical Windows byte hashes are not requirements
for future versions or normalized Linux source files.

| Recorder host / dependency | Recorded value |
| --- | --- |
| Machine | ASUS ROG Strix G814JZ_G814JZ; Intel Core i9-13980HX, 24 cores / 32 logical processors |
| Physical RAM | 68,319,563,776 bytes |
| OS / Python | Windows 11 build 26300 AMD64 / 3.12.13 |
| quantfit source / editable distribution | 0.36.0 / 0.36.0 |
| huggingface_hub / pytest | 1.31.0 / 9.0.3 |
| torch / transformers | absent / absent; null in the receipt |

These host details describe the synthetic CLI recorder, not an authenticated model
execution or original producer host. The exact recorded invocation from external
directory `C:/tmp/sequential-delivery-20261017` was:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = 'C:/tmp/qf-label-reconciliation-delivery-20261018'
& C:/tmp/sequential-delivery-20261017/qf-unit-env/Scripts/python.exe C:/tmp/qf-label-reconciliation-consumers-20261018/validation/2026-10-18-label-reconciliation/run_validation.py --out C:/tmp/sequential-delivery-20261017/qf036-label-reconciliation-validation-final --private-work C:/tmp/sequential-delivery-20261017/qf036-label-reconciliation-private-final --expected-source C:/tmp/qf-label-reconciliation-delivery-20261018
```

To reproduce the count plans from a candidate checkout, use two new directories:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = (Get-Location).Path
python validation/2026-10-18-label-reconciliation/run_validation.py --out C:/tmp/reconciliation-aggregates --private-work C:/tmp/reconciliation-private
```

The recorder asserts source origin before any CLI command. Its private directory
must be outside both the checkout and public output directory. Commands invoke the
actual parser, dispatch and JSON emission:

```text
calibrate reconcile --sheet-a PRIVATE_A --sheet-b PRIVATE_B --key PRIVATE_KEY --out AGGREGATE --json
```

Each successful case retains its actual aggregate output and CLI envelope.
Refusals retain only the categorical CLI envelope. The API has no JUnit output.
The 42 source consumers cover actual CLI orientation, order/BOM/multiline behavior,
null denominators, self-controls, all native key versions, the complete 4096-pair
boundary, malformed populations/CSV/labels/hashes, byte limits, record limits and
output aliases. Installed artifact qualification is a separate guarded execution.

## Checks and limits of the evidence

`checks.json` records an independent standard-library CSV lookup through the
native-produced private key, followed by per-arm counters and matrix margin/
partition checks. It verifies 16 matrices and 39 logical whole-input bindings
against 35 distinct private buffers. It does not replace the native validators or
compute calibration statistics. The historical public regression checks aggregate
matrices, partitions and CLI/receipt hash-link consistency; it cannot check the
unpublished private contents and does not assert current source hashes or rerun
historical statistics with a future package.

All 23 JSON files pass the aggregate-key walk, and no private cell contents, salt,
row identifier or per-row hash appears in their contents. Every committed JSON Git
blob is compared literally to working bytes, without newline normalization.
`.gitattributes` disabled text conversion before the first output was added. No
earlier validation package is edited.

This is source CLI/aggregate receiving evidence. It establishes no actual model
behavior, human adjudication, rater identity, independent rating process, calibrated
judge error, consensus labels, safety finding, sensitivity-control result,
scientific GO, speed or memory performance. The scope declarations and source
hashes do not authenticate missing private data. Disagreements are retained,
unusable labels retain their own counts, and neither arm is pooled into the other.
