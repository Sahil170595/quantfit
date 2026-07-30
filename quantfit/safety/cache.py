"""Fingerprint-keyed baseline caching for `quantfit gate` (ROADMAP 0.7).

A quantizer gating N quants of one base model regenerates the identical baseline
arm N times. That arm is the expensive half of a paired diff and it is
bit-identical across those N runs *by construction* — greedy decode
(`do_sample=False`), one revision-pinned probe set, one engine — so it is the one
thing in a QSR run that can be reused without changing what was measured.

It is reusable only as far as its IDENTITY is complete, and that is the whole
design constraint here. A wrong cache hit does not make a gate slow; it silently
**fabricates a measurement**. The baseline half of the pair would come from some
other model, precision, engine, decode setting or probe revision, the drift
vector would be computed against it anyway, and the resulting report would look
exactly as clean and as auditable as a real one. So this module is written the
paranoid way round:

  - **The key is derived, never accepted.** `baseline_fingerprint` is a sha256
    over a canonical identity record (`fingerprint_inputs`) built from an
    ArmRun-shaped provenance record plus the probe, decode and environment facts,
    and `store` takes that record and derives the key itself. No caller can file arm A's
    completions under arm B's key, because no caller supplies a key to store at.
  - **No content identity, no cache — and content identity means a DIGEST.** A
    40- or 64-char lowercase hex `revision` (a resolved commit) pins a snapshot;
    a 64-char `artifact_sha256` pins one file. A floating ref pins nothing:
    `main`, `HEAD`, `refs/heads/main` and tags all name whatever the repo owner
    pushed last, so an entry keyed on `revision="main"` would have a perfectly
    stable key under which NOTHING binds to the weights' content — it would
    survive new weights being pushed, and the baseline half of the next paired
    diff would be fabricated. A revision that is not digest-shaped therefore
    counts as no revision at all, and an arm with neither a digest revision nor
    an `artifact_sha256` is refused rather than cached. (A floating revision is
    still *digested* when an `artifact_sha256` is present: a GGUF arm resolves HF
    `main` — `docs/sensitivity-control-v0.md` §2.3 — and its content is pinned by
    the file hash. It just may never be the thing that confers identity.) The
    cost of refusing is one regeneration, which the budget rule below has already
    paid for; the cost of caching it is a fabricated measurement.
  - **Hits are audited, not trusted.** Every entry carries its own fingerprint
    INPUTS in its header, and `load` re-derives the key from them and refuses the
    entry unless the derived digest equals both the stored `fingerprint` and the
    key it was filed under. A hand-edited entry, or a payload copied to another
    key, is therefore never served. This is an integrity check against editing
    and misfiling, NOT authentication: there is no secret, so someone who edits
    the inputs *and* recomputes the digest *and* renames the file can still
    forge one. What bounds that risk is that the cache is local-only and never
    committed or shared (see "Data handling" below).
  - **Missing is normal; broken is not.** Three outcomes, kept distinct on
    purpose: an absent entry is a MISS (`load` returns `None`) because a cold
    cache is the expected state; an entry this schema cannot interpret at all is
    also a MISS, because a cache is derived and disposable and regenerating is
    always safe; an entry that claims to be a valid current-schema entry and
    contradicts itself is REFUSED with `CacheError`, because serving it would
    fabricate a measurement and silently regenerating it would hide that a
    measurement input was edited.

**Budget rule (ROADMAP 0.7, verbatim intent).** Budgets assume ZERO cache hits.
A hit is a wall-clock speedup and nothing else: never a correctness assumption,
never a planning assumption, never load-bearing for a gate's runtime estimate.
A gate that is only affordable when the cache hits is not affordable. This is a
planning rule, so no code path enforces it — it is stated here, carried in every
entry header as `budget_rule`, and it is why every refusal in this module is
cheap: the fallback is the run the budget already assumed.

**What is deliberately NOT in the fingerprint.** `arm.runtime_s` is an output of
a run, not an input to one — two byte-identical arms differ in it, so including
it would make the cache never hit. Neither is `CACHE_SCHEMA_VERSION`,
`created_utc` or `quantfit_version`: they version and date the *container*, not
the measurement, and a container change must not invalidate keys. Conversely
`CAPTURE_PROTOCOL_VERSION` **is** in the fingerprint, and it is a hand-bumped
constant: nothing here observes the completion-capture code, so a change to how
completions are produced or trimmed (prompt-token slicing, `skip_special_tokens`,
strip, chat-template wrapping, llama-server flags) is only reflected in keys if
that constant is bumped in the same commit. Bumping it invalidates every existing
entry, which is the intended and cheap outcome.

**The execution environment IS an input.** `env` — the same dict
`report.environment_fingerprint()` records in a DriftReport (python, torch,
transformers, CUDA, device) — is digested WHOLE, exactly like `arm.engine`. Two
baseline runs that this project itself classifies as differently-determined,
because they ran on different torch/CUDA versions or a different GPU, must not
collide on one key; cross-hardware variation is an OPEN 0.7 workstream
(`docs/ci-integration.md` §12), which is exactly why it cannot be assumed away
here. It is required, never defaulted, and — like every other over-covering
choice in this module — costs at most a miss, and a miss is free under the budget
rule. Adding it changed every key, which costs nothing even for an entry already
on disk: a key IS the filename, so an entry written under a pre-`env` key is
unreachable rather than refused, and `purge` removes it like any other.

**Data handling.** A cache entry contains model COMPLETION TEXT — including
completions to expected-`unsafe` probes — i.e. exactly the text
`docs/data-handling-completions.md` governs, and that doc is the explicit
recorded decision ROADMAP's non-goal demands ("no raw harmful corpora or
archived harmful long-form completions without an explicit recorded data-handling
decision — never a silent reversal"). Honoring it here means, concretely: entries
are **local-only** and never committed (the filename convention is
`<fingerprint>.baseline-cache.json`, and `*.baseline-cache.json` is a
doc-mandated `.gitignore` pattern), never published, never attached to a report
or a model card; every entry header carries the same completion-text warning
verbatim, so a directory holding completion text says so in every file it
contains; and retention is operator-actionable through `purge`. Nothing
published depends on an entry: report schema v2 has no completion field at all
(`quantfit/safety/report.py`), so purging a cache can never invalidate evidence.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # ArmRun is only an annotation here — cache.py imports nothing heavy
    from quantfit.safety.report import ArmRun

# --- envelope + filename convention ----------------------------------------------

CACHE_SCHEMA_VERSION = 1  # the cache entry envelope — its own schema namespace, not the report's
_KIND = "quantfit-baseline-cache"

# Doc-mandated by docs/data-handling-completions.md: entries hold completion text,
# so the name is what the .gitignore pattern `*.baseline-cache.json` matches. The
# stem is always the 64-hex fingerprint, so an entry's filename IS its key and a
# misfiled payload is detectable (see `load`).
CACHE_ENTRY_SUFFIX = ".baseline-cache.json"
CACHE_ENTRY_GLOB = "*.baseline-cache.json"
GITIGNORE_PATTERN = CACHE_ENTRY_GLOB

# Temp files for the atomic write live in the cache dir (os.replace needs one
# filesystem) and are dot-prefixed so they can never match CACHE_ENTRY_GLOB and
# be mistaken for a servable entry.
_TMP_PREFIX = ".quantfit-baseline-cache-"
_TMP_SUFFIX = ".tmp"
_TMP_GLOB = f"{_TMP_PREFIX}*{_TMP_SUFFIX}"

# HAND-BUMPED. Nothing in this module observes the capture code, so this constant
# is the only thing that separates keys across a change in how completions are
# produced or trimmed. Bump it in the same commit as any such change; bumping
# invalidates every existing entry, which is the cheap and intended outcome.
# "qsr-v0" names the protocol (spec/qsr-v0.md §2.3-2.4: greedy, continuation-only,
# model-default chat template); "capture-1" is quantfit's capture generation.
CAPTURE_PROTOCOL_VERSION = "qsr-v0/capture-1"

# --- header prose, carried in every entry ----------------------------------------

COMPLETION_TEXT_WARNING = (
    "CONTAINS MODEL COMPLETION TEXT, including completions to expected-unsafe probes. "
    "Local-only: never commit, never publish, never attach to a report or model card. "
    "Governed by docs/data-handling-completions.md; delete with "
    "quantfit.safety.cache.purge(cache_dir) or by removing the directory."
)

RETENTION_NOTE = (
    "Retention is operator-actionable: purge(cache_dir, older_than_days=N) drops entries older "
    "than N days, purge(cache_dir) drops all of them. No published artifact depends on any entry "
    "-- report schema v2 has no completion field -- so purging never invalidates evidence."
)

BUDGET_RULE = (
    "Budgets assume ZERO cache hits (ROADMAP 0.7). A hit is a wall-clock speedup only: never a "
    "correctness assumption, never a planning assumption. A gate that is only affordable when the "
    "cache hits is not affordable."
)

# --- the fingerprint input list, as data so a test can catch doc drift ------------

_ARM_IDENTITY_FIELDS = ("model", "revision", "resolved_dtype", "engine", "artifact_sha256")

#: The ArmRun fields deliberately OUTSIDE the key, as data so a test can assert that
#: `_ARM_IDENTITY_FIELDS` plus this tuple is exactly `ArmRun`'s field set. Without that
#: guard the whitelist above silently stops covering a field someone adds to ArmRun,
#: which is a wrong-hit channel; with it, adding a field forces a deliberate decision.
#: `runtime_s` is the only member and belongs here because it is a measured OUTPUT.
_ARM_NON_IDENTITY_FIELDS = ("runtime_s",)

#: Every input the key covers, dotted. `arm.engine` and `env` are digested WHOLE
#: rather than as whitelists of keys (name/version/device for transformers arms;
#: name/binary_sha256/source/threads/device for llama.cpp arms; python/torch/
#: transformers/cuda/device for the environment) because a future field — an offload
#: flag, a device split, a driver version — would otherwise fall outside the
#: fingerprint silently, and that is a wrong-hit channel. Over-covering costs at most
#: a miss, and a miss is free under the budget rule above.
FINGERPRINT_INPUTS = (
    "capture_protocol_version",
    "arm.model",
    "arm.revision",
    "arm.resolved_dtype",
    "arm.engine",
    "arm.artifact_sha256",
    "env",
    "probe.dataset_id",
    "probe.dataset_revision",
    "probe.split",
    "probe.n_prompts",
    "probe.prompts_sha256",
    "decode.max_new_tokens",
    "decode.do_sample",
    "decode.chat_template",
)

_INPUT_SECTIONS = frozenset({"capture_protocol_version", "arm", "env", "probe", "decode"})
_ARM_INPUT_FIELDS = frozenset(_ARM_IDENTITY_FIELDS)
#: `env` has NO exact key set on purpose (it is digested whole), but these three axes
#: must always be stated: an env block that omits `device` would key two different GPUs
#: identically, which is the collision this input exists to prevent.
_ENV_MIN_FIELDS = frozenset({"torch", "cuda", "device"})
_PROBE_INPUT_FIELDS = frozenset({"dataset_id", "dataset_revision", "split", "n_prompts", "prompts_sha256"})
_DECODE_INPUT_FIELDS = frozenset({"max_new_tokens", "do_sample", "chat_template"})
_HEADER_FIELDS = frozenset(
    {
        "warning",
        "kind",
        "schema_version",
        "created_utc",
        "quantfit_version",
        "capture_protocol_version",
        "fingerprint",
        "fingerprint_inputs",
        "payload_sha256",
        "n_completions",
        "budget_rule",
        "retention",
    }
)

# Domain-separation tags: a digest computed for one purpose must never be able to
# equal a digest computed for another, even on identical canonical bytes.
_DOMAIN_FINGERPRINT = "quantfit/baseline-fingerprint/1"
_DOMAIN_PROMPTS = "quantfit/probe-prompts/1"
_DOMAIN_PAYLOAD = "quantfit/baseline-cache-payload/1"

_FORBIDDEN_DTYPE = "auto"  # mirrors report.py: "auto" is an input, not a resolved precision
_HEX = "0123456789abcdef"
# Content-identity shapes. 40 = git sha1 commit (what the Hub resolves a revision to),
# 64 = sha256 (a file artifact, a sha256 git object, this module's own keys). Lowercase
# only, mirroring `_validated_key`: an uppercase or abbreviated digest is not the
# canonical form, and accepting variants of one identity would key it two ways.
_SHA1_HEX_LEN = 40
_SHA256_HEX_LEN = 64
_REVISION_DIGEST_LENS = (_SHA1_HEX_LEN, _SHA256_HEX_LEN)

# One message for every unpinned-revision refusal, so the text stays true to the check.
_UNPINNED_REVISION = (
    "must be a pinned commit digest (40- or 64-char lowercase hex), not a floating ref: `main`, "
    "`HEAD`, `refs/heads/main`, a tag and an abbreviated hash all name whatever was pushed last, "
    "so nothing keyed on one can be re-derived later"
)


class CacheError(RuntimeError):
    """Unusable cache directory, entry or identity (operational: clean CLI exit 2, no traceback)."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CacheError(message)


# --- canonicalization + digests ---------------------------------------------------


def _canonical(obj) -> str:
    """The one serialization every digest is taken over: sorted keys, no whitespace, ASCII.

    JSON is used rather than a delimiter-joined string precisely because it is
    unambiguous — no field value can imitate a separator and shift the meaning of
    the record around it.
    """
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CacheError(f"cache record is not canonically serializable: {exc}") from exc


def _digest(domain: str, obj) -> str:
    return hashlib.sha256(f"{domain}\n{_canonical(obj)}".encode()).hexdigest()


def _is_hex_digest(value, *lengths: int) -> bool:
    """True only for a lowercase hex digest of one of `lengths` characters.

    The single shape rule behind every content-identity check here: cache keys
    (64), arm `artifact_sha256` (64), and the revisions that may confer content
    identity (40 or 64). A floating ref — `main`, `HEAD`, `refs/heads/main`, `v1.0`
    — and an abbreviated hash both fail it, which is the point: neither binds to
    content that cannot change afterwards.
    """
    return isinstance(value, str) and len(value) in lengths and all(ch in _HEX for ch in value)


def _validated_key(fingerprint) -> str:
    """A key may only ever be a 64-char lowercase hex digest.

    Enforced because the key becomes a filename: a caller-supplied string that
    could contain a separator or `..` would turn a cache lookup into a path
    traversal, and a key that is not a digest could not be re-derived on load.
    """
    _require(isinstance(fingerprint, str), "cache fingerprint must be a string")
    _require(
        _is_hex_digest(fingerprint, _SHA256_HEX_LEN),
        f"cache fingerprint {fingerprint!r} is not a 64-character lowercase hex sha256 digest",
    )
    return fingerprint


# --- fingerprint -----------------------------------------------------------------


def _normalize_arm(arm: ArmRun | Mapping, what: str) -> dict:
    """Accept an ArmRun (or an ArmRun-shaped mapping) as a plain dict."""
    if dataclasses.is_dataclass(arm) and not isinstance(arm, type):
        record = dataclasses.asdict(arm)
    elif isinstance(arm, Mapping):
        record = dict(arm)
    else:
        raise CacheError(f"{what} must be an ArmRun or an ArmRun-shaped mapping, got {type(arm).__name__}")
    missing = sorted(f for f in _ARM_IDENTITY_FIELDS if f not in record)
    _require(not missing, f"{what} is missing identity fields {missing}")
    return record


def _arm_identity(record: Mapping) -> dict:
    """The subset of an ArmRun that determines its completions, validated.

    `runtime_s` is deliberately absent: it is a measured output, and two
    byte-identical arms differ in it.
    """
    model = record.get("model")
    _require(isinstance(model, str) and bool(model.strip()), "arm model must be a non-empty string")

    revision = record.get("revision")
    _require(revision is None or isinstance(revision, str), "arm revision must be a string or null")

    dtype = record.get("resolved_dtype")
    _require(isinstance(dtype, str) and bool(dtype.strip()), "arm resolved_dtype must be a non-empty string")
    _require(
        dtype.strip().lower() != _FORBIDDEN_DTYPE,
        "arm resolved_dtype must be the precision actually loaded, not the 'auto' input: "
        "two different precisions both recorded as 'auto' would share one fingerprint",
    )

    engine = record.get("engine")
    _require(isinstance(engine, Mapping), "arm engine must be a JSON object")
    name = engine.get("name")
    _require(
        isinstance(name, str) and bool(name.strip()),
        "arm engine must name what generated the completions (engine.name)",
    )

    artifact_sha256 = record.get("artifact_sha256")
    _require(
        artifact_sha256 is None or isinstance(artifact_sha256, str), "arm artifact_sha256 must be a string or null"
    )
    # A field named artifact_sha256 that is not a sha256 is broken provenance, not a
    # weaker pin: it would still satisfy a non-emptiness test while binding to nothing.
    _require(
        artifact_sha256 is None or _is_hex_digest(artifact_sha256, _SHA256_HEX_LEN),
        f"arm artifact_sha256 {artifact_sha256!r} is not a 64-character lowercase hex sha256 digest: "
        "an artifact hash that is not a digest pins no content",
    )

    # The content-identity mandate, and it is a PINNING check rather than a
    # non-emptiness one. A *resolved* commit digest pins a snapshot; an
    # artifact_sha256 pins a single file. A floating ref (`main`, `HEAD`,
    # `refs/heads/main`, a tag) pins nothing — it names whatever was pushed last, so
    # an entry filed under it stays valid-looking after the weights change and the
    # baseline half of a paired diff becomes fabricated. So a non-digest revision
    # counts as NO revision here. With neither pin, "the same model" means only "the
    # same path", and a local directory's weights can change under it — so the arm is
    # not cacheable at all rather than cacheable-and-wrong.
    has_revision = _is_hex_digest(revision, *_REVISION_DIGEST_LENS)
    has_artifact = artifact_sha256 is not None
    _require(
        has_revision or has_artifact,
        f"arm {model!r} has no content identity and cannot be cached: revision {revision!r} is not a "
        "resolved commit digest (40- or 64-char lowercase hex) and no artifact_sha256 is recorded, so "
        "nothing here binds to the weights' content — the same path or the same floating ref can hold "
        "different weights later. Pin the revision to a resolved commit, or pass a single-file artifact "
        "whose sha256 is recorded.",
    )

    return {
        "model": model,
        "revision": revision,
        "resolved_dtype": dtype,
        "engine": dict(engine),
        "artifact_sha256": artifact_sha256,
    }


def _env_identity(env, what: str = "env") -> dict:
    """The execution environment, validated but NOT whitelisted (it is digested whole).

    No exact key set: an unrecognized key must land in the key rather than fall
    outside it. What is mandatory is that all three axes are *stated* —
    `torch`/`cuda` may be null (a CPU-only run has no CUDA), but `device` must name
    the hardware, because an env block that omits it keys two different GPUs
    identically and cross-hardware variation is an open 0.7 workstream.
    """
    _require(isinstance(env, Mapping), f"{what} must be a JSON object (the execution environment)")
    _require(all(isinstance(k, str) for k in env), f"{what} keys must all be strings")
    missing = sorted(_ENV_MIN_FIELDS - set(env))
    _require(
        not missing,
        f"{what} is missing {missing}: the environment fingerprint must state torch, cuda and device "
        "(use quantfit.safety.cache.environment_identity(), which is report.environment_fingerprint())",
    )
    device = env["device"]
    _require(
        isinstance(device, str) and bool(device.strip()),
        f"{what}.device must be a non-empty string naming the hardware ('cpu' or the GPU name): "
        "two different devices with no recorded name would share one fingerprint",
    )
    return dict(env)


def environment_identity() -> dict:
    """The `env` fingerprint input, resolved from the running process.

    Thin wrapper over `report.environment_fingerprint()` so a cached key's `env` is
    the same record the run's DriftReport carries. Imported lazily inside the
    function on purpose: nothing else in this module needs torch, and the module
    (and its test suite) must stay importable without it.
    """
    from quantfit.safety.report import environment_fingerprint

    return _env_identity(environment_fingerprint(), "environment_fingerprint()")


def fingerprint_inputs(
    arm: ArmRun | Mapping,
    *,
    probe_dataset_id: str,
    probe_dataset_revision: str,
    probe_split: str,
    prompts: list[str] | tuple[str, ...],
    max_new_tokens: int,
    do_sample: bool,
    chat_template_policy: str,
    env: Mapping,
) -> dict:
    """The canonical identity record `baseline_fingerprint` digests, as auditable data.

    Every parameter is keyword-only and REQUIRED — none has a default. A default
    on a fingerprint input is a hole: a caller could omit it and get a key that
    silently ignores the setting it actually ran with. `CAPTURE_PROTOCOL_VERSION`
    is the one input that is not a parameter, because it must not be
    caller-supplied (module docstring).

    `prompts` is the probe text actually sent to the arm, digested (never stored):
    it makes the (dataset id, revision, split) pin auditable instead of merely
    asserted, and it covers probe count and order, which positional completions
    depend on.

    `env` is the execution environment — pass `environment_identity()` in a real
    run. It is a parameter rather than a module-resolved constant so that this
    function stays importable and testable without torch, and so the key's env is
    the same record the run's report carries.
    """
    identity = _arm_identity(_normalize_arm(arm, "arm"))
    environment = _env_identity(env)

    _require(
        isinstance(probe_dataset_id, str) and bool(probe_dataset_id.strip()),
        "probe_dataset_id must be a non-empty string",
    )
    _require(
        _is_hex_digest(probe_dataset_revision, *_REVISION_DIGEST_LENS),
        f"probe_dataset_revision {probe_dataset_revision!r} {_UNPINNED_REVISION}",
    )
    _require(isinstance(probe_split, str) and bool(probe_split.strip()), "probe_split must be a non-empty string")

    _require(isinstance(prompts, (list, tuple)), "prompts must be a list or tuple of probe strings")
    _require(bool(prompts), "prompts must be non-empty: a cache key over zero probes measures nothing")
    _require(all(isinstance(p, str) for p in prompts), "every prompt must be a string")

    _require(
        isinstance(max_new_tokens, int) and not isinstance(max_new_tokens, bool) and max_new_tokens > 0,
        "max_new_tokens must be a positive int",
    )
    _require(isinstance(do_sample, bool), "do_sample must be a bool")
    _require(
        isinstance(chat_template_policy, str) and bool(chat_template_policy.strip()),
        "chat_template_policy must be a non-empty string (the policy recorded in decode.chat_template)",
    )

    return {
        "capture_protocol_version": CAPTURE_PROTOCOL_VERSION,
        "arm": identity,
        "env": environment,
        "probe": {
            "dataset_id": probe_dataset_id,
            "dataset_revision": probe_dataset_revision,
            "split": probe_split,
            "n_prompts": len(prompts),
            "prompts_sha256": _digest(_DOMAIN_PROMPTS, list(prompts)),
        },
        "decode": {
            "max_new_tokens": max_new_tokens,
            "do_sample": do_sample,
            "chat_template": chat_template_policy,
        },
    }


def baseline_fingerprint(
    arm: ArmRun | Mapping,
    *,
    probe_dataset_id: str,
    probe_dataset_revision: str,
    probe_split: str,
    prompts: list[str] | tuple[str, ...],
    max_new_tokens: int,
    do_sample: bool,
    chat_template_policy: str,
    env: Mapping,
) -> str:
    """sha256 over the canonical identity of one baseline arm's generation.

    Covers exactly `FINGERPRINT_INPUTS`. Built from an ArmRun-shaped provenance
    record plus the probe, decode and environment facts — never from a
    caller-supplied string.
    """
    return _digest(
        _DOMAIN_FINGERPRINT,
        fingerprint_inputs(
            arm,
            probe_dataset_id=probe_dataset_id,
            probe_dataset_revision=probe_dataset_revision,
            probe_split=probe_split,
            prompts=prompts,
            max_new_tokens=max_new_tokens,
            do_sample=do_sample,
            chat_template_policy=chat_template_policy,
            env=env,
        ),
    )


def _validated_inputs(inputs, where: str) -> dict:
    """Structurally validate a fingerprint-input record (as built, or as read off disk).

    Exact key sets at every level except `env`, which is open by design (digested
    whole, see `_env_identity`). A tamperer who adds a key would also break the
    digest check, but "unknown key `revisionn`" is the message that tells an
    operator what happened, and a typo'd key must never read as an omitted field.
    """
    _require(isinstance(inputs, Mapping), f"{where} must be a JSON object")
    unknown = sorted(set(inputs) - _INPUT_SECTIONS)
    _require(not unknown, f"{where} has unknown keys {unknown}; allowed: {sorted(_INPUT_SECTIONS)}")
    missing = sorted(_INPUT_SECTIONS - set(inputs))
    _require(not missing, f"{where} is missing {missing}")

    for section, allowed in (
        ("arm", _ARM_INPUT_FIELDS),
        ("probe", _PROBE_INPUT_FIELDS),
        ("decode", _DECODE_INPUT_FIELDS),
    ):
        block = inputs[section]
        _require(isinstance(block, Mapping), f"{where}.{section} must be a JSON object")
        _require(
            set(block) == allowed, f"{where}.{section} keys must be exactly {sorted(allowed)}, got {sorted(block)}"
        )

    _require(
        isinstance(inputs["capture_protocol_version"], str) and bool(inputs["capture_protocol_version"]),
        f"{where}.capture_protocol_version must be a non-empty string",
    )
    identity = _arm_identity(inputs["arm"])
    environment = _env_identity(inputs["env"], f"{where}.env")
    probe = dict(inputs["probe"])
    _require(
        isinstance(probe["n_prompts"], int) and not isinstance(probe["n_prompts"], bool) and probe["n_prompts"] > 0,
        f"{where}.probe.n_prompts must be a positive int",
    )
    _require(
        isinstance(probe["prompts_sha256"], str) and len(probe["prompts_sha256"]) == 64,
        f"{where}.probe.prompts_sha256 must be a sha256 digest",
    )
    for field in ("dataset_id", "split"):
        _require(
            isinstance(probe[field], str) and bool(probe[field].strip()),
            f"{where}.probe.{field} must be a non-empty string",
        )
    # Same pinning rule as `fingerprint_inputs`, applied to entries read off disk too:
    # an entry keyed on a floating probe revision cannot be re-derived, so it is refused
    # here rather than served.
    _require(
        _is_hex_digest(probe["dataset_revision"], *_REVISION_DIGEST_LENS),
        f"{where}.probe.dataset_revision {probe['dataset_revision']!r} {_UNPINNED_REVISION}",
    )
    decode = dict(inputs["decode"])
    _require(
        isinstance(decode["max_new_tokens"], int)
        and not isinstance(decode["max_new_tokens"], bool)
        and decode["max_new_tokens"] > 0,
        f"{where}.decode.max_new_tokens must be a positive int",
    )
    _require(isinstance(decode["do_sample"], bool), f"{where}.decode.do_sample must be a bool")
    _require(
        isinstance(decode["chat_template"], str) and bool(decode["chat_template"].strip()),
        f"{where}.decode.chat_template must be a non-empty string",
    )
    return {
        "capture_protocol_version": inputs["capture_protocol_version"],
        "arm": identity,
        "env": environment,
        "probe": probe,
        "decode": decode,
    }


# --- entry paths -----------------------------------------------------------------


def entry_path(cache_dir: str | os.PathLike, fingerprint: str) -> Path:
    """Where a fingerprint's entry lives: `<cache_dir>/<fingerprint>.baseline-cache.json`."""
    return Path(cache_dir) / f"{_validated_key(fingerprint)}{CACHE_ENTRY_SUFFIX}"


# --- store -----------------------------------------------------------------------


def store(
    cache_dir: str | os.PathLike,
    fingerprint_inputs_record: Mapping,
    completions: list[str] | tuple[str, ...],
    arm_record: ArmRun | Mapping,
) -> Path:
    """Write one baseline arm's completions under the key derived from its identity.

    Takes the fingerprint INPUTS (from `fingerprint_inputs`), not a fingerprint
    string, and derives the key itself. That is deliberate and is the point of the
    signature: a `store(dir, key, ...)` that accepted a key independent of the
    inputs would let a caller file arm A's completions under arm B's key, which is
    exactly the wrong hit this module exists to prevent. `arm_record` is the full
    ArmRun (identity + `runtime_s`) and is cross-checked against the inputs.

    The write is atomic — temp file in the same directory, flushed and fsync'd,
    then `os.replace` — so a process crash or a full disk cannot leave a
    half-written entry at a servable filename, and a reader never sees a partial
    one. Stated exactly, because "never" would be an overclaim: the fsync covers
    the entry's CONTENTS, not the rename, and the containing directory is not
    synced. So a power loss can still lose a just-written entry, or (on a
    filesystem that reorders) publish a torn one. Neither is a wrong hit: an entry
    that will not parse is a MISS, and one that parses with mangled bytes fails the
    `payload_sha256` / fingerprint re-derivation in `load` and is refused. The
    worst case is the regeneration the zero-hit budget already paid for.
    """
    import quantfit

    inputs = _validated_inputs(fingerprint_inputs_record, "fingerprint inputs")
    fingerprint = _digest(_DOMAIN_FINGERPRINT, inputs)

    _require(isinstance(completions, (list, tuple)), "completions must be a list or tuple of strings")
    _require(all(isinstance(c, str) for c in completions), "every completion must be a string")
    _require(
        len(completions) == inputs["probe"]["n_prompts"],
        f"{len(completions)} completions for {inputs['probe']['n_prompts']} prompts: completions are stored "
        "positionally against the fingerprinted probe list, so a length mismatch is a misaligned pair",
    )

    record = _normalize_arm(arm_record, "arm_record")
    identity = inputs["arm"]
    for field in _ARM_IDENTITY_FIELDS:
        _require(
            record.get(field) == identity[field],
            f"arm_record.{field} disagrees with the fingerprint inputs "
            f"({record.get(field)!r} vs {identity[field]!r}): the stored arm must be the arm the key describes",
        )

    payload = {"arm": record, "completions": list(completions)}
    header = {
        # First key on purpose: `head` on any entry shows what the file contains.
        "warning": COMPLETION_TEXT_WARNING,
        "kind": _KIND,
        "schema_version": CACHE_SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "quantfit_version": quantfit.__version__,
        "capture_protocol_version": inputs["capture_protocol_version"],
        "fingerprint": fingerprint,
        # The auditable half: a hit can be inspected against the run's own facts,
        # not merely trusted because the filename matched.
        "fingerprint_inputs": inputs,
        "payload_sha256": _digest(_DOMAIN_PAYLOAD, payload),
        "n_completions": len(completions),
        "budget_rule": BUDGET_RULE,
        "retention": RETENTION_NOTE,
    }
    # Serialize BEFORE touching the filesystem: an unserializable arm_record must
    # fail without having created a temp file at all.
    text = json.dumps({"header": header, "payload": payload}, indent=2) + "\n"

    directory = Path(cache_dir)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CacheError(f"cannot create cache directory {directory}: {exc}") from exc

    final = entry_path(directory, fingerprint)
    fd, tmp_name = tempfile.mkstemp(dir=str(directory), prefix=_TMP_PREFIX, suffix=_TMP_SUFFIX)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())  # the bytes are on the device before the name points at them
        os.replace(tmp_name, final)
    except OSError as exc:
        raise CacheError(f"cannot write cache entry {final}: {exc}") from exc
    finally:
        # No-op after a successful replace (the temp name is gone); on any failure
        # this is what guarantees no partial file is left behind.
        Path(tmp_name).unlink(missing_ok=True)
    return final


# --- load ------------------------------------------------------------------------


def _read_entry(path: Path) -> dict | None:
    """Parse an entry file. `None` for absent-or-uninterpretable; raises on unreadable."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None  # a cold cache is the expected state, not an error
    except UnicodeDecodeError:
        # Not our bytes at all: our own writes are UTF-8 JSON. Undecodable is the same
        # kind of uninterpretable as unparseable, so it is a MISS — the documented
        # behavior — and NOT an uncaught UnicodeDecodeError out of load/read_header/purge.
        return None
    except OSError as exc:
        raise CacheError(f"cannot read cache entry {path}: {exc}") from exc
    try:
        entry = json.loads(text)
    except json.JSONDecodeError:
        # Our own writes are atomic, so this is a foreign or mangled file at our
        # filename. A cache is derived and disposable: regenerate rather than
        # refuse, because the fallback costs only what the budget already assumed.
        return None
    if not isinstance(entry, dict):
        return None
    header = entry.get("header")
    if not isinstance(header, dict) or header.get("schema_version") != CACHE_SCHEMA_VERSION:
        # A different envelope version cannot be interpreted -> miss, not refusal.
        # A cache must not brick an operator's gate across a schema bump.
        return None
    return entry


def _validated_entry(path: Path, fingerprint: str) -> dict | None:
    """Fully check an entry against its own header and its key. Refuses, never repairs."""
    entry = _read_entry(path)
    if entry is None:
        return None

    header = entry["header"]
    unknown = sorted(set(header) - _HEADER_FIELDS)
    _require(not unknown, f"cache entry {path.name} header has unknown keys {unknown}")
    missing = sorted(_HEADER_FIELDS - set(header))
    _require(not missing, f"cache entry {path.name} header is missing {missing}")
    _require(header["kind"] == _KIND, f"cache entry {path.name} is not a {_KIND} ({header['kind']!r})")

    inputs = _validated_inputs(header.get("fingerprint_inputs"), f"cache entry {path.name} fingerprint_inputs")
    derived = _digest(_DOMAIN_FINGERPRINT, inputs)
    # The two checks that make a hit auditable rather than trusted: the entry must
    # agree with its own recorded inputs, and it must be filed under them. Either
    # failure means an edited or misfiled entry, and serving one would fabricate
    # the baseline half of a measurement.
    _require(
        header.get("fingerprint") == derived,
        f"cache entry {path.name} does not match its own recorded inputs "
        f"(derived {derived[:12]}..., header says {str(header.get('fingerprint'))[:12]}...): "
        "the entry was edited. Purge it; do not serve it.",
    )
    _require(
        derived == fingerprint,
        f"cache entry {path.name} is filed under a key its inputs do not derive "
        f"(derived {derived[:12]}...): the payload was moved or copied. Purge it; do not serve it.",
    )

    payload = entry.get("payload")
    _require(isinstance(payload, dict), f"cache entry {path.name} payload must be a JSON object")
    _require(set(payload) == {"arm", "completions"}, f"cache entry {path.name} payload keys must be arm + completions")
    completions = payload["completions"]
    _require(
        isinstance(completions, list) and all(isinstance(c, str) for c in completions),
        f"cache entry {path.name} completions must be a list of strings",
    )
    _require(
        header.get("payload_sha256") == _digest(_DOMAIN_PAYLOAD, payload),
        f"cache entry {path.name} payload does not match its recorded payload_sha256: the completions "
        "or the arm record were edited. Purge it; do not serve it.",
    )
    _require(
        len(completions) == inputs["probe"]["n_prompts"] == header.get("n_completions"),
        f"cache entry {path.name} holds {len(completions)} completions for "
        f"{inputs['probe']['n_prompts']} fingerprinted prompts",
    )
    record = _normalize_arm(payload["arm"], f"cache entry {path.name} payload.arm")
    for field in _ARM_IDENTITY_FIELDS:
        _require(
            record.get(field) == inputs["arm"][field],
            f"cache entry {path.name} payload.arm.{field} disagrees with its fingerprint inputs",
        )
    return entry


def load(cache_dir: str | os.PathLike, fingerprint: str) -> tuple[list[str], dict] | None:
    """Serve one baseline arm's `(completions, arm_record)`, or `None` on a miss.

    A miss is absence or an uninterpretable envelope — no file, bytes that are not
    UTF-8, text that is not JSON, or a schema version this code does not read; all
    are normal and cost a regeneration the budget already assumed. An entry that claims to be a valid
    current-schema entry and contradicts itself — edited inputs, edited payload,
    filed under a key its own inputs do not derive — raises `CacheError` rather
    than being served or silently treated as a miss: serving it would fabricate
    the baseline half of a measurement, and hiding it would keep the operator
    from learning their cache was edited.
    """
    entry = _validated_entry(entry_path(cache_dir, fingerprint), fingerprint)
    if entry is None:
        return None
    payload = entry["payload"]
    return list(payload["completions"]), dict(payload["arm"])


def read_header(cache_dir: str | os.PathLike, fingerprint: str) -> dict | None:
    """The validated header of an entry, with no completion text — for auditing a hit.

    Lets a gate print WHICH inputs a hit was keyed on (and the warning, the budget
    rule and the retention note) without moving completion text into a log or a
    terminal. Same refusal semantics as `load`.
    """
    entry = _validated_entry(entry_path(cache_dir, fingerprint), fingerprint)
    return None if entry is None else dict(entry["header"])


# --- retention -------------------------------------------------------------------


def _as_utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


def _created_utc(path: Path) -> datetime | None:
    """An entry's recorded creation time, or None when it cannot be read.

    `created_utc` travels with the entry, so retention survives a copy that reset
    file mtimes. Never raises: every unreadable form — absent, undecodable,
    unparseable, wrong schema, unreadable by the OS, unparseable timestamp —
    answers None, which purge treats as "retention has nothing to protect here".
    A header no one can read is one no one can serve.
    """
    try:
        entry = _read_entry(path)
    except CacheError:
        return None
    if entry is None:
        return None
    try:
        return _as_utc(datetime.fromisoformat(str(entry["header"].get("created_utc"))))
    except (AttributeError, TypeError, ValueError):
        return None


def _tmp_mtime(path: Path) -> datetime | None:
    """A leftover temp file's mtime (it carries no header), or None if unstattable."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise CacheError(f"cannot delete cache entry {path}: {exc}") from exc


def purge(
    cache_dir: str | os.PathLike,
    older_than_days: float | None = None,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Delete cache entries; returns the filenames removed, sorted.

    `older_than_days=None` deletes every entry — the operator's "this directory
    held completion text and no longer does" button, which the data-handling
    doc's retention posture requires be one call. A number keeps entries newer
    than that many days, dated from each entry's own recorded `created_utc`.

    An entry whose header cannot be read is deleted regardless of the cutoff: it
    can never be served (`load` treats it as a miss or refuses it), so retention
    has nothing to protect there. Leftover `.tmp` files from a hard-killed write
    are swept the same way. A cache directory has one writer by construction — a
    gate's arms run strictly sequentially — so this does not race a `store`;
    do not purge a directory another process is writing.

    **The sweep is per-entry.** One file that cannot be read — foreign bytes, not
    UTF-8, a truncated write — or even one that cannot be deleted must not abort
    the pass and strand every remaining entry's completion text on disk, because
    this is the deletion control the data-handling decision relies on. So each
    entry is handled independently; files that could not be deleted are collected
    and reported in a single `CacheError` raised AFTER everything deletable is
    gone, so the operator learns what remains without the rest surviving.

    `now` is an injection point for deterministic retention tests and audits.
    """
    directory = Path(cache_dir)
    if not directory.is_dir():
        return []  # nothing to retain; purging a cache that never existed is not an error

    if older_than_days is not None:
        _require(
            isinstance(older_than_days, (int, float)) and not isinstance(older_than_days, bool),
            "older_than_days must be a number of days or None",
        )
        _require(older_than_days >= 0, "older_than_days must be >= 0")
    moment = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    cutoff = None if older_than_days is None else moment - timedelta(days=float(older_than_days))

    removed: list[str] = []
    stranded: list[str] = []

    def sweep(path: Path, dated: datetime | None) -> None:
        if cutoff is not None and dated is not None and dated >= cutoff:
            return
        try:
            _unlink(path)
        except CacheError as exc:
            stranded.append(f"{path.name} ({exc})")
            return
        removed.append(path.name)

    for path in sorted(directory.glob(CACHE_ENTRY_GLOB)):
        sweep(path, _created_utc(path))
    for path in sorted(directory.glob(_TMP_GLOB)):
        sweep(path, _tmp_mtime(path))

    if stranded:
        raise CacheError(
            f"purged {len(removed)} of {len(removed) + len(stranded)} files in {directory}, but could not "
            f"delete {stranded}. These still hold model completion text (docs/data-handling-completions.md): "
            "remove them by hand, or remove the directory."
        )
    return sorted(removed)
