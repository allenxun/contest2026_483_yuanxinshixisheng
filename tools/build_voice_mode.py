"""Exact reviewed predecessor sync and independent build; never RAM loads."""
import base64
import json
from cloud_radio_stage_audit import ROOT,remote
from audit_voice_mode_sdk import FILES

baseline=json.loads((ROOT/'evidence/voice-mode-20260915/sdk-before.json').read_text())
assert set(baseline)==set(FILES)
bp='evidence/sync/voice-mode-20260915.json'
(ROOT/bp).write_text(json.dumps(baseline,indent=2)+'\n')
payload={p:base64.b64encode((ROOT/p).read_bytes()).decode() for p in FILES+[bp,'tools/sync_sdk.py']}
code='''import pathlib,hashlib,base64,subprocess
sdk=pathlib.Path('/home/swl/openvela');root=sdk/'work/velavision-project'
for rel,digest in %r.items():
 assert hashlib.sha256((sdk/'apps/examples'/rel[4:]).read_bytes()).hexdigest()==digest,rel
for rel,data in %r.items():
 p=root/rel;raw=base64.b64decode(data)
 if p.exists() and p.read_bytes()!=raw:
  old=p.read_bytes();before=root/'evidence/voice-mode-20260915/project-before'/hashlib.sha256(old).hexdigest()/rel
  before.parent.mkdir(parents=True,exist_ok=True);before.write_bytes(old)
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
args=['python3',str(root/'tools/sync_sdk.py'),'--sdk',str(sdk)]
for rel in %r:args+=['--include',rel]
for mode in ['--check','--apply','--check']:subprocess.check_call(args+[mode])
ev=root/'evidence/voice-mode-20260915';ev.mkdir(parents=True,exist_ok=True)
with (ev/'build.log').open('xb') as log:
 cmd='source build/envsetup.sh >/dev/null && prebuilts/tools/cmake/bin/cmake -S nuttx -B cmake_out/velavision_voice_mode_20260915 -G Ninja -DBOARD_CONFIG=kickpi_k7:velavision_cloud_speech_buffered && prebuilts/tools/cmake/bin/cmake --build cmake_out/velavision_voice_mode_20260915 -j4; result=$?; echo $result > work/velavision-project/evidence/voice-mode-20260915/build.exit; exit $result'
 child=subprocess.Popen(['bash','-c',cmd],cwd=sdk,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print('build_pid',child.pid)
'''%(baseline,payload,FILES)
print(remote(code).decode())
