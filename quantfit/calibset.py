"""The calibration set as one token stream, packed into fixed-length blocks.

Every reader of the calibration set goes through `packed_blocks`, so they read the same
tokens in the same order:

- the quantize path (`backends/compressed_tensors.py`), at `spec.calib_seqlen`;
- `probe` (`policy/probe.py`), at its own shorter block length.

The probe's blocks are therefore exactly the first tokens of the stream the quantizer
calibrates on.

Until 0.15.0 the probe tokenized rows one at a time and averaged a per-row KL, so a
9-token wikitext heading weighed as much as a 437-token paragraph. The 4-bit "spread" on
Qwen2.5-1.5B was that weighting, not the model (validation/2026-10-01-probe-at-n64/).
Fixed-length blocks have no length to weight by. They also give every token the
surrounding text the quantizer sees: a heading is a few tokens of context, not a row of
its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quantfit.spec import QuantSpec


def packed_blocks(spec: QuantSpec, tokenizer, n_blocks: int, seqlen: int, token: str | None = None) -> list[list[int]]:
    """Up to `n_blocks` blocks of exactly `seqlen` token ids, from the spec's pinned set.

    Non-empty rows are shuffled by `spec.seed`, concatenated, and chunked in order. Fewer
    than `n_blocks` come back only when the set runs out of tokens. Callers decide whether
    that is an error (the quantize path) or a short delivery to report (the probe).
    """
    from datasets import load_dataset

    ds = load_dataset(
        spec.calib_dataset, spec.calib_config, split=spec.calib_split, revision=spec.calib_revision, token=token
    )
    ds = ds.filter(lambda ex: ex["text"] is not None and ex["text"].strip() != "")
    ds = ds.shuffle(seed=spec.seed)

    needed = n_blocks * seqlen
    buf: list[int] = []
    for ex in ds:
        buf.extend(tokenizer(ex["text"]).input_ids)
        if len(buf) >= needed:
            break
    # Only chunk over tokens actually collected; a short dataset yields fewer blocks, never
    # an empty or ragged one (range(0, needed, ...) would slice past len(buf)).
    usable = (len(buf) // seqlen) * seqlen
    return [buf[i : i + seqlen] for i in range(0, min(needed, usable), seqlen)]
