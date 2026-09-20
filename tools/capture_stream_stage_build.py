"""Scoped predecessor-guarded sync and independent ARM64 build."""
import base64,hashlib,json
from cloud_radio_stage_audit import ROOT,remote
ev=ROOT/'evidence/capture-stream-20260914'
before=json.loads((ev/'predecessors.json').read_text())
baseline={'app/k7sound/'+n:hashlib.sha256(base64.b64decode(v)).hexdigest() for n,v in before.items() if v is not None}
cloud=json.loads((ROOT/'evidence/cloud-radio-build-20260914/audit.json').read_text())
for p in ['app/k7agent/CMakeLists.txt','app/k7agent/cloud/src/k7cloud_main.c']:
    baseline[p]=cloud[p]['source_sha256']
bp='evidence/sync/capture-stream-baseline-20260914.json'
(ROOT/bp).write_text(json.dumps(baseline,indent=2)+'\n')
files=['app/k7sound/'+n for n in before]+['app/k7agent/CMakeLists.txt','app/k7agent/cloud/src/k7cloud_main.c','app/k7agent/cloud/src/capture_stream_probe.c']
payload={p:base64.b64encode((ROOT/p).read_bytes()).decode() for p in files+[bp,'tools/sync_sdk.py']}
code='''import base64,hashlib,pathlib,subprocess
sdk=pathlib.Path('/home/swl/openvela'); root=sdk/'work/velavision-project'
baseline=%r
files=%r
for rel in files:
 p=sdk/('apps/examples/'+rel[4:])
 expected=baseline.get(rel)
 actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
 assert expected==actual,rel
for rel,encoded in %r.items():
 p=root/rel; data=base64.b64decode(encoded)
 if p.exists() and p.read_bytes()!=data:
  old=p.read_bytes(); b=root/'evidence/capture-stream-20260914/project-before'/hashlib.sha256(old).hexdigest()/rel
  b.parent.mkdir(parents=True,exist_ok=True); b.write_bytes(old)
 p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
args=['/usr/bin/python3.10',str(root/'tools/sync_sdk.py'),'--sdk',str(sdk)]
for rel in files:args+=['--include',rel]
for mode in ['--check','--apply','--check']:subprocess.check_call(args+[mode])
ev=root/'evidence/capture-stream-20260914'
with (ev/'arm64-build.log').open('xb') as log:
 cmd='source build/envsetup.sh >/dev/null && prebuilts/tools/cmake/bin/cmake -S nuttx -B cmake_out/velavision_capture_stream_20260914 -G Ninja -DBOARD_CONFIG=kickpi_k7:velavision_cloud_speech_local && prebuilts/tools/cmake/bin/cmake --build cmake_out/velavision_capture_stream_20260914 -j4'
 p=subprocess.Popen(['bash','-c',cmd],cwd=str(sdk),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print('BUILD_PID',p.pid)
''' % (baseline,files,payload)
print(remote(code).decode())
