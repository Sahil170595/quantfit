"""Private local-source software controls; no Hub, model or judge inference."""

import hashlib
import json
import subprocess
import sys

from test_probe_corpus import rows, software_arms

from quantfit.safety import verify as native
from quantfit.safety.report import DriftReport

pytest_plugins = ["test_probe_corpus"]


def private_rows(tmp_path):
    values = rows(6)
    values[1]["prompt"] = "  exact Ω\r\nstandalone\rNUL\x00end  "
    path = tmp_path / "private.probe-rows.json"
    path.write_bytes(json.dumps(values, ensure_ascii=False).encode("utf-8"))
    return path, values


def test_existing_hub_whole_population_positive(sdk):
    actual = native._load_probes(None)
    assert [p.prompt for p in actual] == [r["prompt"] for r in rows()]
    assert len(actual) == sdk["yielded"] == 40 and sdk["iterations"] == 1


def test_private_builder_pins_actual_whole_bytes(tmp_path):
    from quantfit import LocalProbeCorpus, prepare_probe_bundle

    path, values = private_rows(tmp_path)
    output = tmp_path / "private.probe-bundle.json"
    result = prepare_probe_bundle(str(path), out_path=str(output))
    data = output.read_bytes()
    assert json.loads(data) == {"probe_bundle_schema": 1, "probes": values}
    assert result["sha256"] == hashlib.sha256(data).hexdigest()
    assert result["n_probes"] == 6
    assert LocalProbeCorpus(result["sha256"]).sha256 == result["sha256"]
    assert "prompt" not in json.dumps(result) and str(path) not in json.dumps(result)


def test_native_local_report_and_nonnull_capture_identity(monkeypatch, tmp_path):
    from quantfit import LocalProbeCorpus, prepare_probe_bundle

    path, values = private_rows(tmp_path)
    bundle = tmp_path / "private.probe-bundle.json"
    receipt = prepare_probe_bundle(str(path), out_path=str(bundle))
    source = LocalProbeCorpus(receipt["sha256"])
    calls = software_arms(monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("local corpus must never invoke the Hub loader")

    monkeypatch.setattr(native, "_load_probes", forbidden)
    report_path = tmp_path / "report.json"
    capture_path = tmp_path / "private.capture.jsonl"
    drift = native.verify_safety(
        "controlled/base",
        "controlled/quant",
        probe_corpus=source,
        probe_bundle_path=str(bundle),
        report_path=str(report_path),
        capture_path=str(capture_path),
    )
    expected = {
        "source_kind": "local",
        "format": "quantfit-probe-bundle-v1",
        "sha256": receipt["sha256"],
        "n_probes": 6,
    }
    report = DriftReport.from_json(str(report_path))
    assert report.probe_dataset == expected and drift.probe_corpus == source
    header = json.loads(capture_path.read_bytes().splitlines()[0])
    assert header["binding"] is not None and header["binding_error"] is None
    assert header["binding"]["identity"]["identity_schema"] == 2
    assert header["binding"]["identity"]["probe_dataset"] == expected
    assert calls == [[r["prompt"] for r in values]] * 2
    assert str(bundle) not in json.dumps(json.loads(report_path.read_bytes()))


def test_actual_os_cli_builds_private_bundle(tmp_path):
    path, values = private_rows(tmp_path)
    output = tmp_path / "private.probe-bundle.json"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-X",
            "utf8",
            "-m",
            "quantfit.cli",
            "probes",
            "bundle",
            "--rows",
            str(path),
            "--out",
            str(output),
            "--json",
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8")
    envelope = json.loads(result.stdout)
    assert envelope["exit_code"] == 0
    assert envelope["result"]["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert json.loads(output.read_bytes())["probes"] == values
