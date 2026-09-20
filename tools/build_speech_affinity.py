import base64,hashlib,json
from cloud_radio_stage_audit import ROOT,remote
rel='app/k7agent/cloud/src/board_speech_bridge.c'
old=hashlib.sha256((ROOT/'evidence/board-speech-affinity-20260914/board_speech_bridge.before.c').read_bytes()).hexdigest()
bp='evidence/sync/board-speech-affinity-20260914.json';(ROOT/bp).write_text(json.dumps({rel:old}))
payload={p:base64.b64encode((ROOT/p).read_bytes()).decode() for p in [rel,bp,'tools/sync_sdk.py']}
code='''import pathlib,hashlib,base64,subprocess
sdk=pathlib.Path('/home/swl/openvela');root=sdk/'work/velavision-project'
assert hashlib.sha256((sdk/'apps/examples/k7agent/cloud/src/board_speech_bridge.c').read_bytes()).hexdigest()==%r
for rel,data in %r.items():
 p=root/rel;raw=base64.b64decode(data)
 if p.exists() and p.read_bytes()!=raw:
  old=p.read_bytes();b=root/'evidence/board-speech-affinity-20260914/before'/hashlib.sha256(old).hexdigest()/rel
  b.parent.mkdir(parents=True,exist_ok=True);b.write_bytes(old)
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
args=['python3',str(root/'tools/sync_sdk.py'),'--sdk',str(sdk),'--include','app/k7agent/cloud/src/board_speech_bridge.c']
for mode in ['--check','--apply','--check']:subprocess.check_call(args+[mode])
ev=root/'evidence/board-speech-affinity-20260914';ev.mkdir(exist_ok=True)
with (ev/'build.log').open('xb') as log:
 cmd='source build/envsetup.sh >/dev/null && prebuilts/tools/cmake/bin/cmake -S nuttx -B cmake_out/velavision_board_speech_affinity_20260914 -G Ninja -DBOARD_CONFIG=kickpi_k7:velavision_cloud_speech_buffered && prebuilts/tools/cmake/bin/cmake --build cmake_out/velavision_board_speech_affinity_20260914 -j4'
 child=subprocess.Popen(['bash','-c',cmd],cwd=sdk,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(child.pid)
'''%(old,payload)
print(remote(code).decode())
