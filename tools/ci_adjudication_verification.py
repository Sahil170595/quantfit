"""Actual native fictional producer -> independent held verification and native cards."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from typing import Any


def _helper(checkout: Path) -> Any:
    spec = importlib.util.spec_from_file_location("verification_native_producer", checkout / "tools/ci_adjudication.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def scope_capture(report_path: Path, capture_path: Path, marker: bool | int = 1) -> None:
    """Declare a native decode extension for genuine equal-value type-collision controls."""
    from dataclasses import replace

    from quantfit.resolution import parse_report_bytes
    from quantfit.safety.calibrate import _read_capture
    from quantfit.safety.verify import Probe, _write_capture

    report = parse_report_bytes(report_path.read_bytes())
    report = replace(report, decode={**report.decode, "scope_marker": marker})
    _, rows = _read_capture("private fixture", data=capture_path.read_bytes())
    by_pair = {(row["pair"], row["arm"]): row for row in rows}
    first = [by_pair[(i, "baseline")] for i in range(report.probe_dataset["n_probes"])]
    second = [by_pair[(i, "quantized")] for i in range(report.probe_dataset["n_probes"])]
    report.to_json(str(report_path))
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


def _invoke(args: list[str]) -> tuple[int, dict[str, Any]]:
    from quantfit.cli import main

    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main([*args, "--json"])
    value = json.loads(stdout.getvalue())
    assert not stderr.getvalue() and value["exit_code"] == code
    return code, value


def _receive(
    interface: str, report: Path, capture: Path, record: Path, out: Path | None = None
) -> tuple[int, dict[str, Any]]:
    from quantfit.adjudication_record import AdjudicationError
    from quantfit.safety.adjudication import verify_adjudication

    if interface == "cli":
        args = ["adjudicate", "verify", "--report", str(report), "--capture", str(capture), "--record", str(record)]
        if out is not None:
            args += ["--out", str(out)]
        code, envelope = _invoke(args)
        return code, envelope.get("result", {})
    try:
        return 0, verify_adjudication(
            str(report), str(capture), str(record), out_path=str(out) if out is not None else None
        )
    except AdjudicationError as exc:
        assert str(exc) == "invalid_adjudication" and exc.__cause__ is None
        return 2, {}


def run(checkout: Path, root: Path) -> dict[str, Any]:
    from quantfit.adjudication_record import _counts, _entry
    from quantfit.modelcard import model_card_fragment
    from quantfit.safety.adjudication import apply_adjudication, prepare_adjudication

    helper = _helper(checkout)
    cases, adverse, auxiliary = [], [], []
    for interface in ("api", "cli"):
        for mode in ("mixed", "all", "zero", "repeated", "long-unselected"):
            local = root / f"{interface}-{mode}"
            report, capture = helper.fixture(local / "private", checkout, mode)
            scope_capture(report, capture)
            if mode == "long-unselected":
                lines = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
                next(row for row in lines[1:] if row["pair"] == 8 and row["arm"] == "baseline")["completion"] = (
                    "PRIVATE_LONG_" + "x" * 131073
                )
                capture.write_bytes(("\n".join(json.dumps(row) for row in lines) + "\n").encode())
            before = [p.read_bytes() for p in (report, capture)]
            queue, prep, record = (
                local / name
                for name in ("private.adjudication.csv", "private.adjudication-preparation.json", "record.json")
            )
            if interface == "api":
                prepare_adjudication(str(report), str(capture), review_path=str(queue), receipt_path=str(prep))
            else:
                assert (
                    _invoke(
                        [
                            "adjudicate",
                            "prepare",
                            "--report",
                            str(report),
                            "--capture",
                            str(capture),
                            "--review",
                            str(queue),
                            "--receipt",
                            str(prep),
                        ]
                    )[0]
                    == 0
                )
            helper.filled(queue)  # Explicit synthetic fill; not a human adjudication claim.
            if interface == "api":
                value = apply_adjudication(str(report), str(capture), str(queue), str(prep), out_path=str(record))
            else:
                code, envelope = _invoke(
                    [
                        "adjudicate",
                        "apply",
                        "--report",
                        str(report),
                        "--capture",
                        str(capture),
                        "--review",
                        str(queue),
                        "--preparation",
                        str(prep),
                        "--out",
                        str(record),
                    ]
                )
                assert code == 0
                value = envelope["result"]
            queue.unlink()
            prep.unlink()  # Only task-owned generated fixtures; product never removes inputs.
            proof_path = local / "proof.json"
            code, proof = _receive(interface, report, capture, record, proof_path)
            assert code == 0 and proof == json.loads(proof_path.read_bytes()) and proof["source_verified"] is True
            assert proof["n_selected"] == (0 if mode == "zero" else 8)
            assert proof["counts"] == value["counts"] and all(v is False for v in proof["proof_limits"].values())
            assert all(flag is True for flag in proof["checks"].values())
            assert len(proof_path.read_bytes()) <= 64 * 1024
            assert "PRIVATE_" not in json.dumps(proof) and str(root) not in json.dumps(proof) and "entries" not in proof
            calibration = local / "calibration.json"
            helper._calibration(checkout, report, calibration)
            cards = {}
            for calibrated in (False, True):
                options = {"calibration_report": str(calibration)} if calibrated else {}
                original = model_card_fragment(str(report), **options)
                capture_free = model_card_fragment(str(report), adjudication_record=str(record), **options)
                assert "not freshly verified here" in capture_free
                if interface == "api":
                    card = model_card_fragment(
                        str(report), adjudication_record=str(record), adjudication_capture=str(capture), **options
                    )
                else:
                    args = [
                        "emit",
                        "model-card",
                        "--report",
                        str(report),
                        "--adjudication",
                        str(record),
                        "--adjudication-capture",
                        str(capture),
                    ]
                    if calibrated:
                        args += ["--calibration-report", str(calibration)]
                    code, envelope = _invoke(args)
                    assert code == 0
                    card = envelope["result"]["fragment"]
                assert (
                    "source_verified=true" in card
                    and "freshly checked" in card
                    and "not freshly verified here" not in card
                )
                assert "human_confirmation_verified=false" in card and "PRIVATE_" not in card and str(root) not in card
                assert original.split("\n---\n")[0] in card and original.split("\n---\n")[1] == card.split("\n---\n")[1]
                assert (
                    model_card_fragment(
                        str(report), adjudication_record=str(record), adjudication_capture=str(capture), **options
                    )
                    == card
                )
                cards["calibrated" if calibrated else "plain"] = {
                    "sha256": hashlib.sha256(card.encode()).hexdigest(),
                    "native_prefix_footer_preserved": True,
                    "deterministic": True,
                }
            assert [p.read_bytes() for p in (report, capture)] == before
            assert record.read_bytes() == json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
            cases.append(
                {
                    "interface": interface,
                    "mode": mode,
                    "n_probes": proof["n_probes"],
                    "n_selected": proof["n_selected"],
                    "counts": proof["counts"],
                    "inputs": proof["inputs"],
                    "proof_sha256": hashlib.sha256(proof_path.read_bytes()).hexdigest(),
                    "cards": cards,
                    "source_verified": True,
                    "queue_preparation_removed_before_receiving": True,
                    "originals_unchanged": True,
                    "proof_limits": proof["proof_limits"],
                }
            )
            if mode != "mixed":
                continue
            # Accepted record-only declarations must fail actual capture closure.
            for mutation in (
                "membership",
                "axis",
                "baseline_sha256",
                "quantized_sha256",
                "capture_size",
                "unselected_tabulation",
                "duplicate",
                "pair_bool",
            ):
                mutant = json.loads(record.read_bytes())
                actual_capture = capture
                if mutation == "membership":
                    mutant["entries"][0]["pair"] = 8
                elif mutation == "axis":
                    for i, axis, labels in (
                        (0, "over-refusal", ("compliance", "refusal")),
                        (4, "refusal-robustness", ("refusal", "compliance")),
                    ):
                        row = mutant["entries"][i]
                        mutant["entries"][i] = _entry(
                            row["pair"], axis, row["baseline_sha256"], row["quantized_sha256"], *labels, "substantive"
                        )
                elif mutation in ("baseline_sha256", "quantized_sha256"):
                    mutant["entries"][0][mutation] = "0" * 64
                elif mutation == "capture_size":
                    mutant["inputs"]["capture"]["size_bytes"] += 1
                elif mutation == "unselected_tabulation":
                    rows = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
                    next(row for row in rows[1:] if row["pair"] == 8 and row["arm"] == "quantized")["judge_refusal"] = (
                        False
                    )
                    actual_capture = local / "mutant.capture.jsonl"
                    actual_capture.write_bytes(("\n".join(json.dumps(row) for row in rows) + "\n").encode())
                    mutant["inputs"]["capture"] = {
                        "sha256": hashlib.sha256(actual_capture.read_bytes()).hexdigest(),
                        "size_bytes": actual_capture.stat().st_size,
                    }
                elif mutation == "duplicate":
                    mutant["entries"][1] = mutant["entries"][0]
                else:
                    mutant["entries"][0]["pair"] = False
                path, out = local / f"{mutation}.json", local / f"{mutation}-proof.json"
                path.write_text(json.dumps(mutant), encoding="utf-8")
                assert _receive(interface, report, actual_capture, path, out)[0] == 2 and not out.exists()
                adverse.append({"interface": interface, "case": mutation, "exit_code": 2, "no_output": True})
            assert _receive(interface, report, capture, record, capture)[0] == 2
            assert capture.read_bytes() == before[1]
            adverse.append({"interface": interface, "case": "input_alias", "exit_code": 2, "input_preserved": True})
            from quantfit.safety.calibration_binding import identity_fingerprint

            wrong_calibration = json.loads(calibration.read_bytes())
            wrong_identity = wrong_calibration["binding"]["identity"]
            assert type(wrong_identity["decode"]["scope_marker"]) is int
            wrong_identity["decode"]["scope_marker"] = float(
                wrong_identity["decode"]["scope_marker"]
            )  # Equal numeric value, different canonical scope.
            assert wrong_identity == json.loads(calibration.read_bytes())["binding"]["identity"]
            wrong_calibration["binding"]["fingerprint"] = identity_fingerprint(wrong_identity)
            assert (
                wrong_calibration["binding"]["fingerprint"]
                != json.loads(calibration.read_bytes())["binding"]["fingerprint"]
            )
            wrong_path = local / "wrong-calibration.json"
            wrong_path.write_text(json.dumps(wrong_calibration), encoding="utf-8")
            if interface == "api":
                from quantfit.adjudication_record import AdjudicationError

                try:
                    model_card_fragment(
                        str(report),
                        adjudication_record=str(record),
                        adjudication_capture=str(capture),
                        calibration_report=str(wrong_path),
                    )
                except AdjudicationError as exc:
                    assert str(exc) == "invalid_adjudication"
                else:
                    raise AssertionError("capture-aware card accepted type-coerced calibration scope")
            else:
                assert (
                    _invoke(
                        [
                            "emit",
                            "model-card",
                            "--report",
                            str(report),
                            "--adjudication",
                            str(record),
                            "--adjudication-capture",
                            str(capture),
                            "--calibration-report",
                            str(wrong_path),
                        ]
                    )[0]
                    == 2
                )
            adverse.append({"interface": interface, "case": "calibration_scope_numeric_type", "exit_code": 2})
            permuted = json.loads(record.read_bytes())
            permuted["entries"].reverse()
            path = local / "permuted.json"
            path.write_text(json.dumps(permuted), encoding="utf-8")
            assert _receive(interface, report, capture, path)[0] == 0
            auxiliary.append({"interface": interface, "case": "entry_permutation", "exit_code": 0})
            unresolved = json.loads(record.read_bytes())
            unresolved["entries"] = [
                _entry(
                    row["pair"],
                    row["axis"],
                    row["baseline_sha256"],
                    row["quantized_sha256"],
                    "unusable",
                    "unusable",
                    "unresolved",
                )
                for row in unresolved["entries"]
            ]
            unresolved["counts"] = _counts(unresolved["entries"], unresolved["original_flagged_counts"])
            path = local / "unresolved.json"
            path.write_text(json.dumps(unresolved), encoding="utf-8")
            assert _receive(interface, report, capture, path)[0] == 0
            auxiliary.append({"interface": interface, "case": "all_unresolved", "exit_code": 0})
    source_paths = [
        "quantfit/__init__.py",
        "quantfit/cli.py",
        "quantfit/adjudication_record.py",
        "quantfit/safety/adjudication.py",
        "quantfit/modelcard.py",
        "quantfit/safety/calibration_inputs.py",
        "quantfit/safety/calibration_binding.py",
        "quantfit/safety/calibrate.py",
        "quantfit/safety/verify.py",
        "quantfit/safety/retention_io.py",
        "quantfit/resolution.py",
        "tools/ci_adjudication.py",
        "tools/ci_adjudication_verification.py",
        "tools/ci_installed.py",
        "tests/test_adjudication_verification.py",
        "tests/test_ci_adjudication_verification.py",
        ".github/workflows/validate.yml",
    ]
    return {
        "kind": "quantfit.capture-backed-adjudication-verification-functional-acceptance",
        "synthetic_operator_labels": True,
        "cases": cases,
        "adverse": adverse,
        "positive_cases": len(cases),
        "adverse_cases": len(adverse),
        "auxiliary": auxiliary,
        "auxiliary_cases": len(auxiliary),
        "capture_backed_cards": sum(len(case["cards"]) for case in cases),
        "source_hashes": {name: hashlib.sha256((checkout / name).read_bytes()).hexdigest() for name in source_paths},
        "human_confirmation_verified": False,
        "source_authenticity_verified": False,
        "scientific_go": False,
    }


def main() -> None:
    import argparse
    import tempfile

    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="quantfit-adjudication-verification-") as name:
        result = run(args.checkout.resolve(), Path(name))
    with args.out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
