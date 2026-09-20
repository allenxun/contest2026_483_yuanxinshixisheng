"""Stage reviewed cloud files, retaining project predecessors, then sync SDK."""
import base64
import json
from cloud_radio_stage_audit import ROOT, OUT, FILES, remote

audit=json.loads((OUT/'audit.json').read_text())
files=FILES+['tools/sync_sdk.py','evidence/sync/cloud-radio-baseline-20260914.json']
payload={p:base64.b64encode((ROOT/p).read_bytes()).decode() for p in files}
code='''import base64,hashlib,json,pathlib,subprocess
sdk=pathlib.Path('/home/swl/openvela')
root=sdk/'work/velavision-project'
audit=%r
payload=%r
for rel,item in audit.items():
 dest=('apps/examples/'+rel[4:]) if rel.startswith('app/') else ('nuttx/boards/arm64/rk3576/'+rel[6:])
 p=sdk/dest
 actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
 if actual!=item['sdk_sha256']: raise RuntimeError('SDK changed since audit: '+rel)
for rel,encoded in payload.items():
 p=root/rel
 data=base64.b64decode(encoded)
 if p.exists() and p.read_bytes()!=data:
  old=p.read_bytes()
  backup=root/'evidence/cloud-radio-build-20260914/project-before'/hashlib.sha256(old).hexdigest()/rel
  backup.parent.mkdir(parents=True,exist_ok=True)
  backup.write_bytes(old)
 p.parent.mkdir(parents=True,exist_ok=True)
 p.write_bytes(data)
args=['/usr/bin/python3.10',str(root/'tools/sync_sdk.py'),'--sdk',str(sdk)]
for rel in audit: args+=['--include',rel]
for mode in ['--check','--apply','--check']:
 subprocess.check_call(args+[mode])
''' % (audit,payload)
print(remote(code).decode())
