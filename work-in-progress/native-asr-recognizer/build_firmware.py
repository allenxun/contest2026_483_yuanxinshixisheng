import hashlib,json,subprocess
from pathlib import Path
r=Path(__file__).resolve().parent;sdk=Path('/home/swl/openvela');runtime=r/'link2/recognizer-runtime.o'
gate=json.loads((r/'link2/result.json').read_text());assert gate['exit_code']==0
digest=hashlib.sha256(runtime.read_bytes()).hexdigest();assert digest==gate['runtime_sha256']
build=sdk/'cmake_out/velavision_voice_asr_recognizer_20260911';assert not build.exists()
cmd=('source build/envsetup.sh && cmake -S nuttx -B '+str(build)+
 ' -G Ninja -DBOARD_CONFIG=kickpi_k7:velavision_audio_sound_local -DK7VOICE_NATIVE_ORT_ADD=ON -DK7VOICE_NATIVE_ASR_MODEL=ON'
 ' -DK7VOICE_ORT_OBJECT='+str(runtime)+' -DK7VOICE_ORT_OBJECT_SHA256='+digest+
 ' && cmake --build '+str(build)+' -j4')
with (r/'firmware-build.log').open('wb') as f:p=subprocess.run(['bash','-c',cmd],cwd=sdk,stdout=f,stderr=subprocess.STDOUT,timeout=1800)
report={'exit_code':p.returncode,'command':cmd,'board_tested':False}
if p.returncode==0:report['binary_sha256']=hashlib.sha256((build/'nuttx.bin').read_bytes()).hexdigest()
(r/'firmware-result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
