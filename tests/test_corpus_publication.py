import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_corpus_calibration import gguf_runtime
from test_corpus_gate import alternative
from test_gguf_arm import F16, Q4_K_M, _write_gguf
from test_probe_corpus import rows

from quantfit import gate
from quantfit.safety import gguf_arm
from quantfit.screen import run_screen

R = Path(__file__).resolve().parents[1]
pytest_plugins = ["test_probe_corpus"]


@pytest.mark.parametrize(
    "case",
    [
        "gate_valid",
        "screen_valid",
        "gate_out_base",
        "gate_report_quant",
        "gate_out_quant_hardlink",
        "screen_junit_late_base",
        "screen_junit_late_quant_hardlink",
    ],
)
def test_known_local_model_roles(sdk, monkeypatch, tmp_path, case):
    source = alternative(sdk)
    sdk["rows"] = rows(30)
    real_resolve = gguf_arm.resolve_pair
    calls = gguf_runtime(monkeypatch)
    monkeypatch.setattr(gguf_arm, "resolve_pair", real_resolve)
    base = _write_gguf(tmp_path / "base.GGUF", file_type=F16, chat_template="controlled")
    quant = _write_gguf(tmp_path / "quant.gguf", file_type=Q4_K_M, chat_template="controlled")
    late_base = _write_gguf(
        tmp_path / "late-base.gguf", file_type=F16, chat_template="controlled", name="distinct late baseline"
    )
    late_quant = _write_gguf(
        tmp_path / "late-quant.gguf", file_type=Q4_K_M, chat_template="controlled", name="distinct late quant"
    )
    models = (base, quant, late_base, late_quant)
    before = {p.name: p.read_bytes() for p in models}
    for p in models:
        (tmp_path / (p.name + ".before.bin")).write_bytes(before[p.name])
    assert gguf_arm._read_meta(base)["file_type"] == "F16"
    output = tmp_path / "decision.json"
    report = tmp_path / "native.json"
    junit = tmp_path / "junit.xml"
    if case == "gate_out_base":
        output = base
    if case == "gate_report_quant":
        report = quant
    if case == "gate_out_quant_hardlink":
        output = tmp_path / "alias.json"
        os.link(quant, output)
    if case == "screen_junit_late_base":
        junit = late_base
    if case == "screen_junit_late_quant_hardlink":
        junit = tmp_path / "alias.xml"
        os.link(late_quant, junit)
    manifest = tmp_path / "targets.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "native local roles",
                "targets": [
                    {"name": "first", "stratum": "gguf", "baseline": str(base), "quant": str(quant)},
                    {"name": "last", "stratum": "gguf", "baseline": str(late_base), "quant": str(late_quant)},
                ],
            }
        )
    )
    error = None
    result = None
    try:
        if case.startswith("gate_"):
            result = gate.run_gate(
                str(base), str(quant), threshold=0.3, probe_corpus=source, report_path=str(report), out_path=str(output)
            )
        else:
            result = run_screen(str(manifest), str(tmp_path / "reports"), probe_corpus=source, junit_path=str(junit))
    except RuntimeError as exc:
        error = str(exc)
    finally:
        for p in models:
            (tmp_path / (p.name + ".after.bin")).write_bytes(p.read_bytes())
        (tmp_path / "facts.json").write_text(
            json.dumps(
                {
                    "case": case,
                    "error": error,
                    "sdk_loads": len(sdk["loads"]),
                    "controlled_model_calls": len(calls),
                    "model_bytes_held": all(p.read_bytes() == before[p.name] for p in models),
                    "native_exit": result.get("exit_code") if result else None,
                }
            )
        )
    if case.endswith("valid"):
        assert error is None and len(sdk["loads"]) == 1 and calls
    else:
        assert error is not None, "known local model publication alias was accepted"
        assert not sdk["loads"] and not calls, "known alias reached source/model"
    assert all(p.read_bytes() == before[p.name] for p in models)


@pytest.mark.parametrize("case", ["valid", "directory", "parent_file"])
def test_actual_cli_junit_roles(tmp_path, case):
    work = tmp_path
    report = work / "native.json"
    out = work / "gate.json"
    junit = work / "gate.xml"
    events = work / "events.jsonl"
    if case == "directory":
        junit.mkdir()
    if case == "parent_file":
        junit.write_bytes(b"held")
        junit = junit / "child.xml"
    argv = [
        sys.executable,
        "-B",
        "-X",
        "utf8",
        "-m",
        "quantfit.cli",
        "gate",
        "--baseline",
        "controlled/base1",
        "--quant",
        "controlled/quant1",
        "--threshold",
        "30",
        "--probe-dataset",
        "controlled/alternative",
        "--probe-revision",
        "d" * 40,
        "--probe-split",
        "validation",
        "--report",
        str(report),
        "--out",
        str(out),
        "--junit",
        str(junit),
        "--json",
    ]
    child = subprocess.Popen(
        argv,
        cwd=work,
        env=dict(
            os.environ,
            PYTHONPATH=str(R / "tools/ci_corpus_fixture"),
            PYTHONDONTWRITEBYTECODE="1",
            QUANTFIT_CORPUS_CI="1",
            QUANTFIT_CORPUS_CI_CASE="0",
            QUANTFIT_CORPUS_CI_LOG=str(events),
            HF_HUB_OFFLINE="1",
            HF_DATASETS_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = child.communicate()
    (work / "stdout.log").write_bytes(stdout)
    (work / "stderr.log").write_bytes(stderr)
    (work / "facts.json").write_text(
        json.dumps(
            {
                "argv": argv,
                "pid": child.pid,
                "native_exit": child.returncode,
                "joined": True,
                "report_published": report.exists(),
                "out_published": out.exists(),
                "source_events": events.read_text() if events.exists() else None,
            }
        )
    )
    if case == "valid":
        assert child.returncode == 0 and report.is_file() and out.is_file() and junit.is_file()
    else:
        assert child.returncode == 2
        assert not events.exists() and not report.exists() and not out.exists(), (
            "invalid JUnit role caused native contact/publication"
        )


@pytest.mark.parametrize("sink", ["out", "report", "junit"])
def test_cli_known_local_alias_without_any_model_execution(tmp_path, sink):
    base = _write_gguf(tmp_path / "base.GGUF", file_type=F16)
    quant = _write_gguf(tmp_path / "quant.gguf", file_type=Q4_K_M)
    before = base.read_bytes()
    (tmp_path / "model.before.bin").write_bytes(before)
    paths = {"out": tmp_path / "gate.json", "report": tmp_path / "native.json", "junit": tmp_path / "gate.xml"}
    paths[sink] = base
    events = tmp_path / "events.jsonl"
    argv = [
        sys.executable,
        "-B",
        "-X",
        "utf8",
        "-m",
        "quantfit.cli",
        "gate",
        "--baseline",
        str(base),
        "--quant",
        str(quant),
        "--threshold",
        "30",
        "--probe-dataset",
        "controlled/alternative",
        "--probe-revision",
        "d" * 40,
        "--probe-split",
        "validation",
        *[v for k, p in paths.items() for v in ("--" + k, str(p))],
        "--json",
    ]
    child = subprocess.Popen(
        argv,
        cwd=tmp_path,
        env=dict(
            os.environ,
            PYTHONPATH=str(R / "tools/ci_corpus_fixture"),
            PYTHONDONTWRITEBYTECODE="1",
            QUANTFIT_CORPUS_CI="1",
            QUANTFIT_CORPUS_CI_N="6",
            QUANTFIT_CORPUS_CI_LOG=str(events),
            HF_HUB_OFFLINE="1",
            HF_DATASETS_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = child.communicate()
    (tmp_path / "stdout.log").write_bytes(stdout)
    (tmp_path / "stderr.log").write_bytes(stderr)
    (tmp_path / "model.after.bin").write_bytes(base.read_bytes())
    (tmp_path / "facts.json").write_text(
        json.dumps(
            {
                "argv": argv,
                "pid": child.pid,
                "native_exit": child.returncode,
                "joined": True,
                "model_bytes_held": before == base.read_bytes(),
                "source_events": events.read_text() if events.exists() else None,
            }
        )
    )
    assert child.returncode == 2 and not events.exists() and base.read_bytes() == before


@pytest.mark.parametrize("aliased", [False, True])
def test_valid_native_model_symlink_label_and_resolved_target_alias(sdk, monkeypatch, tmp_path, aliased):
    source = alternative(sdk)
    sdk["rows"] = rows(30)
    real = gguf_arm.resolve_pair
    calls = gguf_runtime(monkeypatch)
    monkeypatch.setattr(gguf_arm, "resolve_pair", real)
    base = _write_gguf(tmp_path / "base.GGUF", file_type=F16)
    quant = _write_gguf(tmp_path / "quant.gguf", file_type=Q4_K_M)
    link = tmp_path / "baseline-link.GGUF"
    try:
        link.symlink_to(base)
    except OSError as exc:
        (tmp_path / "symlink-unavailable.json").write_text(
            json.dumps({"errno": exc.errno, "winerror": getattr(exc, "winerror", None), "actual_platform_limit": True})
        )
        pytest.skip("native file symlink unavailable on this platform: " + str(exc))
    before = base.read_bytes()
    (tmp_path / "model.before.bin").write_bytes(before)
    error = None
    result = None
    try:
        result = gate.run_gate(
            str(link),
            str(quant),
            threshold=0.3,
            probe_corpus=source,
            out_path=str(base if aliased else tmp_path / "gate.json"),
        )
    except RuntimeError as exc:
        error = str(exc)
    finally:
        (tmp_path / "model.after.bin").write_bytes(base.read_bytes())
        (tmp_path / "facts.json").write_text(
            json.dumps(
                {
                    "aliased": aliased,
                    "error": error,
                    "source_loads": len(sdk["loads"]),
                    "controlled_model_calls": len(calls),
                    "model_bytes_held": base.read_bytes() == before,
                    "native_exit": result.get("exit_code") if result else None,
                }
            )
        )
    if aliased:
        assert error is not None and not sdk["loads"] and not calls
    else:
        assert error is None and result["exit_code"] == 0 and sdk["loads"] and calls
    assert base.read_bytes() == before


def test_actual_saved_cli_keeps_original_bytes_and_does_not_load_source(tmp_path):
    test_actual_cli_junit_roles(tmp_path, "valid")
    report = tmp_path / "native.json"
    before = {p.name: p.read_bytes() for p in (report, tmp_path / "gate.json", tmp_path / "gate.xml")}
    events = tmp_path / "saved.events"
    out = tmp_path / "saved.json"
    junit = tmp_path / "saved.xml"
    argv = [
        sys.executable,
        "-B",
        "-X",
        "utf8",
        "-m",
        "quantfit.cli",
        "gate",
        "--from-report",
        str(report),
        "--threshold",
        "30",
        "--probe-dataset",
        "controlled/alternative",
        "--probe-revision",
        "d" * 40,
        "--probe-split",
        "validation",
        "--out",
        str(out),
        "--junit",
        str(junit),
        "--json",
    ]
    child = subprocess.run(
        argv,
        cwd=tmp_path,
        env=dict(
            os.environ,
            PYTHONPATH=str(R / "tools/ci_corpus_fixture"),
            PYTHONDONTWRITEBYTECODE="1",
            QUANTFIT_CORPUS_CI="1",
            QUANTFIT_CORPUS_CI_LOG=str(events),
            HF_HUB_OFFLINE="1",
            HF_DATASETS_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
        ),
        capture_output=True,
        check=False,
    )
    assert child.returncode == 0, child.stderr.decode(errors="replace")
    data = json.loads(out.read_bytes())
    assert data["schema_version"] == 3 and data["probe_corpus"]["population_basis"] == "saved_report_native_counts"
    assert data["source_evidence"]["report_sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()
    assert junit.is_file() and not events.exists()
    assert all((tmp_path / name).read_bytes() == raw for name, raw in before.items())
