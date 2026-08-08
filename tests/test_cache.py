"""Fingerprint-keyed baseline cache (hermetic: no network, no model load, no torch).

The property under test is not "the cache works" but "the cache cannot be wrong":
a hit must be impossible unless every input that can change a completion matched,
and an entry that contradicts itself must never be served. So the fingerprint
tests are exhaustive by parametrization over each input, and the load tests are
mostly about refusals.

Hermeticity is a hard rule here, which is why the `env` input is INJECTED (`_env`)
rather than resolved: `cache.environment_identity()` would import torch and read a
device, and this suite must run identically on a GPU box, a CPU box, and a machine
with no torch installed at all.
"""

import dataclasses
import fnmatch
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quantfit.safety import cache
from quantfit.safety.cache import CacheError, baseline_fingerprint, fingerprint_inputs, load, purge, store

PROMPTS = ["refuse this one", "answer this one"]
COMPLETIONS = ["I cannot help with that.", "COMPLETION-TEXT-SENTINEL: sure, here is how."]
REPO_ROOT = Path(__file__).resolve().parents[1]  # located from the test file, never the CWD


def _transformers_engine(**overrides):
    engine = {"name": "transformers", "version": "4.57.1", "device": "cuda"}
    engine.update(overrides)
    return engine


def _gguf_engine(**overrides):
    engine = {
        "name": "llama.cpp",
        "binary_sha256": "c" * 64,
        "source": "pinned release archive b9817 (SHA256-verified)",
        "threads": 6,
        "device": "cpu",
    }
    engine.update(overrides)
    return engine


def _arm(**overrides):
    """A real ArmRun, so the cache is exercised against the shipped provenance schema."""
    from quantfit.safety.report import ArmRun

    fields = {
        "model": "org/base-model",
        "revision": "a" * 40,
        "resolved_dtype": "torch.bfloat16",
        "runtime_s": 12.5,
        "engine": _transformers_engine(),
        "artifact_sha256": None,
    }
    fields.update(overrides)
    return ArmRun(**fields)


def _gguf_arm(**overrides):
    from quantfit.safety.report import ArmRun

    fields = {
        "model": "hf:org/repo/base-f16.gguf",
        "revision": "a" * 40,
        "resolved_dtype": "F16",
        "runtime_s": 12.5,
        "engine": _gguf_engine(),
        "artifact_sha256": "d" * 64,
    }
    fields.update(overrides)
    return ArmRun(**fields)


def _env(**overrides):
    """The execution environment, shaped like report.environment_fingerprint()'s output.

    A literal, not a call: injecting it keeps the suite hermetic (no torch import, no
    device query) while still exercising the real input.
    """
    env = {
        "python": "3.11.9",
        "torch": "2.5.1+cu121",
        "transformers": "4.57.1",
        "cuda": "12.1",
        "device": "NVIDIA GeForce RTX 4090",
    }
    env.update(overrides)
    return env


def _facts(**overrides):
    facts = {
        "probe_dataset_id": "Crusadersk/quantsafe-judge-benchmark",
        "probe_dataset_revision": "c26cc2e15fcadab9c0ec24a5b57d37b140f7ed58",
        "probe_split": "train",
        "prompts": list(PROMPTS),
        "max_new_tokens": 64,
        "do_sample": False,
        "chat_template_policy": "model-default when present, raw prompt otherwise",
        "env": _env(),
    }
    facts.update(overrides)
    return facts


def _fp(arm=None, **fact_overrides):
    return baseline_fingerprint(arm if arm is not None else _arm(), **_facts(**fact_overrides))


def _stored(tmp_path, arm=None, completions=None, **fact_overrides):
    """Store one entry; returns (cache_dir, fingerprint, path)."""
    arm = arm if arm is not None else _arm()
    cache_dir = tmp_path / "cache"
    inputs = fingerprint_inputs(arm, **_facts(**fact_overrides))
    path = store(cache_dir, inputs, completions if completions is not None else COMPLETIONS, arm)
    return cache_dir, baseline_fingerprint(arm, **_facts(**fact_overrides)), path


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _rewrite(path, entry):
    path.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")


# --- fingerprint stability + coverage --------------------------------------------


def test_fingerprint_is_stable_when_nothing_changes():
    # Rebuilt arm objects, rebuilt fact dicts, fresh prompt list: same identity,
    # same key. A cache that re-keys per process never hits.
    assert _fp() == _fp()
    assert _fp() == baseline_fingerprint(_arm(), **_facts(prompts=list(PROMPTS)))
    assert len(_fp()) == 64


_MUTATIONS = [
    # (case id, arm overrides, fact overrides) -- exactly one input moves per case.
    ("model", {"model": "org/other-model"}, {}),
    ("revision", {"revision": "f" * 40}, {}),
    ("resolved_dtype", {"resolved_dtype": "torch.float16"}, {}),
    ("engine_transformers_version", {"engine": _transformers_engine(version="4.58.0")}, {}),
    ("engine_device", {"engine": _transformers_engine(device="cpu")}, {}),
    # Not a whitelist: a field the fingerprint code has never heard of still moves
    # the key, because the whole engine dict is digested.
    ("engine_unknown_key", {"engine": _transformers_engine(offload="disk")}, {}),
    ("artifact_sha256", {"artifact_sha256": "e" * 64}, {}),
    ("probe_dataset_id", {}, {"probe_dataset_id": "other/probe-set"}),
    ("probe_dataset_revision", {}, {"probe_dataset_revision": "9" * 40}),
    ("probe_split", {}, {"probe_split": "test"}),
    ("prompt_text", {}, {"prompts": ["refuse this one", "answer this one, differently"]}),
    ("prompt_order", {}, {"prompts": list(reversed(PROMPTS))}),
    ("prompt_count", {}, {"prompts": [*PROMPTS, "a third probe"]}),
    ("max_new_tokens", {}, {"max_new_tokens": 128}),
    ("do_sample", {}, {"do_sample": True}),
    ("chat_template_policy", {}, {"chat_template_policy": "raw prompt always"}),
    # The execution environment. Two baselines this project itself calls
    # differently-determined must not collide on one key, and cross-hardware variation
    # is an open 0.7 workstream rather than something this module may assume away.
    ("env_torch", {}, {"env": _env(torch="2.6.0")}),
    ("env_cuda", {}, {"env": _env(cuda="12.4")}),
    ("env_device", {}, {"env": _env(device="NVIDIA A100-SXM4-40GB")}),
    ("env_transformers", {}, {"env": _env(transformers="4.58.0")}),
    ("env_python", {}, {"env": _env(python="3.12.4")}),
    # Same not-a-whitelist property as arm.engine: env is digested whole, so a key the
    # fingerprint code has never heard of still moves the fingerprint.
    ("env_unknown_key", {}, {"env": _env(driver="560.94")}),
    ("env_cpu_only", {}, {"env": _env(cuda=None, device="cpu")}),
]


@pytest.mark.parametrize(
    ("arm_overrides", "fact_overrides"), [m[1:] for m in _MUTATIONS], ids=[m[0] for m in _MUTATIONS]
)
def test_fingerprint_changes_when_any_input_changes(arm_overrides, fact_overrides):
    assert _fp(_arm(**arm_overrides), **fact_overrides) != _fp()


_GGUF_MUTATIONS = [
    ("binary_sha256", {"engine": _gguf_engine(binary_sha256="9" * 64)}),
    ("threads", {"engine": _gguf_engine(threads=12)}),
    ("device", {"engine": _gguf_engine(device="cuda")}),
    ("source", {"engine": _gguf_engine(source="QUANTFIT_LLAMACPP (user-provided build; tag not verified)")}),
]


@pytest.mark.parametrize("overrides", [m[1] for m in _GGUF_MUTATIONS], ids=[m[0] for m in _GGUF_MUTATIONS])
def test_gguf_engine_identity_is_covered(overrides):
    # The GGUF arm's engine identity IS the binary hash + threads + device (the
    # same-binary mandate, QSR v0 §3.2); each of them must re-key.
    assert _fp(_gguf_arm(**overrides)) != _fp(_gguf_arm())


def test_capture_protocol_version_is_covered(monkeypatch):
    before = _fp()
    monkeypatch.setattr(cache, "CAPTURE_PROTOCOL_VERSION", "qsr-v0/capture-2")
    assert _fp() != before


def test_runtime_s_is_deliberately_not_in_the_fingerprint():
    # runtime_s is a measured output. Two byte-identical arms differ in it, so
    # digesting it would mean the cache never hits.
    assert _fp(_arm(runtime_s=999.0)) == _fp(_arm(runtime_s=0.1))


def test_documented_input_list_matches_what_is_digested():
    # Catches doc drift in both directions: a new digested field that FINGERPRINT_INPUTS
    # does not list, and a listed field that is no longer digested.
    inputs = fingerprint_inputs(_arm(), **_facts())
    dotted = set()
    for key, value in inputs.items():
        if key in ("arm", "probe", "decode"):
            dotted.update(f"{key}.{sub}" for sub in value)
        else:
            # capture_protocol_version is a scalar; `env` is a LEAF on purpose — like
            # arm.engine it is digested whole, so it is listed as one input rather than
            # as a whitelist of keys that a new key could fall outside of.
            dotted.add(key)
    assert dotted == set(cache.FINGERPRINT_INPUTS)
    assert "env" in cache.FINGERPRINT_INPUTS


def test_the_arm_identity_whitelist_is_tied_to_the_armrun_field_set():
    # _ARM_IDENTITY_FIELDS is a hardcoded whitelist, so without this guard a field added
    # to ArmRun falls outside the fingerprint SILENTLY -- a wrong-hit channel. With it,
    # adding a field fails here until someone decides, deliberately, which side it is on.
    from quantfit.safety.report import ArmRun

    assert {f.name for f in dataclasses.fields(ArmRun)} == set(cache._ARM_IDENTITY_FIELDS) | set(
        cache._ARM_NON_IDENTITY_FIELDS
    )
    # The intentional exclusion is exactly one field, and it is an OUTPUT of a run.
    assert cache._ARM_NON_IDENTITY_FIELDS == ("runtime_s",)


def test_importing_the_cache_module_does_not_drag_torch():
    # The claim is about THIS module: `import quantfit.safety.cache` must not pull torch,
    # which is what keeps the env input injectable and this suite hermetic. Checked in a
    # fresh interpreter rather than against sys.modules, for two reasons: in-process,
    # sibling test modules legitimately import torch first (tests/test_probe.py,
    # tests/test_report.py both importorskip it), so the in-process form asserts a
    # suite-wide invariant that does not exist and turns import ORDER into a failure of
    # this file; and a subprocess is the only form that actually proves the user-facing
    # property -- a cold interpreter importing the module stays torch-free.
    probe = "import quantfit.safety.cache, sys; print('torch' in sys.modules)"
    done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, cwd=REPO_ROOT, check=False)
    # Two assertions, so a subprocess that could not import quantfit at all fails as
    # itself rather than as a torch finding (or, worse, vacuously).
    assert done.returncode == 0, f"the probe interpreter failed:\n{done.stdout}{done.stderr}"
    assert done.stdout.strip() == "False", f"import quantfit.safety.cache pulled in torch:\n{done.stdout}"


def test_environment_identity_wraps_the_reports_fingerprint_and_validates_it(monkeypatch):
    # The real caller's env comes from report.environment_fingerprint(), lazily imported
    # so cache stays importable without torch. Patched here rather than called, so this
    # test needs neither torch nor a GPU.
    from quantfit.safety import report

    monkeypatch.setattr(report, "environment_fingerprint", lambda: _env())
    assert cache.environment_identity() == _env()

    monkeypatch.setattr(report, "environment_fingerprint", lambda: {"torch": "2.5.1+cu121"})
    with pytest.raises(CacheError, match="environment_fingerprint"):
        cache.environment_identity()


def test_gguf_and_transformers_arms_never_collide():
    # Same model string, revision, prompts, decode and split; different engine class.
    shared = {"model": "org/base-model", "revision": "a" * 40, "resolved_dtype": "F16", "artifact_sha256": "d" * 64}
    transformers_like = _arm(**shared, engine=_transformers_engine())
    gguf_like = _gguf_arm(**shared, engine=_gguf_engine())
    assert _fp(transformers_like) != _fp(gguf_like)


def test_prompt_text_is_digested_never_stored(tmp_path):
    _, _, path = _stored(tmp_path)
    inputs = _read(path)["header"]["fingerprint_inputs"]
    assert len(inputs["probe"]["prompts_sha256"]) == 64
    assert inputs["probe"]["n_prompts"] == len(PROMPTS)
    for prompt in PROMPTS:
        assert prompt not in json.dumps(inputs)


# --- identity refusals -----------------------------------------------------------


def test_arm_without_content_identity_is_refused():
    # A local dir with no resolved revision and no artifact hash: "the same model"
    # means only "the same path", so it is not cacheable rather than wrong.
    with pytest.raises(CacheError, match="no content identity"):
        _fp(_arm(model="./local-checkpoint", revision=None, artifact_sha256=None))


def test_artifact_sha256_alone_is_enough_content_identity():
    assert len(_fp(_arm(revision=None, artifact_sha256="d" * 64))) == 64


# A revision confers content identity only if it is DIGEST-SHAPED. Each of these is
# non-empty, so each one satisfies a non-emptiness check -- and each one names whatever
# the repo owner pushed last, which is the wrong-hit channel: a stable key under which
# nothing binds to the weights' content survives new weights being pushed, and the
# baseline half of the next paired diff is then fabricated.
_UNPINNED_ARM_REVISIONS = [
    ("branch", "main"),
    ("head", "HEAD"),
    ("full_ref", "refs/heads/main"),
    ("remote_ref", "refs/remotes/origin/main"),
    ("tag", "v1.0"),
    ("short_hex", "a" * 7),
    ("abbrev_hex", "a" * 12),
    ("uppercase_hex", "A" * 40),
    ("empty", ""),
    ("whitespace", "   "),
    ("absent", None),
]


@pytest.mark.parametrize(
    "revision", [r[1] for r in _UNPINNED_ARM_REVISIONS], ids=[r[0] for r in _UNPINNED_ARM_REVISIONS]
)
def test_a_revision_that_is_not_a_commit_digest_is_no_content_identity(revision):
    with pytest.raises(CacheError, match="no content identity"):
        _fp(_arm(revision=revision, artifact_sha256=None))


def test_the_refusal_names_the_floating_ref_as_the_reason():
    # The message has to be true: the arm HAS a revision, it just is not a pin.
    with pytest.raises(CacheError, match="not a resolved commit digest"):
        _fp(_arm(revision="main", artifact_sha256=None))


@pytest.mark.parametrize(
    "revision", ["a" * 40, "b" * 64, "c26cc2e15fcadab9c0ec24a5b57d37b140f7ed58", "0123456789abcdef" * 4]
)
def test_a_full_length_commit_digest_is_accepted(revision):
    # 40 (git sha1) and 64 (sha256) hex, lowercase: the two resolved forms.
    assert len(_fp(_arm(revision=revision, artifact_sha256=None))) == 64


def test_a_floating_revision_is_still_digested_when_an_artifact_hash_pins_the_content():
    # A GGUF arm resolves HF `main` (docs/sensitivity-control-v0.md 2.3) and carries an
    # artifact_sha256, so it stays cacheable -- the file hash is what binds to content.
    # The floating ref is still IN the key; it just may never be what confers identity.
    assert len(_fp(_gguf_arm(revision="main"))) == 64
    assert _fp(_gguf_arm(revision="main")) != _fp(_gguf_arm(revision="a" * 40))


@pytest.mark.parametrize("artifact", ["", "   ", "d" * 63, "d" * 65, "D" * 64, "not-hex" * 8, f"sha256:{'d' * 64}"])
def test_an_artifact_sha256_that_is_not_a_sha256_is_refused(artifact):
    # Present-but-not-a-digest is broken provenance, not a weaker pin: it would satisfy a
    # non-emptiness check while binding to nothing.
    with pytest.raises(CacheError, match="not a 64-character lowercase hex sha256 digest"):
        _fp(_arm(revision="a" * 40, artifact_sha256=artifact))


@pytest.mark.parametrize(
    ("env", "message"),
    [
        (None, "must be a JSON object"),
        ("cuda 12.1", "must be a JSON object"),
        ({}, r"missing \['cuda', 'device', 'torch'\]"),
        ({"torch": "2.5.1+cu121", "cuda": "12.1"}, r"missing \['device'\]"),
        ({"cuda": "12.1", "device": "cpu"}, r"missing \['torch'\]"),
        ({"torch": "2.5.1+cu121", "device": "cpu"}, r"missing \['cuda'\]"),
        (_env(device=""), "device must be a non-empty string"),
        (_env(device="   "), "device must be a non-empty string"),
        (_env(device=None), "device must be a non-empty string"),
    ],
)
def test_an_env_that_does_not_state_the_hardware_is_refused(env, message):
    # cuda may be null (a CPU-only run has none), but the device must be NAMED: two
    # different GPUs with no recorded name would share one fingerprint.
    with pytest.raises(CacheError, match=message):
        _fp(env=env)


def test_a_cpu_only_env_is_accepted():
    assert len(_fp(env=_env(cuda=None, device="cpu"))) == 64


def test_auto_dtype_is_refused():
    # Two different precisions both recorded as "auto" would share one key. ArmRun
    # already refuses "auto" on construction (report.py), so this guard is for the
    # ArmRun-SHAPED-mapping path: a hand-built record, or the inputs block of an
    # entry read off disk, neither of which passes through ArmRun.__post_init__.
    from quantfit.safety.report import ReportError

    with pytest.raises(ReportError, match="not the 'auto' input"):
        _arm(resolved_dtype="auto")

    record = {
        "model": "org/base-model",
        "revision": "a" * 40,
        "resolved_dtype": "auto",
        "runtime_s": 12.5,
        "engine": _transformers_engine(),
        "artifact_sha256": None,
    }
    with pytest.raises(CacheError, match="not the 'auto' input"):
        _fp(record)


@pytest.mark.parametrize(
    "revision",
    [
        None,
        "",
        "   ",
        # The cases the old name CLAIMED and the old check did not cover: every one of
        # these is non-empty, so a non-emptiness check passes it, and none of them can be
        # re-derived later.
        "main",
        "HEAD",
        "refs/heads/main",
        "v1.0",
        "c26cc2e",
        "C26CC2E15FCADAB9C0EC24A5B57D37B140F7ED58",
    ],
)
def test_unpinned_probe_revision_is_refused(revision):
    # A floating branch is not an identity: nothing keyed on an unpinned probe set
    # can be re-derived.
    with pytest.raises(CacheError, match="pinned commit digest"):
        _fp(probe_dataset_revision=revision)


def test_an_entry_pinned_to_a_floating_probe_revision_is_refused_on_load_too(tmp_path):
    # The same pinning rule applies to what is read off disk, so the entries an older
    # (weaker) check could have written are refused rather than served.
    cache_dir, fingerprint, path = _stored(tmp_path)
    entry = _read(path)
    entry["header"]["fingerprint_inputs"]["probe"]["dataset_revision"] = "main"
    _rewrite(path, entry)
    with pytest.raises(CacheError, match="pinned commit digest"):
        load(cache_dir, fingerprint)


@pytest.mark.parametrize("omit", list(_facts()))
def test_fingerprint_inputs_have_no_defaults(omit):
    # A default on a fingerprint input is a hole: a caller could omit the setting
    # it actually ran with and still get a key.
    facts = _facts()
    facts.pop(omit)
    with pytest.raises(TypeError):
        baseline_fingerprint(_arm(), **facts)


def test_a_key_can_only_ever_be_a_digest(tmp_path):
    for bad in ("../escape", "not-hex" * 8, "A" * 64, "a" * 63):
        with pytest.raises(CacheError, match="hex sha256 digest"):
            load(tmp_path, bad)


# --- store / load round trip -----------------------------------------------------


def test_store_load_round_trip(tmp_path):
    cache_dir, fingerprint, path = _stored(tmp_path)

    assert path.name == f"{fingerprint}{cache.CACHE_ENTRY_SUFFIX}"
    assert path.name.endswith(".baseline-cache.json")

    hit = load(cache_dir, fingerprint)
    assert hit is not None
    completions, arm_record = hit
    assert completions == COMPLETIONS
    assert arm_record["model"] == "org/base-model"
    assert arm_record["runtime_s"] == 12.5  # the full ArmRun rides along, runtime included
    assert arm_record["engine"] == _transformers_engine()


def test_miss_returns_none(tmp_path):
    cache_dir, fingerprint, _ = _stored(tmp_path)
    # Same directory, a different arm: absence is a miss, not an error.
    assert load(cache_dir, _fp(_arm(model="org/other-model"))) is None
    assert load(tmp_path / "never-existed", fingerprint) is None


def test_store_refuses_an_arm_record_that_is_not_the_arm_the_key_describes(tmp_path):
    inputs = fingerprint_inputs(_arm(), **_facts())
    with pytest.raises(CacheError, match="disagrees with the fingerprint inputs"):
        store(tmp_path / "cache", inputs, COMPLETIONS, _arm(model="org/other-model"))


def test_store_refuses_a_completion_count_that_does_not_match_the_prompts(tmp_path):
    inputs = fingerprint_inputs(_arm(), **_facts())
    with pytest.raises(CacheError, match="misaligned pair"):
        store(tmp_path / "cache", inputs, ["only one"], _arm())


def test_store_overwrites_its_own_key_atomically(tmp_path):
    cache_dir, fingerprint, path = _stored(tmp_path)
    replacement = ["fresh a", "fresh b"]
    store(cache_dir, fingerprint_inputs(_arm(), **_facts()), replacement, _arm())
    assert load(cache_dir, fingerprint)[0] == replacement
    assert sorted(p.name for p in cache_dir.iterdir()) == [path.name]


def test_the_repos_gitignore_actually_ignores_cache_entries(tmp_path):
    # Asserting cache.GITIGNORE_PATTERN against cache.CACHE_ENTRY_SUFFIX would be the
    # module agreeing with itself and would stay green with the pattern absent from the
    # repo. The claim that matters -- entries hold completion text and are never
    # committed (docs/data-handling-completions.md clause 8) -- needs the REAL file.
    gitignore = REPO_ROOT / ".gitignore"
    assert gitignore.is_file(), f"no .gitignore at {gitignore}"
    patterns = [line.strip() for line in gitignore.read_text(encoding="utf-8").splitlines()]
    assert cache.GITIGNORE_PATTERN in patterns, (
        f"{cache.GITIGNORE_PATTERN!r} is not in {gitignore}: cache entries carry model completion text "
        "and the doc-mandated backstop against committing them is this pattern"
    )
    # ...and the pattern in the repo matches the filenames this module actually writes.
    _, _, path = _stored(tmp_path)
    assert fnmatch.fnmatch(path.name, cache.GITIGNORE_PATTERN)


# --- the header is auditable ------------------------------------------------------


def test_header_carries_the_warning_the_budget_rule_and_the_inputs(tmp_path):
    _, fingerprint, path = _stored(tmp_path)
    header = _read(path)["header"]

    assert header["warning"] == cache.COMPLETION_TEXT_WARNING
    assert "never commit" in header["warning"]
    assert "docs/data-handling-completions.md" in header["warning"]
    assert header["budget_rule"] == cache.BUDGET_RULE
    assert "ZERO cache hits" in header["budget_rule"]
    assert header["retention"] == cache.RETENTION_NOTE
    assert header["schema_version"] == cache.CACHE_SCHEMA_VERSION
    assert header["fingerprint"] == fingerprint
    assert header["capture_protocol_version"] == cache.CAPTURE_PROTOCOL_VERSION
    assert header["n_completions"] == len(COMPLETIONS)
    datetime.fromisoformat(header["created_utc"])  # parses as ISO 8601

    # A hit can be audited against the run's own facts, not merely trusted.
    inputs = header["fingerprint_inputs"]
    assert inputs["arm"] == {
        "model": "org/base-model",
        "revision": "a" * 40,
        "resolved_dtype": "torch.bfloat16",
        "engine": _transformers_engine(),
        "artifact_sha256": None,
    }
    assert inputs["env"] == _env()  # the execution environment is auditable from the entry
    assert inputs["probe"]["dataset_revision"] == "c26cc2e15fcadab9c0ec24a5b57d37b140f7ed58"
    assert inputs["decode"] == {
        "max_new_tokens": 64,
        "do_sample": False,
        "chat_template": "model-default when present, raw prompt otherwise",
    }
    assert "runtime_s" not in inputs["arm"]


def test_read_header_audits_a_hit_without_touching_completion_text(tmp_path):
    cache_dir, fingerprint, _ = _stored(tmp_path)
    header = cache.read_header(cache_dir, fingerprint)
    assert header["fingerprint"] == fingerprint
    assert "COMPLETION-TEXT-SENTINEL" not in json.dumps(header)
    assert cache.read_header(cache_dir, "0" * 64) is None


def test_the_warning_travels_in_every_entry(tmp_path):
    cache_dir, _, _ = _stored(tmp_path)
    store(cache_dir, fingerprint_inputs(_gguf_arm(), **_facts()), COMPLETIONS, _gguf_arm())
    entries = sorted(cache_dir.glob(cache.CACHE_ENTRY_GLOB))
    assert len(entries) == 2
    for path in entries:
        assert _read(path)["header"]["warning"] == cache.COMPLETION_TEXT_WARNING


# --- tamper refusals -------------------------------------------------------------


def test_edited_fingerprint_inputs_are_refused(tmp_path):
    cache_dir, fingerprint, path = _stored(tmp_path)
    entry = _read(path)
    # Hand-edit a measurement input while leaving the key and the digest alone:
    # the entry now claims 128 new tokens under a key derived from 64.
    entry["header"]["fingerprint_inputs"]["decode"]["max_new_tokens"] = 128
    _rewrite(path, entry)
    with pytest.raises(CacheError, match="does not match its own recorded inputs"):
        load(cache_dir, fingerprint)


def test_edited_arm_identity_in_the_inputs_is_refused(tmp_path):
    cache_dir, fingerprint, path = _stored(tmp_path)
    entry = _read(path)
    entry["header"]["fingerprint_inputs"]["arm"]["resolved_dtype"] = "torch.float16"
    _rewrite(path, entry)
    with pytest.raises(CacheError, match="does not match its own recorded inputs"):
        load(cache_dir, fingerprint)


def test_a_payload_moved_under_another_key_is_refused(tmp_path):
    cache_dir, fingerprint, path = _stored(tmp_path)
    other = "0" * 64
    (cache_dir / f"{other}{cache.CACHE_ENTRY_SUFFIX}").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(CacheError, match="filed under a key its inputs do not derive"):
        load(cache_dir, other)
    assert load(cache_dir, fingerprint)[0] == COMPLETIONS  # the original is untouched


def test_edited_completions_are_refused(tmp_path):
    cache_dir, fingerprint, path = _stored(tmp_path)
    entry = _read(path)
    entry["payload"]["completions"][0] = "Sure, here is how to do the thing."
    _rewrite(path, entry)
    with pytest.raises(CacheError, match="payload_sha256"):
        load(cache_dir, fingerprint)


def test_edited_stored_arm_runtime_is_refused(tmp_path):
    # runtime_s is outside the fingerprint but inside the payload digest: the cache
    # will not serve a record someone edited, even in a field the key ignores.
    cache_dir, fingerprint, path = _stored(tmp_path)
    entry = _read(path)
    entry["payload"]["arm"]["runtime_s"] = 0.0
    _rewrite(path, entry)
    with pytest.raises(CacheError, match="payload_sha256"):
        load(cache_dir, fingerprint)


def test_a_missing_header_field_is_refused(tmp_path):
    cache_dir, fingerprint, path = _stored(tmp_path)
    entry = _read(path)
    del entry["header"]["payload_sha256"]
    _rewrite(path, entry)
    with pytest.raises(CacheError, match="header is missing"):
        load(cache_dir, fingerprint)


def test_a_foreign_or_unreadable_envelope_is_a_miss_not_a_refusal(tmp_path):
    # A cache is derived and disposable: when it cannot be interpreted at all, the
    # safe answer is regenerate (the zero-hit budget already paid for that), not
    # brick the gate.
    cache_dir, fingerprint, path = _stored(tmp_path)

    entry = _read(path)
    entry["header"]["schema_version"] = 99
    _rewrite(path, entry)
    assert load(cache_dir, fingerprint) is None

    path.write_text("not json at all", encoding="utf-8")
    assert load(cache_dir, fingerprint) is None

    path.write_text("[]", encoding="utf-8")
    assert load(cache_dir, fingerprint) is None


def test_bytes_that_are_not_utf8_are_a_miss_and_never_abort_a_purge(tmp_path):
    # Undecodable bytes at an entry filename are the same kind of uninterpretable as
    # unparseable JSON, so they must MISS (the documented behavior) rather than raise
    # UnicodeDecodeError out of load / read_header / purge. Two of them, one sorting
    # before every real key and one after, so a sweep that aborted on either would be
    # caught whichever side the real entry lands on.
    cache_dir, fingerprint, good = _stored(tmp_path)
    first = cache_dir / f"{'0' * 64}{cache.CACHE_ENTRY_SUFFIX}"
    last = cache_dir / f"{'f' * 64}{cache.CACHE_ENTRY_SUFFIX}"
    for path in (first, last):
        path.write_bytes(b'{"header": {"schema_version": 1, "created_utc": "\xff\xfe not utf-8"}}')

    assert load(cache_dir, "0" * 64) is None
    assert load(cache_dir, "f" * 64) is None
    assert cache.read_header(cache_dir, "0" * 64) is None
    assert cache.read_header(cache_dir, "f" * 64) is None

    # An entry no one can read is one no one can serve, so retention has nothing to
    # protect: both go regardless of the window, and the sweep continues past them.
    assert purge(cache_dir, older_than_days=3650) == sorted([first.name, last.name])
    # The real entry is untouched by the neighbours' unreadability...
    assert load(cache_dir, fingerprint)[0] == COMPLETIONS
    # ...and, crucially, was never stranded on disk by an aborted sweep.
    assert purge(cache_dir) == [good.name]
    assert list(cache_dir.glob(cache.CACHE_ENTRY_GLOB)) == []


# --- atomic write ----------------------------------------------------------------


def test_a_failed_write_leaves_no_partial_file(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    inputs = fingerprint_inputs(_arm(), **_facts())

    def full_disk(src, dst):
        raise OSError("no space left on device")

    monkeypatch.setattr(cache.os, "replace", full_disk)
    with pytest.raises(CacheError, match="cannot write cache entry"):
        store(cache_dir, inputs, COMPLETIONS, _arm())

    # Neither a servable entry nor a leftover temp: the temp is dot-prefixed and
    # cannot match the entry glob, and the finally-clause removes it either way.
    assert list(cache_dir.iterdir()) == []


def test_store_flushes_and_fsyncs_before_publishing_the_entry(tmp_path, monkeypatch):
    # The docstring's durability claim, kept honest rather than assumed: the bytes reach
    # the device BEFORE the servable name points at them. (The rename itself is not
    # synced, which the docstring says outright -- that case degrades to a miss.)
    order = []
    real_fsync, real_replace = cache.os.fsync, cache.os.replace

    def fsync(fd):
        order.append("fsync")
        return real_fsync(fd)

    def replace(src, dst):
        order.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(cache.os, "fsync", fsync)
    monkeypatch.setattr(cache.os, "replace", replace)
    _stored(tmp_path)
    assert order == ["fsync", "replace"]


def test_an_unserializable_arm_record_fails_before_touching_the_directory(tmp_path):
    cache_dir = tmp_path / "cache"
    inputs = fingerprint_inputs(_arm(), **_facts())
    unserializable = {
        "model": "org/base-model",
        "revision": "a" * 40,
        "resolved_dtype": "torch.bfloat16",
        "runtime_s": {1, 2},  # a set is not JSON
        "engine": _transformers_engine(),
        "artifact_sha256": None,
    }
    with pytest.raises(CacheError, match="not canonically serializable"):
        store(cache_dir, inputs, COMPLETIONS, unserializable)
    assert not cache_dir.exists()


# --- retention -------------------------------------------------------------------


def _backdate(path, days):
    entry = _read(path)
    when = datetime.now(timezone.utc) - timedelta(days=days)
    entry["header"]["created_utc"] = when.isoformat(timespec="seconds")
    _rewrite(path, entry)


def test_purge_all_empties_the_directory(tmp_path):
    cache_dir, _, _ = _stored(tmp_path)
    store(cache_dir, fingerprint_inputs(_gguf_arm(), **_facts()), COMPLETIONS, _gguf_arm())
    removed = purge(cache_dir)
    assert len(removed) == 2
    assert all(name.endswith(cache.CACHE_ENTRY_SUFFIX) for name in removed)
    assert list(cache_dir.glob(cache.CACHE_ENTRY_GLOB)) == []


def test_purge_by_age_keeps_fresh_entries(tmp_path):
    cache_dir, fresh_fp, fresh_path = _stored(tmp_path)
    stale_arm = _gguf_arm()
    stale_path = store(cache_dir, fingerprint_inputs(stale_arm, **_facts()), COMPLETIONS, stale_arm)
    _backdate(stale_path, days=30)

    removed = purge(cache_dir, older_than_days=7)

    assert removed == [stale_path.name]
    assert not stale_path.exists()
    # created_utc is outside every digest, so backdating does not invalidate the
    # survivor -- retention and integrity are independent.
    assert load(cache_dir, fresh_fp)[0] == COMPLETIONS
    assert fresh_path.exists()


def test_purge_uses_the_injected_clock(tmp_path):
    cache_dir, _, path = _stored(tmp_path)
    assert purge(cache_dir, older_than_days=7, now=datetime.now(timezone.utc)) == []
    assert purge(cache_dir, older_than_days=7, now=datetime.now(timezone.utc) + timedelta(days=8)) == [path.name]


def test_purge_removes_entries_it_cannot_read_regardless_of_age(tmp_path):
    cache_dir, _, _ = _stored(tmp_path)
    junk = cache_dir / f"{'1' * 64}{cache.CACHE_ENTRY_SUFFIX}"
    junk.write_text("garbage", encoding="utf-8")
    # An unreadable entry can never be served, so retention has nothing to protect.
    assert purge(cache_dir, older_than_days=3650) == [junk.name]


def test_purge_finishes_the_sweep_then_reports_what_it_could_not_delete(tmp_path, monkeypatch):
    # A file this process cannot delete (locked, read-only, gone weird) must not abort the
    # pass and leave every other entry's completion text on disk. The failure is reported,
    # after everything deletable is already gone.
    cache_dir, _, good = _stored(tmp_path)
    locked = cache_dir / f"{'0' * 64}{cache.CACHE_ENTRY_SUFFIX}"  # sorts before any real key
    locked.write_text("garbage", encoding="utf-8")
    real_unlink = Path.unlink

    def refuse(self, *args, **kwargs):
        if self.name == locked.name:
            raise PermissionError("file is in use by another process")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", refuse)
    with pytest.raises(CacheError, match="could not delete"):
        purge(cache_dir)

    assert not good.exists()  # the sweep continued past the failure
    assert locked.exists()  # and the operator is told what is left


def test_purge_sweeps_leftover_temp_files(tmp_path):
    # A hard-killed store (SIGKILL, power loss) can leave a temp the finally-clause
    # never ran on. It is dot-prefixed, so it is never servable; purge removes it.
    cache_dir, fingerprint, _ = _stored(tmp_path)
    leftover = cache_dir / f"{cache._TMP_PREFIX}abcd{cache._TMP_SUFFIX}"
    leftover.write_text("partial", encoding="utf-8")
    assert not fnmatch.fnmatch(leftover.name, cache.CACHE_ENTRY_GLOB)

    assert purge(cache_dir, older_than_days=7) == []  # fresh: inside the retention window
    assert purge(cache_dir) == sorted([leftover.name, f"{fingerprint}{cache.CACHE_ENTRY_SUFFIX}"])


def test_purge_on_a_missing_directory_is_not_an_error(tmp_path):
    assert purge(tmp_path / "never-existed") == []


def test_purge_rejects_a_negative_retention_window(tmp_path):
    cache_dir, _, _ = _stored(tmp_path)
    with pytest.raises(CacheError, match=">= 0"):
        purge(cache_dir, older_than_days=-1)
