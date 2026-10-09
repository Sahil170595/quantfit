"""Actual source CLI with a fixture HTTP transport; no external download/inference."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / "validation/2026-10-09-phi4-public-candidate"
code = f'''
import sys
sys.path.insert(0,{str(ROOT)!r})
from pathlib import Path
import httpx
from quantfit import evidence
from quantfit.cli import main
source=Path({str(SOURCE)!r})
held={{path:(source/'public-dataset-card.md' if path=='README.md' else source/'public-manifest.json' if path==evidence.PREFIX+'manifest.json' else source/'producer'/path.removeprefix(evidence.PREFIX)).read_bytes() for path,_,_ in evidence.INVENTORY}}
class Stream(httpx.AsyncByteStream):
 async def __aiter__(self):
  for i in range(0,len(self.raw),257): yield self.raw[i:i+257]
 async def aclose(self): pass
def handle(request):
 assert 'authorization' not in request.headers and 'cookie' not in request.headers
 path=request.url.path.split(evidence.REVISION+'/',1)[1]
 stream=Stream();stream.raw=held[path]
 return httpx.Response(200,stream=stream)
factory=httpx.AsyncClient
evidence.httpx.AsyncClient=lambda **kw:factory(**kw,transport=httpx.MockTransport(handle))
raise SystemExit(main(sys.argv[1:]))
'''
target = OUT / "received"
argv = [sys.executable, "-c", code, "evidence", "fetch", "--out", str(target), "--json"]
process = subprocess.run(argv, cwd=ROOT, capture_output=True, check=False, timeout=30)
assert process.returncode == 0, process.stdout + process.stderr
envelope = json.loads(process.stdout)
result = envelope["result"]
assert result["receiving_analysis"]["exit_code"] == 3 and len(result["files"]) == 12
(OUT / "functional-fetch.json").write_bytes(process.stdout)
moved = OUT / "relocated"
target.rename(moved)
members = []
for item in result["files"]:
    raw = (moved / item["path"]).read_bytes()
    assert len(raw) == item["size_bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"]
    members.append(item)
prefix = "v0/campaigns/2026-10-09-phi4-cpu"
replay = subprocess.run([sys.executable, "-m", "quantfit.cli", "repeatability", "--reports",
                         *[str(moved / prefix / f"run-{i}/report.json") for i in range(1,4)], "--json"],
                        cwd=ROOT, capture_output=True, check=False, timeout=30)
assert replay.returncode == json.loads(replay.stdout)["exit_code"] == 3
assert json.loads(replay.stdout)["result"]["native_t0"]["result"]["protocol_pass"] is True
(OUT / "functional-relocated.json").write_bytes(replay.stdout)
refusal = subprocess.run([sys.executable, "-m", "quantfit.cli", "evidence", "fetch", "--out", str(moved)],
                         cwd=ROOT, capture_output=True, check=False, timeout=30)
assert refusal.returncode == 2 and b"new directory" in refusal.stdout
(OUT / "functional-existing-target-prose.log").write_bytes(refusal.stdout)
record = {"schema_version": 1, "source_head": subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT).decode().strip(),
          "actual_cli_invocations": 3, "fake_http_requests": 12, "external_network_calls": 0,
          "new_inference_performed": False, "original_bytes_preserved_after_relocation": True,
          "fetch_exit": 0, "relocated_analysis_exit": 3, "existing_target_prose_exit": 2,
          "files": members, "total_bytes": sum(m["size_bytes"] for m in members),
          "scope": "Source CLI/fake HTTP transport only. Historical aggregate bytes, not a fresh model/campaign/public download qualification."}
(OUT / "functional.json").write_bytes((json.dumps(record,indent=2,sort_keys=True)+'\n').encode())
print("PASS3actualofflineCLI:12original files78390bytes preserved/relocated, original negative3 retained, existing target refused2")
