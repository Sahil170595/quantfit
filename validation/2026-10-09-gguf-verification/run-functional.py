"""Actual crafted-binary source CLI0/3/2 and Windows preprovision refusal; no inference."""

import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def string(value):
    raw = value.encode()
    return struct.pack("<Q", len(raw)) + raw


raw = b"GGUF" + struct.pack("<IQQ", 3, 1, 1)
raw += string("general.architecture") + struct.pack("<I",8) + string("llama")
raw += string("test.weight") + struct.pack("<IQQIQ",2,32,2,2,0)
raw += b"\x00" * (-len(raw) % 32) + b"\x00" * 36
valid, bad, unverified = OUT / "complete.GGUF", OUT / "magic-only.gguf", OUT / "version1.gguf"
valid.write_bytes(raw);bad.write_bytes(b"GGUF");unverified.write_bytes(raw[:4]+struct.pack("<I",1)+raw[8:])
cases=[]
for name, path, code, extra, json_mode in (
    ("complete-json",valid,0,[],True), ("complete-prose",valid,0,[],False),
    ("magic-only-json",bad,3,[],True), ("version1-json",unverified,2,[],True),
    ("deadline-without-runtime",valid,2,["--timeout-seconds","1"],True),
):
    argv=[sys.executable,"-m","quantfit.cli","verify","--model",str(path),*extra,*(["--json"] if json_mode else [])]
    p=subprocess.run(argv,cwd=ROOT,capture_output=True,check=False,timeout=15)
    assert p.returncode==code,p.stdout+p.stderr
    artifact=OUT/(name+('.json' if json_mode else '.log'));artifact.write_bytes(p.stdout)
    if json_mode:assert json.loads(p.stdout)["exit_code"]==code
    cases.append({"case":name,"argv":argv,"exit_code":p.returncode,"artifact":artifact.name,"stderr_bytes":len(p.stderr)})
if os.name=="nt":
    p=subprocess.run([sys.executable,"-m","quantfit.cli","verify","--model",str(valid),"--runtime","--json"],cwd=ROOT,capture_output=True,check=False,timeout=15)
    value=json.loads(p.stdout);assert p.returncode==2 and value['result']['structure']['status']=='pass' and value['result']['runtime']['status']=='unverified'
    assert value['result']['runtime']['platform_supported'] is False
    (OUT/'windows-runtime-refusal.json').write_bytes(p.stdout)
    cases.append({'case':'actual-windows-runtime-refusal','exit_code':2,'artifact':'windows-runtime-refusal.json','binary_provisioning_attempted':False})
p=subprocess.run([sys.executable,"-m","quantfit.cli","verify","--model",str(valid),"--runtime","--timeout-seconds","bad","--json"],cwd=ROOT,capture_output=True,check=False,timeout=15)
assert p.returncode==2 and not p.stdout and b'usage:' in p.stderr
(OUT/'parser-refusal.log').write_bytes(p.stderr)
cases.append({'case':'actual-parser-refusal','exit_code':2,'stdout_bytes':0,'artifact':'parser-refusal.log'})
record={'schema_version':1,'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'actual_cli_invocations':len(cases),'external_network_calls':0,'new_model_inference_performed':False,
        'new_binary_provisioning_attempts':0,'cases':cases,
        'inputs':[{'path':p.name,'size_bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (valid,bad,unverified)],
        'scope':'Crafted zero-filled tensor binary syntax and operational/parser/platform refusal only; no native Linux execution or meaningful weights/quality/safety claim.'}
(OUT/'functional.json').write_bytes((json.dumps(record,indent=2,sort_keys=True)+'\n').encode())
print('PASS actualsourceCLI0/3/2:completezero-filledstructure,magic-onlyfailure,version1unverified,explicitdeadline/parserandWindowsruntime-refusal')
