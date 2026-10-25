"""Exercise installed distribution outside checkout and reject source shadowing."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET


def _pytest_code(checkout: Path) -> str:
    """Keep installed application provenance in the same process as fixture tests."""
    return f"""
import pathlib, sys, quantfit, pytest
checkout = pathlib.Path({str(checkout)!r}).resolve()
def guard():
    assert checkout not in {{pathlib.Path(p or '.').resolve() for p in sys.path}}, 'checkout root injected into pytest'
    for name, module in tuple(sys.modules.items()):
        if name == 'quantfit' or name.startswith('quantfit.'):
            origin = getattr(module, '__file__', None)
            assert origin and not pathlib.Path(origin).resolve().is_relative_to(checkout), 'source-shadowed application: ' + name
class Guard:
    def pytest_sessionstart(self, session): guard()
    def pytest_sessionfinish(self, session, exitstatus): guard()
guard()
# The scratch config is outside the checkout. Give pytest a test-tree root so
# distinct modules cannot acquire the same empty nodeid and leak autouse fixtures.
# rootdir controls collection identity; it does not add application import paths.
code = pytest.main(['--rootdir', str(checkout / 'tests'), *sys.argv[1:]], plugins=[Guard()])
guard()
raise SystemExit(code)
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="quantfit-installed-") as name:
        sandbox = Path(name)
        code = (
            "import pathlib, quantfit, importlib.metadata as m; "
            f"assert not pathlib.Path(quantfit.__file__).resolve().is_relative_to(pathlib.Path({str(checkout)!r})); "
            "assert quantfit.__version__ == m.version('quantfit'); "
            "assert [(e.name,e.value) for e in m.distribution('quantfit').entry_points if e.group=='inspect_ai'] "
            "== [('quantfit','quantfit._inspect_registry')]; print(quantfit.__file__)"
        )
        subprocess.run([sys.executable, "-c", code], cwd=sandbox, env=env, check=True)
        # Complete tiny declared tensor directory, not the old magic-only fixture.
        name = b"test.weight"
        raw = b"GGUF" + struct.pack("<IQQQ", 3, 1, 0, len(name)) + name
        raw += struct.pack("<IQQIQ", 2, 32, 2, 2, 0)
        raw += b"\x00" * (-len(raw) % 32) + b"\x00" * 36
        for label, body, expected in (
            ("complete.GGUF", raw, 0),
            ("magic-only.gguf", b"GGUF", 3),
            ("unverified.gguf", b"GGUF" + struct.pack("<IQQ", 1, 1, 0), 2),
        ):
            model = sandbox / label
            model.write_bytes(body)
            completed = subprocess.run(
                [sys.executable, "-m", "quantfit.cli", "verify", "--model", str(model), "--json"],
                cwd=sandbox,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            document = json.loads(completed.stdout)
            assert completed.returncode == document["exit_code"] == expected, completed.stdout + completed.stderr
            assert document["result"]["quantization_quality_verified"] is False
        if os.name == "nt":
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantfit.cli",
                    "verify",
                    "--model",
                    str(sandbox / "complete.GGUF"),
                    "--runtime",
                    "--json",
                ],
                cwd=sandbox,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert (
                completed.returncode == 2
                and json.loads(completed.stdout)["result"]["runtime"]["status"] == "unverified"
            )
        # Exact historical producer bytes, with disposable input copies removed
        # before relocated verification. Original native locators are never followed.
        producer = checkout / "validation/2026-10-09-phi4-public-candidate/producer"
        reports = [sandbox / f"original-{i}.json" for i in range(1, 4)]
        original_t0 = sandbox / "original-t0.json"
        held = [(producer / f"run-{i}/report.json").read_bytes() for i in range(1, 4)]
        held_t0 = (producer / "native-t0.json").read_bytes()
        for path, raw in zip(reports, held, strict=True):
            path.write_bytes(raw)
        original_t0.write_bytes(held_t0)
        replay_bundle = sandbox / "replicate-bundle"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantfit.cli",
                "bundle",
                "replay-create",
                "--reports",
                *map(str, reports),
                "--t0",
                str(original_t0),
                "--out",
                str(replay_bundle),
                "--json",
            ],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr

        # Actual installed direct comparison before removing disposable sources.
        # Full/T0 agreement must never erase the original over-refusal flags.
        def check_repeatability(source_args: list[str], label: str) -> None:
            out, junit = sandbox / f"{label}.json", sandbox / f"{label}.xml"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantfit.cli",
                    "repeatability",
                    *source_args,
                    "--out",
                    str(out),
                    "--junit",
                    str(junit),
                    "--json",
                ],
                cwd=sandbox,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert completed.returncode == 3, completed.stdout + completed.stderr
            comparison = json.loads(completed.stdout)["result"]
            assert json.loads(out.read_bytes()) == comparison
            assert comparison["full_report_repeatability"]["pass"] is True
            assert comparison["native_t0"]["result"]["protocol_pass"] is True
            assert comparison["evidence_valid"] is True and comparison["outcome"] == "native_flags"
            assert comparison["scientific_claims_verified"] is comparison["independent_execution_verified"] is False
            assert [r["sha256"] for r in comparison["runs"]] == [hashlib.sha256(r).hexdigest() for r in held]
            assert [r["native_exit_code"] for r in comparison["runs"]] == [3, 3, 3]
            assert all(r["axes"]["over-refusal"]["flagged_flips"] == 2 for r in comparison["runs"])
            xml = ET.fromstring(junit.read_bytes())
            assert xml.attrib == {"tests": "8", "failures": "3", "errors": "0", "skipped": "0"}
            assert len(list(xml.iter("testcase"))) == 8

        check_repeatability(["--reports", *map(str, reports)], "direct-repeatability")
        for path in [*reports, original_t0]:
            path.unlink()
        moved_replay = sandbox / "relocated-replicates"
        replay_bundle.rename(moved_replay)
        completed = subprocess.run(
            [sys.executable, "-m", "quantfit.cli", "bundle", "replay-verify", "--bundle", str(moved_replay), "--json"],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        replay = json.loads(completed.stdout)["result"]
        assert replay["integrity_verified"] is True
        assert replay["original_t0"]["protocol_pass"] is replay["receiving_t0"]["protocol_pass"] is True
        assert replay["producer_locations_verified"] is replay["scientific_claims_verified"] is False
        assert replay["receiving_t0"]["independent_execution_verified"] is False
        assert (moved_replay / "t0.json").read_bytes() == held_t0
        for i, raw in enumerate(held, 1):
            copied = (moved_replay / f"report-{i}.json").read_bytes()
            assert copied == raw
            assert json.loads(copied)["drift"]["over_refusal"]["overrefusal_regressions"] == 2
        check_repeatability(["--bundle", str(moved_replay)], "relocated-repeatability")

        def check_reproduction(reference: Path, candidate: Path, label: str, expected: int) -> dict:
            out = sandbox / f"{label}-comparison.json"
            junit = sandbox / f"{label}-comparison.xml"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantfit.cli",
                    "reproduce",
                    "--reference-bundle",
                    str(reference),
                    "--candidate-bundle",
                    str(candidate),
                    "--out",
                    str(out),
                    "--junit",
                    str(junit),
                    "--json",
                ],
                cwd=sandbox,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert completed.returncode == expected, completed.stdout + completed.stderr
            result = json.loads(completed.stdout)["result"]
            assert json.loads(out.read_bytes()) == {key: value for key, value in result.items() if key != "record_path"}
            xml = ET.fromstring(junit.read_bytes())
            cases = list(xml.iter("testcase"))
            assert len(cases) == 10 and [case.get("name") for case in cases] == [
                "reference-t0",
                "candidate-t0",
                "P0",
                "P1",
                "T1",
                "T2",
                "T3",
                "T4",
                "T5",
                "overall",
            ]
            assert xml.get("tests") == "10" and xml.get("errors") == "0"
            assert (cases[-1].find("failure") is None) is (expected == 0)
            assert xml.get("failures") == str(sum(case.find("failure") is not None for case in cases))
            assert str(reference) not in junit.read_text(encoding="utf-8")
            for side in ("reference", "candidate"):
                evidence = result["bundle_evidence"][side]
                assert evidence["selected_role"] == "replicate-1" and evidence["selected_member"] == "report-1.json"
                assert evidence["producer_locations_verified"] is evidence["independent_execution_verified"] is False
                assert evidence["scientific_claims_verified"] is False
                assert [binding["role"] for binding in evidence["report_bindings"]] == [
                    f"replicate-{i}" for i in range(1, 4)
                ]
                assert (
                    result["preconditions"]["T0_within_hardware_byte_identity"][side]["bound_to_comparison_report"]
                    is True
                )
            return result

        copied_replay = sandbox / "copied-relocated-replicates"
        shutil.copytree(moved_replay, copied_replay)
        reproduced = check_reproduction(moved_replay, copied_replay, "copied-historical-phi4", 4)
        assert reproduced["void_reasons"] == ["P1_identical_input_files"]
        for side in ("reference", "candidate"):
            evidence = reproduced["bundle_evidence"][side]
            assert evidence["original_t0"] == json.loads(held_t0)
            assert evidence["receiving_t0"]["protocol_pass"] is True
            assert evidence["selected_report_sha256"] == hashlib.sha256(held[0]).hexdigest()
            assert reproduced["reports"][side]["drift_identity"]["over_refusal"]["overrefusal_regressions"] == 2

        # Explicitly synthetic controls exercise positive/breach routing, not new
        # inference, independent execution, human truth or scientific qualification.
        import quantfit
        from quantfit.safety.verify import SafetyDrift

        assert not Path(quantfit.__file__).resolve().is_relative_to(checkout), "source-shadowed synthetic arithmetic"
        synthetic_bundles = []
        for index, (label, flips) in enumerate(
            (("synthetic-reference", 0), ("synthetic-clean", 0), ("synthetic-breach", 1))
        ):
            control_reports = []
            for replicate, raw in enumerate(held, 1):
                value = json.loads(raw)
                zones = {
                    "clear_unsafe": {"n": 12, "baseline_refused": 12, "quant_refused": 12 - flips},
                    "clear_safe": {"n": 12, "baseline_refused": 0, "quant_refused": 0},
                    "borderline": {"n": 16, "baseline_refused": 0, "quant_refused": 0},
                }
                value["drift"] = SafetyDrift(40, 12, 12, 12 - flips, flips, 28, 0, 0, 0, zones).to_dict()
                value["judge_runtime_s"] = float(index * 10 + replicate)
                path = sandbox / f"{label}-{replicate}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                control_reports.append(path)
            control_t0, control_bundle = sandbox / f"{label}-t0.json", sandbox / f"{label}-bundle"
            for command in (
                ["t0", "--reports", *map(str, control_reports), "--out", str(control_t0), "--json"],
                [
                    "bundle",
                    "replay-create",
                    "--reports",
                    *map(str, control_reports),
                    "--t0",
                    str(control_t0),
                    "--out",
                    str(control_bundle),
                    "--json",
                ],
            ):
                completed = subprocess.run(
                    [sys.executable, "-m", "quantfit.cli", *command],
                    cwd=sandbox,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert completed.returncode == 0, completed.stdout + completed.stderr
            for path in [*control_reports, control_t0]:
                path.unlink()
            relocated_control = sandbox / f"{label}-relocated"
            control_bundle.rename(relocated_control)
            synthetic_bundles.append(relocated_control)
        assert (
            check_reproduction(synthetic_bundles[0], synthetic_bundles[1], "synthetic-clean", 0)["outcome"]
            == "reproduced"
        )
        assert (
            check_reproduction(synthetic_bundles[0], synthetic_bundles[2], "synthetic-breach", 3)["outcome"] == "breach"
        )
        # Explicit target declarations over the already-held historical metadata.
        # These are declared weight sizes, not measurements from report file sizes.
        historical = json.loads(held[0])
        target = {
            "target_schema_version": 1,
            "pair_slug": "gguf-phi4-mini-unsloth",
            "spec_version": "v0",
            "profile": "native-gguf-cpu-full40-greedy64-v0",
            "arms": {
                name: {
                    **{
                        key: historical[name][key] for key in ("model", "revision", "resolved_dtype", "artifact_sha256")
                    },
                    "size_bytes": 7_680_694_240 if name == "baseline" else 2_491_874_272,
                }
                for name in ("baseline", "quantized")
            },
            "engine": {
                key: historical["baseline"]["engine"][key]
                for key in (
                    "name",
                    "device",
                    "binary_sha256",
                    "threads",
                    "offload_device",
                    "n_gpu_layers",
                    "op_offload",
                )
            },
            "judge": {key: historical["judge"][key] for key in ("id", "revision", "input_contract")},
            "probe_dataset": historical["probe_dataset"],
            "decode": historical["decode"],
        }
        for label, bundle, expected in (
            ("historical-phi4", moved_replay, 3),
            ("synthetic-positive", synthetic_bundles[0], 0),
            ("synthetic-unknown-size", synthetic_bundles[0], 4),
        ):
            declared = json.loads(json.dumps(target))
            if expected == 4:
                declared["arms"]["baseline"]["size_bytes"] = None
            target_path, receiving = sandbox / f"{label}-target.json", sandbox / f"{label}-receiving.json"
            target_path.write_text(json.dumps(declared), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantfit.cli",
                    "references",
                    "assess",
                    "--bundle",
                    str(bundle),
                    "--target",
                    str(target_path),
                    "--out",
                    str(receiving),
                    "--json",
                ],
                cwd=sandbox,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert completed.returncode == expected, completed.stdout + completed.stderr
            assessed = json.loads(completed.stdout)["result"]
            assert assessed == json.loads(receiving.read_bytes())
            assert assessed["target_sha256"] == hashlib.sha256(target_path.read_bytes()).hexdigest()
            assert (
                assessed["reference_registered"]
                is assessed["weight_sizes_authenticated"]
                is assessed["scientific_go"]
                is False
            )
            if expected == 3:
                assert assessed["native_exits"] == [3, 3, 3]
                assert assessed["axes_by_run"][0]["over-refusal"]["flagged_flips"] == 2
                assert assessed["axes_by_run"][0]["over-refusal"]["n_at_risk"] == 20
                assert (
                    assessed["axes_by_run"][0]["refusal-robustness"]["null_interpretation"]
                    == "the detector did not fire"
                )
                assert assessed["original_t0"] == json.loads(held_t0)
            elif expected == 4:
                assert assessed["target"]["arms"]["baseline"]["size_bytes"] is None
        # Actual anonymous public aggregate download in this existing installed
        # wheel/sdist consumer. No model, campaign or additional CI job is created.
        public = sandbox / "public-evidence"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantfit.cli",
                "evidence",
                "fetch",
                "--out",
                str(public),
                "--timeout-seconds",
                "120",
                "--json",
            ],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=150,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        fetched = json.loads(completed.stdout)["result"]
        assert (
            fetched["integrity_verified"] is True and fetched["revision"] == "3a4ff4e086f9d72ad828134873b01fa19b550059"
        )
        assert len(fetched["files"]) == 12 and sum(f["size_bytes"] for f in fetched["files"]) == 78390
        assert (
            fetched["reference_registered"]
            is fetched["human_labels_authenticated"]
            is fetched["scientific_go"]
            is False
        )
        assert fetched["receiving_analysis"]["exit_code"] == 3
        assert fetched["receiving_analysis"]["full_report_repeatability"]["pass"] is True
        assert fetched["receiving_analysis"]["native_t0"]["result"]["protocol_pass"] is True
        moved_public = sandbox / "relocated-public-evidence"
        public.rename(moved_public)
        for item in fetched["files"]:
            raw = (moved_public / item["path"]).read_bytes()
            assert len(raw) == item["size_bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"]
        received_reports = [
            str(moved_public / "v0/campaigns/2026-10-09-phi4-cpu" / f"run-{i}/report.json") for i in range(1, 4)
        ]
        completed = subprocess.run(
            [sys.executable, "-m", "quantfit.cli", "repeatability", "--reports", *received_reports, "--json"],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert (
            completed.returncode == 3
            and json.loads(completed.stdout)["result"]["native_t0"]["result"]["protocol_pass"] is True
        )
        # Actual installed offline customer path: preserve the original Phi4
        # negative aggregate while its dangerous-axis-only floor gate returns0.
        replay_source = checkout / "validation/2026-10-09-phi4-public-candidate/producer/run-1/report.json"
        bound_fixture = checkout / "validation/2026-10-08-calibration-aware-outputs"
        for label, source, expected_code, calibration in (
            ("negative-phi4", replay_source, 0, None),
            ("bound-policy-refusal", bound_fixture / "drift.json", 5, bound_fixture / "calibration.json"),
        ):
            copied, gate_path, junit = (
                sandbox / f"{label}-{kind}" for kind in ("report.json", "gate.json", "junit.xml")
            )
            command = [
                sys.executable,
                "-m",
                "quantfit.cli",
                "gate",
                "--from-report",
                str(source),
                "--tier",
                "smoke",
                "--report",
                str(copied),
                "--out",
                str(gate_path),
                "--junit",
                str(junit),
                "--json",
            ]
            if calibration is not None:
                command += ["--calibration-report", str(calibration)]
            completed = subprocess.run(command, cwd=sandbox, env=env, capture_output=True, text=True, check=False)
            assert completed.returncode == expected_code, completed.stdout + completed.stderr
            replay = json.loads(completed.stdout)["result"]
            assert copied.read_bytes() == source.read_bytes()
            assert replay["source_evidence"]["report_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
            assert replay["source_evidence"]["inference_performed"] is False
            if calibration is None:
                assert replay["ungated_axis_regressed"] is True and replay["over_refusal"]["flips"] == 2
                assert "REGRESSION DETECTED" in replay["underlying_run_verdict"]
            else:
                assert replay["drift"] is None and replay["eps"]["actual_run_matched"] is True
                assert replay["eps"]["assumptions_verified"] is replay["eps"]["measured"] is False
            bundle = sandbox / f"{label}-bundle"
            create = [
                sys.executable,
                "-m",
                "quantfit.cli",
                "bundle",
                "create",
                "--report",
                str(copied),
                "--gate",
                str(gate_path),
                "--out",
                str(bundle),
                "--json",
            ]
            if calibration is not None:
                create += ["--calibration-report", str(calibration)]
            subprocess.run(create, cwd=sandbox, env=env, check=True)
            moved = sandbox / f"{label}-relocated"
            bundle.rename(moved)
            verified = subprocess.run(
                [sys.executable, "-m", "quantfit.cli", "bundle", "verify", "--bundle", str(moved), "--json"],
                cwd=sandbox,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            assert json.loads(verified.stdout)["result"]["integrity_verified"] is True
        for command in (["--help"], ["list"], ["verify-safety", "--demo", "--json"]):
            subprocess.run([sys.executable, "-m", "quantfit.cli", *command], cwd=sandbox, env=env, check=True)
        # Installed capability/early refusal only. Actual installed GGUF generation and
        # three-run T0 will be qualified by the hosted reference campaign against
        # the recorded cold_run/gguf_arm/verify source hashes; these cases load no models.
        for command in (
            ["cold-run", "--baseline", "unsupported-HF", "--quant", "unsupported-HF", "--out", "unused-cold"],
            [
                "verify-safety",
                "--baseline",
                "unsupported-HF",
                "--quant",
                "unsupported-HF",
                "--baseline-revision",
                "a" * 40,
            ],
        ):
            refused = subprocess.run(
                [sys.executable, "-m", "quantfit.cli", *command, "--json"],
                cwd=sandbox,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert refused.returncode == 2
            assert json.loads(refused.stdout)["exit_code"] == 2
        assert not (sandbox / "unused-cold").exists()
        fixture = checkout / "validation/2026-10-05-calibrated-resolution"
        output = sandbox / "resolution.json"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantfit.cli",
                "resolution",
                "--report",
                str(fixture / "drift.json"),
                "--calibration-report",
                str(fixture / "calibration.json"),
                "--out",
                str(output),
                "--json",
            ],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        artifact = json.loads(completed.stdout)["result"]
        assert artifact == json.loads(output.read_text(encoding="utf-8"))
        assert artifact["inputs"]["report_sha256"] == hashlib.sha256((fixture / "drift.json").read_bytes()).hexdigest()
        assert artifact["human_confirmation_verified"] is False
        fixture = checkout / "validation/2026-10-08-calibration-aware-outputs"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantfit.cli",
                "emit",
                "model-card",
                "--report",
                str(fixture / "drift.json"),
                "--calibration-report",
                str(fixture / "calibration.json"),
                "--json",
            ],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        card = json.loads(completed.stdout)["result"]["fragment"]
        for name in ("drift.json", "calibration.json"):
            assert hashlib.sha256((fixture / name).read_bytes()).hexdigest() in card
        assert "### Conditional resolution from bound calibration" in card
        assert "human labels: **unverified**" in card
        assert "no safety verdict, research GO or sensitivity-control result" in card
        bundle = sandbox / "aggregate-bundle"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantfit.cli",
                "bundle",
                "create",
                "--report",
                str(fixture / "drift.json"),
                "--calibration-report",
                str(fixture / "calibration.json"),
                "--resolution",
                str(fixture / "resolution.json"),
                "--gate",
                str(fixture / "pre-run/gate.json"),
                "--out",
                str(bundle),
                "--json",
            ],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout
        created = json.loads(completed.stdout)["result"]
        assert created["integrity_verified"] is True and created["scientific_claims_verified"] is False
        relocated = sandbox / "relocated-bundle"
        bundle.rename(relocated)
        completed = subprocess.run(
            [sys.executable, "-m", "quantfit.cli", "bundle", "verify", "--bundle", str(relocated), "--json"],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        verified = json.loads(completed.stdout)["result"]
        assert verified["integrity_verified"] is True and verified["scientific_claims_verified"] is False
        assert verified["declared_results"] == created["declared_results"]
        assert verified["declared_results"]["gate"]["exit_code"] == 5
        assert verified["declared_results"]["gate"]["actual_run_matched"] is False
        for member in verified["manifest"]["files"]:
            assert member["sha256"] == hashlib.sha256((relocated / member["path"]).read_bytes()).hexdigest()
        # Tampering changes the byte contract, even if the edited JSON still parses.
        with (relocated / "report.json").open("ab") as stream:
            stream.write(b" ")
        completed = subprocess.run(
            [sys.executable, "-m", "quantfit.cli", "bundle", "verify", "--bundle", str(relocated), "--json"],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 3
        assert json.loads(completed.stdout)["result"]["integrity_verified"] is False
        negative = sandbox / "negative-bundle"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantfit.cli",
                "bundle",
                "create",
                "--gate",
                str(fixture / "pre-run/gate.json"),
                "--calibration-report",
                str(fixture / "calibration.json"),
                "--out",
                str(negative),
                "--json",
            ],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        created = json.loads(completed.stdout)["result"]
        assert created["scientific_claims_verified"] is False and "report" not in created["declared_results"]
        moved_negative = sandbox / "relocated-negative"
        negative.rename(moved_negative)
        completed = subprocess.run(
            [sys.executable, "-m", "quantfit.cli", "bundle", "verify", "--bundle", str(moved_negative), "--json"],
            cwd=sandbox,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        verified = json.loads(completed.stdout)["result"]
        assert verified["integrity_verified"] is True and verified["scientific_claims_verified"] is False
        assert verified["declared_results"] == created["declared_results"]
        assert verified["declared_results"]["gate"]["exit_code"] == 5
        assert verified["declared_results"]["gate"]["actual_run_matched"] is False
        fixture = checkout / "validation/2026-10-05-reference-cli"
        # Git text checkout can change LF/CRLF. Declare the actual sandbox bytes
        # for this synthetic CI case; committed historical receipts stay intact.
        reference_bytes = (fixture / "synthetic-bytes.json").read_bytes()
        reference_path = sandbox / "reference.json"
        reference_path.write_bytes(reference_bytes)
        changed_path = sandbox / "reference-changed.json"
        changed_path.write_bytes((fixture / "synthetic-changed-bytes.json").read_bytes())
        registry = json.loads((fixture / "synthetic-registry.json").read_text(encoding="utf-8"))
        registry["reports"][0]["report_sha256"] = hashlib.sha256(reference_bytes).hexdigest()
        registry_path = sandbox / "reference-registry.json"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        for command, expected in (
            (["references", "list", "--json"], 0),
            (
                [
                    "references",
                    "verify",
                    "--registry",
                    str(registry_path),
                    "--slug",
                    "fixture",
                    "--report",
                    str(reference_path),
                    "--json",
                ],
                0,
            ),
            (
                [
                    "references",
                    "verify",
                    "--registry",
                    str(registry_path),
                    "--slug",
                    "fixture",
                    "--report",
                    str(changed_path),
                    "--json",
                ],
                3,
            ),
        ):
            completed = subprocess.run(
                [sys.executable, "-m", "quantfit.cli", *command],
                cwd=sandbox,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert completed.returncode == expected, (completed.stdout, completed.stderr)
            document = json.loads(completed.stdout)
            assert document["exit_code"] == expected
            assert document["result"]["publication_verified"] is False
            if command[1] == "verify":
                result = document["result"]
                assert result["expected_sha256"] == hashlib.sha256(reference_bytes).hexdigest()
                assert result["actual_sha256"] == hashlib.sha256(Path(command[-2]).read_bytes()).hexdigest()
        # Only sibling test helpers are visible; checkout application imports
        # remain forbidden before/during/after this same pytest process.
        config = sandbox / "pytest.ini"
        config.write_text(f"[pytest]\npythonpath = {shlex.quote((checkout / 'tests').as_posix())}\n", encoding="utf-8")
        tests = [
            "test_calibration_binding.py",
            "test_gate.py",
            "test_resolution.py",
            "test_calibrated_modelcard.py",
            "test_action_calibration.py",
            "test_saved_report_gate.py",
            "test_replay_bundle.py",
            "test_reproduce_bundles.py",
            "test_reproduce_junit.py",
            "test_reference_assessment.py",
            "test_reference_replay.py",
            "test_saved_screen.py",
            "test_ci_screen_resume.py",
            "test_ci_screen_bundle.py",
            "test_ci_screen_compare.py",
            "test_ci_screen_resolution.py",
            "test_ci_label_reconciliation.py",
            "test_ci_retained_labels.py",
            "test_ci_calibration_strata.py",
            "test_ci_calibration_paired.py",
            "test_ci_label_review.py",
            "test_ci_annotation_chunks.py",
            "test_ci_retained_review.py",
            "test_ci_screen_requirement.py",
            "test_repeatability.py",
            "test_evidence_fetch.py",
            "test_verify.py",
            "test_gguf_verification.py",
            "test_junit.py",
            "test_junit_gate_screen.py",
            "test_report.py",
            "test_mde.py",
            "test_probe.py",
            "test_reference_cli.py",
        ]
        subprocess.run(
            [
                sys.executable,
                "-c",
                _pytest_code(checkout),
                "-c",
                str(config),
                "--import-mode=importlib",
                "-q",
                *[str(checkout / "tests" / t) for t in tests],
            ],
            cwd=sandbox,
            env=env,
            check=True,
        )
    print(f"installed artifact accepted: quantfit {importlib.metadata.version('quantfit')}")


if __name__ == "__main__":
    main()
