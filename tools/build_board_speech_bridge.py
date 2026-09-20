import base64,hashlib,json
from cloud_radio_stage_audit import ROOT,remote
ev=ROOT/'evidence/board-speech-bridge-20260914'
baseline={p:hashlib.sha256((ev/n).read_bytes()).hexdigest() for p,n in [
 ('app/k7agent/CMakeLists.txt','CMakeLists.before.txt'),
 ('app/k7agent/cloud/src/k7cloud_main.c','k7cloud_main.before.c')]}
bp='evidence/sync/board-speech-bridge-20260914.json'
(ROOT/bp).write_text(json.dumps(baseline))
files=list(baseline)+['app/k7agent/cloud/src/board_speech_bridge.c']
payload={p:base64.b64encode((ROOT/p).read_bytes()).decode() for p in files+[bp,'tools/sync_sdk.py']}
code='''import pathlib,hashlib,base64,subprocess
sdk=pathlib.Path('/home/swl/openvela');root=sdk/'work/velavision-project'
files=%r
for rel,expected in %r.items():
 assert hashlib.sha256((sdk/('apps/examples/'+rel[4:])).read_bytes()).hexdigest()==expected,rel
assert not (sdk/'apps/examples/k7agent/cloud/src/board_speech_bridge.c').exists()
for rel,data in %r.items():
 p=root/rel;b=base64.b64decode(data)
 if p.exists() and p.read_bytes()!=b:
  old=p.read_bytes();backup=root/'evidence/board-speech-bridge-20260914/before'/hashlib.sha256(old).hexdigest()/rel
  backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(old)
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
args=['python3',str(root/'tools/sync_sdk.py'),'--sdk',str(sdk)]
for rel in files:args+=['--include',rel]
for mode in ['--check','--apply','--check']:subprocess.check_call(args+[mode])
ev=root/'evidence/board-speech-bridge-20260914';ev.mkdir(exist_ok=True)
with (ev/'build.log').open('xb') as log:
 command='source build/envsetup.sh >/dev/null && prebuilts/tools/cmake/bin/cmake -S nuttx -B cmake_out/velavision_board_speech_bridge_20260914 -G Ninja -DBOARD_CONFIG=kickpi_k7:velavision_cloud_speech_local && prebuilts/tools/cmake/bin/cmake --build cmake_out/velavision_board_speech_bridge_20260914 -j4'
 child=subprocess.Popen(['bash','-c',command],cwd=sdk,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print('BUILD_PID',child.pid)
'''%(files,baseline,payload)
print(remote(code).decode())
