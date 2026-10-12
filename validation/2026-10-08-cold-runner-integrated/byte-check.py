"""Check actual Git index/HEAD bytes, and emitted member hashes; no self-hash claims."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PREFIX = OUT.relative_to(ROOT).as_posix()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--head", default=None, help="default reads staged blobs; HEAD reads committed blobs")
    args = parser.parse_args()
    checked = []
    for file in sorted(OUT.rglob("*.json")):
        path = file.relative_to(ROOT).as_posix()
        data = file.read_bytes()
        spec = f"{args.head}:{path}" if args.head else f":{path}"
        blob = subprocess.run(["git", "show", spec], cwd=ROOT, capture_output=True, check=True).stdout
        assert blob == data, path
        checked.append({"path": path, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)})
    members = 0
    for file in OUT.glob("*/cold-run.json"):
        receipt = json.loads(file.read_bytes())
        for run in receipt["runs"]:
            for key in ("report", "final_report"):
                member = run.get(key)
                if member:
                    relative = member["path"][member["path"].index(PREFIX):]
                    raw = (ROOT / relative).read_bytes()
                    assert hashlib.sha256(raw).hexdigest() == member["sha256"]
                    assert len(raw) == member["size_bytes"]
                    members += 1
        if receipt["t0"]:
            for member in receipt["t0"]["reports"]:
                relative = member["path"][member["path"].index(PREFIX):]
                assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == member["report_sha256"]
                members += 1
    # Raw-field walk: only the explicit no-cache boolean may match these private-data
    # tokens. The remaining matched source-file locator is a metadata path, not raw data.
    def walk(value, context):
        if isinstance(value, dict):
            for key, child in value.items():
                if any(token in key.lower() for token in ("prompt", "completion", "response", "generation", "text")):
                    assert key == "completion_cache_requested" and child is False, (context, key)
                walk(child, f"{context}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{context}[{index}]")
    for file in OUT.rglob("*.json"):
        walk(json.loads(file.read_bytes()), str(file.relative_to(ROOT)))
    print(json.dumps({"all_new_json_git_blob_equals_working": len(checked), "emitted_member_hash_checks": members,
                      "raw_fields_retained": False, "source": args.head or "index"}))


if __name__ == "__main__":
    main()
