"""Verify new committed evidence bytes, hashes and declared raw-field metadata."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
checked, hits = [], []
for path in sorted(OUT.rglob("*.json")) + sorted((OUT / "producer").rglob("*.md")) + [OUT / "public-dataset-card.md"]:
    if path.name == "byte-check.json":
        continue
    relative = path.relative_to(ROOT).as_posix()
    raw = path.read_bytes()
    blob = subprocess.run(["git", "show", ":" + relative], cwd=ROOT, capture_output=True, check=True).stdout
    assert raw == blob, relative
    checked.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw), "working_index_bytes_equal": True})
    if not path.name.endswith(".json"):
        continue

    def walk(item, pointer):
        if isinstance(item, dict):
            for key, child in item.items():
                if re.search(r"prompt|completion|response|text|generation", key, re.IGNORECASE):
                    assert key == "completion_cache_requested" and child is False, (relative, pointer, key)
                    hits.append({"file": relative, "pointer": pointer + "/" + key, "value": False, "meaning": "Explicitly false cache-request metadata, no payload."})
                walk(child, pointer + "/" + key)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, pointer + "/" + str(index))

    walk(json.loads(raw), "")
producer_files = json.loads((OUT / "integration-verification.json").read_bytes())["producer_files"]
for item in producer_files:
    body = (OUT / "producer" / item["path"]).read_bytes()
    assert len(body) == item["size_bytes"] and hashlib.sha256(body).hexdigest() == item["sha256"]
publication = json.loads((OUT / "public-reference-publication.json").read_bytes())
assert publication["download_verified"] is True and publication["registry_admission"] == "blocked"
record = {"files_checked": len(checked), "files": checked, "exact_producer_hashes_sizes_checked": len(producer_files), "raw_field_metadata_hits": hits,
          "public_commit": publication["commit"], "raw_payloads_found": False, "qualified_reference_count": 0,
          "scope": "Exact Git-index/input bytes, original hosted and anonymous downloaded evidence. Integrity does not authenticate human truth or imply scientific GO."}
(OUT / "byte-check.json").write_bytes((json.dumps(record, indent=2, sort_keys=True) + "\n").encode())
print(json.dumps({"exact_index_files": len(checked), "exact_producer_members": len(producer_files), "permitted_metadata_hits": len(hits), "raw_payloads": False}))
