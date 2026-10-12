"""Actual Git index JSON bytes and referenced synthetic report SHA verification."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
files, report_hashes, key_hits = [], 0, []
for path in sorted(OUT.rglob("*.json")):
    if path.name == "byte-check.json":
        continue
    relative = path.relative_to(ROOT).as_posix()
    raw = path.read_bytes()
    blob = subprocess.run(["git", "show", ":" + relative], cwd=ROOT, capture_output=True, check=True).stdout
    assert raw == blob, relative
    value = json.loads(raw)
    files.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw), "git_index_bytes_equal": True})
    if path.name == "assessment.json":
        for source in value["source_reports"]:
            member = Path(source["path"]).read_bytes()
            assert len(member) == source["size_bytes"] and hashlib.sha256(member).hexdigest() == source["sha256"]
            report_hashes += 1
    def walk(item, pointer):
        if isinstance(item, dict):
            for key, child in item.items():
                if re.search(r"prompt|completion|response|text|generation", key, re.IGNORECASE):
                    key_hits.append({"file": relative, "path": pointer + "/" + key, "kind": type(child).__name__})
                walk(child, pointer + "/" + key)
        elif isinstance(item, list):
            for i, child in enumerate(item):
                walk(child, pointer + "/" + str(i))
    walk(value, "")
receipt = {"files_checked": len(files), "files": files, "referenced_report_hashes_checked": report_hashes,
           "broad_raw_field_key_hits": key_hits, "scientific_claims_verified": False,
           "scope": "Only this new local qualification record; original model measurements and publication pending."}
(OUT / "byte-check.json").write_bytes((json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
print(json.dumps({"json_bytes_equal": len(files), "referenced_report_hashes_checked": report_hashes, "raw_key_hits": key_hits}))
