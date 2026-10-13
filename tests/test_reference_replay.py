"""Frozen replay guards and receiving receipts; no model execution in these controls."""

import hashlib
import json
from pathlib import Path

import pytest
from test_reference_assessment import target_declaration
from test_reproduce_bundles import make_bundle

from quantfit.bundle import create_replay_bundle
from quantfit.reproduce import within_hardware_identical
from quantfit.safety import gguf_arm
from quantfit.safety.verify import SafetyDrift


def setup_recipe(tmp_path, monkeypatch, *, negative=None):
    _, reports, _ = make_bundle(tmp_path, "seed", flips=int(negative == "flags"), disagreement=negative == "t0")
    declaration = target_declaration()
    weights = {}
    resolved = {}
    server = tmp_path / "llama-server"
    server.write_bytes(b"explicit synthetic executable")
    declaration["engine"].update(binary_sha256=hashlib.sha256(server.read_bytes()).hexdigest(), threads=2)
    for name in ("baseline", "quantized"):
        path = tmp_path / f"{name}.gguf"
        path.write_bytes(f"explicit synthetic {name} asset".encode())
        weights[name] = str(path)
        arm = declaration["arms"][name]
        arm.update(model=str(path), revision=None, size_bytes=path.stat().st_size)
        arm["artifact_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        resolved[name] = gguf_arm.ResolvedGguf(
            str(path), path, None, arm["artifact_sha256"], "llama", arm["resolved_dtype"], False, None
        )
    for path in reports:
        value = json.loads(Path(path).read_bytes())
        for name in ("baseline", "quantized"):
            value[name].update({k: v for k, v in declaration["arms"][name].items() if k != "size_bytes"})
            value[name]["engine"].update(declaration["engine"])
        Path(path).write_text(json.dumps(value), encoding="utf-8")
    t0 = tmp_path / "original-t0.json"
    within_hardware_identical(reports, out_path=str(t0))
    bundle = tmp_path / "original"
    create_replay_bundle(reports, str(t0), str(bundle))
    target = tmp_path / "target.json"
    target.write_text(json.dumps(declaration), encoding="utf-8")
    monkeypatch.setattr(gguf_arm, "resolve_pair", lambda *a, **kw: (resolved["baseline"], resolved["quantized"]))
    monkeypatch.setattr(gguf_arm, "llama_server_bin", lambda: server)
    import quantfit.reference_replay as replay

    monkeypatch.setattr(replay, "llama_server_bin", lambda: server)
    monkeypatch.setattr(gguf_arm, "_threads", lambda: 2)
    return bundle, target, declaration, resolved, server


@pytest.mark.parametrize("asset", ["weight", "executable"])
def test_guard_rejects_substitution_before_any_server_starts(tmp_path, monkeypatch, asset):
    from quantfit.reference_replay import _load_execution_guard

    _, _, declaration, resolved, server = setup_recipe(tmp_path, monkeypatch)
    recipe = {
        "target": declaration,
        "weights": {k: str(v.path) for k, v in resolved.items()},
        "executable": str(server),
    }
    path = tmp_path / "recipe.json"
    raw = json.dumps(recipe).encode()
    path.write_bytes(raw)
    guard = _load_execution_guard(str(path), hashlib.sha256(raw).hexdigest())
    changed = resolved["baseline"].path if asset == "weight" else server
    changed.write_bytes(b"substituted")
    spawned = []
    monkeypatch.setattr(gguf_arm.subprocess, "Popen", lambda *a, **kw: spawned.append(a))
    with pytest.raises(RuntimeError, match="execution_recipe_mismatch"):
        gguf_arm.generate_completions(resolved["baseline"], [], 64, _execution_guard=guard)
    assert spawned == []


@pytest.mark.parametrize("timeout", [True, 0, -1, float("nan"), float("inf"), 3601])
def test_invalid_deadline_never_resolves_or_creates_output(tmp_path, monkeypatch, timeout):
    from quantfit.reference_replay import rerun_candidate

    monkeypatch.setattr(gguf_arm, "resolve_pair", lambda *a, **kw: pytest.fail("resolved"))
    output = tmp_path / "new"
    result = rerun_candidate("missing", "missing", str(output), timeout_seconds=timeout)
    assert result["exit_code"] == 2 and result["reference_replay_schema_version"] == 1
    assert not output.exists()


def mock_lifecycle(bundle, monkeypatch, mode="clean"):
    import quantfit.reference_replay as replay

    monkeypatch.setattr(replay, "_runner_supported", lambda: True)

    def run(base, quant, out, **kwargs):
        root = Path(out)
        root.mkdir()
        runs, paths = [], []
        for index in range(1, 4):
            value = json.loads((bundle / f"report-{index}.json").read_bytes())
            if mode != "duplicate":
                value["created_utc"] = f"explicit synthetic fresh run {index}"
            count = int(mode == "breach" or (mode == "disagree" and index == 3))
            unsafe = 0 if mode == "unmeasured" else 12
            zones = {
                "clear_unsafe": {"n": 12, "baseline_refused": unsafe, "quant_refused": unsafe - count},
                "clear_safe": {"n": 12, "baseline_refused": 0, "quant_refused": 0},
                "borderline": {"n": 16, "baseline_refused": 0, "quant_refused": 0},
            }
            value["drift"] = SafetyDrift(40, 12, unsafe, unsafe - count, count, 28, 0, 0, 0, zones).to_dict()
            if mode == "full-disagree" and index == 3:
                value["baseline"]["engine"]["runtime_s"] = 7
            folder = root / f"run-{index}"
            folder.mkdir()
            path = folder / "report.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            paths.append(str(path))
            observed = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            runs.append(
                {
                    "status": "completed",
                    "report": observed,
                    "final_report": dict(observed),
                    "native_exit_code": 3 if count else 4 if unsafe == 0 else 0,
                    "cleanup": {"direct_child_reaped": True, "no_live_group_members_observed": mode != "cleanup"},
                }
            )
        t0 = within_hardware_identical(paths, out_path=str(root / "t0.json"))
        receipt = {"cold_run_schema_version": 1, "exit_code": 0 if t0["protocol_pass"] else 3, "runs": runs, "t0": t0}
        if mode in ("timeout", "cancel"):
            receipt.update(exit_code=2, t0=None)
            (root / "t0.json").unlink()
            runs[0]["status"] = mode
            (root / "cold-run.json").write_text(json.dumps(receipt), encoding="utf-8")
            if mode == "cancel":
                raise KeyboardInterrupt()
        if mode == "source-substitution":
            value["created_utc"] = "after observed report"
            Path(paths[-1]).write_text(json.dumps(value), encoding="utf-8")
        return receipt

    monkeypatch.setattr(replay, "cold_run", run)
    return replay


@pytest.mark.parametrize(
    "mode,code",
    [
        ("clean", 0),
        ("breach", 3),
        ("unmeasured", 4),
        ("disagree", 3),
        ("full-disagree", 3),
        ("cleanup", 2),
        ("timeout", 2),
        ("cancel", 2),
        ("source-substitution", 2),
    ],
)
def test_complete_and_negative_receipts_keep_native_outcomes(tmp_path, monkeypatch, mode, code):
    bundle, target, _, _, _ = setup_recipe(tmp_path, monkeypatch)
    replay = mock_lifecycle(bundle, monkeypatch, mode)
    originals = {p: p.read_bytes() for p in bundle.iterdir()}
    result = replay.rerun_candidate(str(bundle), str(target), str(tmp_path / "rerun"), timeout_seconds=10)
    assert result["exit_code"] == code, result
    assert result["reference_assessment"]["exit_code"] == 4
    assert result["original_native_exits"] == [0, 0, 0]
    assert result["cold_run"] is not None and len(result["fresh_native_exits"]) == 3
    assert all(path.read_bytes() == raw for path, raw in originals.items())
    assert result["scientific_go"] is result["independent_execution_verified"] is False
    if mode != "source-substitution":
        root = tmp_path / "rerun"
        manifest = json.loads((root / "manifest.json").read_bytes())
        assert manifest["exit_code"] == code
        assert {row["path"] for row in manifest["files"]} == {
            p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
        } - {"manifest.json"}
        for row in manifest["files"]:
            raw = (root / row["path"]).read_bytes()
            assert row["sha256"] == hashlib.sha256(raw).hexdigest() and row["size_bytes"] == len(raw)
        if code == 2:
            assert result["comparison"] is None and not (root / "fresh/manifest.json").exists()


@pytest.mark.parametrize("field,value", [("revision", "main"), ("size_bytes", None), ("resolved_dtype", "Q4_K_M")])
def test_unenforceable_recipe_refuses_before_resolution(tmp_path, monkeypatch, field, value):
    bundle, target, declaration, _, _ = setup_recipe(tmp_path, monkeypatch)
    import quantfit.reference_replay as replay

    monkeypatch.setattr(replay, "_runner_supported", lambda: True)
    declaration["arms"]["baseline"][field] = value
    target.write_text(json.dumps(declaration), encoding="utf-8")
    monkeypatch.setattr(gguf_arm, "resolve_pair", lambda *a, **kw: pytest.fail("resolved"))
    result = replay.rerun_candidate(str(bundle), str(target), str(tmp_path / "new"))
    assert result["exit_code"] == 2 and not (tmp_path / "new").exists()


def test_held_inputs_are_consumed_once_and_never_reopened(tmp_path, monkeypatch):
    bundle, target, _, _, _ = setup_recipe(tmp_path, monkeypatch)
    replay = mock_lifecycle(bundle, monkeypatch)
    verify = replay._verified_bundle
    calls = []

    def held(path):
        calls.append(path)
        result = verify(path)
        # The original root remains protected, but its report bytes no longer exist.
        for member in bundle.iterdir():
            member.unlink()
        return result

    monkeypatch.setattr(replay, "_verified_bundle", held)
    # Fresh synthetic children use retained independent buffers, just as a native child would.
    raw = {i: (bundle / f"report-{i}.json").read_bytes() for i in range(1, 4)}
    original_read = Path.read_bytes

    def only_mock_children(path):
        if path.parent == bundle:
            return raw[int(path.stem[-1])]
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", only_mock_children)
    result = replay.rerun_candidate(str(bundle), str(target), str(tmp_path / "new"))
    assert result["exit_code"] == 0 and calls == [str(bundle)]


def test_operational_diagnostics_are_bounded(tmp_path, monkeypatch):
    bundle, target, _, _, _ = setup_recipe(tmp_path, monkeypatch)
    replay = mock_lifecycle(bundle, monkeypatch)

    def fail(*a, **kw):
        raise RuntimeError("PRIVATE provider response and secret local path")

    monkeypatch.setattr(replay, "cold_run", fail)
    result = replay.rerun_candidate(str(bundle), str(target), str(tmp_path / "new"))
    assert result["exit_code"] == 2 and "PRIVATE" not in json.dumps(result)


def test_conflicting_identical_refs_refuse_before_resolution_or_generation(tmp_path, monkeypatch):
    bundle, target, declaration, resolved, _ = setup_recipe(tmp_path, monkeypatch)
    replay = mock_lifecycle(bundle, monkeypatch)
    declaration["arms"]["quantized"]["model"] = declaration["arms"]["baseline"]["model"]
    target.write_text(json.dumps(declaration), encoding="utf-8")
    calls = []

    def resolve(*args, **kwargs):
        calls.append("resolve")
        return resolved["baseline"], resolved["baseline"]

    def native(*args, **kwargs):
        calls.append("native")

    monkeypatch.setattr(gguf_arm, "resolve_pair", resolve)
    monkeypatch.setattr(replay, "cold_run", native)
    result = replay.rerun_candidate(str(bundle), str(target), str(tmp_path / "new"))
    assert result["exit_code"] == 2 and calls == [] and not (tmp_path / "new").exists()


def test_identical_consistent_full_precision_guard_remains_valid(tmp_path, monkeypatch):
    _, _, declaration, resolved, server = setup_recipe(tmp_path, monkeypatch)
    import quantfit.reference_replay as replay

    declaration["arms"]["quantized"] = dict(declaration["arms"]["baseline"])
    recipe = {
        "target": declaration,
        "weights": {name: str(resolved["baseline"].path) for name in resolved},
        "executable": str(server),
    }
    guard = replay._recipe_guard(recipe)
    guard(resolved["baseline"], server, 2)


@pytest.mark.parametrize("fault", ["manifest", "partial", "promote", "held-member-substitution"])
def test_publication_fault_cannot_advertise_success(tmp_path, monkeypatch, fault):
    bundle, target, _, _, _ = setup_recipe(tmp_path, monkeypatch)
    replay = mock_lifecycle(bundle, monkeypatch)
    write = replay._write_member

    def broken(path, raw):
        if path.parent.name.startswith(".quantfit-replay-") and path.name == "manifest.json":
            if fault == "manifest":
                raise OSError("PRIVATE disk diagnostics")
            if fault == "held-member-substitution":
                (path.parent / "comparison.json").write_bytes(b"substituted")
        if fault == "partial" and path.name == "reference-assessment.json":
            path.write_bytes(raw[:3])
            raise OSError("PRIVATE partial diagnostics")
        write(path, raw)

    monkeypatch.setattr(replay, "_write_member", broken)
    if fault == "promote":

        def no_publish(*args):
            raise OSError("PRIVATE promotion diagnostics")

        monkeypatch.setattr(replay, "_promoter", lambda: no_publish)
    output = tmp_path / "new"
    result = replay.rerun_candidate(str(bundle), str(target), str(output))
    assert result["exit_code"] == 2 and not output.exists() and "PRIVATE" not in json.dumps(result)
    assert not list(tmp_path.glob(".quantfit-replay-*"))


@pytest.mark.parametrize("alias", ["bundle", "target", "weight", "executable"])
def test_receiving_output_preserves_consumed_sources(tmp_path, monkeypatch, alias):
    bundle, target, _, resolved, server = setup_recipe(tmp_path, monkeypatch)
    replay = mock_lifecycle(bundle, monkeypatch)
    path = {"bundle": bundle / "new", "target": target, "weight": resolved["baseline"].path, "executable": server}[
        alias
    ]
    originals = {p: p.read_bytes() for p in [target, server, *[a.path for a in resolved.values()], *bundle.iterdir()]}
    monkeypatch.setattr(replay, "cold_run", lambda *a, **kw: pytest.fail("native started"))
    result = replay.rerun_candidate(str(bundle), str(target), str(path))
    assert result["exit_code"] == 2 and all(p.read_bytes() == raw for p, raw in originals.items())


def test_hf_moving_or_null_revision_never_reaches_resolver(tmp_path, monkeypatch):
    bundle, target, declaration, _, _ = setup_recipe(tmp_path, monkeypatch)
    replay = mock_lifecycle(bundle, monkeypatch)
    declaration["arms"]["baseline"].update(model="hf:synthetic/repo/base.gguf", revision=None)
    target.write_text(json.dumps(declaration), encoding="utf-8")
    monkeypatch.setattr(gguf_arm, "resolve_pair", lambda *a, **kw: pytest.fail("resolved moving ref"))
    result = replay.rerun_candidate(str(bundle), str(target), str(tmp_path / "new"))
    assert result["exit_code"] == 2 and not (tmp_path / "new").exists()


@pytest.mark.parametrize("field,change", [("threads", 3), ("binary_sha256", "f" * 64)])
def test_guard_controls_match_applied_native_facts(tmp_path, monkeypatch, field, change):
    _, _, declaration, resolved, server = setup_recipe(tmp_path, monkeypatch)
    import quantfit.reference_replay as replay

    declaration["engine"][field] = change
    guard = replay._recipe_guard(
        {"target": declaration, "weights": {k: str(v.path) for k, v in resolved.items()}, "executable": str(server)}
    )
    with pytest.raises(RuntimeError, match="execution_recipe_mismatch"):
        guard(resolved["baseline"], server, 2)


def test_original_target_identity_mismatch_refuses_before_resolution(tmp_path, monkeypatch):
    bundle, target, declaration, resolved, _ = setup_recipe(tmp_path, monkeypatch)
    replay = mock_lifecycle(bundle, monkeypatch)
    declaration["arms"]["baseline"]["artifact_sha256"] = "f" * 64
    target.write_text(json.dumps(declaration), encoding="utf-8")
    calls = []

    def resolve(*args, **kwargs):
        calls.append("resolve")
        return resolved["baseline"], resolved["quantized"]

    monkeypatch.setattr(gguf_arm, "resolve_pair", resolve)
    result = replay.rerun_candidate(str(bundle), str(target), str(tmp_path / "new"))
    assert result["exit_code"] == 2 and calls == []
    assert result["reference_assessment"]["criteria"]["run-1.arms.baseline.artifact_sha256"]["pass"] is False


@pytest.mark.parametrize("negative,code", [("flags", 3), ("t0", 4)])
def test_original_valid_negatives_and_local_unknown_lineage_remain_rerunnable(tmp_path, monkeypatch, negative, code):
    bundle, target, _, _, _ = setup_recipe(tmp_path, monkeypatch, negative=negative)
    replay = mock_lifecycle(bundle, monkeypatch)
    result = replay.rerun_candidate(str(bundle), str(target), str(tmp_path / "new"))
    assert result["exit_code"] == code and result["cold_run"] is not None
    assert result["reference_assessment"]["exit_code"] == 3
    assert "target_facts_unestablished" in result["reference_assessment"]["unknown_reasons"]


def test_private_recipe_flags_are_not_the_public_documented_surface():
    from quantfit.audit import _parser_surface
    from quantfit.cli import _build_parser

    options = _parser_surface()["verify-safety"]["options"]
    assert "--_execution-recipe" not in options and "--_execution-recipe-sha256" not in options
    assert "--max-new-tokens" in options and "--baseline-revision" in options
    parser = _build_parser()
    args = parser.parse_args(
        [
            "verify-safety",
            "--baseline",
            "b.gguf",
            "--quant",
            "q.gguf",
            "--_execution-recipe",
            "recipe.json",
            "--_execution-recipe-sha256",
            "a" * 64,
        ]
    )
    assert args._execution_recipe == "recipe.json"


def test_cli_operational_envelope_keeps_bounded_replay_schema(tmp_path, capsys):
    from quantfit.cli import main

    code = main(
        [
            "evidence",
            "rerun",
            "--bundle",
            "missing",
            "--target",
            "missing",
            "--out",
            str(tmp_path / "new"),
            "--timeout-seconds",
            "0",
            "--json",
        ]
    )
    envelope = json.loads(capsys.readouterr().out)
    assert code == envelope["exit_code"] == 2 and envelope["command"] == "evidence rerun"
    assert envelope["result"]["reference_replay_schema_version"] == 1 and envelope["result"]["comparison"] is None


def test_recipe_is_held_once_and_cannot_be_substituted_after_loading(tmp_path, monkeypatch):
    _, _, declaration, resolved, server = setup_recipe(tmp_path, monkeypatch)
    import quantfit.reference_replay as replay

    recipe = {
        "target": declaration,
        "weights": {k: str(v.path) for k, v in resolved.items()},
        "executable": str(server),
    }
    path = tmp_path / "recipe.json"
    raw = json.dumps(recipe).encode()
    path.write_bytes(raw)
    guard = replay._load_execution_guard(str(path), hashlib.sha256(raw).hexdigest())
    path.write_bytes(b"PRIVATE corrupt recipe")
    guard(resolved["baseline"], server, 2)
    with pytest.raises(RuntimeError, match="execution_recipe_mismatch"):
        replay._load_execution_guard(str(path), hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize("max_tokens", [63, 65, True, 64.0])
def test_guarded_native_decode_refuses_before_any_probe_or_model_load(monkeypatch, max_tokens):
    from quantfit.safety import verify

    monkeypatch.setattr(verify, "_load_probes", lambda *a: pytest.fail("probes loaded"))
    with pytest.raises(RuntimeError, match="execution_recipe_mismatch"):
        verify.verify_safety("b.gguf", "q.gguf", max_new_tokens=max_tokens, _execution_guard=lambda *a: None)


def test_guarded_arm_decode_refuses_before_executable_or_port_resolution(tmp_path, monkeypatch):
    _, _, _, resolved, _ = setup_recipe(tmp_path, monkeypatch)
    monkeypatch.setattr(gguf_arm, "llama_server_bin", lambda: pytest.fail("executable resolved"))
    with pytest.raises(RuntimeError, match="execution_recipe_mismatch"):
        gguf_arm.generate_completions(resolved["baseline"], [], 64.0, _execution_guard=lambda *a: None)


def test_supported_hf_snapshot_symlinks_bind_canonical_blobs(tmp_path, monkeypatch):
    _, _, declaration, resolved, server = setup_recipe(tmp_path, monkeypatch)
    import quantfit.reference_replay as replay

    snapshot = tmp_path / "snapshots" / ("a" * 40)
    snapshot.mkdir(parents=True)
    link = snapshot / "base.gguf"
    try:
        link.symlink_to(resolved["baseline"].path)
    except OSError:
        pytest.skip("creating symlinks requires platform support")
    declaration["arms"]["baseline"].update(model="hf:synthetic/repo/base.gguf", revision="a" * 40)
    arm = gguf_arm.ResolvedGguf(
        declaration["arms"]["baseline"]["model"],
        link,
        "a" * 40,
        resolved["baseline"].sha256,
        "llama",
        "BF16",
        False,
        None,
    )
    guard = replay._recipe_guard(
        {"target": declaration, "weights": {k: str(v.path) for k, v in resolved.items()}, "executable": str(server)}
    )
    guard(arm, server, 2)


def test_native_spawn_failure_closes_owned_log_descriptor_and_path(tmp_path, monkeypatch):
    import os

    _, _, _, resolved, _ = setup_recipe(tmp_path, monkeypatch)
    create = gguf_arm.tempfile.mkstemp
    created = []

    def own_log(**kwargs):
        fd, path = create(dir=tmp_path, **kwargs)
        created.append((fd, Path(path)))
        return fd, path

    def fail(*args, **kwargs):
        raise OSError("explicit synthetic spawn failure")

    monkeypatch.setattr(gguf_arm.tempfile, "mkstemp", own_log)
    monkeypatch.setattr(gguf_arm, "_free_port", lambda: 1)
    monkeypatch.setattr(gguf_arm.subprocess, "Popen", fail)
    with pytest.raises(OSError, match="spawn failure"):
        gguf_arm.generate_completions(resolved["baseline"], [], 64)
    assert len(created) == 1
    fd, path = created[0]
    try:
        with pytest.raises(OSError):
            os.fstat(fd)
        assert not path.exists()
    finally:
        # Close the deliberately exposed pre-fix leak so the RED control owns no open FD.
        try:
            os.close(fd)
        except OSError:
            pass


def test_publication_cancellation_closes_stage_and_returns_negative_receipt(tmp_path, monkeypatch):
    bundle, target, _, _, _ = setup_recipe(tmp_path, monkeypatch)
    replay = mock_lifecycle(bundle, monkeypatch)
    write = replay._write_member

    def interrupt(path, raw):
        if path.name == "reference-assessment.json":
            raise KeyboardInterrupt()
        write(path, raw)

    monkeypatch.setattr(replay, "_write_member", interrupt)
    escaped = False
    try:
        result = replay.rerun_candidate(str(bundle), str(target), str(tmp_path / "new"))
    except KeyboardInterrupt:
        escaped = True
        result = {}
    assert not escaped and result["exit_code"] == 2 and result["cold_run"] is not None
    assert not (tmp_path / "new").exists() and not list(tmp_path.glob(".quantfit-replay-*"))


@pytest.mark.parametrize("cancel", [False, True])
def test_post_promotion_failure_revokes_only_owned_advertisement(tmp_path, monkeypatch, cancel):
    bundle, target, _, _, _ = setup_recipe(tmp_path, monkeypatch)
    replay = mock_lifecycle(bundle, monkeypatch)
    promote = replay._promoter()

    def fail_after(source, destination):
        promote(source, destination)
        if cancel:
            raise KeyboardInterrupt()
        raise OSError("explicit synthetic failure after rename")

    monkeypatch.setattr(replay, "_promoter", lambda: fail_after)
    output = tmp_path / "new"
    result = replay.rerun_candidate(str(bundle), str(target), str(output))
    assert result["exit_code"] == 2 and not output.exists() and not list(tmp_path.glob(".quantfit-replay-*"))


def test_promotion_refusal_preserves_foreign_destination(tmp_path, monkeypatch):
    bundle, target, _, _, _ = setup_recipe(tmp_path, monkeypatch)
    replay = mock_lifecycle(bundle, monkeypatch)

    def foreign(source, destination):
        destination.mkdir()
        (destination / "foreign.txt").write_bytes(b"foreign content")
        raise OSError("exclusive promotion refused")

    monkeypatch.setattr(replay, "_promoter", lambda: foreign)
    output = tmp_path / "new"
    result = replay.rerun_candidate(str(bundle), str(target), str(output))
    assert result["exit_code"] == 2 and (output / "foreign.txt").read_bytes() == b"foreign content"
    assert not list(tmp_path.glob(".quantfit-replay-*"))
