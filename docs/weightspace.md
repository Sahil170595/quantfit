# Weight-space checkpoints

Install `quantfit[weightspace]` for CPU checkpoint encoding and reconstruction. The exact codec accepts SafeTensors files or named NumPy array mappings with the same keys, shapes, and dtypes. It stores the base, changed byte vectors, and a portable `weightspace-manifest/v1` sidecar in a **new** directory. Unchanged tensors use the verified base. Each changed tensor uses its bytewise XOR, which also preserves signed zero and floating-point cancellation cases. This first codec reads one file per checkpoint and applies a default 256 MiB per-file limit. Mapping inputs with ambiguous shared storage are rejected.

```bash
quantfit weightspace encode --base base.safetensors --target target.safetensors --out delta --json
quantfit weightspace decode --base base.safetensors --artifact delta/manifest.json --out recovered.safetensors --json
```

```python
from quantfit.weightspace import encode, decode

receipt = encode("base.safetensors", "target.safetensors", "delta")
decoded = decode("base.safetensors", "delta/manifest.json", "recovered.safetensors")
assert decoded["logical_sha256"] == receipt["identities"]["target"]
```

The logical digest covers a name-sorted array of `name`, `dtype`, `shape` and per-tensor SHA-256 records in compact, sorted-key UTF-8 JSON. Tensor bytes are contiguous row-major little endian. Decode verifies the physical bundle members, supplied base, full tensor coverage and reconstructed logical target before publishing the output. Container metadata and original SafeTensors header ordering are outside the tensor commitment. Cold bytes include the base, payload and manifest. Incremental bytes count the manifest and payload when the exact base is already available. The codec makes no compression or task-quality guarantee.

## Arithmetic task vectors

Use `weightspace encode --codec task-vector-v1` (Python keyword `codec`) to store numerical updates. `weightspace decode --scale -1` subtracts an update, zero preserves the exact base, and one reconstructs the standard numerical target. NumPy float64 is used for differences and accumulation before the result is cast to the base dtype. Finite F16, BF16, F32 and F64 tensors are supported. Unchanged integer or Boolean tensors pass through. A changed nonfloating tensor or a nonfinite update is rejected. Scaling changes weights and may change model behavior.

The manifest keeps the original target and unit-scale reconstructed logical digests separately. The receipt reports changed-tensor count, maximum absolute error at unit scale, and the digest for the actual scale. Byte-exact reconstruction is available with the default XOR codec.

## Grouped low-bit deltas

Choose `grouped-int-v1` with `bits=4` or `8` and a `group_size` from 1 through 65536. Defaults are 4 bits and 64 elements. Each changed tensor is flattened in row-major order. Each consecutive group stores a little-endian float64 scale equal to the largest absolute delta divided by 7 or 127. A zero range uses zero scale and all-zero codes. Each value divided by its scale is clipped to the symmetric range and rounded to nearest with ties to even. Signed 4-bit codes put the first value in the low nibble, zero-padding the final high nibble for odd lengths. Eight-bit codes use signed two's complement bytes. In the SafeTensors payload, `codes.N` and `scales.N` correspond to the Nth name in the sorted changed inventory, starting at zero. Receipts measure physical byte totals (including group scales and headers) and maximum absolute unit-scale reconstruction error.

## Compile and run a standalone text head

`compile_head(recipient_anchors, donor_anchors, donor_weight, donor_bias, out, *, vocabulary, labels, lowercase=True)` fits the minimum-norm least-squares map from augmented recipient features (including a column of ones) to donor features. Rows in the two arrays must refer to the same unlabeled inputs in the same order. The donor head is class-major, and its bias is added after composing the affine intercept. Fit rank and parameter counts are reported. Only a strictly narrower recipient is accepted. Model weights and biases are stored as finite F32 SafeTensors.

The companion transform optionally lowercases raw text, splits by Unicode whitespace, counts vocabulary words in their declared order, and ignores other words. Recipient features used for fitting must follow that contract. Files in the recipient bundle carry SHA-256 commitments to the transform, class order, model bytes and logical tensors. `predict_head(manifest, text)` returns logits and the first maximum in the declared class order. The three runtime files and their manifest suffice for prediction.

Inference computes the matrix product with float32 counts and weights, then adds the float32 bias. Ties select the lowest index in the declared class order.

## Matched-query head benchmark

`benchmark_heads(spec)` evaluates precomputed local features. Supply ordered class names (`labels`), class-major `donor_weight`, `donor_bias`, distinct `wrong_donor_weight` and `wrong_donor_bias`, nonnegative integer `seeds` and `budgets`. The `archive` object carries lists of `ids`, `recipient` and `donor` vectors on the same unlabeled cases. The `queries` object carries these fields plus integer gold class indices in `labels`. The `held_out` object carries only `ids`, `recipient` and `labels`. All three ID sets must be disjoint. Use precomputed features from the same frozen transforms.

Each seed draws one query ordering and reuses its prefix for all arms at a given budget. The compiled recipient is evaluated directly and with a least-squares correction fit on the selected target teacher logits. The wrong-donor and permuted-anchor controls use the same correction. The random head stays fixed for the seed. A labeled student fits one-hot gold labels on the selected queries. Output-only fits use teacher logits either on the matched archive plus the selected queries or on the selected queries alone. All arms score the same held-out recipient features with float32 readouts; first class wins ties. At zero queries a target-only untrained readout has zero logits.

The aggregate reports actual offline archive and cached target logit rows once and per-arm information usage separately. Matched output-only receives scores for every source anchor given to the compiler. Archive-feature extraction, offline head access, and gold label acquisition are distinct resources. The held-out predictions are available only to an explicit local `observe` callback. Pairwise wins and losses use the adapted compiled head as reference and count per-case correctness; both-correct and both-incorrect are ties. Compatible affine arms can tie. No result generalizes beyond the supplied split.
