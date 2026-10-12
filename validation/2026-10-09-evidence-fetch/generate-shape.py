"""Derive the fixed installed shape from the approved byte-verified publication."""

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "validation/2026-10-09-phi4-public-candidate"
PREFIX = "v0/campaigns/2026-10-09-phi4-cpu/"
inventory = json.loads((SOURCE / "public-reference-publication.json").read_bytes())["files"]


def shape(value):
    if isinstance(value, dict):
        return {k: shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(v) for v in value]
    return "null" if value is None else "true" if value is True else "false" if value is False else type(value).__name__


shapes = {}
for item in inventory:
    name = item["path"]
    local = SOURCE / "public-dataset-card.md" if name == "README.md" else SOURCE / "public-manifest.json" if name == PREFIX + "manifest.json" else SOURCE / "producer" / name.removeprefix(PREFIX)
    raw = local.read_bytes()
    assert len(raw) == item["size_bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"]
    if name.endswith(".json"):
        shapes[name] = shape(json.loads(raw))
counts = Counter()


def key(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def count(value):
    if isinstance(value, (dict, list)):
        counts[key(value)] += 1
        for child in value.values() if isinstance(value, dict) else value:
            count(child)


for value in shapes.values():
    count(value)
templates = {}
names = {}


def compact(value):
    if not isinstance(value, (dict, list)):
        return value
    canonical = key(value)
    if canonical in names:
        return {"$ref": names[canonical]}
    children = {k: compact(v) for k, v in value.items()} if isinstance(value, dict) else [compact(v) for v in value]
    if counts[canonical] > 1:
        name = "shape_" + str(len(templates) + 1)
        templates[name] = children
        names[canonical] = name
        return {"$ref": name}
    return children


files = {name: compact(value) for name, value in shapes.items()}
result = {"shape_version": 1, "source_commit": "3a4ff4e086f9d72ad828134873b01fa19b550059", "templates": templates, "files": files}
target = ROOT / "quantfit/data/reference-evidence-shape-v0.json"
target.parent.mkdir(exist_ok=True)
target.write_bytes((json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
print(json.dumps({"files": len(files), "shared_shapes": len(templates), "bytes": target.stat().st_size}))
