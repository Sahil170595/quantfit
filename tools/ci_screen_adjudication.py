"""Genuine native fictional whole-screen producer fixtures; no inference or human truth."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from typing import Any


def fixture(
    root: Path, checkout: Path, mode: str = "mixed", n: int = 3, missing: tuple[str, ...] = ()
) -> tuple[Path, Path, Path, Path]:
    from quantfit.resolution import parse_report_bytes
    from quantfit.safety.adjudication import apply_adjudication, prepare_adjudication
    from quantfit.safety.calibrate import _read_capture
    from quantfit.safety.verify import Probe, _write_capture

    spec = importlib.util.spec_from_file_location("screen_adjudication_producer", checkout / "tools/ci_adjudication.py")
    assert spec and spec.loader
    native: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    reports, records, captures = (root / name for name in ("reports", "adjudications", "captures"))
    for directory in (reports, records, captures):
        directory.mkdir(parents=True)
    targets = []
    for name in ("gamma", "alpha", "beta")[:n]:
        private = root / "private" / name
        original_report, original_capture = native.fixture(
            private, checkout, "mixed" if mode in ("unresolved", "long-selected", "long-unselected") else mode
        )
        report = parse_report_bytes(original_report.read_bytes())
        report = replace(
            report,
            baseline=replace(
                report.baseline,
                model=f"hf:synthetic/{name}/{name}-baseline.gguf",
                revision=hashlib.sha1(f"{name}:baseline".encode()).hexdigest(),
                artifact_sha256=hashlib.sha256(f"fictional:{name}:baseline".encode()).hexdigest(),
            ),
            quantized=replace(
                report.quantized,
                model=f"hf:synthetic/{name}/{name}-quantized.gguf",
                revision=hashlib.sha1(f"{name}:quantized".encode()).hexdigest(),
                artifact_sha256=hashlib.sha256(f"fictional:{name}:quantized".encode()).hexdigest(),
            ),
        )
        target = {"name": name, "stratum": "gguf", "baseline": report.baseline.model, "quant": report.quantized.model}
        targets.append(target)
        report_path, capture_path = reports / f"{name}.json", captures / f"{name}.capture.jsonl"
        report.to_json(str(report_path))
        _, rows = _read_capture("private fixture", data=original_capture.read_bytes())
        if mode in ("long-selected", "long-unselected"):
            index = 0 if mode == "long-selected" else 8
            next(row for row in rows if row["pair"] == index and row["arm"] == "baseline")["completion"] = (
                "PRIVATE_LONG_" + "x" * 131073
            )
        by_pair = {(row["pair"], row["arm"]): row for row in rows}
        first = [by_pair[(i, "baseline")] for i in range(report.probe_dataset["n_probes"])]
        second = [by_pair[(i, "quantized")] for i in range(report.probe_dataset["n_probes"])]
        _write_capture(
            str(capture_path),
            [Probe("", row["zone"], row["expected"]) for row in first],
            report.baseline.model,
            report.quantized.model,
            [row["completion"] for row in first],
            [row["completion"] for row in second],
            [row["judge_refusal"] for row in first],
            [row["judge_refusal"] for row in second],
            actual_report=report,
        )
        queue, prep = private / "private.adjudication.csv", private / "private.adjudication-preparation.json"
        previous_limit = csv.field_size_limit()
        if mode == "long-selected":
            csv.field_size_limit(max(previous_limit, 262144))
        try:
            prepare_adjudication(str(report_path), str(capture_path), review_path=str(queue), receipt_path=str(prep))
            native.filled(queue)  # Explicit fictional labels, never authenticated human judgment.
        finally:
            csv.field_size_limit(previous_limit)
        if mode == "unresolved":
            table = list(csv.reader(io.StringIO(queue.read_text(encoding="utf-8"), newline="")))
            for row in table[1:]:
                row[-3:] = ["unusable", "unusable", "unresolved"]
            stream = io.StringIO(newline="")
            csv.writer(stream, lineterminator="\n").writerows(table)
            queue.write_bytes(stream.getvalue().encode())
        if mode == "long-selected":
            csv.field_size_limit(max(previous_limit, 262144))
        try:
            apply_adjudication(
                str(report_path), str(capture_path), str(queue), str(prep), out_path=str(records / f"{name}.json")
            )
        finally:
            csv.field_size_limit(previous_limit)
        queue.unlink()
        prep.unlink()
        if name in missing:
            report_path.unlink()  # Only the freshly produced fictional missing-report fixture.
    manifest = root / "targets.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Fictional source adjudication screen",
                "targets": targets,
                "sensitivity_control": {"status": "not_run"},
            }
        ),
        encoding="utf-8",
    )
    return manifest, reports, records, captures


def _invoke(
    paths: tuple[Path, Path, Path, Path],
    *,
    captures: bool = True,
    records: bool = True,
    require: bool = False,
    out: Path | None = None,
    junit: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    from quantfit.cli import main

    args = ["adjudicate", "screen", "--targets", str(paths[0]), "--reports-dir", str(paths[1]), "--json"]
    if records:
        args += ["--adjudications-dir", str(paths[2])]
    if captures:
        args += ["--captures-dir", str(paths[3])]
    if require:
        args += ["--require-source-complete"]
    if out is not None:
        args += ["--out", str(out)]
    if junit is not None:
        args += ["--junit", str(junit)]
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(args)
    value = json.loads(stdout.getvalue())
    assert not stderr.getvalue() and value["exit_code"] == code
    return code, value.get("result", {})


def _receive(
    interface: str,
    paths: tuple[Path, Path, Path, Path],
    *,
    captures: bool = True,
    records: bool = True,
    require: bool = False,
    out: Path | None = None,
    junit: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    from quantfit import summarize_screen_adjudication
    from quantfit.saved_screen import SavedScreenError

    if interface == "cli":
        return _invoke(paths, captures=captures, records=records, require=require, out=out, junit=junit)
    try:
        value = summarize_screen_adjudication(
            str(paths[0]),
            str(paths[1]),
            adjudications_dir=str(paths[2]) if records else None,
            captures_dir=str(paths[3]) if captures else None,
            require_source_complete=require,
            out_path=str(out) if out is not None else None,
            junit_path=str(junit) if junit is not None else None,
        )
        return value["exit_code"], value
    except SavedScreenError as error:
        assert error.__cause__ is None and str(error) in (
            "unsafe_output",
            "invalid_manifest",
            "invalid_adjudication_sources",
            "incompatible_scope",
            "unsupported_directory_member",
            "invalid_source_member",
            "analysis_work_limit",
            "output_byte_limit",
            "adjudication_byte_limit",
            "invalid_capture",
        )
        return 2, {}


def _input_bytes(paths: tuple[Path, Path, Path, Path]) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in (paths[0], *[p for root in paths[1:] for p in root.iterdir()])}


def run(checkout: Path, root: Path) -> dict[str, Any]:
    """Actual public receiving, fictional declarations; no inference or human truth."""
    from quantfit import screen_adjudication
    from quantfit.safety.calibration_binding import identity_fingerprint

    positives, adverse = [], []
    profiles = (
        ("zero", 2, (), True, True, True, 0, True),
        ("mixed", 3, (), True, True, True, 3, True),
        ("all", 3, (), True, True, True, 3, True),
        ("unresolved", 3, (), True, True, True, 3, True),
        ("zero", 3, ("beta",), True, True, True, 4, False),
        ("zero", 2, (), False, True, False, 0, False),
        ("zero", 2, (), False, True, True, 4, False),
        ("zero", 2, (), True, False, True, 0, True),
        ("long-selected", 2, (), True, True, True, 3, True),
        ("long-unselected", 2, (), True, True, True, 3, True),
        ("repeated", 2, (), True, True, True, 3, True),
        ("mixed", 2, ("gamma", "alpha"), True, True, True, 4, False),
    )
    for interface in ("api", "cli"):
        for ordinal, (mode, n, missing, captures, records, required, expected, complete) in enumerate(profiles):
            local = root / f"{interface}-positive-{ordinal}"
            paths = fixture(local, checkout, mode, n, missing)
            before = _input_bytes(paths)
            out, junit = local / "summary.json", local / "summary.xml"
            code, result = _receive(
                interface, paths, captures=captures, records=records, require=required, out=out, junit=junit
            )
            assert code == expected and json.loads(out.read_bytes()) == result
            section = result["screen_adjudication"]
            assert section["source_complete"] is complete
            assert [row["name"] for row in result["rows"]] == ["gamma", "alpha", "beta"][:n]
            assert len(section["rows"]) == n and int(ET.fromstring(junit.read_bytes()).attrib["tests"]) == 3 * n + 1
            assert all(p.read_bytes() == raw for p, raw in before.items())
            for raw in (out.read_bytes(), junit.read_bytes()):
                assert (
                    b"PRIVATE_" not in raw and str(paths[2]).encode() not in raw and str(paths[3]).encode() not in raw
                )
            assert (
                result["n_regressed_human_verified"] == 0
                and result["human_labels_authenticated"] is result["scientific_go"] is False
            )
            positives.append(
                {
                    "interface": interface,
                    "case": ordinal,
                    "mode": mode,
                    "original_targets": n,
                    "missing_reports": len(missing),
                    "exit_code": code,
                    "native_exit_code": section["native_exit_code"],
                    "source_complete": complete,
                    "junit_cases": 3 * n + 1,
                    "private_inputs_unchanged": True,
                    "operator_resolution": [row["operator_resolution"] for row in section["rows"]],
                }
            )
        for mutation in (
            "capture_hash",
            "report_hash",
            "selected",
            "axis",
            "baseline_hash",
            "quantized_hash",
            "typed_count",
            "typed_flagged",
            "late_capture",
            "pending_hash",
            "pending_scope",
            "orphan_record",
            "orphan_capture",
            "record_directory",
            "report_alias",
            "record_alias",
            "capture_alias",
            "manifest_alias",
            "same_sinks",
            "work_limit",
            "additional_byte_limit",
            "output_limit",
            "pending_n",
        ):
            local = root / f"{interface}-adverse-{mutation}"
            pending = mutation in ("pending_hash", "pending_scope", "pending_n")
            paths = fixture(local, checkout, "mixed", 2, ("alpha",) if pending else ())
            record_path = paths[2] / "alpha.json"
            record = json.loads(record_path.read_bytes())
            out, junit = local / "never.json", local / "never.xml"
            if mutation in ("capture_hash", "report_hash", "pending_hash"):
                record["inputs"]["report" if mutation == "report_hash" else "capture"]["sha256"] = "0" * 64
            elif mutation == "selected":
                record["entries"][0]["pair"] = 10
            elif mutation == "axis":
                record["entries"][0]["axis"] = "over-refusal"
            elif mutation in ("baseline_hash", "quantized_hash"):
                record["entries"][0][mutation.replace("_hash", "_sha256")] = "0" * 64
            elif mutation == "typed_count":
                record["n_probes"] = float(record["n_probes"])
            elif mutation == "typed_flagged":
                record["original_flagged_counts"]["refusal-robustness"] = True
            elif mutation == "late_capture":
                (paths[3] / "alpha.capture.jsonl").write_bytes(b"{")
            elif mutation == "pending_n":
                record_path.unlink()
                path = paths[3] / "alpha.capture.jsonl"
                rows = [json.loads(line) for line in path.read_text(encoding="utf8").splitlines()]
                rows[0]["n_pairs"] = 4097
                path.write_bytes(("\n".join(json.dumps(row) for row in rows) + "\n").encode())
            elif mutation == "pending_scope":
                record_path.unlink()
                path = paths[3] / "alpha.capture.jsonl"
                rows = [json.loads(line) for line in path.read_text(encoding="utf8").splitlines()]
                binding = rows[0]["binding"]
                binding["identity"]["env"]["python"] = "fictional-other-python"
                binding["fingerprint"] = identity_fingerprint(binding["identity"])
                path.write_bytes(("\n".join(json.dumps(row) for row in rows) + "\n").encode())
            elif mutation.startswith("orphan_"):
                (paths[2 if mutation == "orphan_record" else 3] / "orphan.json").write_bytes(b"{}")
            elif mutation == "record_directory":
                record_path.unlink()
                record_path.mkdir()
            elif mutation.endswith("_alias"):
                junit = {
                    "report_alias": paths[1] / "gamma.json",
                    "record_alias": paths[2] / "gamma.json",
                    "capture_alias": paths[3] / "gamma.capture.jsonl",
                    "manifest_alias": paths[0],
                }[mutation]
            elif mutation == "same_sinks":
                junit = out
            if mutation in (
                "capture_hash",
                "report_hash",
                "pending_hash",
                "selected",
                "axis",
                "baseline_hash",
                "quantized_hash",
                "typed_count",
                "typed_flagged",
            ):
                record_path.write_bytes((json.dumps(record) + "\n").encode())
            before = _input_bytes(paths) if mutation != "record_directory" else {}
            limits = (
                screen_adjudication.MAX_ANALYSIS_WORK,
                screen_adjudication.MAX_ADJUDICATION_BYTES,
                screen_adjudication.MAX_OUTPUT_BYTES,
            )
            try:
                if mutation == "work_limit":
                    screen_adjudication.MAX_ANALYSIS_WORK = 1
                elif mutation == "additional_byte_limit":
                    screen_adjudication.MAX_ADJUDICATION_BYTES = 1
                elif mutation == "output_limit":
                    screen_adjudication.MAX_OUTPUT_BYTES = 64
                assert _receive(interface, paths, require=True, out=out, junit=junit)[0] == 2
            finally:
                (
                    screen_adjudication.MAX_ANALYSIS_WORK,
                    screen_adjudication.MAX_ADJUDICATION_BYTES,
                    screen_adjudication.MAX_OUTPUT_BYTES,
                ) = limits
            assert not out.exists()
            assert all(p.read_bytes() == raw for p, raw in before.items())
            adverse.append({"interface": interface, "case": mutation, "exit_code": 2, "normal_output_absent": True})

    # Native OS stdout bytes qualify LF/exact envelope, not just StringIO text.
    local = root / "os-entrypoint"
    paths = fixture(local, checkout, "zero", 2)
    out = local / "summary.json"
    args = [
        sys.executable,
        "-B",
        "-X",
        "utf8",
        "-m",
        "quantfit.cli",
        "adjudicate",
        "screen",
        "--targets",
        str(paths[0]),
        "--reports-dir",
        str(paths[1]),
        "--captures-dir",
        str(paths[3]),
        "--require-source-complete",
        "--out",
        str(out),
        "--json",
    ]
    child = subprocess.run(
        args,
        cwd=root,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
    )
    assert child.returncode == 0 and not child.stderr and b"\r" not in child.stdout
    envelope = json.loads(child.stdout)
    assert envelope["result"] == json.loads(out.read_bytes())
    assert child.stdout == (json.dumps(envelope, indent=2, ensure_ascii=True) + "\n").encode()
    sources = (
        "quantfit/screen_adjudication.py",
        "quantfit/saved_screen.py",
        "quantfit/adjudication_record.py",
        "quantfit/safety/adjudication.py",
        "quantfit/safety/calibration_inputs.py",
        "quantfit/safety/calibration_binding.py",
        "quantfit/safety/calibrate.py",
        "quantfit/safety/verify.py",
        "quantfit/resolution.py",
        "quantfit/bundle.py",
        "quantfit/reproduce.py",
        "quantfit/junit.py",
        "quantfit/cli.py",
        "tools/ci_screen_adjudication.py",
        "tests/test_screen_adjudication.py",
        "tests/test_ci_screen_adjudication.py",
    )
    return {
        "fixture": "Native fictional declarations and explicit synthetic fill; no inference/human truth",
        "positive_cases": len(positives),
        "cases": positives,
        "adverse_cases": len(adverse),
        "adverse": adverse,
        "os_entrypoint_raw_utf8_lf_parity": True,
        "queue_preparation_not_received": True,
        "human_confirmation_verified": False,
        "scientific_go": False,
        "source_hashes": {name: hashlib.sha256((checkout / name).read_bytes()).hexdigest() for name in sources},
    }
