import hashlib,json,subprocess
from pathlib import Path
r=Path(__file__).resolve().parent; old=r.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert not (r/'decoder-runtime.o').exists()
previous=json.loads((old/'link-result.json').read_text())
for key,log in [('compile_command','compile.log'),('sha_command','sha.log')]:
    cmd=[x.replace(str(old)+'/',str(r)+'/') for x in previous[key]]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
    (r/log).write_bytes(p.stdout);assert p.returncode==0,p.stdout
runtime=Path('/home/swl/openvela/work/native-vits-lexicon-20260911/link1/session.o')
assert sha(runtime)=='e43242de83135f400ee8c72668813d92c534f6b6f0020e3525f14904d6a4c767'
cmd=[x.replace(str(old)+'/',str(r)+'/') for x in previous['link_command']]
p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
(r/'link.log').write_bytes(p.stdout);assert p.returncode==0,p.stdout
digest=sha(r/'decoder-runtime.o')
(r/'link-result.json').write_text(json.dumps({'exit_code':0,'sha256':digest,'inputs':{x.name:sha(x) for x in r.iterdir() if x.suffix in ('.cpp','.hpp','.h','.c','.py')},'board_tested':False},indent=2))
sdk=Path('/home/swl/openvela');build=sdk/'cmake_out/velavision_voice_asr_encoder_20260911'
assert not build.exists()
command=('source build/envsetup.sh && cmake -S nuttx -B '+str(build)+
 ' -G Ninja -DBOARD_CONFIG=kickpi_k7:velavision_audio_sound_local -DK7VOICE_NATIVE_ORT_ADD=ON -DK7VOICE_NATIVE_ASR_MODEL=ON'
 ' -DK7VOICE_ORT_OBJECT='+str(r/'decoder-runtime.o')+' -DK7VOICE_ORT_OBJECT_SHA256='+digest+
 ' && cmake --build '+str(build)+' -j4')
with (r/'build.log').open('wb') as f:p=subprocess.run(['bash','-c',command],cwd=sdk,stdout=f,stderr=subprocess.STDOUT,timeout=1800)
result={'exit_code':p.returncode,'command':command,'board_tested':False}
if p.returncode==0:result['binary_sha256']=sha(build/'nuttx.bin')
(r/'build-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
