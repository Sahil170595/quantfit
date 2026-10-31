"""Private fictional review-page fixtures; no human or model execution."""

from __future__ import annotations

import csv
import importlib.util
import io
import json
from pathlib import Path
from typing import Any


def _native(checkout: Path) -> Any:
    spec = importlib.util.spec_from_file_location("private_native_adjudication", checkout / "tools/ci_adjudication.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def fixture(root: Path, checkout: Path, text: str | None = None, mode: str = "mixed") -> dict[str, Path]:
    from quantfit.resolution import parse_report_bytes
    from quantfit.safety.adjudication import prepare_adjudication
    from quantfit.safety.calibration_inputs import _capture
    from quantfit.safety.verify import Probe, _write_capture

    helper = _native(checkout)
    report_path, capture_path = helper.fixture(root / "producer", checkout, mode)
    if text is not None:
        report = parse_report_bytes(report_path.read_bytes())
        n = report.probe_dataset["n_probes"]
        _, rows = _capture(capture_path.read_bytes(), n)
        captured = {(row["pair"], row["arm"]): row for row in rows}
        first = [captured[(pair, "baseline")] for pair in range(n)]
        second = [captured[(pair, "quantized")] for pair in range(n)]
        capture_path = root / "exact-strings.capture.jsonl"
        _write_capture(
            str(capture_path),
            [Probe("", row["zone"], row["expected"]) for row in first],
            report.baseline.model,
            report.quantized.model,
            [text for _ in first],
            ["other" for _ in second],
            [row["judge_refusal"] for row in first],
            [row["judge_refusal"] for row in second],
            actual_report=report,
        )
    queue, preparation = root / "private.adjudication.csv", root / "preparation.json"
    prepare_adjudication(str(report_path), str(capture_path), review_path=str(queue), receipt_path=str(preparation))
    return {"report": report_path, "capture": capture_path, "queue": queue, "preparation": preparation}


def native_roundtrip(checkout: Path, root: Path, text: str | None = None) -> dict[str, Any]:
    from quantfit.safety.adjudication import COLUMNS, _originals, _preparation, _queue, apply_adjudication
    from quantfit.safety.retention_io import hold

    paths = fixture(root, checkout, text)
    raw = paths["queue"].read_bytes()
    preparation = json.loads(paths["preparation"].read_bytes())
    original = _originals((hold(paths["report"], 8 * 1024 * 1024), hold(paths["capture"], 16 * 1024 * 1024)))
    assert _queue(original) == raw and _preparation(original, preparation["quantfit_version"]) == preparation
    rows = list(csv.reader(io.StringIO(raw.decode("utf8"), newline=""), strict=True))
    assert tuple(rows[0]) == COLUMNS and len(rows) == preparation["n_selected"] + 1 == 9
    if text is not None:
        assert all(row[4] == text for row in rows[1:])
    for row in rows[1:]:
        row[6:] = _native(checkout).LABELS[int(row[0]) % 8]
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    filled = root / "filled.adjudication.csv"
    filled.write_bytes(stream.getvalue().encode())
    record = apply_adjudication(
        str(paths["report"]),
        str(paths["capture"]),
        str(filled),
        str(paths["preparation"]),
        out_path=str(root / "record.json"),
    )
    assert len(record["entries"]) == 8
    return {
        "original_n": 12,
        "selected": 8,
        "blank_read_exact": True,
        "regeneration_byte_exact": True,
        "native_apply_completed": True,
    }


def _render(interface: str, paths: dict[str, Path], out: Path) -> tuple[int, dict[str, Any]]:
    if interface == "api":
        from quantfit.safety.adjudication_review import AdjudicationReviewError, render_adjudication_review

        try:
            return 0, render_adjudication_review(str(paths["queue"]), str(paths["preparation"]), out_path=str(out))
        except AdjudicationReviewError as error:
            assert str(error) == "invalid_adjudication_review" and error.__cause__ is None
            return 2, {}
    import subprocess
    import sys

    child = subprocess.run(
        [
            sys.executable,
            "-B",
            "-X",
            "utf8",
            "-m",
            "quantfit.cli",
            "adjudicate",
            "review-page",
            "--review",
            str(paths["queue"]),
            "--preparation",
            str(paths["preparation"]),
            "--out",
            str(out),
            "--json",
        ],
        cwd=out.parent,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    assert not child.stderr and b"PRIVATE_" not in child.stdout
    if child.returncode == 0:
        assert b"\r" not in child.stdout
    result = json.loads(child.stdout)
    assert result["exit_code"] == child.returncode
    return child.returncode, result.get("result") or {}


def decisions(rows: list[list[str]]) -> list[list[str]]:
    result = []
    for index, row in enumerate(rows):
        first, second = ("refusal", "compliance") if row[1] == "refusal-robustness" else ("compliance", "refusal")
        result.append(
            (
                [first, second, "substantive"],
                [first, second, "degenerate"],
                [second, second, "not-a-flip"],
                ["unusable", second, "unresolved"],
            )[index % 4]
        )
    return result


def prepare_pages(checkout: Path, root: Path) -> dict[str, Any]:
    cases = []
    controls = [
        ("mixed", None, "mixed"),
        ("all", None, "all"),
        ("zero", None, "zero"),
        ("unicode", 'PRIVATE_ </script><img src="https://invalid.example">\r\nLF\nCR\rNUL\0 \U0001f600', "mixed"),
        ("bare-cr", "left\rright", "mixed"),
        ("nul-byte", "left\0right", "mixed"),
    ]
    for interface in ("api", "cli"):
        for label, text, mode in controls:
            name = f"{interface}-{label}"
            directory = root / name
            paths = fixture(directory, checkout, text, mode)
            out = directory / "private.adjudication.html"
            code, receipt = _render(interface, paths, out)
            assert code == 0 and out.is_file() and receipt["source_verified"] is False
            expected = 0 if mode == "zero" else 8
            assert receipt["n_selected"] == expected
            paths["page"] = out
            paths["filled"] = directory / "filled.adjudication.csv"
            cases.append(
                {
                    "name": name,
                    "interface": interface,
                    "selected": expected,
                    "paths": {key: str(path.relative_to(root)) for key, path in paths.items()},
                    "receipt": receipt,
                }
            )
    value = {"cases": cases, "expected_pages": len(cases)}
    (root / "handoff.json").write_text(json.dumps(value, indent=2), encoding="utf8")
    return value


def receive_pages(checkout: Path, root: Path) -> dict[str, Any]:
    import hashlib
    import subprocess
    import sys

    from quantfit.modelcard import model_card_fragment
    from quantfit.safety.adjudication import apply_adjudication

    manifest = json.loads((root / "handoff.json").read_bytes())
    cases = []
    for case in manifest["cases"]:
        paths = {key: root / value for key, value in case["paths"].items()}
        blank = list(csv.reader(io.StringIO(paths["queue"].read_bytes().decode("utf8"), newline=""), strict=True))
        filled = list(csv.reader(io.StringIO(paths["filled"].read_bytes().decode("utf8"), newline=""), strict=True))
        assert len(blank) == len(filled) == case["selected"] + 1 and blank[0] == filled[0]
        assert [row[:6] for row in blank[1:]] == [row[:6] for row in filled[1:]]
        expected = io.StringIO(newline="")
        csv.writer(expected, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
            [blank[0], *[[*row[:6], *choice] for row, choice in zip(blank[1:], decisions(blank[1:]), strict=True)]]
        )
        assert paths["filled"].read_bytes() == expected.getvalue().encode()
        record_path = paths["page"].parent / "record.json"
        if case["interface"] == "api":
            record = apply_adjudication(
                str(paths["report"]),
                str(paths["capture"]),
                str(paths["filled"]),
                str(paths["preparation"]),
                out_path=str(record_path),
            )
        else:
            child = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "quantfit.cli",
                    "adjudicate",
                    "apply",
                    "--report",
                    str(paths["report"]),
                    "--capture",
                    str(paths["capture"]),
                    "--review",
                    str(paths["filled"]),
                    "--preparation",
                    str(paths["preparation"]),
                    "--out",
                    str(record_path),
                    "--json",
                ],
                cwd=root,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
            )
            assert child.returncode == 0 and not child.stderr
            record = json.loads(child.stdout)["result"]
        assert len(record["entries"]) == case["selected"]
        calibration = paths["page"].parent / "calibration.json"
        _native(checkout)._calibration(checkout, paths["report"], calibration)
        for calibrated in (False, True):
            options = {"calibration_report": str(calibration)} if calibrated else {}
            original = model_card_fragment(str(paths["report"]), **options)
            card = model_card_fragment(str(paths["report"]), adjudication_record=str(record_path), **options)
            assert "human_confirmation_verified=false" in card and "PRIVATE_" not in card
            assert original.split("\n---\n")[0] in card and original.split("\n---\n")[1] == card.split("\n---\n")[1]
        cases.append(
            {
                "case": case["name"],
                "selected": case["selected"],
                "six_fields_exact": True,
                "csv_utf8_crlf_bytes_exact": True,
                "native_apply_completed": True,
                "cards_plain_and_calibrated": True,
                "csv_sha256": hashlib.sha256(paths["filled"].read_bytes()).hexdigest(),
            }
        )
    return {"positive_cases": len(cases), "cases": cases}


def run(checkout: Path, root: Path) -> dict[str, Any]:
    import hashlib

    prepared = prepare_pages(checkout, root)
    for case in prepared["cases"]:
        paths = {key: root / value for key, value in case["paths"].items()}
        rows = list(csv.reader(io.StringIO(paths["queue"].read_bytes().decode(), newline=""), strict=True))
        stream = io.StringIO(newline="")
        csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
            [rows[0], *[[*row[:6], *choice] for row, choice in zip(rows[1:], decisions(rows[1:]), strict=True)]]
        )
        paths["filled"].write_bytes(stream.getvalue().encode())
    result = receive_pages(checkout, root)
    adverse = []
    for interface in ("api", "cli"):
        for mutation in ("queue-hash", "extra", "count-bool", "nonblank", "existing", "alias", "suffix", "input-cap"):
            paths = fixture(root / f"bad-{interface}-{mutation}", checkout)
            out = paths["queue"].parent / "refused.adjudication.html"
            metadata = json.loads(paths["preparation"].read_bytes())
            if mutation == "queue-hash":
                paths["queue"].write_bytes(paths["queue"].read_bytes() + b" ")
            if mutation == "extra":
                metadata["extra"] = True
            if mutation == "count-bool":
                metadata["n_selected"] = True
            if mutation == "nonblank":
                rows = list(csv.reader(io.StringIO(paths["queue"].read_bytes().decode(), newline="")))
                rows[-1][-1] = "unresolved"
                stream = io.StringIO(newline="")
                csv.writer(stream).writerows(rows)
                paths["queue"].write_bytes(stream.getvalue().encode())
                metadata["review_queue"] = {
                    "sha256": hashlib.sha256(paths["queue"].read_bytes()).hexdigest(),
                    "size_bytes": len(paths["queue"].read_bytes()),
                }
            paths["preparation"].write_text(json.dumps(metadata), encoding="utf8")
            if mutation == "existing":
                out.write_bytes(b"KEEP")
            if mutation == "alias":
                import os

                os.link(paths["queue"], out)
            if mutation == "suffix":
                out = out.with_name("unsafe.html")
            if mutation == "input-cap":
                paths["queue"].write_bytes(b"x" * (16 * 1024 * 1024 + 1))
            before = {key: path.read_bytes() for key, path in paths.items()}
            assert _render(interface, paths, out)[0] == 2
            assert all(path.read_bytes() == before[key] for key, path in paths.items())
            if mutation not in ("existing", "alias"):
                assert not out.exists()
            if mutation == "existing":
                assert out.read_bytes() == b"KEEP"
            adverse.append({"interface": interface, "case": mutation, "exit_code": 2})
    result.update(
        {
            "adverse_cases": len(adverse),
            "adverse": adverse,
            "transport": "stdlib quote-all CSV fixture, NOT browser execution",
            "browser_qualification": "required separately in hosted original/rebuilt profiles",
            "human_confirmation_verified": False,
            "source_authenticity_verified": False,
            "scientific_go": False,
        }
    )
    return result


def main() -> None:
    import argparse
    import sys

    import quantfit

    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", type=Path)
    modes.add_argument("--receive", type=Path)
    args = parser.parse_args()
    package = Path(quantfit.__file__).resolve().parent

    def guard() -> int:
        modules = [
            module for name, module in tuple(sys.modules.items()) if name == "quantfit" or name.startswith("quantfit.")
        ]
        assert not package.is_relative_to(args.checkout.resolve())
        for module in modules:
            origin = getattr(module, "__file__", None)
            assert isinstance(origin, str) and Path(origin).resolve().is_relative_to(package)
        return len(modules)

    guard()
    if args.prepare:
        value = prepare_pages(args.checkout, args.prepare)
        result = {"prepared_private_pages": value["expected_pages"]}
    else:
        result = receive_pages(args.checkout, args.receive)
    result["actual_loaded_package_modules"] = guard()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
