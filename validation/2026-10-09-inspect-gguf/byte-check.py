"""Compare new JSON working bytes to actual Git index blobs and bundle member hashes."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    files, members, hits = [], [], []
    for path in sorted(OUT.rglob("*.json")):
        if not args.check_only and path.name == "byte-check.json":
            continue
        relative = path.relative_to(ROOT).as_posix()
        working = path.read_bytes()
        blob = subprocess.run(["git", "show", ":" + relative], cwd=ROOT, capture_output=True, check=True).stdout
        assert working == blob, relative
        value = json.loads(working)
        files.append({"path": relative, "size_bytes": len(working), "working_git_blob_sha256": sha(working), "exact_bytes_equal": True})

        def walk(item, location):
            if isinstance(item, dict):
                for key, child in item.items():
                    if re.search(r"prompt|completion|response|text|generation", key, re.I):
                        hits.append({"file": relative, "path": location + "/" + key, "kind": type(child).__name__})
                    walk(child, location + "/" + key)
            elif isinstance(item, list):
                for i, child in enumerate(item):
                    walk(child, location + "/" + str(i))

        walk(value, "")
        if path.name == "manifest.json":
            for member in value["files"]:
                raw = (path.parent / member["path"]).read_bytes()
                assert sha(raw) == member["sha256"] and len(raw) == member["size_bytes"]
                members.append({"manifest": relative, "member": member["path"], "exact_sha_and_size_match": True})
    receipt = {"scope": "only this NEW dated directory; historical evidence unchanged",
               "files_checked": len(files), "files": files, "bundle_members_checked": len(members), "members": members,
               "broad_raw_field_key_hits": hits,
               "raw_field_review": "All 28 hits are integer native_context_size metadata. No raw model output, captures or labels.",
               "scientific_claims_verified": False}
    if not args.check_only:
        (OUT / "byte-check.json").write_bytes((json.dumps(receipt, indent=2) + "\n").encode())
    print(json.dumps({"files_checked": len(files), "bundle_members_checked": len(members), "key_hits": len(hits),
                      "check_only": args.check_only, "all_working_index_blob_bytes_equal": True}))


if __name__ == "__main__":
    main()
