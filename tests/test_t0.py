"""Synthetic aggregate reports exercise T0 scope; no inference or hardware campaign."""

import json
from pathlib import Path

import pytest
from test_reproduce import _CLEAN, _ENV_F, _ENV_L, _arm, _write

from quantfit.cli import main
from quantfit.reproduce import ReproduceError, compare, within_hardware_identical


def _reports(tmp_path, prefix="rep", *, n=3, env=None):
    return [
        _write(
            tmp_path,
            f"{prefix}{i}.json",
            created_utc=f"2026-10-0{i + 1}T00:00:00+00:00",
            judge_runtime_s=float(i),
            env=env or _ENV_L,
            judge={"id": "judge", "revision": "c" * 40, "input_contract": "completion-only"},
            probe_dataset={"id": "probes", "revision": "d" * 40, "split": "train", "n_probes": 40},
            quantized=_arm(model="org/quant", revision="e" * 40),
        )
        for i in range(n)
    ]


def _edit(path, section, field, value):
    payload = json.loads(Path(path).read_text())
    payload[section][field] = value
    Path(path).write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    "section, field, value",
    [
        ("judge", "revision", "f" * 40),
        ("judge", "input_contract", "prompt-and-completion"),
        ("probe_dataset", "revision", "f" * 40),
        ("probe_dataset", "split", "test"),
        ("decode", "max_new_tokens", 32),
        ("decode", "chat_template", "raw prompt always"),
        ("baseline", "revision", "f" * 40),
        ("quantized", "resolved_dtype", "torch.bfloat16"),
        ("quantized", "engine", {"name": "transformers", "version": "different", "device": "cuda"}),
        ("env", "device", "Tesla T4"),
        ("env", "torch", "different"),
    ],
)
def test_same_counts_cannot_hide_mixed_t0_identity(tmp_path, section, field, value):
    paths = _reports(tmp_path)
    _edit(paths[-1], section, field, value)
    with pytest.raises(ReproduceError, match="identity|environment"):
        within_hardware_identical(paths)


@pytest.mark.parametrize("field, value", [("revision", "main"), ("revision", None)])
def test_equal_unpinned_weights_do_not_establish_t0(tmp_path, field, value):
    paths = _reports(tmp_path)
    for path in paths:
        _edit(path, "baseline", field, value)
    with pytest.raises(ReproduceError, match="identity|pin"):
        within_hardware_identical(paths)


def test_equal_cached_baselines_do_not_establish_t0(tmp_path):
    paths = _reports(tmp_path)
    for path in paths:
        raw = json.loads(Path(path).read_text())
        raw["baseline"]["engine"]["baseline_cache"] = {"served": True, "fingerprint": "f" * 64}
        Path(path).write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReproduceError, match="cached baseline"):
        within_hardware_identical(paths)


@pytest.mark.parametrize(
    "decode",
    [
        {"do_sample": True, "greedy": True},
        {"do_sample": 1, "greedy": True},
        {"do_sample": False, "greedy": 1},
        {"do_sample": False, "temperature": False},
    ],
)
def test_equal_invalid_decode_declarations_cannot_establish_t0(tmp_path, decode):
    paths = _reports(tmp_path)
    for path in paths:
        raw = json.loads(Path(path).read_text())
        raw["decode"].update(decode)
        Path(path).write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReproduceError, match="decode"):
        within_hardware_identical(paths)


def test_new_t0_records_scope_and_does_not_assert_execution_independence(tmp_path):
    result = within_hardware_identical(_reports(tmp_path))
    assert result["pass"] is True
    assert result["measurement_identity"]["judge"]["revision"] == "c" * 40
    assert result["environment_identity"] == _ENV_L
    assert result["independent_execution_verified"] is False
    assert result["protocol_pass"] is True


def test_partial_library_set_is_recorded_without_protocol_pass(tmp_path):
    result = within_hardware_identical(_reports(tmp_path, n=2))
    assert result["pass"] is True
    assert result["meets_protocol_replicate_count"] is False
    assert result["protocol_pass"] is False


def test_t0_copies_are_refused(tmp_path):
    paths = _reports(tmp_path)
    Path(paths[1]).write_bytes(Path(paths[0]).read_bytes())
    with pytest.raises(ReproduceError, match="BYTE-IDENTICAL"):
        within_hardware_identical(paths)


def test_positive_unbound_t0_cannot_license_reproduction(tmp_path):
    left, right = _reports(tmp_path, "left"), _reports(tmp_path, "right", env=_ENV_F)
    for value in (True, {"pass": True, "meets_protocol_replicate_count": True, "n_replicates": 3}):
        result = compare(left[0], right[0], t0_reference=value, t0_candidate=value)
        assert result["outcome"] == "reproduced_t0_unverified"
        assert result["exit_code"] == 3


def test_bound_t0_must_contain_comparison_report_bytes(tmp_path):
    left, right = _reports(tmp_path, "left"), _reports(tmp_path, "right", env=_ENV_F)
    left_t0, right_t0 = within_hardware_identical(left), within_hardware_identical(right)
    assert compare(left[0], right[0], t0_reference=left_t0, t0_candidate=right_t0)["exit_code"] == 0
    other = _reports(tmp_path, "other", env=_ENV_L)
    raw = json.loads(Path(other[0]).read_text())
    raw["created_utc"] = "2026-10-05T12:34:56+00:00"
    Path(other[0]).write_text(json.dumps(raw), encoding="utf-8")
    assert within_hardware_identical(other)["identity_sha256"] == left_t0["identity_sha256"]
    result = compare(other[0], right[0], t0_reference=left_t0, t0_candidate=right_t0)
    assert result["outcome"] == "reproduced_t0_unverified"


def test_t0_source_evidence_is_rechecked_when_consumed(tmp_path):
    left, right = _reports(tmp_path, "left"), _reports(tmp_path, "right", env=_ENV_F)
    left_t0, right_t0 = within_hardware_identical(left), within_hardware_identical(right)
    _edit(left[-1], "judge", "revision", "f" * 40)
    with pytest.raises(ReproduceError, match="identity|changed|hash"):
        compare(left[0], right[0], t0_reference=left_t0, t0_candidate=right_t0)


def test_t0_artifact_cannot_misstate_the_number_of_rechecked_sources(tmp_path):
    left, right = _reports(tmp_path, "left"), _reports(tmp_path, "right", env=_ENV_F)
    left_t0, right_t0 = within_hardware_identical(left), within_hardware_identical(right)
    left_t0["n_replicates"] = 5
    with pytest.raises(ReproduceError, match="n_replicates"):
        compare(left[0], right[0], t0_reference=left_t0, t0_candidate=right_t0)


@pytest.mark.parametrize("n, expected", [(2, 2), (3, 0)])
def test_standalone_t0_cli_minimum_and_json_envelope(tmp_path, capsys, n, expected):
    paths = _reports(tmp_path, n=n)
    out = tmp_path / "t0.json"
    assert main(["t0", "--reports", *paths, "--out", str(out), "--json"]) == expected
    document = json.loads(capsys.readouterr().out)
    assert document["command"] == "t0" and document["exit_code"] == expected
    if n == 3:
        assert json.loads(out.read_text())["protocol_pass"] is True
    else:
        assert not out.exists()


def test_standalone_t0_returns_failed_agreement_without_claiming_a_pass(tmp_path, capsys):
    from test_reproduce import _drift

    paths = _reports(tmp_path)
    raw = json.loads(Path(paths[-1]).read_text())
    raw["drift"] = _drift({**_CLEAN, "clear_safe": (0, 0, 1)})
    Path(paths[-1]).write_text(json.dumps(raw), encoding="utf-8")
    out = tmp_path / "t0.json"
    assert main(["t0", "--reports", *paths, "--out", str(out), "--json"]) == 3
    result = json.loads(capsys.readouterr().out)["result"]
    assert result["pass"] is False and result["protocol_pass"] is False


@pytest.mark.parametrize("artifact_input", [True, False], ids=["standalone-artifact", "existing-report-list"])
def test_reproduce_cli_consumes_bound_t0_artifacts_or_existing_report_lists(tmp_path, capsys, artifact_input):
    left, right = _reports(tmp_path, "left"), _reports(tmp_path, "right", env=_ENV_F)
    inputs = []
    for label, paths in (("reference", left), ("candidate", right)):
        if artifact_input:
            artifact = tmp_path / f"{label}-t0.json"
            within_hardware_identical(paths, out_path=str(artifact))
            inputs.extend([f"--t0-{label}", str(artifact)])
        else:
            inputs.extend([f"--t0-{label}", *paths])
    assert main(["reproduce", "--reference", left[0], "--candidate", right[0], *inputs, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)["result"]
    t0 = result["preconditions"]["T0_within_hardware_byte_identity"]
    assert t0["reference"]["bound_to_comparison_report"] is True
    assert t0["candidate"]["bound_to_comparison_report"] is True


def test_reproduce_cli_legacy_positive_artifact_is_accepted_as_unverified(tmp_path, capsys):
    left, right = _reports(tmp_path, "left"), _reports(tmp_path, "right", env=_ENV_F)
    legacy = tmp_path / "legacy-t0.json"
    legacy.write_text(json.dumps({"pass": True, "meets_protocol_replicate_count": True}), encoding="utf-8")
    assert (
        main(
            [
                "reproduce",
                "--reference",
                left[0],
                "--candidate",
                right[0],
                "--t0-reference",
                str(legacy),
                "--t0-candidate",
                str(legacy),
                "--json",
            ]
        )
        == 3
    )
    assert json.loads(capsys.readouterr().out)["result"]["outcome"] == "reproduced_t0_unverified"
