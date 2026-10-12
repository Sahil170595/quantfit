"""Check anonymous immutable downloads against producer and publication receipts."""

import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
INPUT = Path("C:/tmp/qf-next-pr-receipts-20261008")
DOWNLOADS = INPUT / "reference-publication/downloaded"
PREFIX = "v0/campaigns/2026-10-09-phi4-cpu/"
receipt_raw = (INPUT / "public-reference-publication.json").read_bytes()
receipt = json.loads(receipt_raw)
assert receipt["download_verified"] is True and receipt["public"] is True
assert receipt["commit"] == "3a4ff4e086f9d72ad828134873b01fa19b550059"
assert receipt["repo"] == "Crusadersk/quantfit-reference-reports" and receipt["repo_type"] == "dataset"
assert receipt["registry_admission"] == "blocked" and receipt["reference_registered"] is False
assert receipt["scientific_go"] is False
manifest_raw = (DOWNLOADS / (PREFIX + "manifest.json")).read_bytes()
manifest = json.loads(manifest_raw)
expected = {record["path"]: record for record in manifest["files"]}
assert len(expected) == 10 and manifest["registered_reference_count"] == 0
for record in receipt["files"]:
    name = record["path"]
    raw = (DOWNLOADS / name).read_bytes()
    assert len(raw) == record["size_bytes"] and hashlib.sha256(raw).hexdigest() == record["sha256"]
    if name in expected:
        assert record == expected[name]
        assert raw == (OUT / "producer" / name.removeprefix(PREFIX)).read_bytes()
    elif name == "README.md":
        (OUT / "public-dataset-card.md").write_bytes(raw)
    else:
        assert name == PREFIX + "manifest.json"
assert len(receipt["files"]) == 12
(OUT / "public-manifest.json").write_bytes(manifest_raw)
(OUT / "public-reference-publication.json").write_bytes(receipt_raw)
print(json.dumps({"verified_anonymous_downloads": 12, "exact_producer_matches": 10, "commit": receipt["commit"], "registry_count": 0}))
