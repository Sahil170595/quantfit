"""Preserve ten exact producer buffers; independently recheck relocated sources."""

import hashlib
import json
import subprocess
from pathlib import Path

from tools import ci_reference_campaign as campaign

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
INPUT = Path("C:/tmp/qf-next-pr-receipts-20261008")
SOURCE = INPUT / "hosted-reference-campaign-37890682118"
PRODUCER = OUT / "producer"
MEASURED_HEAD = "2997c9304f4c0de02f2299fe7c42f1693539bf6d"


def write(path, value):
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


assert {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*") if p.is_file()} == set(campaign.PUBLIC_FILES)
proof_raw = (INPUT / "root-quant5-hosted-verified.json").read_bytes()
proof = json.loads(proof_raw)
expected = {item["path"]: item for item in proof["public_source_files"]}
files = []
for name in campaign.PUBLIC_FILES:
    raw = (SOURCE / name).read_bytes()
    item = expected[name]
    assert digest(raw) == item["sha256"] and len(raw) == item["size_bytes"]
    if name.endswith(".json"):
        campaign._aggregate(json.loads(raw))
    target = PRODUCER / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == raw
    else:
        target.write_bytes(raw)
    files.append({"path": name, "sha256": digest(raw), "size_bytes": len(raw)})
(OUT / "root-hosted-verification.json").write_bytes(proof_raw)
producer = json.loads((PRODUCER / "campaign.json").read_bytes())
assert producer["candidate"]["source_head"] == MEASURED_HEAD
assert producer["omitted_public_token_flag"] is True and "--max-new-tokens" not in producer["public_argv"]
assert producer["actual_native_exits"] == [3, 3, 3]
assert producer["reference_eligibility"] == "blocked" and producer["reference_registered"] is False
source_hashes = producer["candidate"]["installed_source_sha256"]
for name, expected_sha in source_hashes.items():
    blob = subprocess.run(["git", "show", MEASURED_HEAD + ":" + name], cwd=ROOT, capture_output=True, check=True).stdout
    assert digest(blob) == expected_sha
assert len(source_hashes) == 46
paths = [PRODUCER / f"run-{i}/report.json" for i in range(1, 4)]
analysis = campaign.assess_reports(paths, binary_sha256=producer["binary"]["executable_sha256"], threads=producer["native_threads_observed"])
original_assessment = json.loads((PRODUCER / "assessment.json").read_bytes())
original_t0 = (PRODUCER / "native-t0.json").read_bytes()
assert analysis["t0"]["protocol_pass"] is True and analysis["full_report_repeatability"]["pass"] is True
assert analysis["full_report_repeatability"] == original_assessment["full_report_repeatability"]
assert analysis["native_exits"] == [3, 3, 3]
assert analysis["eligible_axes_before_publication"] == [] and analysis["registry_admission"] == "blocked"
assert analysis["blocking_reasons"] == ["fresh_flags_without_human_adjudication"]
assert all(run["over-refusal"]["flagged_flips"] == 2 and run["over-refusal"]["n_at_risk"] == 20 and run["refusal-robustness"]["flagged_flips"] == 0 and run["refusal-robustness"]["n_at_risk"] == 12 for run in analysis["axes_by_run"])
assert digest(original_t0) == proof["original_t0_sha256"]
write(OUT / "relocated-t0.json", analysis["t0"])
write(OUT / "relocated-assessment.json", analysis)
assert (PRODUCER / "native-t0.json").read_bytes() == original_t0
write(OUT / "integration-verification.json", {
    "measured_source_head": MEASURED_HEAD,
    "run": proof["run"], "producer_files": files,
    "independently_matched_installed_package_git_modules": len(source_hashes),
    "relocated_t0_pass": True, "full_report_repeatability_pass": True,
    "original_native_t0_bytes_unchanged": True,
    "original_native_t0_sha256": digest(original_t0),
    "relocated_t0_sha256": digest((OUT / "relocated-t0.json").read_bytes()),
    "native_exits": analysis["native_exits"],
    "blocking_reasons": analysis["blocking_reasons"],
    "reference_registered": False, "scientific_go": False,
    "human_labels_authenticated": False, "independent_execution_verified": False,
    "scope": "Actual hosted aggregate sources copied byte-for-byte; local existing validators recheck those bytes after relocation. This is not another model execution or independent hardware reproduction. Original producer locators are historical, not rewritten.",
})
print(json.dumps({"copied_exact_files": len(files), "matched_git_modules": len(source_hashes), "t0": True, "repeatability": True, "native_exits": analysis["native_exits"], "registry": analysis["registry_admission"]}))
