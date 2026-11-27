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
