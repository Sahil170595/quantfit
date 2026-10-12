"""Historical and explicitly synthetic offline source-CLI observations; no inference."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from quantfit.safety.verify import SafetyDrift

OUT = Path(__file__).resolve().parent
SOURCE = ROOT / "validation/2026-10-09-phi4-public-candidate/producer"
observations = []


def observe(label, source_args, expected, synthetic):
    artifact, junit = OUT / f"{label}.json", OUT / f"{label}.xml"
    argv = [sys.executable, "-m", "quantfit.cli", "repeatability", *source_args,
            "--out", str(artifact), "--junit", str(junit), "--json"]
    process = subprocess.run(argv, cwd=ROOT, capture_output=True, check=False, timeout=30)
    envelope = json.loads(process.stdout)
    assert envelope["exit_code"] == process.returncode == expected
    assert "error" not in envelope and envelope["result"] == json.loads(artifact.read_bytes())
    result = envelope["result"]
    xml = ET.fromstring(junit.read_bytes())
    cases = list(xml.iter("testcase"))
    assert len(cases) == int(xml.attrib["tests"]) == 8
    assert all(int(xml.attrib[label]) == sum(c.find(tag) is not None for c in cases)
               for label, tag in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped")))
    observations.append({"case": label, "synthetic": synthetic, "argv": argv,
                         "exit_code": process.returncode, "outcome": result["outcome"],
                         "full_report_pass": result["full_report_repeatability"]["pass"],
                         "native_t0_status": result["native_t0"]["status"],
                         "original_native_exits": [r["native_exit_code"] for r in result["runs"]],
                         "report_sha256": [r["sha256"] for r in result["runs"]],
                         "junit_counts": xml.attrib, "stderr_bytes": len(process.stderr)})


observe("historical-direct", ["--reports", *[str(SOURCE / f"run-{i}/report.json") for i in range(1, 4)]], 3, False)
bundle = ROOT / "validation/2026-10-09-replicate-bundles/historical-phi4/relocated"
observe("historical-relocated", ["--bundle", str(bundle)], 3, False)
for name, unsafe, flips, code in (("pass", 12, 0, 0), ("flag", 12, 1, 3), ("unmeasured", 0, 0, 4), ("refused", 12, 0, 2)):
    folder = OUT / f"synthetic-{name}-inputs"
    folder.mkdir(exist_ok=False)
    paths = []
    for i in range(1, 4):
        value = json.loads((SOURCE / f"run-{i}/report.json").read_bytes())
        zones = {"clear_unsafe": {"n": 12, "baseline_refused": unsafe, "quant_refused": unsafe - flips},
                 "clear_safe": {"n": 12, "baseline_refused": 0, "quant_refused": 0},
                 "borderline": {"n": 16, "baseline_refused": 0, "quant_refused": 0}}
        value["drift"] = SafetyDrift(40, 12, unsafe, unsafe - flips, flips, 28, 0, 0, 0, zones).to_dict()
        if name == "refused" and i == 2:
            value["env"]["python"] = "explicitly synthetic different environment"
        path = folder / f"report-{i}.json"
        path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())
        paths.append(str(path))
    observe(f"synthetic-{name}", ["--reports", *paths], code, True)
prose = subprocess.run([sys.executable, "-m", "quantfit.cli", "repeatability", "--bundle", str(bundle)],
                       cwd=ROOT, capture_output=True, check=False, timeout=30)
assert prose.returncode == 3 and b"Full report agreement: PASS" in prose.stdout
(OUT / "historical-prose.log").write_bytes(prose.stdout)
record = {"schema_version": 1, "actual_cli_invocations": 7, "new_inference_performed": False,
          "new_network_calls": 0, "source_product_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
          "observations": observations, "historical_prose_exit": prose.returncode,
          "historical_original_bytes_sha256": [hashlib.sha256((SOURCE / f"run-{i}/report.json").read_bytes()).hexdigest() for i in range(1, 4)],
          "scope": "Source CLI only; historical Phi4 aggregates and explicitly synthetic policy cases, no installed-distribution proof."}
(OUT / "functional.json").write_bytes((json.dumps(record, indent=2, sort_keys=True) + "\n").encode())
print("PASS: seven actual offline source CLI invocations; historical negative preserved and synthetic 0/3/4/2 distinct")
