"""Exact-byte check of new evidence without changing historical receipts."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
files, members, hits = [], 0, []
for path in sorted(OUT.rglob("*.json")):
    if path.name == "atomic-byte-check.json":
        continue
    relative = path.relative_to(ROOT).as_posix()
    raw = path.read_bytes()
    blob = subprocess.run(["git", "show", ":" + relative], cwd=ROOT, capture_output=True, check=True).stdout
    assert raw == blob, relative
    value = json.loads(raw)
    files.append({"path": relative, "size_bytes": len(raw), "working_git_index_sha256": hashlib.sha256(raw).hexdigest(), "exact_bytes_equal": True})
    if path.name == "assessment.json":
        for record in value["source_reports"]:
            body = Path(record["path"]).read_bytes()
            assert len(body) == record["size_bytes"] and hashlib.sha256(body).hexdigest() == record["sha256"]
            members += 1

    def walk(item, pointer):
        if isinstance(item, dict):
            for key, child in item.items():
                if re.search(r"prompt|completion|response|text|generation", key, re.IGNORECASE):
                    hits.append({"file": relative, "path": pointer + "/" + key, "kind": type(child).__name__})
                walk(child, pointer + "/" + key)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, pointer + "/" + str(index))

    walk(value, "")
result = {"files_checked": len(files), "files": files, "source_report_hashes_sizes_checked": members,
          "broad_raw_field_key_hits": hits, "scientific_claims_verified": False,
          "scope": "New dated local initial/corrected/atomic qualification only; earlier records unchanged. No native model/public-byte proof."}
(OUT / "atomic-byte-check.json").write_bytes((json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
print(json.dumps({"json_bytes_equal": len(files), "report_hashes_sizes_checked": members, "raw_key_hits": hits}))
