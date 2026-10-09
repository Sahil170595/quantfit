"""Historical aggregates edited as synthetic fixtures; no new model execution."""

import copy
import hashlib
import io
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantfit.safety import verify
from quantfit.safety.gguf_arm import CPU_OFFLOAD_CONTROLS
from tools import ci_reference_campaign as campaign

SOURCE = (
    Path(__file__).resolve().parents[1] / "validation/2026-08-21-screen-complete/reports/gguf-phi4-mini-unsloth.json"
)


def reports(tmp_path, *, unsafe=12, flips=0):
    payload = json.loads(SOURCE.read_bytes())
    payload["env"] = {
        "python": "synthetic",
        "torch": "synthetic",
        "transformers": "synthetic",
        "cuda": None,
        "device": "cpu",
    }
    payload["judge"]["card_xstest_accuracy_label"] = verify._measured_judge_label()
    zones = {
        "clear_unsafe": {"n": 12, "baseline_refused": unsafe, "quant_refused": unsafe - flips},
        "clear_safe": {"n": 12, "baseline_refused": 0, "quant_refused": 0},
        "borderline": {"n": 16, "baseline_refused": 0, "quant_refused": 0},
    }
    payload["drift"] = verify.SafetyDrift(40, 12, unsafe, unsafe - flips, flips, 28, 0, 0, 0, zones).to_dict()
    for arm in ("baseline", "quantized"):
        payload[arm]["engine"].update(CPU_OFFLOAD_CONTROLS, threads=2)
    paths = []
    for index in range(3):
        item = copy.deepcopy(payload)
        item["created_utc"] = f"2026-10-09T00:00:0{index}+00:00"
        item["judge_runtime_s"] = float(index)
        for arm in ("baseline", "quantized"):
            item[arm]["runtime_s"] = float(index + 1)
        path = tmp_path / f"report-{index}.json"
        path.write_bytes((json.dumps(item) + "\n").encode())
        paths.append(path)
    return paths


def assess(paths):
    binary = json.loads(paths[0].read_bytes())["baseline"]["engine"]["binary_sha256"]
    return campaign.assess_reports(paths, binary_sha256=binary, threads=2)


def edit(path, change):
    value = json.loads(path.read_bytes())
    change(value)
    path.write_bytes((json.dumps(value) + "\n").encode())


def test_full_repeatability_strips_only_four_declared_runtime_fields(tmp_path):
    result = assess(reports(tmp_path))
    assert result["t0"]["protocol_pass"] is True
    assert result["full_report_repeatability"]["pass"] is True
    assert result["eligible_axes_before_publication"] == ["refusal-robustness", "over-refusal"]
    assert result["registry_admission"] == "pending_public_byte_verification"
    assert result["reference_registered"] is False
    assert result["scientific_go"] is False and result["human_labels_authenticated"] is False
    assert result["axes_by_run"][0]["refusal-robustness"]["null_interpretation"] == "the detector did not fire"


def test_exit4_excludes_only_the_unmeasured_axis(tmp_path):
    result = assess(reports(tmp_path, unsafe=0))
    assert result["native_exits"] == [4, 4, 4]
    assert result["eligible_axes_before_publication"] == ["over-refusal"]
    assert result["excluded_axes"] == ["refusal-robustness"]


def test_fresh_flags_keep_registry_blocked_even_when_t0_passes(tmp_path):
    result = assess(reports(tmp_path, flips=1))
    assert result["t0"]["protocol_pass"] is True
    assert result["native_exits"] == [3, 3, 3]
    assert result["eligible_axes_before_publication"] == []
    assert "fresh_flags_without_human_adjudication" in result["blocking_reasons"]


def test_t0_disagreement_preserves_negative_aggregate(tmp_path):
    paths = reports(tmp_path)
    # Replace just drift with another internally valid measured decision.
    other = tmp_path / "other"
    other.mkdir()
    changed = json.loads(reports(other, flips=1)[0].read_bytes())["drift"]
    edit(paths[2], lambda value: value.update(drift=changed))
    result = assess(paths)
    assert result["t0"]["protocol_pass"] is False
    assert result["full_report_repeatability"]["pass"] is False
    assert result["eligible_axes_before_publication"] == []


def test_non_drift_causal_field_is_not_stripped_even_if_t0_ignores_it(tmp_path):
    paths = reports(tmp_path)
    edit(paths[2], lambda value: value["baseline"]["engine"].update(runtime_scope="synthetic extra observation"))
    result = assess(paths)
    assert result["t0"]["protocol_pass"] is True
    assert result["full_report_repeatability"]["pass"] is False
    assert result["full_report_repeatability"]["differing_paths"] == ["/baseline/engine/runtime_scope"]
    assert result["eligible_axes_before_publication"] == []


@pytest.mark.parametrize("field", ["decode", "env", "engine", "hash", "revision", "dtype", "raw", "default"])
def test_invalid_campaign_claims_refuse_before_any_publication(tmp_path, field):
    paths = reports(tmp_path)

    def mutate(value):
        if field == "decode":
            value["decode"]["do_sample"] = True
        elif field == "env":
            value["env"]["device"] = "gpu"
        elif field == "engine":
            value["quantized"]["engine"]["threads"] = 3
        elif field == "hash":
            value["baseline"]["artifact_sha256"] = "a" * 64
        elif field == "revision":
            value["quantized"]["revision"] = "a" * 40
        elif field == "dtype":
            value["baseline"]["resolved_dtype"] = "Q4_K_M"
        elif field == "raw":
            value["drift"]["completion"] = "synthetic raw field must be refused"
        else:
            value["decode"]["max_new_tokens"] = 32

    edit(paths[1], mutate)
    with pytest.raises(RuntimeError):
        assess(paths)


def test_t0_source_substitution_refuses_before_assessment_publication(tmp_path, monkeypatch):
    paths = reports(tmp_path)
    real = campaign.within_hardware_identical

    def substituted(items):
        result = real(items)
        edit(paths[0], lambda value: value.update(created_utc="changed-after-validation"))
        return result

    monkeypatch.setattr(campaign, "within_hardware_identical", substituted)
    with pytest.raises(RuntimeError, match="bytes changed"):
        assess(paths)


def test_duplicate_source_reports_are_not_three_executions(tmp_path):
    paths = reports(tmp_path)
    result = assess([paths[0], paths[0], paths[2]])
    assert result["t0"] is None
    assert "t0_operational_refusal" in result["blocking_reasons"]
    assert result["eligible_axes_before_publication"] == []


def test_public_cold_argv_omits_token_flag_and_has_real_immutable_pins(tmp_path):
    argv = campaign.cold_command(tmp_path)
    assert "--max-new-tokens" not in argv
    assert "--capture" not in argv and "--baseline-cache" not in argv
    assert argv[argv.index("--baseline-revision") + 1] == campaign.PHI4_REVISION
    assert argv[argv.index("--quant-revision") + 1] == campaign.PHI4_REVISION
    assert argv[argv.index("--timeout-seconds") + 1] == "3600"


def test_repeated_reports_hash_actual_consumed_bytes(tmp_path):
    paths = reports(tmp_path)
    result = assess(paths)
    assert [item["sha256"] for item in result["source_reports"]] == [
        hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
    ]


@pytest.mark.parametrize("value", [-1, True, float("inf"), float("nan")])
def test_stripped_runtime_does_not_let_invalid_measurement_through(tmp_path, value):
    paths = reports(tmp_path)
    edit(paths[1], lambda item: item.update(judge_runtime_s=value))
    with pytest.raises(RuntimeError):
        assess(paths)


@pytest.mark.parametrize("key", ["prompt", "completions", "response", "text", "generation", "context_size"])
def test_public_aggregate_boundary_refuses_unknown_raw_fields(tmp_path, key):
    target = tmp_path / "artifact.json"
    with pytest.raises(RuntimeError):
        campaign._write(target, {"nested": {key: "synthetic private text"}})
    assert not target.exists()


def test_failure_receipt_is_narrow_on_unsupported_local_platform(tmp_path, monkeypatch, capsys):
    import os
    import sys

    if os.name == "posix":
        pytest.skip("actual unsupported Windows platform refusal")
    monkeypatch.setattr(sys, "argv", ["campaign", "--out", str(tmp_path / "campaign"), "--wheel", "unused.whl"])
    assert campaign.main() == 2
    out = tmp_path / "campaign/publication"
    assert {p.name for p in out.iterdir()} == {"campaign.json"}
    result = json.loads((out / "campaign.json").read_bytes())
    assert result["status"] == "operational_failure" and result["reference_eligibility"] == "blocked"
    assert result["failure_reason"] == "campaign is POSIX-only" and result["public_files"] == []
    assert json.loads(capsys.readouterr().out)["execution_exit"] == 2


@pytest.mark.parametrize(
    "mode",
    [
        "null",
        "flags",
        "cleanup-failed",
        "raw-receipt",
        "source-changed",
        "interrupt-after-assessment",
        "write-after-assessment",
        "interrupt-after-t0",
        "write-after-t0",
        "interrupt-after-campaign",
        "write-after-campaign",
        "null-interrupt-after-t0",
        "null-write-after-campaign",
        "persistent-after-t0",
        "partial-report",
        "partial-card",
    ],
)
def test_campaign_terminal_staging_is_aggregate_and_fail_closed(tmp_path, monkeypatch, mode):
    """Real campaign control flow, declared fake weights/runtime/CLI observations."""
    from quantfit import cli, cold_run
    from quantfit.backends import gguf as backend
    from quantfit.safety import gguf_arm

    root = tmp_path / "campaign"
    source = tmp_path / "reports"
    source.mkdir()
    fault = "after-" in mode
    flagged = mode == "flags" or fault and not mode.startswith("null-")
    paths = reports(source, flips=1 if flagged else 0)
    binary_sha = json.loads(paths[0].read_bytes())["baseline"]["engine"]["binary_sha256"]
    checked_require = campaign.require
    monkeypatch.setattr(
        campaign,
        "require",
        lambda condition, message: None if message == "campaign is POSIX-only" else checked_require(condition, message),
    )
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            cuda=SimpleNamespace(is_available=lambda: False),
            backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
            set_num_threads=lambda _: None,
        ),
    )
    monkeypatch.setattr(campaign, "_candidate", lambda _: {"scope": "SYNTHETIC candidate observation"})
    monkeypatch.setattr(cold_run, "_resources", lambda _: {"scope": "SYNTHETIC hardware observation"})
    monkeypatch.setattr(gguf_arm, "_threads", lambda: 2)

    def resolve(ref, token, revision):
        expected = next(item for item in campaign.PAIR.values() if item["ref"] == ref)
        return SimpleNamespace(
            sha256=expected["sha256"],
            revision=revision,
            file_type=expected["dtype"],
            path=SimpleNamespace(stat=lambda: SimpleNamespace(st_size=expected["size_bytes"])),
        )

    monkeypatch.setattr(gguf_arm, "_resolve", resolve)
    archive = tmp_path / "synthetic-archive"
    archive.write_bytes(b"not an executable or actual verified archive")
    monkeypatch.setattr(backend, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(backend, "_binary_asset", lambda: archive.name)
    monkeypatch.setattr(backend, "llama_server_bin", lambda: archive)
    monkeypatch.setattr(backend, "_verify_or_die", lambda *_: None)
    monkeypatch.setattr(backend, "_sha256", lambda _: binary_sha)
    monkeypatch.delenv("QUANTFIT_LLAMACPP", raising=False)

    def fake_cli(argv):
        assert "--max-new-tokens" not in argv
        native = Path(argv[argv.index("--out") + 1])
        native.mkdir()
        outputs = []
        for i, path in enumerate(paths, 1):
            directory = native / f"run-{i}"
            directory.mkdir()
            output = directory / "report.json"
            shutil.copyfile(path, output)
            outputs.append(output)
        t0 = campaign.within_hardware_identical([str(path) for path in outputs])
        result = {
            "status": "t0_agreement",
            "requested": {"max_new_tokens": 64},
            "completion_cache_requested": False,
            "t0": t0,
            "runs": [
                {
                    "pid": i + 1000,
                    "native_exit_code": 3 if flagged else 0,
                    "argv": ["--max-new-tokens", "64"],
                    "cleanup": {
                        "direct_child_reaped": True,
                        "no_live_group_members_observed": mode != "cleanup-failed",
                    },
                }
                for i in range(3)
            ],
        }
        (native / "t0.json").write_bytes((json.dumps(t0) + "\n").encode())
        if mode == "raw-receipt":
            result["completion"] = "synthetic private value must never escape"
        if mode == "source-changed":
            edit(outputs[0], lambda value: value.update(created_utc="changed-after-native-t0"))
        print(json.dumps({"result": result}))
        return 0

    monkeypatch.setattr(cli, "main", fake_cli)
    partial = mode in ("partial-report", "partial-card")
    partial_written = []
    if partial:
        real_open = io.open
        write_index = []
        partial_index = 1 if mode == "partial-report" else 2

        class PartialWrite:
            def __init__(self, stream):
                self.stream = stream

            def __getattr__(self, key):
                return getattr(self.stream, key)

            def __enter__(self):
                self.stream.__enter__()
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def write(self, data):
                halfway = data[: len(data) // 2]
                self.stream.write(halfway)
                self.stream.flush()
                partial_written.append(halfway)
                raise OSError("SYNTHETIC partial stream write, no model execution")

        def partial_open(file, mode="r", *args, **kwargs):
            stream = real_open(file, mode, *args, **kwargs)
            if isinstance(file, int):
                return stream
            path = Path(file)
            directory = root / "publication/run-1"
            if "w" in mode and (path == directory or path.parent == directory):
                write_index.append((str(path), mode))
                if len(write_index) == partial_index:
                    return PartialWrite(stream)
            return stream

        monkeypatch.setattr(io, "open", partial_open)
    if fault:
        real_replace = campaign.os.replace
        target = (
            "assessment.json"
            if mode.endswith("assessment")
            else "native-t0.json"
            if mode.endswith("t0")
            else "campaign.json"
        )
        raised = []

        def failed_replace(source, destination):
            path = Path(destination)
            if mode == "persistent-after-t0" and raised and path.is_relative_to(root / "publication"):
                raise OSError("SYNTHETIC persistent storage failure")
            result = real_replace(source, destination)
            if path == root / "publication" / target and not raised:
                raised.append(True)
                if "interrupt" in mode:
                    raise KeyboardInterrupt()
                raise OSError("SYNTHETIC post-write failure, no model execution")
            return result

        monkeypatch.setattr(campaign.os, "replace", failed_replace)
    monkeypatch.setattr(sys, "argv", ["campaign", "--out", str(root), "--wheel", "synthetic-unused.whl"])
    success = mode in ("null", "flags")
    try:
        actual = campaign.main()
    except (Exception, KeyboardInterrupt) as exc:  # noqa: BLE001 - capture this synthetic boundary failure as a test assertion.
        actual = type(exc).__name__
    assert actual == ("OSError" if mode == "persistent-after-t0" else 0 if success else 2)
    public = root / "publication"
    if mode == "persistent-after-t0":
        # No storage is available even for a failure receipt: retain measured
        # aggregates, withhold every earlier positive/pending qualification file.
        assert {p.relative_to(public).as_posix() for p in public.rglob("*") if p.is_file()} == {
            f"run-{i}/{name}" for i in range(1, 4) for name in ("report.json", "model-card.md")
        }
        for index, original in enumerate(paths, 1):
            assert (public / f"run-{index}/report.json").read_bytes() == original.read_bytes()
        assert json.loads((root / "native/t0.json").read_bytes())["protocol_pass"] is True
        return
    value = json.loads((public / "campaign.json").read_bytes())
    assert value["reference_registered"] is False and value["scientific_go"] is False
    assert {p.relative_to(public).as_posix() for p in public.rglob("*") if p.is_file()} <= set(campaign.PUBLIC_FILES)
    if success:
        assert len(value["public_files"]) == 9
        expected = "blocked" if mode == "flags" else "pending_public_byte_verification"
        assert value["reference_eligibility"] == expected
        assert (public / "native-t0.json").is_file()
        for index, original in enumerate(paths, 1):
            assert (public / f"run-{index}/report.json").read_bytes() == original.read_bytes()
    else:
        assert value["status"] == "operational_failure" and value["reference_eligibility"] == "blocked"
        assert not (public / "native-t0.json").exists()
        if fault or partial:
            assessment = json.loads((public / "assessment.json").read_bytes())
            assert (
                assessment["registry_admission"] == "blocked" and assessment["eligible_axes_before_publication"] == []
            )
            assert assessment["t0"] is None and assessment["campaign_execution_complete"] is False
            assert "campaign_terminal_failure" in assessment["blocking_reasons"]
            native = json.loads((public / "native-cold-run.json").read_bytes())
            assert native["publication_qualification"] is False and native["campaign_execution_complete"] is False
            assert (
                native["t0"]["protocol_pass"] is True
            )  # Preserve the genuine original observation, with nonqualification explicit.
            if partial:
                assert len(partial_written) == 1
                assert not (public / "run-1/model-card.md").exists()
                if mode == "partial-report":
                    assert not (public / "run-1/report.json").exists(), write_index
                else:
                    assert (public / "run-1/report.json").read_bytes() == paths[0].read_bytes()
                assert all(not (public / f"run-{i}").exists() for i in (2, 3))
                assert json.loads((root / "native/t0.json").read_bytes())["protocol_pass"] is True
            for i, original in enumerate(paths, 1):
                if not partial:
                    assert (public / f"run-{i}/report.json").read_bytes() == original.read_bytes()
                assert assessment["axes_by_run"][i - 1]["refusal-robustness"]["flagged_flips"] == int(flagged)
        else:
            assert not (public / "assessment.json").exists()
            assert all(not (public / f"run-{i}").exists() for i in range(1, 4))
        assert b"synthetic private value" not in (public / "campaign.json").read_bytes()
