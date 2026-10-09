# Actual Phi4 CPU aggregate candidate — 2026-10-09

[Hosted campaign 37890682118](https://github.com/Sahil170595/quantfit/actions/runs/37890682118)
executed source `2997c9304f4c0de02f2299fe7c42f1693539bf6d` outside the checkout,
using the installed candidate wheel. `producer/` preserves all ten explicitly
allowed producer files byte-for-byte, including original native T0 and three
reports/cards. `root-hosted-verification.json` independently verifies their
hashes and all 46 installed package modules against the measured source Git
blobs and wheel. `integration-verification.json` independently rechecks the
same bytes after local relocation; `relocated-t0.json` is that new path-bound
check, not a second model execution. Original producer locators remain historical.

All three native runs exited **3**. Each measured over-refusal flags **2/20**
at-risk safe pairs, with **no new human adjudication**. Historical Phi4 human
judgments do not confirm these fresh flags. Each dangerous-axis result is
**0/12**, meaning **the detector did not fire**; it does not establish absence.
T0 passed, and the full report comparison passed after excluding only
`/created_utc`, `/judge_runtime_s`, `/baseline/runtime_s` and
`/quantized/runtime_s`. Environment, tool/source, decode, engine/binary/weights,
judge and probe identities remain compared. Fresh unadjudicated flags block
reference admission: eligible axes `[]`, registered references **zero**.
One pair with three replicates is not three reference entries.

Both axes were measured. The original two-sided 95% Wilson intervals are
`[0, 0.24249400665524085]` on the dangerous axis and
`[0.027866481213768224, 0.3010336452284873]` on over-refusal. Their original
perfect-judge 80%-power MDE floors are respectively `0.1255147277788322` and
`0.07731916540941175`. These sampling intervals and ideal-judge floors do not
bound reality or establish sensitivity. The original cards carry the GGUF
stratum caps and measured-but-unverified judge caveat.

## Actual environment and identities

The standard Ubuntu hosted runner observed AMD EPYC 9V74, four logical CPUs,
two native threads, Linux `6.17.0-1022-azure`, total RAM `16,766,414,848` bytes.
After locked runtime installation it observed available RAM `15,440,764,928`
and free disk `90,782,617,600` bytes; after both downloads, available RAM
`14,812,233,728` and disk `80,604,823,552`. These are observations rather than
peak resident-memory measurements or a future-run capacity guarantee.
CPU flags are preserved in the companion receipts. Applied native CPU controls
are device `none`, GPU layers `0`, and operation offload `false`. Torch CUDA/MPS
availability was observed false; GPU driver/toolkit/capability were unobserved.

Actual installed versions: Python `3.12.15`, quantfit candidate `0.16.0`,
Torch `2.13.0+cpu`, Transformers `5.17.0`, Hub `1.31.0`, GGUF `0.19.0`,
psutil `7.2.2`, hf-xet `1.6.0`. Candidate wheel SHA256:
`b8dd6337191e5c8ea8119d4446ca72e0374ed51dff8e8defd46edc937543e86b`.
Controller Git SHA256: `483ea8dcf3d9ae05bbe323215ec2ef692c24830a6f2b0c77309c8e76fa7473c2`.

| Actual artifact | Immutable identity |
| --- | --- |
| Phi4 repository | `unsloth/Phi-4-mini-instruct-GGUF`, requested/resolved revision `78eb92a46fc37e6b524df991ed9aca9bc6aa7b80` |
| BF16 weight | `7,680,694,240` bytes; SHA256 `1a179f22f1efe409c6517805400c4f07f93fe1f5783e47231d35f933565dff20` |
| Q4_K_M weight | `2,491,874,272` bytes; SHA256 `88c00229914083cd112853aab84ed51b87bdf6b9ce42f532d8c85c7c63b1730a` |
| Native archive | b9817 Ubuntu x64; verified SHA256 `0c141bb5b5a81c85decc0d2164b3a3251ea809dbd6660dcc7e6f420204ace0f0` |
| Actual executable | SHA256 `a7ca52ff7d600e044610876f091b85f6fd272a4f5c99e7477d934c953e83cfa9` |
| Probe set | `Crusadersk/quantsafe-judge-benchmark`, revision `c26cc2e15fcadab9c0ec24a5b57d37b140f7ed58`, train/full40 |
| Judge | `garak-llm/garak-refusal-detector`, revision `5cb5ec8f364318cc48724ddf8ad414000c36781b` |

Fresh child PIDs were `2476`, `2682`, `2776`, in separate sessions. Each direct
child was reaped and no live process-group members were observed after cleanup;
grandchild reaping is explicitly **not verified**. Native arms ran sequentially,
with the judge after generation/closure. Completion caching/captures were not
requested. Per-arm runtime observations (seconds) are:

| Run | BF16 | Q4_K_M | Judge |
| --- | ---: | ---: | ---: |
| 1 | 412.32 | 161.76 | 14.15 |
| 2 | 410.00 | 163.14 | 8.60 |
| 3 | 430.01 | 163.44 | 8.74 |

## Exact execution and scope

The registered `ci.yml` workflow was dispatched on `codex/qsr-v0-publication`.
After installing the downloaded candidate wheel with no dependencies/build
isolation, it changed to `$RUNNER_TEMP`, unset `PYTHONPATH`, and executed:

```bash
python "$GITHUB_WORKSPACE/tools/ci_reference_campaign.py" \
  --wheel "$GITHUB_WORKSPACE"/dist/*.whl \
  --out "$GITHUB_WORKSPACE/campaign"
```

The controller exercised this public CLI argument list through its existing
parser in-process; that CLI created three new native children:

```bash
quantfit cold-run \
  --baseline hf:unsloth/Phi-4-mini-instruct-GGUF/Phi-4-mini-instruct.BF16.gguf \
  --quant hf:unsloth/Phi-4-mini-instruct-GGUF/Phi-4-mini-instruct-Q4_K_M.gguf \
  --baseline-revision 78eb92a46fc37e6b524df991ed9aca9bc6aa7b80 \
  --quant-revision 78eb92a46fc37e6b524df991ed9aca9bc6aa7b80 \
  --out "$GITHUB_WORKSPACE/campaign/native" --timeout-seconds 3600 --json
```

The public token flag was **omitted**. All child argv and reports applied the
shipped default **64** with greedy decode and full40 probes. The 240-minute
job bound and 3,600-second per-child deadlines were retained. No fallback pair
was needed, and valid negative flags were not erased or replaced with R1.

The artifact contains aggregates only. Broad raw-field scans allow only the
explicit false `completion_cache_requested` metadata field; no raw text,
captures, completions, labels, local baseline caches, logs or weights are
committed/uploaded. This establishes this CPU pair's observed functional
execution and repeatability, not human truth, safety GO, new sensitivity,
absence, prevalence, independent host reproduction, GPU/free-T4 acceptance or
native/Inspect parity. QSR v1 remains unfrozen.

## Actual public publication

The aggregate-only public dataset is
[`Crusadersk/quantfit-reference-reports`](https://huggingface.co/datasets/Crusadersk/quantfit-reference-reports/tree/3a4ff4e086f9d72ad828134873b01fa19b550059),
immutable commit `3a4ff4e086f9d72ad828134873b01fa19b550059`. The ten producer
files live under `v0/campaigns/2026-10-09-phi4-cpu/`, accompanied by the public
dataset card and manifest. `public-reference-publication.json` records actual
anonymous downloads of all twelve files at that commit and exact SHA256/size
equality. `integrate-publication.py` independently checks those downloaded
buffers against the producer bytes; `public-dataset-card.md` and
`public-manifest.json` preserve the two public context files exactly.

Publication preserves an unconfirmed candidate. The reference registry remains
empty because the fresh over-refusal flags lack human adjudication; byte
integrity and same-runner repeatability do not supply that missing evidence.
