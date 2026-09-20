import hashlib,json,subprocess
from pathlib import Path
r=Path(__file__).resolve().parent;prior=r.parent/'native-asr-recognizer';sdk=Path('/home/swl/openvela')
cmd=json.loads((prior/'compile-attempt2.json').read_text())['command']
cmd[cmd.index('-c')+1]=str(r/'recognizer_probe.cpp');cmd[cmd.index('-o')+1]=str(r/'recognizer_probe.o');cmd+=['-I'+str(prior)]
p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120);(r/'compile.log').write_bytes(p.stdout)
assert p.returncode==0,'mic probe compile'
link=json.loads((prior/'link2/result.json').read_text())['link_command']
link[link.index('-o')+1]=str(r/'runtime.o')
link=[str(r/'recognizer_probe.o') if x==str(prior/'link2/recognizer_probe.cpp.o') else x for x in link]
p=subprocess.run(link,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180);(r/'link.log').write_bytes(p.stdout);assert p.returncode==0
digest=hashlib.sha256((r/'runtime.o').read_bytes()).hexdigest()
(r/'link-result.json').write_text(json.dumps({'exit_code':0,'sha256':digest,'command':link,'compile':cmd},indent=2))
build=sdk/'cmake_out/velavision_voice_asr_microphone_20260911';assert not build.exists()
command=('source build/envsetup.sh && cmake -S nuttx -B '+str(build)+' -G Ninja -DBOARD_CONFIG=kickpi_k7:velavision_audio_sound_local -DK7VOICE_NATIVE_ORT_ADD=ON -DK7VOICE_NATIVE_ASR_MODEL=ON -DK7VOICE_NATIVE_ASR_MIC=ON -DK7VOICE_ORT_OBJECT='+str(r/'runtime.o')+' -DK7VOICE_ORT_OBJECT_SHA256='+digest+' && cmake --build '+str(build)+' -j4')
with (r/'build.log').open('wb') as f:p=subprocess.run(['bash','-c',command],cwd=sdk,stdout=f,stderr=subprocess.STDOUT,timeout=1800)
result={'exit_code':p.returncode,'command':command,'board_tested':False}
if not p.returncode:result['sha256']=hashlib.sha256((build/'nuttx.bin').read_bytes()).hexdigest()
(r/'build-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
