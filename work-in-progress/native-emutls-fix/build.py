import hashlib,json,subprocess
from pathlib import Path
r=Path(__file__).resolve().parent;prior=r.parent/'native-asr-recognizer';sdk=Path('/home/swl/openvela')
gate=json.loads((r/'host-result.json').read_text());assert gate['passed']
for n,h in gate['sources'].items():assert hashlib.sha256((r/n).read_bytes()).hexdigest()==h
base=json.loads((prior/'compile-attempt2.json').read_text())['command'];commands=[]
for name in ('recognizer_probe.cpp','tls_probe.cpp','emutls.c'):
 cmd=base[:];cmd[cmd.index('-c')+1]=str(r/name);cmd[cmd.index('-o')+1]=str(r/(name+'.o'));cmd+=['-I'+str(prior)]
 if name.endswith('.c'):
  cmd=[x for x in cmd if not x.startswith('-std=') and x!='-nostdinc++'];cmd[0]=cmd[0].replace('-g++','-gcc')
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120);(r/(name+'.log')).write_bytes(p.stdout);commands.append(cmd)
 assert p.returncode==0,name
link=json.loads((prior/'link2/result.json').read_text())['link_command']
link[link.index('-o')+1]=str(r/'runtime.o')
link=[str(r/'recognizer_probe.cpp.o') if x==str(prior/'link2/recognizer_probe.cpp.o') else x for x in link]
link += [str(r/'tls_probe.cpp.o'),str(r/'emutls.c.o')]
p=subprocess.run(link,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180);(r/'link.log').write_bytes(p.stdout);assert not p.returncode
digest=hashlib.sha256((r/'runtime.o').read_bytes()).hexdigest()
(r/'link-result.json').write_text(json.dumps({'exit_code':0,'sha256':digest,'command':link,'compile':commands},indent=2))
build=sdk/'cmake_out/velavision_voice_tls_20260911';assert not build.exists()
command=('source build/envsetup.sh && cmake -S nuttx -B '+str(build)+' -G Ninja -DBOARD_CONFIG=kickpi_k7:velavision_audio_sound_local -DK7VOICE_NATIVE_ORT_ADD=ON -DK7VOICE_NATIVE_ASR_MODEL=ON -DK7VOICE_NATIVE_ASR_MIC=ON -DK7VOICE_ORT_OBJECT='+str(r/'runtime.o')+' -DK7VOICE_ORT_OBJECT_SHA256='+digest+' && cmake --build '+str(build)+' -j4')
with (r/'build.log').open('wb') as f:p=subprocess.run(['bash','-c',command],cwd=sdk,stdout=f,stderr=subprocess.STDOUT,timeout=1800)
result={'exit_code':p.returncode,'command':command,'board_tested':False}
if not p.returncode:result['sha256']=hashlib.sha256((build/'nuttx.bin').read_bytes()).hexdigest()
(r/'build-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
