"""Audit/sync two explicit voice edits and build a separate native ORT image."""
import hashlib,json,subprocess,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];REV='voice-ort-trace-20260911'
P=R/'private'/REV;P.mkdir(exist_ok=True)
O=R/'evidence/build'/REV;O.mkdir(parents=True,exist_ok=False)
prior=json.loads((R/'evidence/build/voice-ort-add-20260911/verification.json').read_text())
files=['app/voicelink/CMakeLists.txt','app/voicelink/src/k7voice_main.cpp']
manifest={rel:dict(old=prior['sources'][rel],new=hashlib.sha256((R/rel).read_bytes()).hexdigest()) for rel in files}
runtime=json.loads((R/'evidence/native-session-trace-20260911/result.json').read_text())
assert runtime['missing_count']==0
(O/'staging.json').write_text(json.dumps(manifest,indent=2))
remote=r'''
import hashlib,json,shlex,shutil,subprocess,tarfile
from pathlib import Path
SDK=Path('/home/swl/openvela');P=SDK/'work/velavision-project'
S=SDK/'work/voice-ort-trace-stage-20260911';O=SDK/'work/voice-ort-trace-evidence-20260911';O.mkdir()
B=SDK/'cmake_out/velavision_voice_ort_trace_20260911';assert not B.exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((S/'staging.json').read_text())
for rel,x in manifest.items():
 assert sha(S/rel)==x['new']
 assert sha(P/rel) in (x['old'],x['new']),rel
for rel in manifest:(P/rel).write_bytes((S/rel).read_bytes())
records=[]
def run(name,cmd,cwd=SDK,timeout=900):
 with (O/(name+'.log')).open('wb') as f:
  q=subprocess.run(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
 record=dict(name=name,command=cmd,exit_code=q.returncode);records.append(record)
 (O/'progress.json').write_text(json.dumps(records,indent=2))
 print(name,q.returncode,flush=True)
 if q.returncode:raise RuntimeError((O/(name+'.log')).read_text(errors='replace')[-3500:])
run('sync-check',['python3',str(P/'tools/sync_sdk.py'),'--sdk',str(SDK),'--check'])
run('sync-apply',['python3',str(P/'tools/sync_sdk.py'),'--sdk',str(SDK),'--apply'])
T=Path('/dev/shm/velavision-ort-session-20260911')
rt=json.loads((T/'link-trace1/result.json').read_text());assert rt['missing_count']==0
obj=T/'link-trace1/session.o';assert sha(obj)==rt['relocatable_sha256']
dest=SDK/'work/native-ort-trace-runtime-20260911';dest.mkdir(exist_ok=True)
if (dest/'runtime.o').exists():assert sha(dest/'runtime.o')==sha(obj)
else:shutil.copyfile(obj,dest/'runtime.o')
configure=['cmake','-S','nuttx','-B',str(B),'-G','Ninja',
 '-DBOARD_CONFIG=kickpi_k7:velavision_audio_sound_local','-DK7VOICE_NATIVE_ORT_ADD=ON',
 '-DK7VOICE_ORT_OBJECT='+str(dest/'runtime.o'),'-DK7VOICE_ORT_OBJECT_SHA256='+sha(obj)]
run('configure',['bash','-c','source build/envsetup.sh >/dev/null && '+shlex.join(configure)])
run('build',['bash','-c','source build/envsetup.sh >/dev/null && cmake --build '+shlex.quote(str(B))+' -j4'])
result=dict(revision='voice-ort-trace-20260911',build_exit_code=0,hardware_tested=False,
 sources={rel:sha(P/rel) for rel in manifest},runtime_sha256=sha(obj),
 artifacts={n:dict(bytes=(B/n).stat().st_size,sha256=sha(B/n)) for n in ('nuttx','nuttx.bin','.config')},
 limitation='Explicit Add diagnostic only; no ASR/TTS. Runtime support localeconv was compiled from real NuttX source in isolated TU.',records=records)
(O/'verification.json').write_text(json.dumps(result,indent=2))
with tarfile.open(O/'results.tar.gz','w:gz') as t:
 for x in O.iterdir():
  if x.suffix in ('.json','.log'):t.add(x,arcname='evidence/build/voice-ort-trace-20260911/'+x.name)
 for n in ('nuttx','nuttx.bin','.config'):t.add(B/n,arcname='artifacts/voice-ort-trace-20260911/'+n)
print('BUILD_PASS',flush=True)
'''
(P/'build.py').write_text(remote)
with tarfile.open(P/'stage.tar.gz','w:gz') as t:
 for rel in files:t.add(R/rel,arcname=rel)
 t.add(O/'staging.json',arcname='staging.json')
 t.add(P/'build.py',arcname='build.py')
options=['-i','C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/ubuntu_vm_pc2025_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=C:/Users/pc2025/Documents/Codex/2026-09-03/new-chat/work/ssh/known_hosts']
host='swl@192.168.152.131';dest='/home/swl/openvela/work/voice-ort-trace-stage-20260911'
subprocess.run(['ssh.exe',*options,host,'mkdir '+dest],check=True)
subprocess.run(['scp.exe',*options,str(P/'stage.tar.gz'),host+':'+dest+'/stage.tar.gz'],check=True)
subprocess.run(['ssh.exe',*options,host,'cd '+dest+' && tar -xzf stage.tar.gz && python3 build.py'],check=True)
subprocess.run(['scp.exe',*options,host+':/home/swl/openvela/work/voice-ort-trace-evidence-20260911/results.tar.gz',str(P/'results.tar.gz')],check=True)
with tarfile.open(P/'results.tar.gz') as t:
 for x in t.getmembers():assert x.isfile() and not Path(x.name).is_absolute() and '..' not in Path(x.name).parts
 t.extractall(R,filter='data')
